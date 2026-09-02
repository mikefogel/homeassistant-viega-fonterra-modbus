"""Config flow for the Viega Fonterra Modbus integration."""

from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DEVICE_NAME,
    CONF_MODBUS_TIMEOUT,
    CONF_POLLING_INTERVAL,
    DEFAULT_HOST,
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

    @staticmethod
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow for an existing module."""
        return ViegaFonterraOptionsFlow(config_entry)

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
            rooms = user_input.get("rooms", {})
            if isinstance(rooms, str):
                try:
                    rooms = json.loads(rooms)
                except json.JSONDecodeError:
                    errors["rooms"] = "invalid_rooms"
                else:
                    if not isinstance(rooms, dict):
                        errors["rooms"] = "invalid_rooms"
            if errors:
                return self._show_user_form(user_input, errors)

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
                self._device_config = {
                    key: value
                    for key, value in user_input.items()
                    if key != "rooms"
                }
                self._discovered_rooms = rooms
                return await self.async_step_finalize()

        return self._show_user_form(user_input, errors)

    def _show_user_form(
        self,
        user_input: dict[str, object] | None,
        errors: dict[str, str],
    ) -> config_entries.FlowResult:
        """Show the single-step module setup form."""
        example = {
            "room_1": {"name": "Wohnzimmer", "actor": 1, "sensor": 10},
            "room_2": {"name": "Schlafzimmer", "actor": 2, "sensor": 11},
        }
        defaults = user_input or {}
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST, default=defaults.get(CONF_HOST, DEFAULT_HOST)
                    ): str,
                    vol.Required(
                        CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)
                    ): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=65535)
                    ),
                    vol.Required(
                        CONF_DEVICE_NAME,
                        default=defaults.get(CONF_DEVICE_NAME, "Fonterra"),
                    ): str,
                    vol.Optional(
                        CONF_POLLING_INTERVAL,
                        default=defaults.get(
                            CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
                    vol.Optional(
                        CONF_MODBUS_TIMEOUT,
                        default=defaults.get(
                            CONF_MODBUS_TIMEOUT, DEFAULT_MODBUS_TIMEOUT
                        ),
                    ): vol.All(vol.Coerce(float), vol.Range(min=1, max=30)),
                    vol.Optional(
                        "rooms", default=defaults.get("rooms", json.dumps(example))
                    ): str,
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
            rooms = user_input.get("rooms", {})
            if isinstance(rooms, str):
                try:
                    rooms = json.loads(rooms)
                except json.JSONDecodeError:
                    errors["rooms"] = "invalid_rooms"
                else:
                    if not isinstance(rooms, dict):
                        errors["rooms"] = "invalid_rooms"
            if errors:
                return self.async_show_form(
                    step_id="rooms",
                    data_schema=vol.Schema(
                        {vol.Optional("rooms", default=json.dumps(rooms)): str}
                    ),
                    errors=errors,
                )
            self._discovered_rooms = rooms
            return await self.async_step_finalize()

        example = {
            "room_1": {"name": "Wohnzimmer", "actor": 1, "sensor": 10},
            "room_2": {"name": "Schlafzimmer", "actor": 2, "sensor": 11},
        }

        return self.async_show_form(
            step_id="rooms",
            data_schema=vol.Schema(
                {
                    vol.Optional("rooms", default=json.dumps(example)): str,
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


class ViegaFonterraOptionsFlow(config_entries.OptionsFlow):
    """Handle editable settings for an existing Viega module."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Show and save editable module settings."""
        errors: dict[str, str] = {}
        current_data = self.config_entry.data
        current_options = self.config_entry.options
        current_rooms = current_options.get("rooms", {})
        if not isinstance(current_rooms, dict):
            current_rooms = {}

        if user_input is not None:
            timeout = float(user_input[CONF_MODBUS_TIMEOUT])
            try:
                client = ViegaModbusClient(
                    str(user_input[CONF_HOST]),
                    int(user_input[CONF_PORT]),
                    timeout=timeout,
                )
                await client.connect()
                await client.disconnect()
            except Exception as err:
                _LOGGER.error("Failed to connect to updated device: %s", err)
                errors["base"] = "cannot_connect"
            else:
                rooms = self._rooms_from_input(user_input, current_rooms)
                data = {
                    **current_data,
                    CONF_HOST: str(user_input[CONF_HOST]),
                    CONF_PORT: int(user_input[CONF_PORT]),
                    CONF_DEVICE_NAME: str(user_input[CONF_DEVICE_NAME]),
                    CONF_POLLING_INTERVAL: int(user_input[CONF_POLLING_INTERVAL]),
                    CONF_MODBUS_TIMEOUT: timeout,
                }
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=data,
                    title=str(user_input[CONF_DEVICE_NAME]),
                )
                return self.async_create_entry(
                    title="",
                    data={**current_options, "rooms": rooms},
                )

        schema: dict[vol.Marker, Any] = {
            vol.Required(
                CONF_HOST, default=current_data.get(CONF_HOST, "")
            ): str,
            vol.Required(
                CONF_PORT, default=current_data.get(CONF_PORT, DEFAULT_PORT)
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            vol.Required(
                CONF_DEVICE_NAME,
                default=current_data.get(CONF_DEVICE_NAME, "Fonterra"),
            ): str,
            vol.Required(
                CONF_POLLING_INTERVAL,
                default=current_data.get(
                    CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL
                ),
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=300)),
            vol.Required(
                CONF_MODBUS_TIMEOUT,
                default=current_data.get(
                    CONF_MODBUS_TIMEOUT, DEFAULT_MODBUS_TIMEOUT
                ),
            ): vol.All(vol.Coerce(float), vol.Range(min=1, max=30)),
        }
        for room_id, room in current_rooms.items():
            if isinstance(room, dict):
                schema[vol.Required(
                    f"room_name_{room_id}", default=room.get("name", room_id)
                )] = str
                schema[vol.Required(
                    f"room_actor_{room_id}", default=room.get("actor", 0)
                )] = vol.Coerce(int)
                schema[vol.Required(
                    f"room_sensor_{room_id}", default=room.get("sensor", 0)
                )] = vol.Coerce(int)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    @staticmethod
    def _rooms_from_input(
        user_input: dict[str, Any], current_rooms: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        """Build the persisted room mapping from individual UI fields."""
        rooms: dict[str, dict[str, Any]] = {}
        for room_id, room in current_rooms.items():
            if isinstance(room, dict):
                rooms[room_id] = {
                    "name": user_input.get(
                        f"room_name_{room_id}", room.get("name", room_id)
                    ),
                    "actor": user_input.get(
                        f"room_actor_{room_id}", room.get("actor", 0)
                    ),
                    "sensor": user_input.get(
                        f"room_sensor_{room_id}", room.get("sensor", 0)
                    ),
                }
        return rooms

