"""Writable room power-level entities."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, MIN_SCAN_INTERVAL
from .device import build_device_info
from .modbus_handler import ViegaModbusClient
from .polling import PollingGate
from .registers import resolve_room_number, room_registers

SCAN_INTERVAL = timedelta(seconds=MIN_SCAN_INTERVAL)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up one power-level number for each room with a resolvable register."""
    rooms = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("rooms", {})
    entities = [
        ViegaPowerLevelNumber(entry.entry_id, room_id, room_config)
        for room_id, room_config in rooms.items()
        if isinstance(room_config, dict)
    ]
    async_add_entities(entity for entity in entities if entity.address is not None)


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
        room_number = resolve_room_number(room_id, room_config)
        registers = room_registers(room_number) if room_number else {}
        address = room_config.get("power_level_register", registers.get("power_level"))
        self._entry_id = entry_id
        self._room_id = room_id
        # No configured/derivable register means the write feature must not
        # be advertised at all (spec.md 5a); async_setup_entry skips adding
        # this entity when `address` is None instead of falling back to
        # register 0, which collides with the base unit's operating-mode
        # register and would let an unconfigured entity write to it.
        self.address: int | None = int(address) if address is not None else None
        self._attr_unique_id = f"{entry_id}_{room_id}_power_level"
        self._attr_translation_key = "power_level"
        self._attr_translation_placeholders = {
            "room": str(room_config.get("name", room_id))
        }
        self._attr_native_value = None
        self._polling_gate = PollingGate()

    async def async_update(self) -> None:
        """Read the current actuator power level."""
        entry_data = self.hass.data[DOMAIN][self._entry_id]
        if self.address is None or (
            "polling" not in entry_data and not self._polling_gate.is_due(self.hass, self._entry_id)
        ):
            return
        client = entry_data["client"]
        try:
            shared = entry_data.get("polling")
            values = await (shared.read(self.hass, self._entry_id, "holding", self.address, 1)
                            if shared else client.read_holding_registers(self.address, 1))
        except Exception:
            return
        if values and values[0] != ViegaModbusClient.ERROR_SENTINEL:
            self._attr_native_value = values[0]

    async def async_set_native_value(self, value: float) -> None:
        """Write a new actuator power level."""
        if self.address is None:
            raise ValueError("no power level register configured for this room")
        level = round(value)
        if not 0 <= level <= 10:
            raise ValueError("power level must be between 0 and 10")
        client = self.hass.data[DOMAIN][self._entry_id]["client"]
        await client.write_register(self.address, level)
        self._attr_native_value = level

    @property
    def device_info(self):
        return build_device_info(self.hass, self._entry_id)
