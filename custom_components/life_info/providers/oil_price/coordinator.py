"""油价 协调器."""
from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed

from ... import storage
from ...api import LifeInfoError
from ...const import DOMAIN, LOGGER
from ...coordinator import LifeInfoCoordinator
from .api import (
    _has_prices,
    async_fetch_adjust,
    async_fetch_prices,
    async_fetch_prices_apizero,
    async_fetch_web,
)
from .const import (
    APIZERO_CACHE_KEY,
    APIZERO_CACHE_TTL_HOURS,
    CONF_API_KEY,
    CONF_NAME,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    PROVINCES,
)

class OilPriceCoordinator(LifeInfoCoordinator):
    """油价协调器：一条目多省份，价格三级冗余，仅全部失败才整体失败."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        interval = max(
            int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)), 1
        )
        super().__init__(hass, entry, update_interval=timedelta(hours=interval))
        self._session = async_get_clientsession(hass)
        self._api_key = str(entry.options.get(CONF_API_KEY, "") or "").strip()

    def account_key(self, account: dict[str, Any]) -> str:
        """账户 key = 省份 slug."""
        return str(account[CONF_REGION])

    async def _fetch(self) -> dict[str, dict[str, Any]]:
        """取数：xxapi→ApiZero→网页 逐级补价格；调价信息独立降级."""
        prices = await self._async_prices()
        # HA 规范：三级源全失败（无任何账户拿到有效价格）必须抛 UpdateFailed，
        # 由协调器统一标记实体不可用、记录日志、下个周期重试；不返回空数据假装成功。
        if self.accounts and not any(_has_prices(item) for item in prices.values()):
            raise UpdateFailed("油价全部数据源（xxapi / ApiZero / 网页）均无有效价格")
        adjust = await self._async_adjust()
        slugs = [self.account_key(account) for account in self.accounts]
        web_list = await asyncio.gather(
            *(self._async_web(slug) for slug in slugs),
            return_exceptions=True,
        )
        web_by_slug = {
            slug: value if isinstance(value, dict) else {}
            for slug, value in zip(slugs, web_list)
        }

        data: dict[str, dict[str, Any]] = {}
        for account in self.accounts:
            slug = self.account_key(account)
            item = dict(prices.get(slug) or {})
            item.setdefault("region_name", PROVINCES.get(slug, slug))
            web = web_by_slug.get(slug, {})
            merged_adjust = dict(adjust)
            if not merged_adjust.get("next_adjustment") and web.get("next_adjustment"):
                merged_adjust["next_adjustment"] = web["next_adjustment"]
            item["adjust"] = merged_adjust
            item["news"] = web.get("news") or {}
            data[slug] = item
        return data

    async def _async_prices(self) -> dict[str, dict[str, Any]]:
        """价格三级冗余：主源全量失败或单省缺失时逐级回补."""
        try:
            return await async_fetch_prices(self._session)
        except (LifeInfoError, TimeoutError, OSError) as err:
            LOGGER.debug("xxapi 全国价格失败，转 ApiZero 逐省回补: %s", err)

        result: dict[str, dict[str, Any]] = {}
        for account in self.accounts:
            slug = self.account_key(account)
            try:
                result[slug] = await async_fetch_prices_apizero(
                    self._session, slug, self._api_key
                )
                continue
            except (LifeInfoError, TimeoutError, OSError) as err:
                LOGGER.debug("ApiZero 价格失败 %s，转网页: %s", slug, err)
            try:
                web = await self._async_web(slug)
                if _has_prices(web):
                    result[slug] = {
                        "region_name": PROVINCES.get(slug, slug),
                        "date": web.get("date"),
                        "prices": web["prices"],
                        "changes": {},
                    }
            except (LifeInfoError, TimeoutError, OSError):
                pass
        return result

    async def _async_adjust(self) -> dict[str, Any]:
        """ApiZero 调价信息：24h 缓存，失败沿用旧值，不拖垮价格."""
        cached = await storage.async_load(self.hass, APIZERO_CACHE_KEY)
        if storage.is_fresh(cached, APIZERO_CACHE_TTL_HOURS * 3600):
            return cached["data"]
        try:
            data = await async_fetch_adjust(self._session, self._api_key)
        except (LifeInfoError, TimeoutError, OSError) as err:
            LOGGER.debug("ApiZero 调价信息获取失败，沿用缓存: %s", err)
            return cached.get("data") or {}
        await storage.async_save(self.hass, APIZERO_CACHE_KEY, data)
        return data

    async def _async_web(self, slug: str) -> dict[str, Any]:
        """网页消息+兜底价格：失败返回空，不影响主流程."""
        try:
            return await async_fetch_web(self._session, slug)
        except (LifeInfoError, TimeoutError, OSError) as err:
            LOGGER.debug("网页获取失败 %s: %s", slug, err)
            return {}

    def device_info_for(self, account: dict[str, Any]) -> DeviceInfo:
        """每省份一台服务类设备：slug 作序列号，发改委作供应方."""
        slug = self.account_key(account)
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.service_id}_{slug}")},
            name=str(account.get(CONF_NAME) or PROVINCES.get(slug, slug)),
            serial_number=slug,
            manufacturer="国家发改委",
            model="成品油价格",
            entry_type=DeviceEntryType.SERVICE,
        )