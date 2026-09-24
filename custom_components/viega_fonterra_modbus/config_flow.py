"""Config flow for the Viega Fonterra Modbus integration."""

from __future__ import annotations

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
        """Handle device configuration entry step.

        Room mapping is intentionally not collected here: the device is the
        source of truth for room-to-actuator association (spec.md 4a) and is
        (re)discovered automatically on every setup. A manually typed room
        mapping is only ever a fallback for when the device can't be read,
        and belongs in the options flow ("Editing an existing module",
        spec.md 6a), not in initial setup.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            # Validate connection to the device
            host = user_input.get(CONF_HOST)
            port = user_input.get(CONF_PORT)
            timeout = user_input.get(CONF_MODBUS_TIMEOUT)

            # Validate host
            if not host or not isinstance(host, str):
                errors[CONF_HOST] = "invalid_host"
            else:
                host = str(host)

            # Validate port
            if port is None:
                errors[CONF_PORT] = "required"
            else:
                try:
                    port = int(port)
                    if port < 1 or port > 65535:
                        errors[CONF_PORT] = "invalid_port"
                except (ValueError, TypeError):
                    errors[CONF_PORT] = "invalid_port"

            # Validate timeout
            if timeout is None:
                errors[CONF_MODBUS_TIMEOUT] = "required"
            else:
                try:
                    timeout = float(timeout)
                    if timeout < 1 or timeout > 30:
                        errors[CONF_MODBUS_TIMEOUT] = "invalid_timeout"
                except (ValueError, TypeError):
                    errors[CONF_MODBUS_TIMEOUT] = "invalid_timeout"

            if not errors:
                try:
                    client = ViegaModbusClient(host, port, timeout=timeout)
                    await client.connect()
                    await client.disconnect()
                except Exception as err:
                    _LOGGER.error("Failed to connect to device: %s", err)
                    errors["base"] = "cannot_connect"
                else:
                    self._device_config = {
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_DEVICE_NAME: str(user_input.get(CONF_DEVICE_NAME, "Fonterra")),
                        CONF_POLLING_INTERVAL: int(user_input.get(CONF_POLLING_INTERVAL, DEFAULT_POLLING_INTERVAL)),
                        CONF_MODBUS_TIMEOUT: timeout,
                    }
                    return await self.async_step_finalize()

        return self._show_user_form(user_input, errors)

    def _show_user_form(
        self,
        user_input: dict[str, object] | None,
        errors: dict[str, str],
    ) -> config_entries.FlowResult:
        """Show the single-step module setup form."""
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
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
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
                }
            ),
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
                "host": self._device_config.get(CONF_HOST, DEFAULT_HOST),
                "port": self._device_config.get(CONF_PORT, DEFAULT_PORT),
                "device_name": self._device_config.get(CONF_DEVICE_NAME, "Fonterra"),
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
            # Validate all inputs
            host = user_input.get(CONF_HOST)
            port = user_input.get(CONF_PORT)
            device_name = user_input.get(CONF_DEVICE_NAME)
            polling_interval = user_input.get(CONF_POLLING_INTERVAL)
            modbus_timeout = user_input.get(CONF_MODBUS_TIMEOUT)

            # Validate host
            if not host or not isinstance(host, str):
                errors[CONF_HOST] = "invalid_host"
            else:
                host = str(host)

            # Validate port
            if port is None:
                errors[CONF_PORT] = "required"
            else:
                try:
                    port = int(port)
                    if port < 1 or port > 65535:
                        errors[CONF_PORT] = "invalid_port"
                except (ValueError, TypeError):
                    errors[CONF_PORT] = "invalid_port"

            # Validate device name
            if not device_name or not isinstance(device_name, str):
                errors[CONF_DEVICE_NAME] = "required"
            else:
                device_name = str(device_name)

            # Validate polling interval
            if polling_interval is None:
                errors[CONF_POLLING_INTERVAL] = "required"
            else:
                try:
                    polling_interval = int(polling_interval)
                    if polling_interval < 5 or polling_interval > 300:
                        errors[CONF_POLLING_INTERVAL] = "invalid_polling_interval"
                except (ValueError, TypeError):
                    errors[CONF_POLLING_INTERVAL] = "invalid_polling_interval"

            # Validate timeout
            if modbus_timeout is None:
                errors[CONF_MODBUS_TIMEOUT] = "required"
            else:
                try:
                    modbus_timeout = float(modbus_timeout)
                    if modbus_timeout < 1 or modbus_timeout > 30:
                        errors[CONF_MODBUS_TIMEOUT] = "invalid_timeout"
                except (ValueError, TypeError):
                    errors[CONF_MODBUS_TIMEOUT] = "invalid_timeout"

            if not errors:
                try:
                    client = ViegaModbusClient(host, port, timeout=modbus_timeout)
                    await client.connect()
                    await client.disconnect()
                except Exception as err:
                    _LOGGER.error("Failed to connect to updated device: %s", err)
                    errors["base"] = "cannot_connect"
                else:
                    rooms = self._rooms_from_input(user_input, current_rooms)
                    data = {
                        **current_data,
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_DEVICE_NAME: device_name,
                        CONF_POLLING_INTERVAL: polling_interval,
                        CONF_MODBUS_TIMEOUT: modbus_timeout,
                    }
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data=data,
                        title=device_name,
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
                schema[vol.Required(
                    f"room_target_register_{room_id}",
                    default=room.get("target_temperature_register", 0),
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
                    "target_temperature_register": user_input.get(
                        f"room_target_register_{room_id}",
                        room.get("target_temperature_register", 0),
                    ),
                }
        return rooms