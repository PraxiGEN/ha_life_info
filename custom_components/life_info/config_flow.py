"""生活信息 配置流：一级选服务，二级步骤由私有包 mixin 注入."""
from __future__ import annotations

from typing import Any
import probatio as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import CONF_SERVICE, DOMAIN
from .providers import FLOW_ENTRY_STEPS, FLOW_MIXINS, OPTIONS_FLOWS, SERVICE_NAMES

class LifeInfoConfigFlow(*FLOW_MIXINS, ConfigFlow, domain=DOMAIN):
    """入口：选服务后路由到该服务在私有包中定义的首个 step."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowWithReload:
        """按条目服务路由到私有包定义的选项流程."""
        return OPTIONS_FLOWS[config_entry.data[CONF_SERVICE]]()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """一级界面：选择要添加的服务（服务级唯一，已配置则直接拒绝）."""
        if user_input is not None:
            service_id = user_input[CONF_SERVICE]
            await self.async_set_unique_id(service_id)
            self._abort_if_unique_id_configured()
            entry_step = FLOW_ENTRY_STEPS[service_id]
            return await getattr(self, f"async_step_{entry_step}")()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_SERVICE): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(value=sid, label=name)
                            for sid, name in SERVICE_NAMES.items()
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                        translation_key="service",
                    )
                ),
            }),
        )