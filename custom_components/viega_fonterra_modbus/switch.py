"""Switch platform for simple Fonterra actuators."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


class ViegaBasicSwitch:
    """A simple switch model for direct actuator logic."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.is_on = False

    def turn_on(self) -> None:
        """Turn the switch on."""
        self.is_on = True

    def turn_off(self) -> None:
        """Turn the switch off."""
        self.is_on = False


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up switch entities for room actuators."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    rooms = entry_data.get("rooms", {})

    entities = [
        ViegaBasicSwitchEntity(
            entry.entry_id,
            room_config.get("name", room_id) if isinstance(room_config, dict) else room_id,
            False,
        )
        for room_id, room_config in rooms.items()
    ]
    async_add_entities(entities)


class ViegaBasicSwitchEntity(SwitchEntity):
    """A minimal switch entity for the simplest actuator controls."""

    _attr_has_entity_name = True

    def __init__(self, entry_id: str, name: str, is_on: bool = False) -> None:
        self._entry_id = entry_id
        self._attr_unique_id = f"{entry_id}_{name}"
        self._attr_name = name
        self._attr_is_on = is_on

    async def async_turn_on(self, **kwargs):
        self._attr_is_on = True

    async def async_turn_off(self, **kwargs):
        self._attr_is_on = False

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "Viega Fonterra Smart Control",
            "manufacturer": "Viega",
            "model": "Smart Control",
        }
