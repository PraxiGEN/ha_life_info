"""服务注册契约：私有包导出一个 SPEC，框架派生全部索引."""
from __future__ import annotations

from dataclasses import dataclass
from homeassistant.config_entries import OptionsFlowWithReload

from ..base import LifeInfoSensorEntityDescription
from ..coordinator import LifeInfoCoordinator

@dataclass(frozen=True, kw_only=True)
class ProviderSpec:
    """单个服务的完整声明；新增服务只需写私有包并加入 SPECS."""

    service_id: str
    name: str
    coordinator: type[LifeInfoCoordinator]
    sensor_descriptions: tuple[LifeInfoSensorEntityDescription, ...]
    flow_entry_step: str
    flow_mixin: type
    options_flow: type[OptionsFlowWithReload]