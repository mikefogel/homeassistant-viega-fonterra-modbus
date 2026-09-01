"""Diagnostic text entities for failed unit values."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up diagnostic text entities for known failure states."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    rooms = entry_data.get("rooms", {})

    entities = [
        ViegaDiagnosticTextEntity(entry.entry_id, f"{room_id}_diagnostic")
        for room_id in rooms.keys()
    ]
    async_add_entities(entities)


class ViegaDiagnosticTextEntity(SensorEntity):
    """Represent a textual diagnosis entity for a failed sensor or unit."""

    _attr_has_entity_name = True

    def __init__(
        self,
        first: str,
        second: str = "error: sensor invalid",
        third: str | None = None,
    ) -> None:
        if third is None:
            # Backwards-compatible compatibility: ViegaDiagnosticTextEntity(name, status)
            self._entry_id = None
            self.name = first
            self.status = second
        else:
            # Home Assistant entry-based setup: ViegaDiagnosticTextEntity(entry_id, name, status)
            self._entry_id = first
            self.name = second
            self.status = third

        self._attr_unique_id = (
            f"{self._entry_id}_{self.name}_diagnostic" if self._entry_id is not None else None
        )
        self._attr_native_value = self.status

    @property
    def state(self) -> str:
        return self.status

    @property
    def device_info(self):
        if self._entry_id is None:
            return None
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "Viega Fonterra Smart Control",
            "manufacturer": "Viega",
            "model": "Smart Control",
        }
