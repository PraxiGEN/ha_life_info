"""油价 API平台."""
from __future__ import annotations

from aiohttp import ClientError, ClientSession

from ...api import (
    HttpStatusError,
    LifeInfoError,
    LifeInfoRequestError,
    async_request_json,
)
from .const import APIZERO_URL, PROVINCES, UA, WEB_URL, XXAPI_URL

class OilPriceApiError(LifeInfoError):
    """油价数据源响应异常."""

def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")

def _auth_headers(api_key: str = "") -> dict[str, str]:
    headers = {"User-Agent": UA}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers

async def async_fetch_prices(session: ClientSession) -> list[dict]:
    """主源 xxapi：一次取全国价格，返回原始 rows list."""
    payload = await async_request_json(
        session, "GET", XXAPI_URL, headers={"User-Agent": UA}
    )
    if not isinstance(payload, dict):
        raise OilPriceApiError("xxapi 响应非对象")
    if payload.get("code") != 200:
        raise OilPriceApiError(f"xxapi code={payload.get('code')}")
    rows = payload.get("data")
    if not isinstance(rows, list) or not rows:
        raise OilPriceApiError("xxapi 无价格数据")
    return rows

async def async_fetch_prices_apizero(
    session: ClientSession, slug: str, api_key: str = ""
) -> dict:
    """备源 ApiZero：按省取单省价格，返回原始 data dict."""
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
    return payload.get("data") or {}

async def async_fetch_adjust(
    session: ClientSession, api_key: str = ""
) -> dict:
    """ApiZero 取全国调价信息，返回原始 data dict."""
    payload = await async_request_json(
        session,
        "POST",
        APIZERO_URL,
        body={"province": PROVINCES["beijing"]},
        headers=_auth_headers(api_key),
    )
    if not isinstance(payload, dict):
        raise OilPriceApiError("ApiZero 响应非对象")
    if payload.get("code") != 0:
        raise OilPriceApiError(f"ApiZero code={payload.get('code')} msg={payload.get('msg')}")
    return payload.get("data") or {}

async def async_fetch_web(session: ClientSession, slug: str) -> str:
    """末源网页：返回解码后的 HTML 文本."""
    url = WEB_URL.format(region=slug)
    try:
        async with session.get(url, headers={"User-Agent": UA}) as response:
            if response.status >= 400:
                raise HttpStatusError(response.status, url)
            raw = await response.read()
    except ClientError as err:
        raise LifeInfoRequestError(f"网页请求失败: {url}: {err}") from err
    return _decode(raw)