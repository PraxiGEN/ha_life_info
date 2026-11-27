"""每日内容 API平台."""
from __future__ import annotations

from typing import Any
from aiohttp import ClientSession

from ...api import LifeInfoError, async_request_json
from .const import APIZERO_BASE, HITOKOTO_OFFICIAL, UA, XXAPI_BASE

class DailyContentApiError(LifeInfoError):
    """每日内容数据源返回异常."""

def _auth_headers(api_key: str = "") -> dict[str, str]:
    headers = {"User-Agent": UA}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers

async def _async_xxapi(
    session: ClientSession, path: str, params: dict[str, Any] | None = None
) -> Any:
    payload = await async_request_json(
        session,
        "GET",
        f"{XXAPI_BASE}{path}",
        params=params,
        headers={"User-Agent": UA},
    )
    if not isinstance(payload, dict):
        raise DailyContentApiError("xxapi 响应非对象")
    if payload.get("code") != 200:
        raise DailyContentApiError(f"xxapi code={payload.get('code')}")
    return payload.get("data")

async def _async_apizero(
    session: ClientSession,
    method: str,
    path: str,
    api_key: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = await async_request_json(
        session,
        method,
        f"{APIZERO_BASE}{path}",
        body=body,
        headers=_auth_headers(api_key),
    )
    if not isinstance(payload, dict):
        raise DailyContentApiError("ApiZero 响应非对象")
    if payload.get("code") != 0:
        raise DailyContentApiError(
            f"ApiZero code={payload.get('code')} msg={payload.get('msg')}"
        )
    data = payload.get("data")
    return data if isinstance(data, dict) else {}

async def async_fetch_xxapi_hitokoto(session: ClientSession) -> Any:
    return await _async_xxapi(session, "/yiyan", {"type": "hitokoto"})

async def async_fetch_xxapi_poetry(session: ClientSession) -> Any:
    return await _async_xxapi(session, "/yiyan", {"type": "poetry"})

async def async_fetch_xxapi_soul_soup(session: ClientSession) -> Any:
    return await _async_xxapi(session, "/dujitang")

async def async_fetch_xxapi_history(session: ClientSession) -> Any:
    return await _async_xxapi(session, "/history")

async def async_fetch_apizero_hitokoto(
    session: ClientSession, api_key: str
) -> dict[str, Any]:
    return await _async_apizero(session, "GET", "/hitokoto", api_key)

async def async_fetch_apizero_poetry(
    session: ClientSession, api_key: str
) -> dict[str, Any]:
    return await _async_apizero(session, "POST", "/shici", api_key, body={})

async def async_fetch_apizero_soul_soup(
    session: ClientSession, api_key: str
) -> dict[str, Any]:
    return await _async_apizero(session, "POST", "/soul-soup", api_key, body={})

async def async_fetch_apizero_history(
    session: ClientSession, api_key: str
) -> dict[str, Any]:
    return await _async_apizero(session, "POST", "/history-today", api_key, body={})

async def async_fetch_official_hitokoto(session: ClientSession) -> dict[str, Any]:
    payload = await async_request_json(
        session, "GET", HITOKOTO_OFFICIAL, headers={"User-Agent": UA}
    )
    if not isinstance(payload, dict):
        raise DailyContentApiError("一言官方响应非对象")
    return payload