"""昆仑燃气 条目选项."""
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
from ...options import LifeInfoOptionsFlow
from .api import async_fetch_balance
from .const import (
    CONF_MDM_CODE,
    CONF_NAME,
    CONF_REGION,
    CONF_USER_CODE,
    DEFAULT_SCAN_INTERVAL,
    SCAN_INTERVAL_OPTIONS,
)
from .regions import REGIONS

class KunlunGasOptionsFlow(LifeInfoOptionsFlow):
    """燃气选项：管理多户号与轮询间隔，两者共存于 entry.options."""

    MENU_OPTIONS = ("add_account", "remove_account")
    INTERVAL_OPTIONS = SCAN_INTERVAL_OPTIONS
    DEFAULT_INTERVAL = DEFAULT_SCAN_INTERVAL
    SCAN_INTERVAL_LABEL = "小时"
    ACCOUNT_KEY = CONF_USER_CODE

    async def async_step_add_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """添加户号：接入名称 + 户号 + 地区，校验后追加."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = str(user_input.get(CONF_NAME) or "").strip()
            code = str(user_input.get(CONF_USER_CODE) or "").strip()
            mdm = str(user_input.get(CONF_REGION) or "").split("|", 1)[0].strip()
            if not mdm:
                errors["base"] = "invalid_region"
            elif not code:
                errors["base"] = "invalid_user_code"
            elif any(a.get(CONF_USER_CODE) == code for a in self._accounts):
                errors["base"] = "already_added"
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
                        accounts = [
                            *self._accounts,
                            {
                                CONF_NAME: name,
                                CONF_USER_CODE: code,
                                CONF_MDM_CODE: mdm,
                            },
                        ]
                        return self._save(accounts, self._interval)

        return self.async_show_form(
            step_id="add_account",
            data_schema=vol.Schema({
                vol.Optional(CONF_NAME, default=""): str,
                vol.Required(CONF_USER_CODE, default=""): str,
                vol.Required(CONF_REGION, default=""): SelectSelector(
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

    async def async_step_remove_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """移除户号：保留至少一个，避免设备全空."""
        errors: dict[str, str] = {}
        if user_input is not None:
            code = str(user_input.get(CONF_USER_CODE) or "")
            if len(self._accounts) <= 1:
                errors["base"] = "cannot_remove_last"
            else:
                return self._save(
                    [a for a in self._accounts if a.get(CONF_USER_CODE) != code],
                    self._interval,
                )

        return self.async_show_form(
            step_id="remove_account",
            data_schema=vol.Schema({
                vol.Required(CONF_USER_CODE): SelectSelector(
                    SelectSelectorConfig(
                        options=[
                            SelectOptionDict(
                                value=a[CONF_USER_CODE],
                                label=a.get(CONF_NAME) or a[CONF_USER_CODE],
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
        """编辑表单：接入名 + 地区（户号锁定）."""
        current = next(
            (
                r["value"] for r in REGIONS
                if r["mdm_code"] == account.get(CONF_MDM_CODE)
            ),
            "",
        )
        return vol.Schema({
            vol.Optional(CONF_NAME, default=account.get(CONF_NAME, "")): str,
            vol.Required(CONF_REGION, default=current): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=r["value"], label=r["label"])
                        for r in REGIONS
                    ],
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        })

    async def _async_validate_edit(
        self, user_input: dict[str, Any], account: dict[str, Any]
    ) -> dict[str, str]:
        """编辑校验：地区合法 + 户号在该地区仍可取数."""
        code = str(account[CONF_USER_CODE])
        mdm = str(user_input.get(CONF_REGION) or "").split("|", 1)[0].strip()
        if not mdm:
            return {"base": "invalid_region"}
        try:
            balance = await async_fetch_balance(
                async_get_clientsession(self.hass), code, mdm
            )
        except (LifeInfoRequestError, ValueError, TimeoutError, OSError):
            return {"base": "cannot_connect"}
        if str(balance.get("userCode") or "") != code:
            return {"base": "invalid_user_code"}
        return {}

    def _build_updated(
        self, user_input: dict[str, Any], account: dict[str, Any]
    ) -> dict[str, Any]:
        """合并：户号不变，地区拆为 mdm_code，接入名为空回落."""
        code = str(account[CONF_USER_CODE])
        return {
            CONF_USER_CODE: code,
            CONF_NAME: str(user_input.get(CONF_NAME) or "").strip()
                or f"户号:{code}",
            CONF_MDM_CODE: str(user_input.get(CONF_REGION) or "").split("|", 1)[0],
        }