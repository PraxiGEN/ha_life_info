"""每日内容 条目选项."""
from __future__ import annotations

from typing import Any
import probatio as vol

from homeassistant.config_entries import ConfigFlowResult

from ...options import LifeInfoOptionsFlow
from .const import (
    ACCOUNT_KEY,
    CONF_ACCOUNT_KEY,
    CONF_API_KEY,
    CONF_NAME,
    DEFAULT_SCAN_INTERVAL,
    SCAN_INTERVAL_OPTIONS,
    SERVICE_NAME,
)

class DailyContentOptionsFlow(LifeInfoOptionsFlow):
    """每日内容选项：仅 KEY 与轮询间隔，伪账户不可增删."""

    MENU_OPTIONS = ("api_key",)
    INTERVAL_OPTIONS = SCAN_INTERVAL_OPTIONS
    DEFAULT_INTERVAL = DEFAULT_SCAN_INTERVAL
    SCAN_INTERVAL_LABEL = "分钟"
    ACCOUNT_KEY = CONF_ACCOUNT_KEY

    async def async_step_api_key(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """设置 ApiZero KEY（可选）：空则回落匿名额度."""
        if user_input is not None:
            data = dict(self.config_entry.options)
            data[CONF_API_KEY] = str(user_input.get(CONF_API_KEY) or "").strip()
            return self.async_create_entry(data=data)

        return self.async_show_form(
            step_id="api_key",
            data_schema=vol.Schema({
                vol.Optional(
                    CONF_API_KEY,
                    description={
                        "suggested_value": self.config_entry.options.get(CONF_API_KEY, "")
                    },
                ): str,
            }),
        )

    def _edit_schema(self, account: dict[str, Any]) -> vol.Schema:
        """编辑表单：仅接入名（伪账户 key 锁定）."""
        return vol.Schema({
            vol.Optional(CONF_NAME, default=account.get(CONF_NAME, "")): str,
        })

    async def _async_validate_edit(
        self, user_input: dict[str, Any], account: dict[str, Any]
    ) -> dict[str, str]:
        """每日内容编辑无外部校验，key 不变."""
        return {}

    def _build_updated(
        self, user_input: dict[str, Any], account: dict[str, Any]
    ) -> dict[str, Any]:
        """合并：key 固定，接入名为空回落服务名."""
        return {
            CONF_ACCOUNT_KEY: ACCOUNT_KEY,
            CONF_NAME: str(user_input.get(CONF_NAME) or "").strip()
                or SERVICE_NAME,
        }