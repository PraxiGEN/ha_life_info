"""生活信息 传感器平台：按账户×描述器展开实体."""
from __future__ import annotations

from typing import Any
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .base import LifeInfoConfigEntry, LifeInfoSensorEntityDescription
from .coordinator import LifeInfoCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    entry: LifeInfoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """按协调器账户清单×私有包描述器建实体."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    async_add_entities(
        LifeInfoSensor(coordinator, description, account)
        for account in coordinator.accounts
        for description in runtime.sensor_descriptions
    )

class LifeInfoSensor(CoordinatorEntity[LifeInfoCoordinator], SensorEntity):
    """公用传感器实体：取值逻辑由描述器注入，账户数据按 key 索引."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LifeInfoCoordinator,
        description: LifeInfoSensorEntityDescription,
        account: dict[str, Any],
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._account_key = coordinator.account_key(account)
        self._attr_unique_id = (
            f"{coordinator.service_id}_{self._account_key}_{description.key}"
        )
        self._attr_device_info = coordinator.device_info_for(account)

    def _account_data(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get(self._account_key)

    @property
    def native_value(self) -> Any:
        """从本账户读数取值."""
        data = self._account_data()
        return self.entity_description.value_fn(data) if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """附加属性由描述器注入；账户数据带 _cache_at 时补缓存时间."""
        data = self._account_data()
        if not data:
            return None
        attrs = (
            dict(self.entity_description.attr_fn(data))
            if self.entity_description.attr_fn
            else {}
        )
        if cache_at := data.get("_cache_at"):
            attrs["cache_at"] = cache_at
        return attrs or None