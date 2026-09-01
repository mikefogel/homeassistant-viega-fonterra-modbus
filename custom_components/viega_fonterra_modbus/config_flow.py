"""Config flow for the Viega Fonterra Modbus integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DEVICE_NAME,
    CONF_MODBUS_TIMEOUT,
    CONF_POLLING_INTERVAL,
    DEFAULT_MODBUS_TIMEOUT,
    DEFAULT_POLLING_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
)
from .device_registry import DeviceRegistry
from .modbus_handler import ViegaModbusClient

_LOGGER = logging.getLogger(__name__)


class ViegaFonterraConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Viega Fonterra."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._device_config: dict[str, object] = {}
        self._device_registry = DeviceRegistry()
        self._discovered_rooms: dict[str, dict[str, object]] = {}

    async def async_step_user(self, user_input: dict[str, object] | None = None):
        """Handle device configuration entry step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate connection to the device
            timeout = float(user_input.get(CONF_MODBUS_TIMEOUT, DEFAULT_MODBUS_TIMEOUT))
            try:
                client = ViegaModbusClient(
                    str(user_input[CONF_HOST]),
                    int(user_input[CONF_PORT]),
                    timeout=timeout,
                )
                await client.connect()
                await client.disconnect()
            except Exception as err:
                _LOGGER.error("Failed to connect to device: %s", err)
                errors["base"] = "cannot_connect"
            else:
                self._device_config = user_input
                return await self.async_step_rooms()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default="192.168.1.10"): str,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                    vol.Required(CONF_DEVICE_NAME, default="Fonterra"): str,
                    vol.Optional(
                        CONF_POLLING_INTERVAL, default=DEFAULT_POLLING_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                    vol.Optional(
                        CONF_MODBUS_TIMEOUT, default=DEFAULT_MODBUS_TIMEOUT
                    ): vol.All(vol.Coerce(float), vol.Range(min=1, max=30)),
                }
            ),
            errors=errors,
        )

    async def async_step_rooms(
        self, user_input: dict[str, object] | None = None
    ) -> config_entries.FlowResult:
        """Discover and configure room mappings with names."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._discovered_rooms = user_input.get("rooms", {})
            return await self.async_step_finalize()

        example = {
            "room_1": {"name": "Wohnzimmer", "actor": 1, "sensor": 10},
            "room_2": {"name": "Schlafzimmer", "actor": 2, "sensor": 11},
        }

        return self.async_show_form(
            step_id="rooms",
            data_schema=vol.Schema(
                {
                    vol.Optional("rooms", default=example): vol.Any(dict, str),
                }
            ),
            description_placeholders={"example": str(example)},
            errors=errors,
        )

    async def async_step_finalize(
        self, user_input: dict[str, object] | None = None
    ) -> config_entries.FlowResult:
        """Finalize and create the config entry."""
        device_id = f"fonterra_{self._device_config.get(CONF_HOST, 'unknown')}"
        self._device_registry.add_device(
            device_id,
            {
                "host": self._device_config.get(CONF_HOST),
                "port": self._device_config.get(CONF_PORT),
                "device_name": self._device_config.get(CONF_DEVICE_NAME),
                "polling_interval": self._device_config.get(
                    CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL
                ),
                "modbus_timeout": self._device_config.get(
                    CONF_MODBUS_TIMEOUT, DEFAULT_MODBUS_TIMEOUT
                ),
                "rooms": self._discovered_rooms,
            },
        )

        return self.async_create_entry(
            title=str(self._device_config.get(CONF_DEVICE_NAME, "Fonterra")),
            data=self._device_config,
            options={
                "rooms": self._discovered_rooms,
                "device_id": device_id,
            },
        )

