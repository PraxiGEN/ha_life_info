"""灾害预警 传感器声明：三类各一条最新状态."""
from __future__ import annotations

from typing import Any, Callable

from ...base import LifeInfoSensorEntityDescription
from .api import record_attributes
from .const import CATEGORY_REPORT, CATEGORY_TSUNAMI, CATEGORY_WARNING

_MAX_STATE = 255

def _quake_text(record: dict[str, Any]) -> str | None:
    magnitude = record.get("magnitude")
    location = str(record.get("location") or "")
    text = f"M{magnitude} {location}".strip() if magnitude is not None else location
    return text[:_MAX_STATE].strip() or None

def _tsunami_text(record: dict[str, Any]) -> str | None:
    """海啸：等级已带「级/報」后缀则不重复加级."""
    level = record.get("level")
    location = str(record.get("location") or "")
    if level in (None, ""):
        text = location
    elif str(level).endswith(("级", "報", "报")):
        text = f"{level} {location}".strip()
    else:
        text = f"{level}级 {location}".strip()
    return text[:_MAX_STATE].strip() or None

def _value(category: str, formatter: Callable[[dict[str, Any]], str | None]):
    def build(data: dict[str, Any]) -> str | None:
        record = data.get(category)
        return formatter(record) if isinstance(record, dict) else None

    return build

def _attributes(category: str):
    def build(data: dict[str, Any]) -> dict[str, Any]:
        record = data.get(category)
        return record_attributes(record) if isinstance(record, dict) else {}

    return build

SENSOR_DESCRIPTIONS: tuple[LifeInfoSensorEntityDescription, ...] = (
    LifeInfoSensorEntityDescription(
        key="earthquake_warning",
        translation_key="quake_warning",
        icon="mdi:alert",
        value_fn=_value(CATEGORY_WARNING, _quake_text),
        attr_fn=_attributes(CATEGORY_WARNING),
    ),
    LifeInfoSensorEntityDescription(
        key="earthquake_report",
        translation_key="quake_report",
        icon="mdi:information-outline",
        value_fn=_value(CATEGORY_REPORT, _quake_text),
        attr_fn=_attributes(CATEGORY_REPORT),
    ),
    LifeInfoSensorEntityDescription(
        key="tsunami_warning",
        translation_key="tsunami_warning",
        icon="mdi:waves",
        value_fn=_value(CATEGORY_TSUNAMI, _tsunami_text),
        attr_fn=_attributes(CATEGORY_TSUNAMI),
    ),
)
