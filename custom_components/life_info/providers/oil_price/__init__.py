"""油价 私有服务包."""
from __future__ import annotations

from .const import (
    CONF_API_KEY,
    CONF_NAME,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    PROVINCES,
    SERVICE_ID,
    SERVICE_NAME,
)
from .coordinator import OilPriceCoordinator
from .flow import FLOW_ENTRY_STEP, OilPriceFlowMixin
from .options import OilPriceOptionsFlow
from .sensor import SENSOR_DESCRIPTIONS

__all__ = [
    "SERVICE_ID",
    "SERVICE_NAME",
    "CONF_API_KEY",
    "CONF_NAME",
    "CONF_REGION",
    "CONF_SCAN_INTERVAL",
    "DEFAULT_SCAN_INTERVAL",
    "PROVINCES",
    "OilPriceCoordinator",
    "SENSOR_DESCRIPTIONS",
    "OilPriceFlowMixin",
    "FLOW_ENTRY_STEP",
    "OilPriceOptionsFlow",
]