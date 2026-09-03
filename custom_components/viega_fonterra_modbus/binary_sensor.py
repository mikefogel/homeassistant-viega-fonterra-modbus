"""Binary sensor platform exposing the base-unit error indicator.

spec.md 13 requires that a non-zero base-unit error code activates a
dedicated error indicator, separate from the raw/human-readable error code
sensor exposed by sensor.py.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from .const import DOMAIN, MIN_SCAN_INTERVAL
from .device import build_device_info
from .modbus_handler import ViegaModbusClient
from .polling import PollingGate
from .registers import BASE_UNIT_REGISTERS

SCAN_INTERVAL = timedelta(seconds=MIN_SCAN_INTERVAL)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the base-unit error indicator for a config entry."""
    async_add_entities([ViegaBaseUnitErrorBinarySensor(entry.entry_id)])


class ViegaBaseUnitErrorBinarySensor(BinarySensorEntity):
    """Report whether the base unit currently reports a non-zero error code."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, entry_id: str) -> None:
        self._entry_id = entry_id
        self._address = BASE_UNIT_REGISTERS["error_code"]
        self._attr_unique_id = f"{entry_id}_base_unit_error"
        self._attr_name = "Base unit error"
        self._attr_is_on = False
        self._polling_gate = PollingGate()

    async def async_update(self) -> None:
        if not self._polling_gate.is_due(self.hass, self._entry_id):
            return
        client = self.hass.data[DOMAIN][self._entry_id]["client"]
        try:
            values = await client.read_input_registers(self._address, 1)
        except Exception:
            return
        if not values or values[0] == ViegaModbusClient.ERROR_SENTINEL:
            return
        self._attr_is_on = values[0] != 0

    @property
    def device_info(self):
        return build_device_info(self.hass, self._entry_id)
