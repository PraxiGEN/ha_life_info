"""灾害预警 协调器."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util

from ... import storage
from ...api import LifeInfoError
from ...const import CONF_ACCOUNTS, DOMAIN, LOGGER
from ...coordinator import LifeInfoCoordinator
from .api import (
    DisasterWarningApiError,
    async_fetch_scope,
    async_fetch_snapshot,
)
from .const import (
    ACCOUNT_KEY,
    CACHE_KEY,
    CACHE_TTL_SECONDS,
    CAPQUAKE_WS,
    CATEGORIES,
    CATEGORY_REPORT,
    CATEGORY_TSUNAMI,
    CONF_ACCOUNT_KEY,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    SCOPE_TO_CATEGORY,
    SERVICE_ID,
    SERVICE_NAME,
    resolve_scopes,
)

def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None

def _float(value: Any) -> float | None:
    try:
        return float(str(value).strip()) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None

def _int(value: Any) -> int | None:
    try:
        return int(float(str(value).strip())) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None

def _bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes")

def iso_time(value: Any) -> str | None:
    """异构时间统一成 ISO：毫秒/秒时间戳与常见日期字符串都收口."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        stamp = float(value) / 1000 if float(value) > 1e11 else float(value)
        return datetime.fromtimestamp(
            stamp, tz=dt_util.DEFAULT_TIME_ZONE
        ).isoformat(timespec="seconds")
    text = str(value).strip()
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(
                tzinfo=dt_util.DEFAULT_TIME_ZONE
            ).isoformat(timespec="seconds")
        except ValueError:
            continue
    return text

def _text(value: Any) -> str | None:
    """标量转展示文本：整数值的 float 去掉 .0，避免烈度显示成 1.0."""
    if value in (None, ""):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)

def _record(
    schema: str,
    scope: str,
    raw: dict[str, Any],
    *,
    event_id: Any = None,
    location: Any = None,
    magnitude: Any = None,
    intensity: Any = None,
    time: Any = None,
    depth: Any = None,
    serial: Any = None,
    is_cancel: Any = None,
    level: Any = None,
    recv_time: Any = None,
) -> dict[str, Any] | None:
    """统一结构；无事件 ID 且无时间视为空 payload，返回 None 由上层忽略."""
    if not isinstance(raw, dict):
        return None
    event_id = str(event_id) if event_id not in (None, "") else ""
    parsed_time = iso_time(time)
    if not event_id and not parsed_time:
        return None
    return {
        "schema": schema,
        "scope": scope,
        "category": SCOPE_TO_CATEGORY.get(scope),
        "event_id": event_id or f"{scope}_{parsed_time or recv_time}",
        "location": _text(location),
        "magnitude": _float(magnitude),
        "intensity": _text(intensity),
        "time": parsed_time,
        "depth": _float(depth),
        "serial": _int(serial),
        "is_cancel": _bool(is_cancel),
        "level": _text(level),
        "recv_time": _int(recv_time),
        "source": "capquake",
        "raw": raw,
        "cache_at": None,
    }

