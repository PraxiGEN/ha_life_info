"""油价 私有服务常量."""
from __future__ import annotations

SERVICE_ID = "oil_price"
SERVICE_NAME = "油价信息"

CONF_NAME = "name"
CONF_REGION = "region"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_API_KEY = "api_key"

# xxapi：一次返回全国 31 省价格，无 key，QPS50（主数据源）
XXAPI_URL = "https://v2.xxapi.cn/api/oilPrice"
# ApiZero：调价时间/预测，全国一致，全局一次 + 24h 缓存（匿名 5 次/日）
APIZERO_URL = "https://v1.apizero.cn/api/oil-price"
APIZERO_PROBE = "北京"
APIZERO_CACHE_KEY = "life_info_oil_price_adjust"
APIZERO_CACHE_TTL_HOURS = 24
# huangjinjiage：只取消息文本做属性，不做独立实体
WEB_URL = "http://www.huangjinjiage.cn/oil/{region}.html"

DEFAULT_REGION = "beijing"
DEFAULT_SCAN_INTERVAL = 12
SCAN_INTERVAL_OPTIONS: tuple[int, ...] = (6, 12, 24)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# 省份 slug -> 显示名（网页 URL 用 slug，xxapi 返回中文名按核心名匹配）
PROVINCES: dict[str, str] = {
    "anhui": "安徽",
    "beijing": "北京",
    "chongqing": "重庆",
    "fujian": "福建",
    "gansu": "甘肃",
    "guangdong": "广东",
    "guangxi": "广西",
    "guizhou": "贵州",
    "hainan": "海南",
    "hebei": "河北",
    "heilongjiang": "黑龙江",
    "henan": "河南",
    "hubei": "湖北",
    "hunan": "湖南",
    "jiangsu": "江苏",
    "jiangxi": "江西",
    "jilin": "吉林",
    "liaoning": "辽宁",
    "neimenggu": "内蒙古",
    "ningxia": "宁夏",
    "qinghai": "青海",
    "shandong": "山东",
    "shanghai": "上海",
    "shanxi": "山西",
    "shanxisheng": "陕西",
    "sichuan": "四川",
    "tianjin": "天津",
    "xinjiang": "新疆",
    "xizang": "西藏",
    "yunnan": "云南",
    "zhejiang": "浙江",
}

_SUFFIXES = (
    "维吾尔自治区",
    "壮族自治区",
    "回族自治区",
    "特别行政区",
    "自治区",
    "省",
    "市",
)

def _core(name: str) -> str:
    """去掉行政后缀，取核心省名."""
    text = str(name or "").strip()
    for suffix in _SUFFIXES:
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text

_CORE_TO_SLUG = {_core(name): slug for slug, name in PROVINCES.items()}

def region_slug(name: str) -> str | None:
    """把 xxapi 中文省名归一化为 slug."""
    return _CORE_TO_SLUG.get(_core(name))

REGION_SELECTOR_OPTIONS = [
    {"value": slug, "label": name} for slug, name in PROVINCES.items()
]