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
    DailyContentApiError,
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
    MIN_SCAN_INTERVAL,
    QUIET_END_HOUR,
    QUIET_START_HOUR,
    SERVICE_NAME,
    TTL_HITOKOTO,
    TTL_POETRY,
    TTL_SOUL_SOUP,
)

_ENTITY_ORDER = ("hitokoto", "poetry", "soul_soup", "history")

def _item(
    text: Any,
    source: str,
    *,
    from_name: str | None = None,
    author: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    value = str(text or "").strip()
    if not value:
        raise DailyContentApiError(f"{source} 无文本内容")
    return {
        "text": value,
        "source": source,
        "from": from_name,
        "author": author,
        "category": category,
    }

def _history_items(rows: Any) -> list[str]:
    items: list[str] = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, str):
            text = row.strip()
        elif isinstance(row, dict):
            year = str(row.get("year") or "").strip()
            date = str(row.get("date") or "").strip()
            day = f"{year}年{date}" if year and date else (date or year)
            title = str(row.get("title") or "").strip()
            desc = str(row.get("desc") or "").strip()
            text = " ".join(part for part in (day, title or desc) if part)
        else:
            text = ""
        if text:
            items.append(text)
    if not items:
        raise DailyContentApiError("历史今日无条目")
    return items

def parse_hitokoto(raw: Any, source: str) -> dict[str, Any]:
    if source == "xxapi":
        return _item(raw, source)
    if source == "apizero":
        return _item(
            raw.get("hitokoto"),
            source,
            from_name=raw.get("from"),
            author=raw.get("from_who"),
            category=raw.get("type_name"),
        )
    if source == "official":
        return _item(
            raw.get("hitokoto"),
            source,
            from_name=raw.get("from"),
            author=raw.get("from_who"),
        )
    raise ValueError(f"未知 source: {source}")

def parse_poetry(raw: Any, source: str) -> dict[str, Any]:
    if source == "xxapi":
        return _item(raw, source)
    if source == "apizero":
        return _item(
            raw.get("content"),
            source,
            from_name=raw.get("origin"),
            author=raw.get("author"),
            category=raw.get("category"),
        )
    raise ValueError(f"未知 source: {source}")

def parse_soul_soup(raw: Any, source: str) -> dict[str, Any]:
    if source == "xxapi":
        return _item(raw, source)
    if source == "apizero":
        return _item(raw.get("content"), source)
    raise ValueError(f"未知 source: {source}")

def parse_history(raw: Any, source: str) -> dict[str, Any]:
    if source == "xxapi":
        return {"items": _history_items(raw), "source": source}
    if source == "apizero":
        return {"items": _history_items(raw.get("items")), "source": source}
    raise ValueError(f"未知 source: {source}")

