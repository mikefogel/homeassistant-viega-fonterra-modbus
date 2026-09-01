"""Config flow for the Viega Fonterra Modbus integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import DEFAULT_PORT, DOMAIN
from .device_registry import DeviceRegistry
from .modbus_handler import ViegaModbusClient
from .room_mapping import RoomMappingDiscovery

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
            try:
                client = ViegaModbusClient(
                    str(user_input[CONF_HOST]), int(user_input[CONF_PORT])
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
                }
            ),
            errors=errors,
        )

    async def async_step_rooms(
        self, user_input: dict[str, object] | None = None
    ) -> config_entries.FlowResult:
        """Discover and configure room mappings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._discovered_rooms = user_input.get("rooms", {})
            return await self.async_step_finalize()

        return self.async_show_form(
            step_id="rooms",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        "rooms", default={"room_1": {"actor": 1, "sensor": 10}}
                    ): vol.Any(dict, str),
                }
            ),
            description_placeholders={
                "example": "{'room_1': {'actor': 1, 'sensor': 10}, 'room_2': {'actor': 2, 'sensor': 11}}"
            },
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
                "rooms": self._discovered_rooms,
            },
        )

        return self.async_create_entry(
            title=f"{self._device_config.get(CONF_HOST)}:{self._device_config.get(CONF_PORT)}",
            data=self._device_config,
            options={"rooms": self._discovered_rooms, "device_id": device_id},
        )

