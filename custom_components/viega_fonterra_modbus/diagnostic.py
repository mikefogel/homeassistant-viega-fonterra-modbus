"""Diagnostic text entities for failed unit values."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .device import build_device_info
from .registers import (
    BASE_UNIT_REGISTERS,
    describe_error_code,
    resolve_room_number,
    room_registers,
)
from .modbus_handler import ViegaModbusClient
from .polling import PollingGate

DEFAULT_STATUS = "error: sensor invalid"

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up diagnostic text entities for known failure states."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    rooms = entry_data.get("rooms", {})

    entities = [
        ViegaDiagnosticTextEntity(
            entry.entry_id,
            f"{room_config.get('name', room_id) if isinstance(room_config, dict) else room_id} diagnostic",
            room_id=room_id,
            address=_room_error_address(room_id, room_config),
            room_name=room_config.get("name", room_id) if isinstance(room_config, dict) else room_id,
        )
        for room_id, room_config in rooms.items()
    ]
    async_add_entities(entities)


def _room_error_address(room_id: str, room_config: object) -> int:
    """Return the room's own error-code register, not the shared base-unit one.

    Each room has its own error/warning register (manual 30051/30053/...,
    codes 21/22/24 - thermostat connectivity/battery). Falling back to the
    shared base-unit error register (as this entity previously always did)
    made every room's diagnostic text identical regardless of that room's
    actual state.
    """
    room_number = resolve_room_number(
        room_id, room_config if isinstance(room_config, dict) else {}
    )
    if room_number:
        return room_registers(room_number)["error_code"]
    return BASE_UNIT_REGISTERS["error_code"]


class ViegaDiagnosticTextEntity(SensorEntity):
    """Represent a textual diagnosis entity for a failed sensor or unit."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry_id: str | None,
        name: str,
        status: str = DEFAULT_STATUS,
        room_id: str | None = None,
        address: int | None = None,
        room_name: str | None = None,
    ) -> None:
        self._entry_id = entry_id
        if room_id is not None and room_name is not None:
            # Localized via translations/*.json entity.sensor.room_diagnostic
            # (spec.md "localize every entity name"). `name` is still kept
            # below as the fallback for the room_id-less call shape used by
            # standalone/legacy diagnosis entities, where there is no "room"
            # to build a translation placeholder from.
            self._attr_translation_key = "room_diagnostic"
            self._attr_translation_placeholders = {"room": str(room_name)}
        else:
            self.name = name
        self.status = status
        self._room_id = room_id
        self._address = address if address is not None else BASE_UNIT_REGISTERS["error_code"]
        self._polling_gate = PollingGate()
        self._attr_unique_id = (
            f"{entry_id}_{room_id}_diagnostic" if entry_id is not None and room_id else
            (f"{entry_id}_{name}_diagnostic" if entry_id is not None else None)
        )
        self._attr_native_value = status

    @property
    def state(self) -> str:
        return self.status

    async def async_update(self) -> None:
        """Refresh the diagnostic status from the shared error-code poll."""
        if self._entry_id is None:
            return
        entry_data = self.hass.data.get(DOMAIN, {}).get(self._entry_id, {})
        if "polling" not in entry_data and not self._polling_gate.is_due(self.hass, self._entry_id):
            return
        try:
            shared = entry_data.get("polling")
            values = await (shared.read(self.hass, self._entry_id, "input", self._address, 1)
                            if shared else entry_data["client"].read_input_registers(self._address, 1))
            if values and values[0] != ViegaModbusClient.ERROR_SENTINEL:
                self.status = describe_error_code(values[0])
                self._attr_native_value = self.status
                if _LOGGER.isEnabledFor(logging.DEBUG):
                    _LOGGER.debug(
                        "Diagnostic %s (room=%s, register PDU=%s): code=%s -> %r",
                        self.name, self._room_id, self._address, values[0], self.status,
                    )
        except Exception:
            return

    @property
    def device_info(self):
        if self._entry_id is None:
            return None
        return build_device_info(self.hass, self._entry_id)
