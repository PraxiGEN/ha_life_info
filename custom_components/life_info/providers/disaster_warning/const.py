"""灾害预警 私有服务常量."""
from __future__ import annotations

SERVICE_ID = "disaster_warning"
SERVICE_NAME = "灾害预警"

CONF_NAME = "name"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SCOPE = "scope"
CONF_ACCOUNT_KEY = "key"
ACCOUNT_KEY = "disaster"

DEFAULT_SCAN_INTERVAL = 5
SCAN_INTERVAL_OPTIONS: tuple[int, ...] = (5, 15, 30, 60)
CACHE_TTL_SECONDS = 3600
CACHE_KEY = "life_info_disaster_warning_latest"

CAPQUAKE_BASE = "https://api.capquake.top/v1"
CAPQUAKE_WS = "wss://api.capquake.top/v1/all?raw=1"

CATEGORY_WARNING = "地震预警"
CATEGORY_REPORT = "地震情报"
CATEGORY_TSUNAMI = "海啸预警"
CATEGORIES: tuple[str, ...] = (CATEGORY_WARNING, CATEGORY_REPORT, CATEGORY_TSUNAMI)

SCOPE_GROUPS: dict[str, tuple[str, ...]] = {
    CATEGORY_WARNING: (
        "cea",
        "cea_pr",
        "cwa_eew",
        "kma_eew",
        "jma_eew",
        "agg_early_est",
        "agg_usgs_shakealert",
        "sasmex_warning",
        "sasmex_city",
    ),
    CATEGORY_REPORT: (
        "cenc",
        "jma_report",
        "cwa_report",
        "usgs",
        "emsc",
        "gfz",
        "sasmex_report",
        "bmkg",
        "bmkg/intensity",
        "geonet",
        "geonet/dyfi",
        "geonet/intensity",
        "usp",
        "funvisis",
        "tmd",
        "phivolcs",
        "palert_eq",
    ),
    CATEGORY_TSUNAMI: (
        "jma_tsunami",
        "nmefc_tsunami",
        "noaa_tsunami",
        "gdacs_tsunami",
        "gdacs_tsunami_obs",
    ),
}

SCOPES: tuple[str, ...] = tuple(
    scope for scopes in SCOPE_GROUPS.values() for scope in scopes
)

SCOPE_TO_CATEGORY: dict[str, str] = {
    scope: category
    for category, scopes in SCOPE_GROUPS.items()
    for scope in scopes
}

SCOPE_ALIASES: dict[str, str] = {
    "bmkg_intensity": "bmkg/intensity",
    "geonet_dyfi": "geonet/dyfi",
    "geonet_intensity": "geonet/intensity",
}
_SCOPE_TO_ALIAS = {scope: alias for alias, scope in SCOPE_ALIASES.items()}

def scope_alias(scope: str) -> str:
    """斜杠 scope 转合法 slug，作选择器 value 与翻译键."""
    return _SCOPE_TO_ALIAS.get(scope, scope)

def scope_from_alias(alias: str) -> str:
    """选择器提交值还原为真实 scope."""
    return SCOPE_ALIASES.get(alias, alias)

SCOPE_SELECTOR_OPTIONS: tuple[str, ...] = tuple(scope_alias(s) for s in SCOPES)

CONF_REGION = "region"
REGION_ALL = "all"

REGION_GROUPS: dict[str, tuple[str, ...]] = {
    REGION_ALL: SCOPES,
    "cn": ("cea", "cea_pr", "cenc", "nmefc_tsunami"),
    "jp": ("jma_eew", "jma_report", "jma_tsunami"),
    "ea": (
        "cea",
        "cea_pr",
        "cenc",
        "nmefc_tsunami",
        "jma_eew",
        "jma_report",
        "jma_tsunami",
        "kma_eew",
        "cwa_eew",
        "cwa_report",
    ),
    "sea": ("bmkg", "bmkg/intensity", "phivolcs", "tmd", "palert_eq"),
    "amer": (
        "usgs",
        "sasmex_warning",
        "sasmex_city",
        "sasmex_report",
        "usp",
        "funvisis",
    ),
    "oce": ("geonet", "geonet/dyfi", "geonet/intensity"),
    "global": (
        "emsc",
        "gfz",
        "agg_early_est",
        "agg_usgs_shakealert",
        "noaa_tsunami",
        "gdacs_tsunami",
        "gdacs_tsunami_obs",
    ),
    "tsunami": (
        "jma_tsunami",
        "nmefc_tsunami",
        "noaa_tsunami",
        "gdacs_tsunami",
        "gdacs_tsunami_obs",
    ),
}

REGION_LABELS: dict[str, str] = {
    REGION_ALL: "全部",
    "cn": "中国",
    "jp": "日本",
    "ea": "东亚",
    "sea": "东南亚·南亚",
    "amer": "美洲",
    "oce": "大洋洲",
    "global": "欧洲·全球",
    "tsunami": "海啸监测",
}

REGION_SELECTOR_OPTIONS: list[dict[str, str]] = [
    {"value": region, "label": label} for region, label in REGION_LABELS.items()
]

def resolve_scopes(options: dict[str, object]) -> tuple[str, ...]:
    """细选优先；未配置细选时按区域预设展开，区域缺省视为全部."""
    selected = {
        str(scope)
        for scope in options.get(CONF_SCOPE) or []
        if scope in SCOPE_TO_CATEGORY
    }
    if not selected:
        regions = options.get(CONF_REGION) or [REGION_ALL]
        for region in regions:
            selected.update(REGION_GROUPS.get(str(region), ()))
    return tuple(scope for scope in SCOPES if scope in selected)