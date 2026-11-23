"""昆仑燃气 传感器声明."""
from __future__ import annotations

from typing import Any
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

from ...base import LifeInfoSensorEntityDescription

_MONEY = dict(
    native_unit_of_measurement="CNY",
    device_class=SensorDeviceClass.MONETARY,
    suggested_display_precision=2,
)

def _f(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def _v(key: str, default: Any = None):
    return lambda d: (d.get("balance") or {}).get(key, default)

def _user_attrs(d: dict[str, Any]) -> dict[str, Any]:
    u = d.get("user") or {}
    b = d.get("balance") or {}
    return {
        "户号": u.get("customerCode"),
        "户名": u.get("name"),
        "地址": u.get("address"),
        "绑定手机号": u.get("phone"),
        "账户编号": u.get("accountId"),
        "表类型": u.get("meterType_dictText") or b.get("meterTypeDesc"),
        "地区代码": u.get("mdmCode"),
        "可缴费": b.get("payPermitted"),
    }

def _fee_attrs(d: dict[str, Any]) -> dict[str, Any]:
    b = d.get("balance") or {}
    return {k: b.get(k) for k in (
        "beginBalance", "endBalance", "gasVolume", "averagePrice", "gasFee",
        "overdue", "oweAmount", "respDesc", "payPermitted",
        "remoteMeterLastCommunicationTime", "isRemoteTransmit",
    ) if b.get(k) is not None}

SENSOR_DESCRIPTIONS: tuple[LifeInfoSensorEntityDescription, ...] = (
    LifeInfoSensorEntityDescription(
        key="kunlun_gas_remote_meter_balance", translation_key="kunlun_gas_remote_meter_balance", icon="mdi:cash",
        **_MONEY,
        value_fn=lambda d: _f(_v("remoteMeterBalance")(d)), attr_fn=_user_attrs,
    ),
    LifeInfoSensorEntityDescription(
        key="kunlun_gas_owe_amount", translation_key="kunlun_gas_owe_amount", icon="mdi:alert-circle-outline",
        **_MONEY,
        value_fn=lambda d: _f(_v("oweAmount")(d)),
    ),
    LifeInfoSensorEntityDescription(
        key="kunlun_gas_account_balance", translation_key="kunlun_gas_account_balance", icon="mdi:wallet-outline",
        **_MONEY,
        value_fn=lambda d: _f(_v("endBalance")(d)),
    ),
    LifeInfoSensorEntityDescription(
        key="kunlun_gas_meter_reading", translation_key="kunlun_gas_meter_reading", icon="mdi:meter-gas",
        native_unit_of_measurement="m³", state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda d: _f(_v("readingLastTime")(d)),
    ),
    LifeInfoSensorEntityDescription(
        key="kunlun_gas_last_communication", translation_key="kunlun_gas_last_communication", icon="mdi:clock-outline",
        value_fn=lambda d: _v("remoteMeterLastCommunicationTime")(d),
    ),
    LifeInfoSensorEntityDescription(
        key="kunlun_gas_latest_gas_fee", translation_key="kunlun_gas_latest_gas_fee", icon="mdi:receipt-text-outline",
        **_MONEY,
        value_fn=lambda d: _f(_v("gasFee")(d)), attr_fn=_fee_attrs,
    ),
    LifeInfoSensorEntityDescription(
        key="kunlun_gas_pay_permitted", translation_key="kunlun_gas_pay_permitted", icon="mdi:check-decagram",
        value_fn=lambda d: _v("payPermitted")(d),
    ),
)