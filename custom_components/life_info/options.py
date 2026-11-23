"""生活信息 选项流基类：账户清单与轮询间隔的共用骨架."""
from __future__ import annotations

from typing import Any
import probatio as vol

from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import CONF_ACCOUNTS, CONF_NAME, CONF_SCAN_INTERVAL

class LifeInfoOptionsFlow(OptionsFlowWithReload):
    """基类：账户增删/编辑/间隔骨架，子类声明唯一键、菜单与校验."""

    MENU_OPTIONS: tuple[str, ...] = ()
    INTERVAL_OPTIONS: tuple[int, ...] = ()
    DEFAULT_INTERVAL: int = 1
    SCAN_INTERVAL_LABEL: str = "小时"
    ACCOUNT_KEY: str = ""

    def __init__(self) -> None:
        super().__init__()
        self._edit_key: str | None = None

    @property
    def _accounts(self) -> list[dict[str, Any]]:
        return list(self.config_entry.options.get(CONF_ACCOUNTS, []))

    @property
    def _interval(self) -> int:
        return int(
            self.config_entry.options.get(CONF_SCAN_INTERVAL, self.DEFAULT_INTERVAL)
        )

    def _save(self, accounts: list[dict[str, Any]], interval: int) -> ConfigFlowResult:
        """保存：覆盖账户与间隔，保留 api_key 等其它 options 字段."""
        data = dict(self.config_entry.options)
        data[CONF_ACCOUNTS] = accounts
        data[CONF_SCAN_INTERVAL] = interval
        return self.async_create_entry(data=data)

    def _account_options(self) -> list[SelectOptionDict]:
        """账户下拉：value 为唯一键，label 为接入名或唯一键."""
        return [
            SelectOptionDict(
                value=str(a[self.ACCOUNT_KEY]),
                label=str(a.get(CONF_NAME) or a[self.ACCOUNT_KEY]),
            )
            for a in self._accounts
        ]

    def _find_account(self, key: str) -> dict[str, Any] | None:
        return next(
            (a for a in self._accounts if str(a.get(self.ACCOUNT_KEY)) == key),
            None,
        )

    def _replace_account(
        self, key: str, updated: dict[str, Any]
    ) -> ConfigFlowResult:
        accounts = [
            updated if str(a.get(self.ACCOUNT_KEY)) == key else a
            for a in self._accounts
        ]
        return self._save(accounts, self._interval)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """菜单：子类增删步骤 + 统一编辑与轮询间隔."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[*self.MENU_OPTIONS, "edit_account", "scan_interval"],
        )

    async def async_step_scan_interval(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """轮询间隔：档位由子类声明，保留账户清单."""
        if user_input is not None:
            return self._save(self._accounts, int(user_input[CONF_SCAN_INTERVAL]))

        return self.async_show_form(
            step_id="scan_interval",
            data_schema=vol.Schema({
                vol.Required(CONF_SCAN_INTERVAL, default=str(self._interval)):
                    SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(
                                    value=str(h),
                                    label=f"{h} {self.SCAN_INTERVAL_LABEL}",
                                )
                                for h in self.INTERVAL_OPTIONS
                            ],
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
            }),
        )

    async def async_step_edit_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """编辑账户第一步：选择要编辑的账户（唯一键不可改）."""
        if self._edit_key is None:
            errors: dict[str, str] = {}
            if user_input is not None:
                key = str(user_input.get(self.ACCOUNT_KEY) or "")
                if self._find_account(key) is None:
                    errors["base"] = "invalid_account"
                else:
                    self._edit_key = key
                    return await self.async_step_edit_detail()

            return self.async_show_form(
                step_id="edit_account",
                data_schema=vol.Schema({
                    vol.Required(self.ACCOUNT_KEY): SelectSelector(
                        SelectSelectorConfig(
                            options=self._account_options(),
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                }),
                errors=errors,
            )

        return await self.async_step_edit_detail(user_input)

    async def async_step_edit_detail(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """编辑账户第二步：子类表单 + 校验 + 原位替换."""
        account = self._find_account(self._edit_key or "")
        if account is None:
            self._edit_key = None
            return await self.async_step_edit_account()

        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_validate_edit(user_input, account)
            if not errors:
                return self._replace_account(
                    self._edit_key or "",
                    self._build_updated(user_input, account),
                )

        return self.async_show_form(
            step_id="edit_detail",
            data_schema=self._edit_schema(account),
            errors=errors,
        )

    def _edit_schema(self, account: dict[str, Any]) -> vol.Schema:
        """子类实现：编辑表单（不含唯一键）."""
        raise NotImplementedError

    async def _async_validate_edit(
        self, user_input: dict[str, Any], account: dict[str, Any]
    ) -> dict[str, str]:
        """子类实现：返回字段错误字典，空字典表示通过."""
        raise NotImplementedError

    def _build_updated(
        self, user_input: dict[str, Any], account: dict[str, Any]
    ) -> dict[str, Any]:
        """子类实现：把表单输入合并回账户（保留唯一键）."""
        raise NotImplementedError