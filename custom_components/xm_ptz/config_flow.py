"""Config flow for the XM camera."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback

from .api import DEFAULT_PORT, XMAuthError, XMCamera, XMError
from .const import CONF_SYNC_TIME, DOMAIN


async def _validate(data: Mapping[str, Any]) -> dict[str, Any]:
    api = XMCamera(data[CONF_HOST], data[CONF_USERNAME], data[CONF_PASSWORD], data[CONF_PORT])
    try:
        return await api.system_info()
    finally:
        await api.close()


class XMConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                info = await _validate(user_input)
            except XMAuthError:
                errors["base"] = "invalid_auth"
            except XMError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(info["SerialNo"])
                self._abort_if_unique_id_configured(updates={CONF_HOST: user_input[CONF_HOST]})
                return self.async_create_entry(
                    title=f"{info.get('DeviceModel', 'XM camera')} ({user_input[CONF_HOST]})", data=user_input)

        defaults = user_input or {}
        schema = vol.Schema({
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): int,
            vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "admin")): str,
            vol.Required(CONF_PASSWORD): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            data = {**entry.data, **user_input}
            try:
                await _validate(data)
            except XMAuthError:
                errors["base"] = "invalid_auth"
            except XMError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data=data)
        schema = vol.Schema({
            vol.Required(CONF_USERNAME, default=entry.data[CONF_USERNAME]): str,
            vol.Required(CONF_PASSWORD): str,
        })
        return self.async_show_form(step_id="reauth_confirm", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return XMOptionsFlow()


class XMOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        schema = vol.Schema({
            vol.Required(CONF_SYNC_TIME, default=self.config_entry.options.get(CONF_SYNC_TIME, True)): bool,
        })
        return self.async_show_form(step_id="init", data_schema=schema)