class DailyContentCoordinator(LifeInfoCoordinator):
    """每日内容协调器：单伪账户 4 实体，每实体独立按降级矩阵取数."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        interval = max(
            int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
            MIN_SCAN_INTERVAL,
        )
        super().__init__(hass, entry, update_interval=timedelta(minutes=interval))
        self._session = async_get_clientsession(hass)
        self._api_key = str(entry.options.get(CONF_API_KEY) or "").strip()

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
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
        return f"{CACHE_KEY_PREFIX}{key}"

    async def _async_restore(self) -> dict[str, dict[str, Any]] | None:
        values: dict[str, Any] = {}
        for key in _ENTITY_ORDER:
            cached = await storage.async_load(self.hass, self._cache_key(key))
            if not storage.is_fresh(cached, CACHE_TTL_HOURS * 3600):
                return None
            values[key] = cached["data"]
        return {ACCOUNT_KEY: values}

    def _in_quiet_hours(self) -> bool:
        return QUIET_START_HOUR <= dt_util.now().hour < QUIET_END_HOUR

    async def _fresh_or_none(self, key: str, ttl: int) -> dict[str, Any] | None:
        if not self._api_key:
            return None
        cached = await storage.async_load(self.hass, self._cache_key(key))
        return cached["data"] if storage.is_fresh(cached, ttl) else None

    @property
    def accounts(self) -> list[dict[str, Any]]:
        stored = self.entry.options.get(CONF_ACCOUNTS) or []
        name = str((stored[0] if stored else {}).get(CONF_NAME) or SERVICE_NAME)
        return [{CONF_ACCOUNT_KEY: ACCOUNT_KEY, CONF_NAME: name}]

    def account_key(self, account: dict[str, Any]) -> str:
        return ACCOUNT_KEY

    async def _fetch(self) -> dict[str, dict[str, Any]]:
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
        if (v := await self._fresh_or_none("hitokoto", TTL_HITOKOTO)) is not None:
            return v
        s, k = self._session, self._api_key
        if k:
            async def _c1(): return parse_hitokoto(await async_fetch_apizero_hitokoto(s, k), "apizero")
            async def _c2(): return parse_hitokoto(await async_fetch_xxapi_hitokoto(s), "xxapi")
            async def _c3(): return parse_hitokoto(await async_fetch_official_hitokoto(s), "official")
            calls = (_c1, _c2, _c3)
        else:
            async def _c1(): return parse_hitokoto(await async_fetch_xxapi_hitokoto(s), "xxapi")
            async def _c2(): return parse_hitokoto(await async_fetch_apizero_hitokoto(s, ""), "apizero")
            async def _c3(): return parse_hitokoto(await async_fetch_official_hitokoto(s), "official")
            calls = (_c1, _c2, _c3)
        return await self._async_first("hitokoto", "一言", calls)

    async def _async_poetry(self) -> dict[str, Any] | None:
        if (v := await self._fresh_or_none("poetry", TTL_POETRY)) is not None:
            return v
        s, k = self._session, self._api_key
        if k:
            async def _c1(): return parse_poetry(await async_fetch_apizero_poetry(s, k), "apizero")
            async def _c2(): return parse_poetry(await async_fetch_xxapi_poetry(s), "xxapi")
            calls = (_c1, _c2)
        else:
            async def _c1(): return parse_poetry(await async_fetch_xxapi_poetry(s), "xxapi")
            async def _c2(): return parse_poetry(await async_fetch_apizero_poetry(s, ""), "apizero")
            calls = (_c1, _c2)
        return await self._async_first("poetry", "诗词", calls)

    async def _async_soul_soup(self) -> dict[str, Any] | None:
        if (v := await self._fresh_or_none("soul_soup", TTL_SOUL_SOUP)) is not None:
            return v
        s, k = self._session, self._api_key
        if k:
            async def _c1(): return parse_soul_soup(await async_fetch_apizero_soul_soup(s, k), "apizero")
            async def _c2(): return parse_soul_soup(await async_fetch_xxapi_soul_soup(s), "xxapi")
            calls = (_c1, _c2)
        else:
            async def _c1(): return parse_soul_soup(await async_fetch_xxapi_soul_soup(s), "xxapi")
            async def _c2(): return parse_soul_soup(await async_fetch_apizero_soul_soup(s, ""), "apizero")
            calls = (_c1, _c2)
        return await self._async_first("soul_soup", "毒鸡汤", calls)

    async def _async_history(self) -> dict[str, Any] | None:
        s, k = self._session, self._api_key
        if k:
            async def _c1(): return parse_history(await async_fetch_apizero_history(s, k), "apizero")
            async def _c2(): return parse_history(await async_fetch_xxapi_history(s), "xxapi")
            calls = (_c1, _c2)
        else:
            async def _c1(): return parse_history(await async_fetch_xxapi_history(s), "xxapi")
            calls = (_c1,)
        return await self._async_first("history", "历史今日", calls)

    async def _async_first(
        self,
        key: str,
        label: str,
        calls: Iterable[Callable[[], Any]],
    ) -> dict[str, Any] | None:
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
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.service_id}_{ACCOUNT_KEY}")},
            name=str(account.get(CONF_NAME) or SERVICE_NAME),
            serial_number=None,
            manufacturer="生活信息",
            model="每日内容",
            entry_type=DeviceEntryType.SERVICE,
        )