"""每日内容 私有服务常量."""
from __future__ import annotations

from typing import Final

SERVICE_ID = "daily_content"
SERVICE_NAME = "每日内容"

CONF_NAME = "name"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_API_KEY = "api_key"
CONF_ACCOUNT_KEY = "key"
ACCOUNT_KEY = "daily"

DEFAULT_SCAN_INTERVAL = 10
MIN_SCAN_INTERVAL = 10
SCAN_INTERVAL_OPTIONS: tuple[int, ...] = (10, 20, 30, 60, 120, 240)

# 有 KEY 时按 ApiZero 日额度限频；诗词/毒鸡汤额度 20 次/日
TTL_HITOKOTO: Final = 600
TTL_POETRY: Final = 3600
TTL_SOUL_SOUP: Final = 3600

QUIET_START_HOUR: Final = 0
QUIET_END_HOUR: Final = 5

CACHE_KEY_PREFIX: Final = "life_info.daily_content_"
CACHE_TTL_HOURS: Final = 24

XXAPI_BASE = "https://v2.xxapi.cn/api"
APIZERO_BASE = "https://v1.apizero.cn/api"
HITOKOTO_OFFICIAL = "https://v1.hitokoto.cn/"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)