"""生活信息 公共契约：实体描述器与条目运行时数据."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from .coordinator import LifeInfoCoordinator

@dataclass(frozen=True, kw_only=True)
class LifeInfoSensorEntityDescription(SensorEntityDescription):
    """传感器描述器：value_fn 取值，attr_fn 补属性."""
    value_fn: Callable[[dict[str, Any]], Any]
    attr_fn: Callable[[dict[str, Any]], dict[str, Any]] | None = None

@dataclass
class LifeInfoRuntimeData:
    """条目运行时数据：每条目一个协调器 + 私有包声明的实体描述."""
    coordinator: LifeInfoCoordinator
    sensor_descriptions: tuple[LifeInfoSensorEntityDescription, ...]

type LifeInfoConfigEntry = ConfigEntry[LifeInfoRuntimeData]