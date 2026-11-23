"""生活信息 公用请求层."""
from __future__ import annotations

import asyncio
import json
from typing import Any
from aiohttp import ClientError, ClientSession

from .const import LOGGER

class LifeInfoError(Exception):
    """公用根异常：请求层与各私有服务的业务异常统一挂载."""

class LifeInfoRequestError(LifeInfoError):
    """请求层统一异常：网络错误 / 状态码 / 响应解析失败."""

class HttpStatusError(LifeInfoRequestError):
    """HTTP 状态码异常（原始类型，由私有层翻译 HA 语义）."""

    def __init__(self, status: int, body: str = "") -> None:
        super().__init__(f"HTTP {status}: {body[:200]}")
        self.status = status

async def async_request_json(
    session: ClientSession,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: int = 15,
) -> Any:
    """统一请求：状态码分类 + JSON 解析，异常归一化为公用类型."""
    try:
        async with asyncio.timeout(timeout):
            resp = await session.request(
                method, url, params=params, headers=headers, json=body
            )
            async with resp:
                text = await resp.text()
                if resp.status >= 400:
                    raise HttpStatusError(resp.status, text)
                return json.loads(text) if text else {}
    except asyncio.TimeoutError as err:
        LOGGER.debug("请求超时: %s %s", method, url)
        raise LifeInfoRequestError(f"请求超时: {method} {url}") from err
    except ClientError as err:
        LOGGER.debug("请求失败: %s %s: %s", method, url, err)
        raise LifeInfoRequestError(f"请求失败: {method} {url}: {err}") from err
    except json.JSONDecodeError as err:
        raise LifeInfoRequestError(f"响应非 JSON: {url}") from err