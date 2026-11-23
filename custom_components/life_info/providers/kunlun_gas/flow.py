"""昆仑燃气 二级配置界面配置流."""
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

from ...api import LifeInfoRequestError
from ...const import CONF_ACCOUNTS, CONF_SERVICE
from .api import async_fetch_balance
from .const import (
    CONF_MDM_CODE,
    CONF_NAME,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_USER_CODE,
    DEFAULT_SCAN_INTERVAL,
    SERVICE_ID,
    SERVICE_NAME,
)
from .regions import REGIONS

FLOW_ENTRY_STEP = "kunlun_gas"

class KunlunGasFlowMixin:
    """昆仑燃气专属步骤；方法名即 step_id，由主 flow 继承后可直接路由."""

    async def async_step_kunlun_gas(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """二级界面：接入名称 + 户号 + 地区，同页提交校验."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input.get(CONF_NAME) or "").strip()
            mdm = str(user_input.get(CONF_REGION) or "").split("|", 1)[0].strip()
            code = str(user_input.get(CONF_USER_CODE) or "").strip()
            if not mdm:
                errors["base"] = "invalid_region"
            elif not code:
                errors["base"] = "invalid_user_code"
            else:
                try:
                    balance = await async_fetch_balance(
                        async_get_clientsession(self.hass), code, mdm
                    )
                except (LifeInfoRequestError, ValueError, TimeoutError, OSError):
                    errors["base"] = "cannot_connect"
                else:
                    if str(balance.get("userCode") or "") != code:
                        errors["base"] = "invalid_user_code"
                    else:
                        name = name or f"户号:{code}"
                        await self.async_set_unique_id(SERVICE_ID)
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=SERVICE_NAME,
                            data={CONF_SERVICE: SERVICE_ID},
                            options={
                                CONF_ACCOUNTS: [{
                                    CONF_NAME: name,
                                    CONF_USER_CODE: code,
                                    CONF_MDM_CODE: mdm,
                                }],
                                CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                            },
                        )

        defaults = user_input or {}
        return self.async_show_form(
            step_id=FLOW_ENTRY_STEP,
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_NAME, default=defaults.get(CONF_NAME, "")
                ): str,
                vol.Required(
                    CONF_USER_CODE, default=defaults.get(CONF_USER_CODE, "")
                ): str,
                vol.Required(
                    CONF_REGION, default=defaults.get(CONF_REGION, "")
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=r["value"], label=r["label"])
                            for r in REGIONS
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
            errors=errors,
        )