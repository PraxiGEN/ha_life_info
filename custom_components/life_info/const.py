"""生活信息 常量平台."""
from __future__ import annotations

import logging
from typing import Final
from homeassistant.const import Platform

DOMAIN: Final = "life_info"
LOGGER = logging.getLogger(__name__)
PLATFORMS: Final = [Platform.SENSOR]

CONF_SERVICE: Final = "service"
CONF_NAME: Final = "name"
CONF_ACCOUNTS: Final = "accounts"
CONF_SCAN_INTERVAL: Final = "scan_interval"