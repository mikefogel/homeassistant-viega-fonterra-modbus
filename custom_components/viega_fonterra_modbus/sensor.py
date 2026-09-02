"""Sensor platform for the Viega Fonterra Modbus integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .diagnostic import ViegaDiagnosticTextEntity
from .modbus_handler import ViegaModbusClient
from .registers import REGISTER_DEFINITIONS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the sensor entities from a config entry."""
    entities = [
        ViegaRegisterSensor(
            entry,
            sensor_key,
            details["name"],
            details["unit"],
            details["address"],
        )
        for sensor_key, details in REGISTER_DEFINITIONS.items()
    ]
    rooms = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("rooms", {})
    entities.extend(
        ViegaDiagnosticTextEntity(
            entry.entry_id,
            f"{room_config.get('name', room_id)}_diagnostic"
            if isinstance(room_config, dict)
            else f"{room_id}_diagnostic",
        )
        for room_id, room_config in rooms.items()
    )
    async_add_entities(entities)


class ViegaRegisterSensor(SensorEntity):
    """Expose a register-backed sensor entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        sensor_key: str,
        name: str,
        unit: str | None,
        address: int,
    ) -> None:
        self._entry_id = entry.entry_id
        self._sensor_key = sensor_key
        self._attr_unique_id = f"{entry.entry_id}_{sensor_key}"
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._address = address
        self._attr_native_value = 0
        self.last_error_message = ""

    async def async_update(self) -> None:
        """Read the current register value from the Modbus client."""
        client = self.hass.data[DOMAIN].get(self._entry_id, {}).get("client")
        if client is None:
            self._attr_native_value = 0
            self.last_error_message = "error: communication timeout"
            return

        try:
            values = await client.read_holding_registers(self._address, 1)
        except Exception:
            self.last_error_message = "error: communication timeout"
            return

        if not values:
            self.last_error_message = "error: sensor invalid"
            return

        value = values[0]
        if value == ViegaModbusClient.ERROR_SENTINEL:
            self.last_error_message = "error: sensor invalid"
            return
        self.last_error_message = ""
        self._attr_native_value = value

    @property
    def state(self):
        """Return the current sensor reading."""
        return self._attr_native_value

    @property
    def unique_id(self) -> str:
        return self._attr_unique_id

    @property
    def icon(self) -> str:
        if "temperature" in self._sensor_key:
            return "mdi:thermometer"
        if "pressure" in self._sensor_key:
            return "mdi:gauge"
        return "mdi:information-outline"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "Viega Fonterra Smart Control",
            "manufacturer": "Viega",
            "model": "Smart Control",
        }

