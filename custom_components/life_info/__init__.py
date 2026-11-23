"""生活信息 集成入口."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .base import LifeInfoConfigEntry, LifeInfoRuntimeData
from .const import CONF_SERVICE, DOMAIN, PLATFORMS
from .providers import get_provider

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """仅 UI 配置，YAML 无配置项."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: LifeInfoConfigEntry) -> bool:
    """按条目 service 建私有协调器，首刷后转发实体平台."""
    coordinator_cls, sensor_descriptions = get_provider(entry.data[CONF_SERVICE])
    coordinator = coordinator_cls(hass, entry)
    entry.runtime_data = LifeInfoRuntimeData(coordinator, sensor_descriptions)

    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: LifeInfoConfigEntry) -> bool:
    """卸载条目平台."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)