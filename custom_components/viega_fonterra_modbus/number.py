"""Writable room power-level entities."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .registers import room_registers


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up one power-level number for each configured room."""
    rooms = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("rooms", {})
    async_add_entities(
        ViegaPowerLevelNumber(entry.entry_id, room_id, room_config)
        for room_id, room_config in rooms.items()
        if isinstance(room_config, dict)
    )


class ViegaPowerLevelNumber(NumberEntity):
    """Read and write the documented room power-level register."""

    _attr_has_entity_name = True
    _attr_native_min_value = 0
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "level"

    def __init__(
        self, entry_id: str, room_id: str, room_config: dict[str, object]
    ) -> None:
        room_number = int(room_config.get("room_number", 0))
        registers = room_registers(room_number) if room_number else {}
        self._entry_id = entry_id
        self._room_id = room_id
        self._address = int(
            room_config.get("power_level_register", registers.get("power_level", 0))
        )
        self._attr_unique_id = f"{entry_id}_{room_id}_power_level"
        self._attr_name = f"{room_config.get('name', room_id)} power level"
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Read the current actuator power level."""
        client = self.hass.data[DOMAIN][self._entry_id]["client"]
        values = await client.read_holding_registers(self._address, 1)
        if values and values[0] != -99:
            self._attr_native_value = values[0]

    async def async_set_native_value(self, value: float) -> None:
        """Write a new actuator power level."""
        level = round(value)
        if not 0 <= level <= 10:
            raise ValueError("power level must be between 0 and 10")
        client = self.hass.data[DOMAIN][self._entry_id]["client"]
        await client.write_register(self._address, level)
        self._attr_native_value = level

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "Viega Fonterra Smart Control",
            "manufacturer": "Viega",
            "model": "Smart Control",
        }
