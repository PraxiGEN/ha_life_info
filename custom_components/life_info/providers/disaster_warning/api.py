"""灾害预警 API平台."""
from __future__ import annotations

from typing import Any
from aiohttp import ClientSession

from ...api import LifeInfoError, async_request_json
from .const import CAPQUAKE_BASE

class DisasterWarningApiError(LifeInfoError):
    """灾害预警数据源返回异常."""

async def async_fetch_snapshot(session: ClientSession) -> dict[str, Any]:
    """全源快照：按 scope 分组对象，缺数据的源不会出现."""
    payload = await async_request_json(
        session, "GET", f"{CAPQUAKE_BASE}/snapshot"
    )
    if not isinstance(payload, dict):
        raise DisasterWarningApiError("snapshot 响应非对象")
    return payload

async def async_fetch_scope(session: ClientSession, scope: str) -> Any:
    """单源最新一条；503 no data yet 视为暂无数据."""
    return await async_request_json(
        session, "GET", f"{CAPQUAKE_BASE}/{scope}"
    )