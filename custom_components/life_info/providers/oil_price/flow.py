"""油价 二级配置配置流."""
from __future__ import annotations

from typing import Any
import probatio as vol

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from ...api import LifeInfoError
from ...const import CONF_ACCOUNTS, CONF_SERVICE
from .api import async_fetch_prices
from .const import (
    CONF_API_KEY,
    CONF_NAME,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    PROVINCES,
    REGION_SELECTOR_OPTIONS,
    SERVICE_ID,
    SERVICE_NAME,
)

FLOW_ENTRY_STEP = "oil_price"

async def _validate_region(hass, slug: str) -> bool:
    """校验省份有价格：xxapi 一次取全国，按 slug 命中即可."""
    if slug not in PROVINCES:
        return False
    try:
        prices = await async_fetch_prices(async_get_clientsession(hass))
    except (LifeInfoError, TimeoutError, OSError):
        return False
    return slug in prices

class OilPriceFlowMixin:
    """油价专属步骤；方法名即 step_id，由主 flow 继承后路由."""

    async def async_step_oil_price(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """二级界面：接入名称/KEY（可选）+ 省份，校验后建条目."""
        errors: dict[str, str] = {}
        if user_input is not None:
            slug = str(user_input.get(CONF_REGION) or "").strip()
            name = str(user_input.get(CONF_NAME) or "").strip()
            api_key = str(user_input.get(CONF_API_KEY) or "").strip()
            if not await _validate_region(self.hass, slug):
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(SERVICE_ID)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=SERVICE_NAME,
                    data={CONF_SERVICE: SERVICE_ID},
                    options={
                        CONF_ACCOUNTS: [{
                            CONF_NAME: name or PROVINCES[slug],
                            CONF_REGION: slug,
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
                vol.Required(
                    CONF_REGION,
                    default=defaults.get(CONF_REGION, DEFAULT_REGION),
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=o["value"], label=o["label"])
                            for o in REGION_SELECTOR_OPTIONS
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
            errors=errors,
        )