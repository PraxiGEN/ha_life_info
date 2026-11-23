"""生活信息 协调器基类：一条目多账户，机制在基类，取数由私有包实现."""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_ACCOUNTS, CONF_SERVICE, DOMAIN, LOGGER

class LifeInfoCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """协调器基类：data 以账户 key 索引，每账户一台设备."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        *,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            config_entry=entry,
            update_interval=update_interval,
        )
        self.entry = entry

    @property
    def service_id(self) -> str:
        """服务标识：条目级唯一 ID，也是实体 unique_id 前缀."""
        return str(self.entry.data[CONF_SERVICE])

    @property
    def accounts(self) -> list[dict[str, Any]]:
        """账户清单：options 可变层，增删账户后重载生效."""
        return list(self.entry.options.get(CONF_ACCOUNTS, []))

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """刷新入口：异常翻译由私有 _fetch 完成，基类只透传."""
        return await self._fetch()

    async def _fetch(self) -> dict[str, dict[str, Any]]:
        """取数：私有包实现，返回按账户 key 索引的规范化读数."""
        raise NotImplementedError

    def account_key(self, account: dict[str, Any]) -> str:
        """账户 key：私有包实现（燃气为用户号）."""
        raise NotImplementedError

    def device_info_for(self, account: dict[str, Any]) -> DeviceInfo:
        """设备信息：私有包实现，每账户一台."""
        raise NotImplementedError