"""昆仑燃气 免密公开接口."""
from __future__ import annotations

from typing import Any
from aiohttp import ClientSession

from ...api import async_request_json
from .const import BASE_URL, PATH_BALANCE, build_headers

async def async_fetch_balance(
    session: ClientSession, user_code: str, mdm_code: str
) -> dict[str, Any]:
    """取免密余额数据；HTTP/解析异常原样上抛，由协调器翻译."""
    payload = await async_request_json(
        session,
        "GET",
        BASE_URL + PATH_BALANCE,
        params={"userCode": user_code, "mdmCode": mdm_code},
        headers=build_headers(mdm_code),
    )
    if not isinstance(payload, dict):
        raise ValueError("昆仑燃气响应非对象")
    if payload.get("code") != 200:
        raise ValueError(f"昆仑燃气 code={payload.get('code')} msg={payload.get('msg')}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("昆仑燃气余额接口未返回数据")
    return data