"""每日内容 二级配置流."""
from __future__ import annotations

from typing import Any
import probatio as vol

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ...api import LifeInfoError
from ...const import CONF_ACCOUNTS, CONF_SERVICE
from .api import async_fetch_xxapi_hitokoto
from .const import (
    ACCOUNT_KEY,
    CONF_ACCOUNT_KEY,
    CONF_API_KEY,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    SERVICE_ID,
    SERVICE_NAME,
)

FLOW_ENTRY_STEP = "daily_content"

async def _validate_xxapi(hass) -> bool:
    """连通性预检：xxapi 为主源且免密，取一条一言即可."""
    try:
        await async_fetch_xxapi_hitokoto(async_get_clientsession(hass))
    except (LifeInfoError, TimeoutError, OSError):
        return False
    return True

class DailyContentFlowMixin:
    """每日内容专属步骤；方法名即 step_id，由主 flow 继承后路由."""

    async def async_step_daily_content(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """二级界面：接入名称与 ApiZero KEY 均可选，预检通过即建条目."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input.get(CONF_NAME) or "").strip()
            api_key = str(user_input.get(CONF_API_KEY) or "").strip()
            if not await _validate_xxapi(self.hass):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(SERVICE_ID)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=SERVICE_NAME,
                    data={CONF_SERVICE: SERVICE_ID},
                    options={
                        CONF_ACCOUNTS: [{
                            CONF_ACCOUNT_KEY: ACCOUNT_KEY,
                            CONF_NAME: name or SERVICE_NAME,
                        }],
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        CONF_API_KEY: api_key,
                    },
                )

        defaults = user_input or {}
        return self.async_show_form(
            step_id=FLOW_ENTRY_STEP,
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_NAME, default=defaults.get(CONF_NAME, "")
                ): str,
                vol.Optional(
                    CONF_API_KEY, default=defaults.get(CONF_API_KEY, "")
                ): str,
            }),
            errors=errors,
        )
