"""生活信息 私有服务包目录：框架只认这里，不认具体服务."""
from __future__ import annotations

from homeassistant.config_entries import OptionsFlowWithReload

from ..base import LifeInfoSensorEntityDescription
from ..coordinator import LifeInfoCoordinator
from . import daily_content, disaster_warning, kunlun_gas, oil_price
from .spec import ProviderSpec

# 新增服务：写私有包 + 在此追加一条 SPEC，其余索引自动派生.
SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec(
        service_id=kunlun_gas.SERVICE_ID,
        name=kunlun_gas.SERVICE_NAME,
        coordinator=kunlun_gas.KunlunGasCoordinator,
        sensor_descriptions=kunlun_gas.SENSOR_DESCRIPTIONS,
        flow_entry_step=kunlun_gas.FLOW_ENTRY_STEP,
        flow_mixin=kunlun_gas.KunlunGasFlowMixin,
        options_flow=kunlun_gas.KunlunGasOptionsFlow,
    ),
    ProviderSpec(
        service_id=oil_price.SERVICE_ID,
        name=oil_price.SERVICE_NAME,
        coordinator=oil_price.OilPriceCoordinator,
        sensor_descriptions=oil_price.SENSOR_DESCRIPTIONS,
        flow_entry_step=oil_price.FLOW_ENTRY_STEP,
        flow_mixin=oil_price.OilPriceFlowMixin,
        options_flow=oil_price.OilPriceOptionsFlow,
    ),
    ProviderSpec(
        service_id=daily_content.SERVICE_ID,
        name=daily_content.SERVICE_NAME,
        coordinator=daily_content.DailyContentCoordinator,
        sensor_descriptions=daily_content.SENSOR_DESCRIPTIONS,
        flow_entry_step=daily_content.FLOW_ENTRY_STEP,
        flow_mixin=daily_content.DailyContentFlowMixin,
        options_flow=daily_content.DailyContentOptionsFlow,
    ),
    ProviderSpec(
        service_id=disaster_warning.SERVICE_ID,
        name=disaster_warning.SERVICE_NAME,
        coordinator=disaster_warning.DisasterWarningCoordinator,
        sensor_descriptions=disaster_warning.SENSOR_DESCRIPTIONS,
        flow_entry_step=disaster_warning.FLOW_ENTRY_STEP,
        flow_mixin=disaster_warning.DisasterWarningFlowMixin,
        options_flow=disaster_warning.DisasterWarningOptionsFlow,
    ),
)

_PROVIDERS: dict[
    str,
    tuple[type[LifeInfoCoordinator], tuple[LifeInfoSensorEntityDescription, ...]],
] = {
    spec.service_id: (spec.coordinator, spec.sensor_descriptions) for spec in SPECS
}

# 配置流消费：一级服务清单 / 各服务入口 step / 待注入的 mixin / 选项流程.
SERVICE_NAMES: dict[str, str] = {spec.service_id: spec.name for spec in SPECS}
FLOW_ENTRY_STEPS: dict[str, str] = {
    spec.service_id: spec.flow_entry_step for spec in SPECS
}
FLOW_MIXINS: tuple[type, ...] = tuple(spec.flow_mixin for spec in SPECS)
OPTIONS_FLOWS: dict[str, type[OptionsFlowWithReload]] = {
    spec.service_id: spec.options_flow for spec in SPECS
}

def get_provider(
    service_id: str,
) -> tuple[type[LifeInfoCoordinator], tuple[LifeInfoSensorEntityDescription, ...]]:
    """取服务实现：协调器类 + 实体描述器清单."""
    return _PROVIDERS[service_id]