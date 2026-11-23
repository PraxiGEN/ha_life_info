"""油价 API平台."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from aiohttp import ClientError, ClientSession
from bs4 import BeautifulSoup

from ...api import (
    HttpStatusError,
    LifeInfoError,
    LifeInfoRequestError,
    async_request_json,
)
from .const import (
    APIZERO_URL,
    PROVINCES,
    UA,
    WEB_URL,
    XXAPI_URL,
    region_slug,
)

_OIL_TYPES = {
    "gasoline_92": "gas92",
    "gasoline_95": "gas95",
    "gasoline_98": "gas98",
    "diesel_0": "die0",
}

class OilPriceApiError(LifeInfoError):
    """油价数据源解析/返回异常."""

def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")

def _empty_prices() -> dict[str, float | None]:
    """四级价格空槽，降级源只填拿到的字段."""
    return {"gas92": None, "gas95": None, "gas98": None, "die0": None}

def _auth_headers(api_key: str = "") -> dict[str, str]:
    """ApiZero 请求头：有 key 走 Bearer，匿名不塞空字段."""
    headers = {"User-Agent": UA}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers

def _has_prices(item: dict[str, Any]) -> bool:
    """判断一条价格数据是否至少有一个有效数值."""
    return any(v is not None for v in (item.get("prices") or {}).values())

async def async_fetch_prices(session: ClientSession) -> dict[str, dict[str, Any]]:
    """主源 xxapi：一次取全国价格，返回 {slug: 价格数据}."""
    payload = await async_request_json(
        session, "GET", XXAPI_URL, headers={"User-Agent": UA}
    )
    if not isinstance(payload, dict):
        raise OilPriceApiError("xxapi 响应非对象")
    code = payload.get("code")
    if code != 200:
        raise OilPriceApiError(f"xxapi code={code}")
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise OilPriceApiError("xxapi 无价格数据")

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

async def async_fetch_prices_apizero(
    session: ClientSession, slug: str, api_key: str = ""
) -> dict[str, Any]:
    """备源 ApiZero：按省取单省价格，返回与主源同构的数据."""
    payload = await async_request_json(
        session,
        "POST",
        APIZERO_URL,
        body={"province": PROVINCES.get(slug, slug)},
        headers=_auth_headers(api_key),
    )
    if not isinstance(payload, dict):
        raise OilPriceApiError("ApiZero 响应非对象")
    if payload.get("code") != 0:
        raise OilPriceApiError(f"ApiZero code={payload.get('code')} msg={payload.get('msg')}")
    data = payload.get("data") or {}
    rows = data.get("prices") or []
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
        "date": data.get("update_date") or date.today().isoformat(),
        "prices": prices,
        "changes": _empty_prices(),
    }

async def async_fetch_adjust(
    session: ClientSession, api_key: str = ""
) -> dict[str, Any]:
    """ApiZero 取全国调价信息（一次即可）."""
    payload = await async_request_json(
        session,
        "POST",
        APIZERO_URL,
        body={"province": PROVINCES["beijing"]},
        headers=_auth_headers(api_key),
    )
    if not isinstance(payload, dict):
        raise OilPriceApiError("ApiZero 响应非对象")
    code = payload.get("code")
    if code != 0:
        raise OilPriceApiError(f"ApiZero code={code} msg={payload.get('msg')}")
    data = payload.get("data") or {}
    return {
        "next_adjustment": data.get("next_adjustment"),
        "forecast": data.get("forecast"),
        "change_rate": _f(data.get("change_rate")),
        "working_day": data.get("working_day"),
    }

async def async_fetch_web(session: ClientSession, slug: str) -> dict[str, Any]:
    """末源网页：一次解析兜底价格 + 消息文本 + 下次调价日期."""
    url = WEB_URL.format(region=slug)
    try:
        async with session.get(url, headers={"User-Agent": UA}) as response:
            if response.status >= 400:
                raise HttpStatusError(response.status, url)
            raw = await response.read()
    except ClientError as err:
        raise LifeInfoRequestError(f"网页请求失败: {url}: {err}") from err
    soup = BeautifulSoup(_decode(raw), "html.parser")

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