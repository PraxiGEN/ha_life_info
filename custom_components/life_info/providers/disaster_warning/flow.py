"""灾害预警 二级配置流."""
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
from .api import async_fetch_snapshot
from .const import (
    ACCOUNT_KEY,
    CONF_ACCOUNT_KEY,
    CONF_NAME,
    CONF_REGION,
    CONF_SCAN_INTERVAL,
    CONF_SCOPE,
    DEFAULT_SCAN_INTERVAL,
    REGION_ALL,
    REGION_GROUPS,
    REGION_SELECTOR_OPTIONS,
    SCOPE_SELECTOR_OPTIONS,
    SCOPE_TO_CATEGORY,
    SERVICE_ID,
    SERVICE_NAME,
)

FLOW_ENTRY_STEP = "disaster_warning"
FLOW_SCOPE_STEP = "disaster_warning_scope"

def _region_selector() -> SelectSelector:
    """一级：区域下拉单选."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=option["value"], label=option["label"])
                for option in REGION_SELECTOR_OPTIONS
            ],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )

def _scope_selector() -> SelectSelector:
    """二级：数据源细选，默认勾选区域展开的源."""
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=option["value"], label=option["label"])
                for option in SCOPE_SELECTOR_OPTIONS
            ],
            mode=SelectSelectorMode.DROPDOWN,
            multiple=True,
        )
    )

async def _validate_snapshot(hass) -> bool:
    """连通性预检：快照可拉即视为可用."""
    try:
        await async_fetch_snapshot(async_get_clientsession(hass))
    except (LifeInfoError, TimeoutError, OSError):
        return False
    return True

class DisasterWarningFlowMixin:
    """灾害预警专属步骤；方法名即 step_id，由主 flow 继承后路由."""

    async def async_step_disaster_warning(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """一级界面：接入名称（可选）+ 区域预设下拉."""
        errors: dict[str, str] = {}
        if user_input is not None:
            region = str(user_input.get(CONF_REGION) or REGION_ALL)
            if region not in REGION_GROUPS:
                errors["base"] = "scope_required"
            else:
                self._disaster_name = str(user_input.get(CONF_NAME) or "").strip()
                self._disaster_region = region
                return await self.async_step_disaster_warning_scope()

        defaults = user_input or {}
        region = str(defaults.get(CONF_REGION) or REGION_ALL)
        if region not in REGION_GROUPS:
            region = REGION_ALL
        return self.async_show_form(
            step_id=FLOW_ENTRY_STEP,
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_NAME, default=defaults.get(CONF_NAME, "")
                ): str,
                vol.Required(CONF_REGION, default=region): _region_selector(),
            }),
            errors=errors,
        )

    async def async_step_disaster_warning_scope(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """二级界面：关注范围细选，默认勾选所选区域的源."""
        errors: dict[str, str] = {}
        region = getattr(self, "_disaster_region", REGION_ALL)
        if user_input is not None:
            scopes = [
                str(scope)
                for scope in user_input.get(CONF_SCOPE) or []
                if scope in SCOPE_TO_CATEGORY
            ]
            if not scopes:
                errors["base"] = "scope_required"
            elif not await _validate_snapshot(self.hass):
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
                            CONF_NAME: getattr(self, "_disaster_name", "") or SERVICE_NAME,
                        }],
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
                        CONF_REGION: [region],
                        CONF_SCOPE: scopes,
                    },
                )

        defaults = user_input or {}
        current = [
            str(scope)
            for scope in defaults.get(CONF_SCOPE) or REGION_GROUPS.get(region, ())
            if scope in SCOPE_TO_CATEGORY
        ]
        return self.async_show_form(
            step_id=FLOW_SCOPE_STEP,
            data_schema=vol.Schema({
                vol.Required(CONF_SCOPE, default=current): _scope_selector(),
            }),
            errors=errors,
        )
