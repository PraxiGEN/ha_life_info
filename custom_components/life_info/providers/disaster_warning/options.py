"""灾害预警 条目选项."""
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

from ...options import LifeInfoOptionsFlow
from .const import (
    ACCOUNT_KEY,
    CONF_ACCOUNT_KEY,
    CONF_NAME,
    CONF_REGION,
    CONF_SCOPE,
    DEFAULT_SCAN_INTERVAL,
    REGION_ALL,
    REGION_GROUPS,
    REGION_SELECTOR_OPTIONS,
    SCAN_INTERVAL_OPTIONS,
    SCOPE_SELECTOR_OPTIONS,
    SCOPE_TO_CATEGORY,
    SERVICE_NAME,
    scope_alias,
    scope_from_alias,
)

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
    """二级：数据源细选，标签走 selector.scope 翻译."""
    return SelectSelector(
        SelectSelectorConfig(
            options=list(SCOPE_SELECTOR_OPTIONS),
            mode=SelectSelectorMode.DROPDOWN,
            multiple=True,
            translation_key="scope",
        )
    )

class DisasterWarningOptionsFlow(LifeInfoOptionsFlow):
    """选项：区域下拉 → 关注范围细选，轮询为分钟档."""

    MENU_OPTIONS = ("scope",)
    INTERVAL_OPTIONS = SCAN_INTERVAL_OPTIONS
    DEFAULT_INTERVAL = DEFAULT_SCAN_INTERVAL
    SCAN_INTERVAL_LABEL = "分钟"
    ACCOUNT_KEY = CONF_ACCOUNT_KEY

    async def async_step_scope(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """一级：区域预设下拉，选中后进入细选."""
        errors: dict[str, str] = {}
        stored = self.config_entry.options
        stored_regions = stored.get(CONF_REGION) or [REGION_ALL]
        stored_region = str(stored_regions[0]) if stored_regions else REGION_ALL

        if user_input is not None:
            region = str(user_input.get(CONF_REGION) or REGION_ALL)
            if region in REGION_GROUPS:
                self._disaster_region = region
                return await self.async_step_scope_detail()
            errors["base"] = "scope_required"

        region = str((user_input or {}).get(CONF_REGION) or stored_region)
        if region not in REGION_GROUPS:
            region = REGION_ALL
        return self.async_show_form(
            step_id="scope",
            data_schema=vol.Schema({
                vol.Required(CONF_REGION, default=region): _region_selector(),
            }),
            errors=errors,
        )

    async def async_step_scope_detail(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """二级：关注范围细选；换区域时按新区域预勾选，同区域沿用已存细选."""
        errors: dict[str, str] = {}
        stored = self.config_entry.options
        stored_region = str((stored.get(CONF_REGION) or [REGION_ALL])[0])
        region = getattr(self, "_disaster_region", stored_region)
        if user_input is not None:
            scopes = [
                scope_from_alias(str(scope))
                for scope in user_input.get(CONF_SCOPE) or []
                if scope_from_alias(str(scope)) in SCOPE_TO_CATEGORY
            ]
            if not scopes:
                errors["base"] = "scope_required"
            else:
                data = dict(stored)
                data[CONF_REGION] = [region]
                data[CONF_SCOPE] = scopes
                return self.async_create_entry(data=data)

        if user_input is not None:
            default_scopes = [
                scope_alias(str(scope))
                for scope in user_input.get(CONF_SCOPE) or []
                if scope in SCOPE_TO_CATEGORY
            ]
        elif region == stored_region and stored.get(CONF_SCOPE):
            default_scopes = [
                scope_alias(str(scope))
                for scope in stored[CONF_SCOPE]
                if scope in SCOPE_TO_CATEGORY
            ]
        else:
            default_scopes = [
                scope_alias(scope)
                for scope in REGION_GROUPS.get(region, ())
                if scope in SCOPE_TO_CATEGORY
            ]
        return self.async_show_form(
            step_id="scope_detail",
            data_schema=vol.Schema({
                vol.Required(CONF_SCOPE, default=default_scopes): _scope_selector(),
            }),
            errors=errors,
        )

    def _edit_schema(self, account: dict[str, Any]) -> vol.Schema:
        """编辑表单：仅接入名（伪账户 key 锁定）."""
        return vol.Schema({
            vol.Optional(CONF_NAME, default=account.get(CONF_NAME, "")): str,
        })

    async def _async_validate_edit(
        self, user_input: dict[str, Any], account: dict[str, Any]
    ) -> dict[str, str]:
        """灾害预警编辑无外部校验，key 不变."""
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