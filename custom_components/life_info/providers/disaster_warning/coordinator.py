"""灾害预警 协调器：快照初始化 + WS 增量覆盖 + HTTP 兜底."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed

from ... import storage
from ...api import LifeInfoError
from ...const import CONF_ACCOUNTS, DOMAIN, LOGGER
from ...coordinator import LifeInfoCoordinator
from .api import (
    DisasterWarningApiError,
    async_fetch_scope,
    async_fetch_snapshot,
    freshness_key,
    iso_time,
    parse_payload,
    record_md5,
)
from .const import (
    ACCOUNT_KEY,
    CACHE_KEY,
    CACHE_TTL_SECONDS,
    CAPQUAKE_WS,
    CATEGORIES,
    CONF_ACCOUNT_KEY,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    SERVICE_ID,
    SERVICE_NAME,
    resolve_scopes,
)

class DisasterWarningCoordinator(LifeInfoCoordinator):
    """三类槽位状态覆盖：HTTP 快照兜底，单条 WS 连接按 scope 增量更新."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        minutes = max(
            int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)), 1
        )
        super().__init__(hass, entry, update_interval=timedelta(minutes=minutes))
        self._session = async_get_clientsession(hass)
        self._scopes = resolve_scopes(entry.options)
        self._ws_task: asyncio.Task | None = None

    @property
    def accounts(self) -> list[dict[str, Any]]:
        """固定单伪账户：接入名取条目选项，缺失回落服务名."""
        stored = self.entry.options.get(CONF_ACCOUNTS) or []
        name = str((stored[0] if stored else {}).get(CONF_NAME) or SERVICE_NAME)
        return [{CONF_ACCOUNT_KEY: ACCOUNT_KEY, CONF_NAME: name}]

    def account_key(self, account: dict[str, Any]) -> str:
        """账户 key 固定 disaster，不随选项变化."""
        return ACCOUNT_KEY

    async def _fetch(self) -> dict[str, dict[str, Any]]:
        """HTTP 兜底：快照按范围解析后合并进三类槽位；失败走 TTL 缓存."""
        try:
            records = await self._async_snapshot_records()
        except (LifeInfoError, TimeoutError, OSError) as err:
            return await self._async_cached_payload(err)

        if not records:
            return await self._async_cached_payload(
                DisasterWarningApiError("快照无范围内有效数据")
            )

        slots = self._current_slots()
        for record in records.values():
            self._merge_record(slots, record)
        await storage.async_save(self.hass, CACHE_KEY, slots)
        self.async_start_ws()
        return self._build_payload(slots)

    async def _async_cached_payload(self, err: Exception) -> dict[str, dict[str, Any]]:
        cached = await storage.async_load(self.hass, CACHE_KEY)
        if storage.is_fresh(cached, CACHE_TTL_SECONDS):
            LOGGER.warning("灾害预警取数失败，沿用缓存: %s", err)
            self.async_start_ws()
            return self._build_payload(
                self._cached_slots(cached), cache_at=cached.get("fetched_at")
            )
        raise UpdateFailed(f"灾害预警取数失败: {err}") from err

    async def _async_snapshot_records(self) -> dict[str, dict[str, Any]]:
        """拉全源快照，快照缺的源逐个补拉；单源异常只丢该源."""
        snapshot = await async_fetch_snapshot(self._session)
        records: dict[str, dict[str, Any]] = {}
        for scope, payload in snapshot.items():
            if scope not in self._scopes:
                continue
            try:
                if record := parse_payload(scope, payload):
                    records[scope] = record
            except DisasterWarningApiError as err:
                LOGGER.debug("灾害预警 %s 解析失败: %s", scope, err)

        missing = [scope for scope in self._scopes if scope not in snapshot]
        if not missing:
            return records
        semaphore = asyncio.Semaphore(5)

        async def fetch(scope: str) -> tuple[str, dict[str, Any] | None]:
            async with semaphore:
                try:
                    payload = await async_fetch_scope(self._session, scope)
                    return scope, parse_payload(scope, payload)
                except (LifeInfoError, TimeoutError, OSError) as err:
                    LOGGER.debug("灾害预警 %s 补拉失败: %s", scope, err)
                    return scope, None

        for scope, record in await asyncio.gather(*(fetch(s) for s in missing)):
            if record:
                records[scope] = record
        return records

    @staticmethod
    def _cached_slots(cached: dict[str, Any]) -> dict[str, dict[str, Any]]:
        data = cached.get("data")
        if not isinstance(data, dict):
            return {}
        return {
            category: data[category]
            for category in CATEGORIES
            if isinstance(data.get(category), dict)
        }

    def _current_slots(self) -> dict[str, dict[str, Any]]:
        account = (self.data or {}).get(ACCOUNT_KEY) or {}
        return {
            category: account[category]
            for category in CATEGORIES
            if isinstance(account.get(category), dict)
        }

    def _build_payload(
        self,
        slots: dict[str, dict[str, Any]],
        *,
        cache_at: Any = None,
    ) -> dict[str, dict[str, Any]]:
        payload: dict[str, Any] = {
            category: slots.get(category) for category in CATEGORIES
        }
        if cache_at is not None:
            payload["_cache_at"] = iso_time(cache_at)
        return {ACCOUNT_KEY: payload}

    def _merge_record(
        self, slots: dict[str, dict[str, Any]], record: dict[str, Any]
    ) -> bool:
        """槽位覆盖：同 md5 跳过；recv_time 不大于当前值也丢弃（防乱序）."""
        category = record.get("category")
        if category not in CATEGORIES:
            return False
        current = slots.get(category)
        if current is not None:
            md5 = record_md5(record)
            if md5 is not None and md5 == record_md5(current):
                return False
            if freshness_key(record) <= freshness_key(current):
                return False
        slots[category] = record
        return True

    def async_start_ws(self) -> None:
        """WS 生命周期绑定条目，unload 自动取消；只起一次."""
        if self._ws_task is not None and not self._ws_task.done():
            return
        self._ws_task = self.entry.async_create_background_task(
            self.hass, self._async_ws_loop(), f"{SERVICE_ID}_ws"
        )

    async def _async_ws_loop(self) -> None:
        """单连接收全量增量：重连补快照，指数退避."""
        backoff = 5
        while True:
            try:
                async with self._session.ws_connect(CAPQUAKE_WS) as ws:
                    backoff = 5
                    await self._async_snapshot_merge()
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._async_handle_frame(ws, msg.json())
                        elif msg.type in (
                            aiohttp.WSMsgType.ERROR,
                            aiohttp.WSMsgType.CLOSED,
                            aiohttp.WSMsgType.CLOSING,
                        ):
                            break
            except asyncio.CancelledError:
                raise
            except (
                LifeInfoError,
                TimeoutError,
                OSError,
                ValueError,
                aiohttp.ClientError,
            ) as err:
                LOGGER.debug("灾害预警 WS 断开: %s", err)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 300)

    async def _async_snapshot_merge(self) -> None:
        """WS 连上后补一次快照，只合并不推送类状态变化."""
        try:
            records = await self._async_snapshot_records()
        except (LifeInfoError, TimeoutError, OSError) as err:
            LOGGER.debug("灾害预警 WS 补快照失败: %s", err)
            return
        slots = self._current_slots()
        changed = False
        for record in records.values():
            changed = self._merge_record(slots, record) or changed
        if not changed:
            return
        await storage.async_save(self.hass, CACHE_KEY, slots)
        self.async_set_updated_data(self._build_payload(slots))

    async def _async_handle_frame(self, ws: Any, frame: dict[str, Any]) -> None:
        """心跳原样回显；event 帧按 scope 归类，仅新于当前槽位才覆盖."""
        frame_type = frame.get("type")
        if frame_type == "heartbeat":
            await ws.send_json({"type": "heartbeat", "data": frame.get("data")})
            return
        if frame_type != "event":
            return

        data = frame.get("data") or {}
        scope = str(data.get("scope") or "")
        if scope not in self._scopes:
            return
        try:
            record = parse_payload(scope, data.get("payload"))
        except DisasterWarningApiError as err:
            LOGGER.debug("灾害预警 %s 帧解析失败: %s", scope, err)
            return
        if not record:
            return

        slots = self._current_slots()
        if not self._merge_record(slots, record):
            return
        await storage.async_save(self.hass, CACHE_KEY, slots)
        self.async_set_updated_data(self._build_payload(slots))

    def device_info_for(self, account: dict[str, Any]) -> DeviceInfo:
        """单台服务类设备：无序列号，按伪账户 key 区分实例."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.service_id}_{ACCOUNT_KEY}")},
            name=str(account.get(CONF_NAME) or SERVICE_NAME),
            serial_number=None,
            manufacturer="生活信息",
            model="灾害预警",
            entry_type=DeviceEntryType.SERVICE,
        )
