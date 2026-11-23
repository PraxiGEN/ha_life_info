"""油价 传感器声明."""
from __future__ import annotations

from typing import Any
from homeassistant.components.sensor import SensorStateClass
from ...base import LifeInfoSensorEntityDescription

_UNIT = "元/升"

def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _price(key: str):
    return lambda data: _f((data.get("prices") or {}).get(key))

def _price_attrs(key: str):
    """价格实体属性：仅本油品涨跌 + 数据日期."""

    def build(data: dict[str, Any]) -> dict[str, Any]:
        changes = data.get("changes") or {}
        attrs = {
            "数据日期": data.get("date"),
            "较上轮涨跌": changes.get(key),
        }
        return {name: value for name, value in attrs.items() if value is not None}

    return build

def _next_adjust(data: dict[str, Any]) -> str | None:
    """消息实体状态：下次调价时间文本."""
    return (data.get("adjust") or {}).get("next_adjustment")

def _message_attrs(data: dict[str, Any]) -> dict[str, Any]:
    """消息实体属性：调价预测 + 网页消息，全部集中于此."""
    adjust = data.get("adjust") or {}
    news = data.get("news") or {}
    attrs = {
        "数据日期": data.get("date"),
        "下次调价": adjust.get("next_adjustment"),
        "调价预测": adjust.get("forecast"),
        "变化率": adjust.get("change_rate"),
        "统计工作日": adjust.get("working_day"),
        "涨跌最新消息": news.get("trend_news"),
        "调整最新消息": news.get("adjust_news"),
    }
    return {name: value for name, value in attrs.items() if value is not None}

SENSOR_DESCRIPTIONS: tuple[LifeInfoSensorEntityDescription, ...] = (
    LifeInfoSensorEntityDescription(
        key="oil_price_gas92",
        translation_key="oil_price_gas92",
        icon="mdi:gas-station",
        native_unit_of_measurement=_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=_price("gas92"),
        attr_fn=_price_attrs("gas92"),
    ),
    LifeInfoSensorEntityDescription(
        key="oil_price_gas95",
        translation_key="oil_price_gas95",
        icon="mdi:gas-station",
        native_unit_of_measurement=_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=_price("gas95"),
        attr_fn=_price_attrs("gas95"),
    ),
    LifeInfoSensorEntityDescription(
        key="oil_price_gas98",
        translation_key="oil_price_gas98",
        icon="mdi:gas-station",
        native_unit_of_measurement=_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=_price("gas98"),
        attr_fn=_price_attrs("gas98"),
    ),
    LifeInfoSensorEntityDescription(
        key="oil_price_die0",
        translation_key="oil_price_die0",
        icon="mdi:gas-station",
        native_unit_of_measurement=_UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=_price("die0"),
        attr_fn=_price_attrs("die0"),
    ),
    LifeInfoSensorEntityDescription(
        key="oil_price_adjust",
        translation_key="oil_price_adjust",
        icon="mdi:newspaper-variant-outline",
        value_fn=_next_adjust,
        attr_fn=_message_attrs,
    ),
)