"""昆仑燃气 协调器."""
from __future__ import annotations

import asyncio
import random
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import UpdateFailed

from ... import storage
from ...api import HttpStatusError, LifeInfoRequestError
from ...const import DOMAIN, LOGGER
from ...coordinator import LifeInfoCoordinator
from .api import async_fetch_balance
from .const import (
    CACHE_TTL_HOURS,
    CONF_MDM_CODE,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_USER_CODE,
    DEFAULT_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    SERVICE_ID,
)

class KunlunGasCoordinator(LifeInfoCoordinator):
    """昆仑燃气免密协调器：一条目多户号，单接口、无令牌、无 reauth."""

    def __init__(self, hass: HomeAssistant, entry) -> None:
        interval = max(
            int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
            MIN_SCAN_INTERVAL,
        )
        super().__init__(hass, entry, update_interval=timedelta(hours=interval))
        self._session = async_get_clientsession(hass)

    def account_key(self, account: dict[str, Any]) -> str:
        """账户 key = 户号."""
        return str(account[CONF_USER_CODE])

    async def _fetch(self) -> dict[str, dict[str, Any]]:
        """并发取所有户号，按户号索引；任一失败则整次刷新失败."""
        multi = len(self.accounts) > 1
        pairs = await asyncio.gather(
            *(
                self._fetch_one(account, index if multi else -1)
                for index, account in enumerate(self.accounts)
            )
        )
        return dict(pairs)

    def _cache_key(self, code: str) -> str:
        """缓存键按户号隔离，避免多户号串味."""
        return f"{DOMAIN}.{SERVICE_ID}_{code}"

    async def _fetch_one(
        self, account: dict[str, Any], index: int = -1
    ) -> tuple[str, dict[str, Any]]:
        """单户号取数：成功落盘；失败在缓存 TTL 内沿用，过期则报错."""
        if index >= 0:
            jitter = index * 2 + random.uniform(0, 1)
            LOGGER.debug("多账号请求相位打散: 账户 %s 延迟 %.1f 秒", index, jitter)
            await asyncio.sleep(jitter)
        code = self.account_key(account)
        mdm = str(account.get(CONF_MDM_CODE) or "")
        cache_key = self._cache_key(code)
        try:
            balance = await async_fetch_balance(self._session, code, mdm)
            if str(balance.get("userCode") or "") != code:
                raise ValueError("接口未返回对应户号")
        except (LifeInfoRequestError, ValueError, TimeoutError, OSError) as err:
            cached = await storage.async_load(self.hass, cache_key)
            # HA 规范：缓存只在 TTL 内兜底短期抖动；过期仍失败须抛 UpdateFailed，
            # 让协调器标记实体不可用，避免无限期展示陈旧数据假装更新成功。
            if storage.is_fresh(cached, CACHE_TTL_HOURS * 3600):
                LOGGER.warning("%s: 取数失败，沿用缓存: %s", code, err)
                stale = dict(cached["data"])
                stale["_cache_at"] = cached.get("fetched_at")
                return code, stale
            if isinstance(err, HttpStatusError):
                raise UpdateFailed(f"{code}: HTTP {err.status}") from err
            raise UpdateFailed(f"{code}: {err}") from err
        item: dict[str, Any] = {
            "user": self._build_user(code, mdm, balance),
            "balance": balance,
        }
        await storage.async_save(self.hass, cache_key, item)
        return code, item

    def _build_user(
        self, code: str, mdm: str, balance: dict[str, Any]
    ) -> dict[str, Any]:
        """从免密响应拼出用户信息（无令牌字段）."""
        return {
            "customerCode": code,
            "name": balance.get("customerName"),
            "address": balance.get("address"),
            "phone": balance.get("phone"),
            "accountId": str(balance.get("accountId") or ""),
            "meterType_dictText": balance.get("meterTypeDesc"),
            "mdmCode": str(balance.get("mdmCode") or mdm),
        }

    def device_info_for(self, account: dict[str, Any]) -> DeviceInfo:
        """每户号一台设备：identifier 用户号，名称用接入名，型号取表类型."""
        code = self.account_key(account)
        account_data = (self.data or {}).get(code) or {}
        meter_type = (account_data.get("user") or {}).get("meterType_dictText")
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self.service_id}_{code}")},
            name=str(account.get(CONF_NAME) or f"户号:{code}"),
            serial_number=code,
            manufacturer="中国石油",
            model=meter_type,
            entry_type=DeviceEntryType.SERVICE,
        )