def parse_cea(scope: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """CEA/CEA-PR 及同类统一事件；字段缺失时按通用别名兜底."""
    return _record(
        "cea",
        scope,
        payload,
        event_id=_first(payload, "event_id", "EventID", "eventId", "identifier", "id"),
        location=_first(
            payload, "location", "epicenter_name", "epicenterPlace",
            "placeName", "Hypocenter",
        ),
        magnitude=_first(payload, "magnitude", "Magunitude", "M"),
        intensity=_first(payload, "max_intensity", "MaxIntensity", "intensity"),
        time=_first(payload, "OriginTime", "origin_time", "time", "originTime"),
        depth=_first(payload, "depth", "Depth"),
        serial=_first(payload, "serial", "Serial"),
        is_cancel=_first(payload, "is_cancel", "isCancel", "cancelled"),
        recv_time=_first(payload, "recv_time", "recvTime"),
    )

def parse_jma(scope: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """JMA 紧急地震速报：保留上游 Magunitude 拼写."""
    return _record(
        "jma_eew",
        scope,
        payload,
        event_id=_first(payload, "EventID", "event_id"),
        location=_first(payload, "Hypocenter", "location"),
        magnitude=_first(payload, "Magunitude", "magnitude"),
        intensity=_first(payload, "MaxIntensity", "max_intensity"),
        time=_first(payload, "OriginTime", "origin_time"),
        depth=_first(payload, "Depth", "depth"),
        serial=_first(payload, "Serial", "serial"),
        is_cancel=_first(payload, "isCancel", "is_cancel"),
        recv_time=_first(payload, "recv_time", "recvTime"),
    )

def _time_value(value: Any) -> float:
    """把时间戳/日期串统一成可比数值，供挑最新一条."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value or "").strip()
    if not text:
        return 0.0
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).timestamp()
        except ValueError:
            continue
    if (parsed := dt_util.parse_datetime(text)) is not None:
        return parsed.timestamp()
    try:
        return float(text)
    except ValueError:
        return 0.0

def _latest(rows: list[Any], *keys: str) -> dict[str, Any] | None:
    """按给定时间字段取最新一条；时间戳与日期串都支持."""
    items = [row for row in rows if isinstance(row, dict)]
    if not items:
        return None

    def sort_key(row: dict[str, Any]) -> float:
        for name in keys:
            if (value := _time_value(row.get(name))) > 0:
                return value
        return 0.0

    return max(items, key=sort_key)

def parse_tsunami(scope: str, payload: Any) -> dict[str, Any] | None:
    """海啸 CAP 报文：items[] 取最新，用报文 id 作事件身份."""
    rows = payload.get("items") if isinstance(payload, dict) else payload
    item = _latest(rows or [], "recv_time", "time_ts", "time")
    if item is None:
        return None
    areas = item.get("areas") or []
    area_name = ""
    if areas and isinstance(areas[0], dict):
        area_name = str(areas[0].get("name") or "")
    raw_area = item.get("area")
    location = (
        str(raw_area)
        if isinstance(raw_area, str) and raw_area
        else area_name or _first(item, "region", "title") or None
    )
    return _record(
        "tsunami",
        scope,
        item,
        event_id=_first(item, "id", "event_id"),
        location=location,
        time=_first(item, "time", "report_time", "update_time"),
        is_cancel=_first(item, "cancelled", "cancel"),
        level=_first(item, "level_name", "level_text", "level"),
        recv_time=_first(item, "recv_time", "update_ts", "alarm_ts", "time_ts"),
    )

def parse_report(scope: str, payload: Any) -> dict[str, Any] | None:
    """地震报告信封：Data / items[] / cenc No* / 裸对象 四种形态收口."""
    if isinstance(payload, list):
        item = _latest(payload, "recvTime", "originTime")
        return _report_record(scope, item) if item else None
    if not isinstance(payload, dict):
        return None

    if isinstance(payload.get("Data"), dict):
        data = payload["Data"]
        record = _report_record(scope, data, raw=payload)
        if record and payload.get("md5"):
            record["event_id"] = record["event_id"] or str(payload["md5"])
        return record

    if isinstance(payload.get("items"), list):
        item = _latest(payload["items"], "report_time_ts", "recv_time", "report_time")
        return _report_record(scope, item) if item else None

    # cenc：No1..NoN 字典 + 顶层 md5 包校验值，只取条目字典.
    if "No1" in payload or (
        payload and all(isinstance(value, dict) for value in payload.values())
    ):
        item = _latest(
            [value for value in payload.values() if isinstance(value, dict)],
            "ReportTime",
            "time",
            "recv_time",
        )
        return _report_record(scope, item) if item else None

    return _report_record(scope, payload)

def _intensity_value(item: dict[str, Any]) -> Any:
    """烈度归一：cwa_report 的 intensity 是分区分站嵌套结构，取最大分区值."""
    value = _first(item, "max_intensity", "intensity", "MaxIntensity")
    if isinstance(value, dict):
        areas = value.get("area") or []
        numbers = [
            _float(area.get("maxIntensity"))
            for area in areas
            if isinstance(area, dict)
        ]
        numbers = [number for number in numbers if number is not None]
        return max(numbers) if numbers else None
    if isinstance(value, list):
        numbers = [
            _float(entry.get("max_intensity") or entry.get("maxInt"))
            for entry in value
            if isinstance(entry, dict)
        ]
        numbers = [number for number in numbers if number is not None]
        return max(numbers) if numbers else None
    return value

def _report_record(
    scope: str, item: dict[str, Any], *, raw: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    payload = raw if raw is not None else item
    return _record(
        "report",
        scope,
        payload,
        event_id=_first(item, "id", "EventID", "event_id", "md5"),
        location=_first(item, "location", "placeName", "epicenterPlace", "title")
        or (
            (item.get("hypocenter") or {}).get("name")
            if isinstance(item.get("hypocenter"), dict)
            else None
        ),
        magnitude=_first(item, "magnitude", "Magunitude"),
        intensity=_intensity_value(item),
        time=_first(item, "OriginTime", "origin_time", "time", "originTime"),
        depth=_first(item, "depth", "Depth"),
        serial=_first(item, "serial", "Serial"),
        is_cancel=_first(item, "is_cancel", "isCancel", "cancelled"),
        recv_time=_first(item, "recv_time", "recvTime"),
    )

def parse_payload(scope: str, payload: Any) -> dict[str, Any] | None:
    """按 scope 归类别派发解析器；解析失败只丢本条，不抛给调用方."""
    if not payload:
        return None
    category = SCOPE_TO_CATEGORY.get(scope)
    LOGGER.debug("灾害预警 %s 原始 payload: %s", scope, payload)
    try:
        if category == CATEGORY_TSUNAMI:
            record = parse_tsunami(scope, payload)
        elif scope == "jma_eew":
            record = parse_jma(scope, payload)
        elif category == CATEGORY_REPORT:
            record = parse_report(scope, payload)
        elif isinstance(payload, dict):
            record = parse_cea(scope, payload)
        else:
            record = None
    except (TypeError, ValueError, KeyError, AttributeError) as err:
        raise DisasterWarningApiError(f"{scope} 解析失败: {err}") from err
    return record

def freshness_key(record: dict[str, Any]) -> float:
    """新旧判定：优先服务端接收时刻，秒级统一换算为毫秒."""
    if (recv := record.get("recv_time")) is not None:
        value = float(recv)
        return value * 1000 if value < 1e11 else value
    if (text := record.get("time")):
        if (parsed := dt_util.parse_datetime(str(text))) is not None:
            return parsed.timestamp() * 1000
    return 0.0

def record_md5(record: dict[str, Any]) -> str | None:
    """报告同份判定：信封顶层或 cenc 条目内的 md5."""
    raw = record.get("raw")
    if isinstance(raw, dict) and raw.get("md5"):
        return str(raw["md5"])
    return None

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