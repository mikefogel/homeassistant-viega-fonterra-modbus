"""Diagnostic text entities for failed unit values."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .device import build_device_info

DEFAULT_STATUS = "error: sensor invalid"


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
        )
        for room_id, room_config in rooms.items()
    ]
    async_add_entities(entities)


class ViegaDiagnosticTextEntity(SensorEntity):
    """Represent a textual diagnosis entity for a failed sensor or unit."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry_id: str | None,
        name: str,
        status: str = DEFAULT_STATUS,
    ) -> None:
        self._entry_id = entry_id
        self.name = name
        self.status = status
        self._attr_unique_id = (
            f"{entry_id}_{name}_diagnostic" if entry_id is not None else None
        )
        self._attr_native_value = status

    @property
    def state(self) -> str:
        return self.status

    @property
    def device_info(self):
        if self._entry_id is None:
            return None
        return build_device_info(self.hass, self._entry_id)
