"""每日内容 传感器声明."""
from __future__ import annotations

from typing import Any

from ...base import LifeInfoSensorEntityDescription

_MAX_STATE = 255

def _section(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    return value if isinstance(value, dict) else {}

def _state(text: Any) -> str | None:
    """HA 状态上限 255：超长截断，完整文本转属性."""
    value = str(text or "").strip()
    return value[:_MAX_STATE] or None

def _text_value(key: str):
    def build(data: dict[str, Any]) -> str | None:
        return _state(_section(data, key).get("text"))

    return build

def _text_attrs(key: str):
    def build(data: dict[str, Any]) -> dict[str, Any]:
        item = _section(data, key)
        attrs = {
            "出处": item.get("from"),
            "作者": item.get("author"),
            "分类": item.get("category"),
            "来源": item.get("source"),
        }
        if len(str(item.get("text") or "")) > _MAX_STATE:
            attrs["完整内容"] = item.get("text")
        return {name: value for name, value in attrs.items() if value is not None}

    return build

def _history_value(data: dict[str, Any]) -> str | None:
    """历史实体状态取首条，完整列表放属性."""
    items = _section(data, "history").get("items") or []
    return _state(items[0]) if items else None

def _history_attrs(data: dict[str, Any]) -> dict[str, Any]:
    item = _section(data, "history")
    attrs = {"events": item.get("items") or [], "来源": item.get("source")}
    return {name: value for name, value in attrs.items() if value}

SENSOR_DESCRIPTIONS: tuple[LifeInfoSensorEntityDescription, ...] = (
    LifeInfoSensorEntityDescription(
        key="daily_content_hitokoto",
        translation_key="daily_content_hitokoto",
        icon="mdi:format-quote-close",
        value_fn=_text_value("hitokoto"),
        attr_fn=_text_attrs("hitokoto"),
    ),
    LifeInfoSensorEntityDescription(
        key="daily_content_poetry",
        translation_key="daily_content_poetry",
        icon="mdi:book-open-variant",
        value_fn=_text_value("poetry"),
        attr_fn=_text_attrs("poetry"),
    ),
    LifeInfoSensorEntityDescription(
        key="daily_content_soul_soup",
        translation_key="daily_content_soul_soup",
        icon="mdi:emoticon",
        value_fn=_text_value("soul_soup"),
        attr_fn=_text_attrs("soul_soup"),
    ),
    LifeInfoSensorEntityDescription(
        key="daily_content_history",
        translation_key="daily_content_history",
        icon="mdi:calendar-clock",
        value_fn=_history_value,
        attr_fn=_history_attrs,
    ),
)
