"""每日内容 协调器."""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from datetime import timedelta
from typing import Any

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
    async_fetch_apizero_history,
    async_fetch_apizero_hitokoto,
    async_fetch_apizero_poetry,
    async_fetch_apizero_soul_soup,
    async_fetch_official_hitokoto,
    async_fetch_xxapi_history,
    async_fetch_xxapi_hitokoto,
    async_fetch_xxapi_poetry,
    async_fetch_xxapi_soul_soup,
)
from .const import (
    ACCOUNT_KEY,
    CACHE_KEY_PREFIX,
    CACHE_TTL_HOURS,
    CONF_ACCOUNT_KEY,
    CONF_API_KEY,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    QUIET_END_HOUR,
    QUIET_START_HOUR,
    SERVICE_NAME,
)

_ENTITY_ORDER = ("hitokoto", "poetry", "soul_soup", "history")

class DailyContentCoordinator(LifeInfoCoordinator):
    """每日内容协调器：单伪账户 4 实体，每实体独立按降级矩阵取数."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        interval = max(
            int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)), 1
        )
        super().__init__(hass, entry, update_interval=timedelta(hours=interval))
        self._session = async_get_clientsession(hass)
        self._api_key = str(entry.options.get(CONF_API_KEY) or "").strip()

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """刷新入口：夜间沿用读数，内存为空则从持久化缓存恢复."""
        if self._in_quiet_hours():
            if self.data:
                LOGGER.debug("每日内容处于夜间静默时段，跳过刷新")
                return self.data
            restored = await self._async_restore()
            if restored:
                LOGGER.debug("每日内容夜间从持久化缓存恢复")
                return restored
        return await super()._async_update_data()

    def _cache_key(self, key: str) -> str:
        """缓存键按实体隔离，避免四实体串味."""
        return f"{CACHE_KEY_PREFIX}{key}"

    async def _async_restore(self) -> dict[str, dict[str, Any]] | None:
        """夜间首启恢复：四实体缓存均 fresh 才整体沿用，否则回落取数."""
        values: dict[str, Any] = {}
        for key in _ENTITY_ORDER:
            cached = await storage.async_load(self.hass, self._cache_key(key))
            if not storage.is_fresh(cached, CACHE_TTL_HOURS * 3600):
                return None
            values[key] = cached["data"]
        return {ACCOUNT_KEY: values}

    def _in_quiet_hours(self) -> bool:
        """静默时段：HA 本地时间 0 点到 5 点（不含 5 点）."""
        return QUIET_START_HOUR <= dt_util.now().hour < QUIET_END_HOUR

    @property
    def accounts(self) -> list[dict[str, Any]]:
        """固定单伪账户：接入名取条目选项，缺失回落服务名."""
        stored = self.entry.options.get(CONF_ACCOUNTS) or []
        name = str((stored[0] if stored else {}).get(CONF_NAME) or SERVICE_NAME)
        return [{CONF_ACCOUNT_KEY: ACCOUNT_KEY, CONF_NAME: name}]

    def account_key(self, account: dict[str, Any]) -> str:
        """账户 key 固定 daily，不随选项变化."""
        return ACCOUNT_KEY

    async def _fetch(self) -> dict[str, dict[str, Any]]:
        """并发取 4 实体：单实体全失败置 None，四实体全失败整体失败."""
        results = await asyncio.gather(
            self._async_hitokoto(),
            self._async_poetry(),
            self._async_soul_soup(),
            self._async_history(),
            return_exceptions=True,
        )
        values: dict[str, dict[str, Any] | None] = {}
        for key, result in zip(_ENTITY_ORDER, results):
            if isinstance(result, BaseException):
                # 停机/取消信号必须继续上抛，不能被当成普通实体失败吞掉.
                if isinstance(result, asyncio.CancelledError):
                    raise result
                LOGGER.warning("每日内容 %s 取数异常: %s", key, result)
                values[key] = None
            else:
                values[key] = result
        if not any(values.values()):
            raise UpdateFailed("每日内容全部数据源均无有效数据")
        return {ACCOUNT_KEY: values}

    async def _async_hitokoto(self) -> dict[str, Any] | None:
        """一言：有 KEY 走 ApiZero 优先；无 KEY 时 xxapi 失败才按需调匿名 ApiZero."""
        if self._api_key:
            calls = (
                lambda: async_fetch_apizero_hitokoto(self._session, self._api_key),
                lambda: async_fetch_xxapi_hitokoto(self._session),
                lambda: async_fetch_official_hitokoto(self._session),
            )
        else:
            calls = (
                lambda: async_fetch_xxapi_hitokoto(self._session),
                lambda: async_fetch_apizero_hitokoto(self._session, ""),
                lambda: async_fetch_official_hitokoto(self._session),
            )
        return await self._async_first("hitokoto", "一言", calls)

    async def _async_poetry(self) -> dict[str, Any] | None:
        """诗词：ApiZero 与 xxapi 互为冗余，无官方兜底."""
        if self._api_key:
            calls = (
                lambda: async_fetch_apizero_poetry(self._session, self._api_key),
                lambda: async_fetch_xxapi_poetry(self._session),
            )
        else:
            calls = (
                lambda: async_fetch_xxapi_poetry(self._session),
                lambda: async_fetch_apizero_poetry(self._session, ""),
            )
        return await self._async_first("poetry", "诗词", calls)

    async def _async_soul_soup(self) -> dict[str, Any] | None:
        """毒鸡汤：ApiZero 与 xxapi 互为冗余，无官方兜底."""
        if self._api_key:
            calls = (
                lambda: async_fetch_apizero_soul_soup(self._session, self._api_key),
                lambda: async_fetch_xxapi_soul_soup(self._session),
            )
        else:
            calls = (
                lambda: async_fetch_xxapi_soul_soup(self._session),
                lambda: async_fetch_apizero_soul_soup(self._session, ""),
            )
        return await self._async_first("soul_soup", "毒鸡汤", calls)

    async def _async_history(self) -> dict[str, Any] | None:
        """历史：ApiZero 强制鉴权，无 KEY 时仅 xxapi 单源."""
        if self._api_key:
            calls = (
                lambda: async_fetch_apizero_history(self._session, self._api_key),
                lambda: async_fetch_xxapi_history(self._session),
            )
        else:
            calls = (lambda: async_fetch_xxapi_history(self._session),)
        return await self._async_first("history", "历史今日", calls)

    async def _async_first(
        self,
        key: str,
        label: str,
        calls: Iterable[Callable[[], Any]],
    ) -> dict[str, Any] | None:
        """按降级顺序取数：成功落盘，全失败在 TTL 内沿用缓存，否则 None."""
        for call in calls:
            try:
                value = await call()
                await storage.async_save(self.hass, self._cache_key(key), value)
                return value
            except (LifeInfoError, TimeoutError, OSError) as err:
                LOGGER.debug("每日内容 %s 数据源失败，尝试下一级: %s", label, err)
        cached = await storage.async_load(self.hass, self._cache_key(key))
        if storage.is_fresh(cached, CACHE_TTL_HOURS * 3600):
            LOGGER.warning("每日内容 %s 取数失败，沿用缓存", label)
            stale = dict(cached["data"])
            stale["_cache_at"] = cached.get("fetched_at")
            return stale
        return None

    def device_info_for(self, account: dict[str, Any]) -> DeviceInfo:
        """单台服务类设备：无序列号，按伪账户 key 区分实例."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.service_id}_{ACCOUNT_KEY}")},
            name=str(account.get(CONF_NAME) or SERVICE_NAME),
            serial_number=None,
            manufacturer="生活信息",
            model="每日内容",
            entry_type=DeviceEntryType.SERVICE,
        )