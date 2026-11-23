"""昆仑燃气 私有服务常量（仅免密公开接口）."""
from __future__ import annotations

SERVICE_ID = "kunlun_gas"
SERVICE_NAME = "昆仑燃气"

CONF_NAME = "name"
CONF_USER_CODE = "user_code"
CONF_MDM_CODE = "mdm_code"
CONF_REGION = "region"
CONF_SCAN_INTERVAL = "scan_interval"

BASE_URL = "https://bol.grs.petrochina.com.cn/retail"
PATH_BALANCE = "/preservice/gasFeePay/getDebt4Wsyyt"

DEFAULT_SCAN_INTERVAL = 6
MIN_SCAN_INTERVAL = 1
SCAN_INTERVAL_OPTIONS: tuple[int, ...] = (1, 3, 6, 12)
# 取数失败时缓存兜底上限：TTL 内沿用旧值，过期仍失败则抛 UpdateFailed
CACHE_TTL_HOURS = 24

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/144.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) "
    "NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF "
    "WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541f38) XWEB/25819"
)

def build_headers(mdm_code: str) -> dict[str, str]:
    """免密请求头：微信小程序 UA + Referer + mdm Cookie，无 Authorization."""
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "User-Agent": UA,
        "Referer": "https://bol.grs.petrochina.com.cn/retail/h5/",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Cookie": f"X-Mdm-Code={mdm_code}",
    }