"""油价 协调器."""
from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta
from typing import Any

from bs4 import BeautifulSoup
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed

from ... import storage
from ...api import LifeInfoError
from ...const import DOMAIN, LOGGER
from ...coordinator import LifeInfoCoordinator
from .api import (
    OilPriceApiError,
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
    region_slug,
)

_OIL_TYPES = {
    "gasoline_92": "gas92",
    "gasoline_95": "gas95",
    "gasoline_98": "gas98",
    "diesel_0": "die0",
}

def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _empty_prices() -> dict[str, float | None]:
    return {"gas92": None, "gas95": None, "gas98": None, "die0": None}

def _has_prices(item: dict[str, Any]) -> bool:
    return any(v is not None for v in (item.get("prices") or {}).values())

def parse_xxapi_prices(rows: list[dict]) -> dict[str, dict[str, Any]]:
    """xxapi 原始 rows → {slug: {region_name, date, prices, changes}}."""
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        slug = region_slug(row.get("regionName"))
        if not slug:
            continue
        result[slug] = {
            "region_name": PROVINCES[slug],
            "date": row.get("date"),
            "prices": {
                "gas92": _f(row.get("n92")),
                "gas95": _f(row.get("n95")),
                "gas98": _f(row.get("n98")),
                "die0": _f(row.get("n0")),
            },
            "changes": {
                "gas92": _f(row.get("n92Change")),
                "gas95": _f(row.get("n95Change")),
                "gas98": _f(row.get("n98Change")),
                "die0": _f(row.get("n0Change")),
            },
        }
    if not result:
        raise OilPriceApiError("xxapi 无匹配省份")
    return result

def parse_apizero_prices(payload: dict, slug: str) -> dict[str, Any]:
    """ApiZero 原始 data → 单省同构项."""
    rows = payload.get("prices") or []
    prices = _empty_prices()
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = _OIL_TYPES.get(str(row.get("type")))
        if key:
            prices[key] = _f(row.get("price"))
    if not any(v is not None for v in prices.values()):
        raise OilPriceApiError("ApiZero 无价格数据")
    return {
        "region_name": PROVINCES.get(slug, slug),
        "date": payload.get("update_date") or date.today().isoformat(),
        "prices": prices,
        "changes": _empty_prices(),
    }

def parse_adjust(payload: dict) -> dict[str, Any]:
    """ApiZero 原始 data → 调价信息."""
    return {
        "next_adjustment": payload.get("next_adjustment"),
        "forecast": payload.get("forecast"),
        "change_rate": _f(payload.get("change_rate")),
        "working_day": payload.get("working_day"),
    }

def parse_web(html: str) -> dict[str, Any]:
    """HTML 文本 → 兜底价格 + 消息 + 调价日期."""
    soup = BeautifulSoup(html, "html.parser")

    tables = soup.find_all("table", class_="bx")
    prices = _empty_prices()
    if tables:
        gas_nums = re.findall(r"\d+\.\d+", tables[0].get_text(" ", strip=True))
        for key, num in zip(("gas92", "gas95", "gas98"), gas_nums[:3]):
            prices[key] = _f(num)
    if len(tables) > 1:
        diesel_nums = re.findall(r"\d+\.\d+", tables[1].get_text(" ", strip=True))
        if diesel_nums:
            prices["die0"] = _f(diesel_nums[0])

    news: dict[str, str] = {}
    next_adjustment: str | None = None
    update_date: str | None = None
    full_text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    for paragraph in soup.find_all("p"):
        text = re.sub(r"\s+", " ", paragraph.get_text(" ", strip=True)).strip()
        if not text:
            continue
        if "：" not in text:
            continue
        if "涨跌最新消息" in text or "今日油价最新消息" in text:
            news["trend_news"] = text
        elif "调整最新消息：" in text:
            news["adjust_news"] = text
    if m := re.search(r"价格更新时间：(\d{4}年\d{1,2}月\d{1,2}日)", full_text):
        update_date = m.group(1)
    if m := re.search(r"下一个油价调整日期为(\d{4}年\d{1,2}月\d{1,2}日[^；;]*)", full_text):
        next_adjustment = m.group(1).strip()

    result: dict[str, Any] = {"news": news}
    if any(v is not None for v in prices.values()):
        result["prices"] = prices
    if update_date:
        result["date"] = update_date
    if next_adjustment:
        result["next_adjustment"] = next_adjustment
    return result

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
        """取数：网页每省只请求一次（价格兜底+消息共用），价格走三级回补."""
        slugs = [self.account_key(account) for account in self.accounts]
        web_list = await asyncio.gather(
            *(self._async_web(slug) for slug in slugs),
            return_exceptions=True,
        )
        web_by_slug: dict[str, dict[str, Any]] = {
            slug: value if isinstance(value, dict) else {}
            for slug, value in zip(slugs, web_list)
        }
        prices = await self._async_prices(web_by_slug)

        if self.accounts and not any(_has_prices(item) for item in prices.values()):
            raise UpdateFailed("油价全部数据源（xxapi / ApiZero / 网页）均无有效价格")
        adjust = await self._async_adjust()

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

    async def _async_prices(
        self, web_by_slug: dict[str, dict[str, Any]]
    ) -> dict[str, dict[str, Any]]:
        """价格三级冗余：主源作为底稿，缺失/无效省份逐省 ApiZero→网页回补."""
        try:
            rows = await async_fetch_prices(self._session)
            result: dict[str, dict[str, Any]] = parse_xxapi_prices(rows)
        except (LifeInfoError, TimeoutError, OSError) as err:
            LOGGER.debug("xxapi 全国价格失败，转 ApiZero 逐省回补: %s", err)
            result = {}

        for account in self.accounts:
            slug = self.account_key(account)
            if _has_prices(result.get(slug) or {}):
                continue
            try:
                payload = await async_fetch_prices_apizero(
                    self._session, slug, self._api_key
                )
                result[slug] = parse_apizero_prices(payload, slug)
                continue
            except (LifeInfoError, TimeoutError, OSError) as err:
                LOGGER.debug("ApiZero 价格失败 %s，转网页: %s", slug, err)
            web = web_by_slug.get(slug) or {}
            if _has_prices(web):
                result[slug] = {
                    "region_name": PROVINCES.get(slug, slug),
                    "date": web.get("date"),
                    "prices": web["prices"],
                    "changes": {},
                }
        return result

    async def _async_adjust(self) -> dict[str, Any]:
        """ApiZero 调价信息：24h 缓存，失败沿用旧值，不拖垮价格."""
        cached = await storage.async_load(self.hass, APIZERO_CACHE_KEY)
        if storage.is_fresh(cached, APIZERO_CACHE_TTL_HOURS * 3600):
            return cached["data"]
        try:
            payload = await async_fetch_adjust(self._session, self._api_key)
            data = parse_adjust(payload)
        except (LifeInfoError, TimeoutError, OSError) as err:
            LOGGER.debug("ApiZero 调价信息获取失败，沿用缓存: %s", err)
            return cached.get("data") or {}
        await storage.async_save(self.hass, APIZERO_CACHE_KEY, data)
        return data

    async def _async_web(self, slug: str) -> dict[str, Any]:
        """网页消息+兜底价格：失败返回空，不影响主流程."""
        try:
            html = await async_fetch_web(self._session, slug)
            return parse_web(html)
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