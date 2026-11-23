"""油价 条目选项."""
from __future__ import annotations

from typing import Any
import probatio as vol

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from ...const import CONF_ACCOUNTS
from ...options import LifeInfoOptionsFlow
from .const import (
    CONF_API_KEY,
    CONF_NAME,
    CONF_REGION,
    DEFAULT_REGION,
    DEFAULT_SCAN_INTERVAL,
    PROVINCES,
    REGION_SELECTOR_OPTIONS,
    SCAN_INTERVAL_OPTIONS,
)
from .flow import _validate_region

class OilPriceOptionsFlow(LifeInfoOptionsFlow):
    """油价选项：管理多省份与轮询间隔，共存于 entry.options."""

    MENU_OPTIONS = ("add_province", "remove_province", "api_key")
    INTERVAL_OPTIONS = SCAN_INTERVAL_OPTIONS
    DEFAULT_INTERVAL = DEFAULT_SCAN_INTERVAL
    ACCOUNT_KEY = CONF_REGION

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
                    default=self.config_entry.options.get(CONF_API_KEY, ""),
                ): str,
            }),
        )

    async def async_step_add_province(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """添加省份：接入名（可选）+ 省份，校验后追加."""
        errors: dict[str, str] = {}
        if user_input is not None:
            slug = str(user_input.get(CONF_REGION) or "").strip()
            name = str(user_input.get(CONF_NAME) or "").strip()
            if any(a.get(CONF_REGION) == slug for a in self._accounts):
                errors["base"] = "already_added"
            elif not await _validate_region(self.hass, slug):
                errors["base"] = "cannot_connect"
            else:
                accounts = [
                    *self._accounts,
                    {CONF_NAME: name or PROVINCES[slug], CONF_REGION: slug},
                ]
                return self._save(accounts, self._interval)

        return self.async_show_form(
            step_id="add_province",
            data_schema=vol.Schema({
                vol.Optional(CONF_NAME, default=""): str,
                vol.Required(CONF_REGION, default=DEFAULT_REGION): SelectSelector(
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

    async def async_step_remove_province(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """移除省份：保留至少一个."""
        errors: dict[str, str] = {}
        if user_input is not None:
            slug = str(user_input.get(CONF_REGION) or "")
            if len(self._accounts) <= 1:
                errors["base"] = "cannot_remove_last"
            else:
                return self._save(
                    [a for a in self._accounts if a.get(CONF_REGION) != slug],
                    self._interval,
                )

        return self.async_show_form(
            step_id="remove_province",
            data_schema=vol.Schema({
                vol.Required(CONF_REGION): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=a[CONF_REGION],
                                label=a.get(CONF_NAME) or a[CONF_REGION],
                            )
                            for a in self._accounts
                        ],
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
            errors=errors,
        )

    def _edit_schema(self, account: dict[str, Any]) -> vol.Schema:
        """编辑表单：仅接入名（省份锁定）."""
        return vol.Schema({
            vol.Optional(CONF_NAME, default=account.get(CONF_NAME, "")): str,
        })

    async def _async_validate_edit(
        self, user_input: dict[str, Any], account: dict[str, Any]
    ) -> dict[str, str]:
        """油价编辑无外部校验，省份不变."""
        return {}

    def _build_updated(
        self, user_input: dict[str, Any], account: dict[str, Any]
    ) -> dict[str, Any]:
        """合并：省份不变，接入名为空回落省份名."""
        slug = str(account[CONF_REGION])
        return {
            CONF_REGION: slug,
            CONF_NAME: str(user_input.get(CONF_NAME) or "").strip()
                or PROVINCES[slug],
        }