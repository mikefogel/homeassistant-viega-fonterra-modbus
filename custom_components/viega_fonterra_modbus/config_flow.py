"""Config flow for the Viega Fonterra Modbus integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import DEFAULT_PORT, DOMAIN


class ViegaFonterraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Viega Fonterra."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            return self.async_create_entry(
                title=f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default="192.168.1.10"): str,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                }
            ),
            errors=errors,
        )

