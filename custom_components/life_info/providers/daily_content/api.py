"""每日内容 数据源接口."""
from __future__ import annotations

from typing import Any

from aiohttp import ClientSession

from ...api import LifeInfoError, async_request_json
from .const import APIZERO_BASE, HITOKOTO_OFFICIAL, UA, XXAPI_BASE

class DailyContentApiError(LifeInfoError):
    """每日内容数据源返回异常."""

def _item(
    text: Any,
    source: str,
    *,
    from_name: str | None = None,
    author: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """统一文本结构：任一源的空文本按失败处理，交由上层降级."""
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

def _auth_headers(api_key: str = "") -> dict[str, str]:
    """ApiZero 请求头：有 KEY 走 Bearer，匿名不塞空字段."""
    headers = {"User-Agent": UA}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers

async def _async_xxapi(
    session: ClientSession, path: str, params: dict[str, Any] | None = None
) -> Any:
    """xxapi 公共请求：统一 code==200 判定，返回 data."""
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
    """ApiZero 公共请求：统一 code==0 判定，返回 data."""
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

def _history_items(rows: Any) -> list[str]:
    """历史条目统一成字符串数组，兼容 xxapi 字符串与 ApiZero 对象两种形态."""
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

async def async_fetch_xxapi_hitokoto(session: ClientSession) -> dict[str, Any]:
    """xxapi 一言."""
    data = await _async_xxapi(session, "/yiyan", {"type": "hitokoto"})
    return _item(data, "xxapi")

async def async_fetch_xxapi_poetry(session: ClientSession) -> dict[str, Any]:
    """xxapi 诗词."""
    data = await _async_xxapi(session, "/yiyan", {"type": "poetry"})
    return _item(data, "xxapi")

async def async_fetch_xxapi_soul_soup(session: ClientSession) -> dict[str, Any]:
    """xxapi 毒鸡汤."""
    data = await _async_xxapi(session, "/dujitang")
    return _item(data, "xxapi")

async def async_fetch_xxapi_history(session: ClientSession) -> dict[str, Any]:
    """xxapi 历史今日：无参数，一次返回当日全部条目."""
    data = await _async_xxapi(session, "/history")
    return {"items": _history_items(data), "source": "xxapi"}

async def async_fetch_apizero_hitokoto(
    session: ClientSession, api_key: str
) -> dict[str, Any]:
    """ApiZero 一言."""
    data = await _async_apizero(session, "GET", "/hitokoto", api_key)
    return _item(
        data.get("hitokoto"),
        "apizero",
        from_name=data.get("from"),
        author=data.get("from_who"),
        category=data.get("type_name"),
    )

async def async_fetch_apizero_poetry(
    session: ClientSession, api_key: str
) -> dict[str, Any]:
    """ApiZero 诗词."""
    data = await _async_apizero(session, "POST", "/shici", api_key, body={})
    return _item(
        data.get("content"),
        "apizero",
        from_name=data.get("origin"),
        author=data.get("author"),
        category=data.get("category"),
    )

async def async_fetch_apizero_soul_soup(
    session: ClientSession, api_key: str
) -> dict[str, Any]:
    """ApiZero 毒鸡汤."""
    data = await _async_apizero(session, "POST", "/soul-soup", api_key, body={})
    return _item(data.get("content"), "apizero")

async def async_fetch_apizero_history(
    session: ClientSession, api_key: str
) -> dict[str, Any]:
    """ApiZero 历史今日：强制 KEY，匿名返回 code 4015."""
    data = await _async_apizero(session, "POST", "/history-today", api_key, body={})
    return {"items": _history_items(data.get("items")), "source": "apizero"}

async def async_fetch_official_hitokoto(session: ClientSession) -> dict[str, Any]:
    """一言官方兜底：公益接口，QPS 限制严格，仅末位调用."""
    payload = await async_request_json(
        session, "GET", HITOKOTO_OFFICIAL, headers={"User-Agent": UA}
    )
    if not isinstance(payload, dict):
        raise DailyContentApiError("一言官方响应非对象")
    return _item(
        payload.get("hitokoto"),
        "official",
        from_name=payload.get("from"),
        author=payload.get("from_who"),
    )
