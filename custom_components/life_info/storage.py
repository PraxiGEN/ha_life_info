"""生活信息 公用持久化层"""
from __future__ import annotations

import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

STORAGE_VERSION = 1

_STORES: dict[str, Store] = {}
_CACHES: dict[str, dict[str, Any]] = {}

def _cache_key(hass: HomeAssistant, key: str) -> str:
    """按 config 路径 + 业务键分键，避免多实例/多服务串味."""
    return hass.config.path(key)

def get_store(hass: HomeAssistant, key: str) -> Store:
    """取得（或惰性创建）当前 hass 的 Store 实例."""
    cache_key = _cache_key(hass, key)
    store = _STORES.get(cache_key)
    if store is None:
        store = Store(hass, STORAGE_VERSION, key)
        _STORES[cache_key] = store
    return store

def is_fresh(cached: dict[str, Any], ttl_seconds: float) -> bool:
    """缓存有数据且在 TTL 内（TTL 由调用方按业务传入）."""
    fetched_at = float(cached.get("fetched_at") or 0)
    return (
        bool(cached.get("data"))
        and time.time() - fetched_at < ttl_seconds
    )

async def async_load(hass: HomeAssistant, key: str) -> dict[str, Any]:
    """读取缓存（进程内优先）."""
    cache_key = _cache_key(hass, key)
    cached = _CACHES.get(cache_key)
    if cached is None:
        cached = await get_store(hass, key).async_load() or {}
        _CACHES[cache_key] = cached
    return cached

async def async_save(
    hass: HomeAssistant, key: str, data: dict[str, Any]
) -> dict[str, Any]:
    """写入缓存（进程内 + 磁盘），返回写入的封装对象."""
    cached: dict[str, Any] = {"fetched_at": time.time(), "data": data}
    _CACHES[_cache_key(hass, key)] = cached
    await get_store(hass, key).async_save(cached)
    return cached

async def async_clear(hass: HomeAssistant, key: str) -> None:
    """清空缓存（进程内 + 磁盘）."""
    cache_key = _cache_key(hass, key)
    _CACHES.pop(cache_key, None)
    await get_store(hass, key).async_remove()