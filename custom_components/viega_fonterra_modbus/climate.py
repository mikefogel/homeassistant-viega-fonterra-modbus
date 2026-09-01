"""Climate platform for room thermostats."""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up climate entities for rooms configured in the registry."""
    entry_data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    rooms = entry_data.get("rooms", {})

    entities = [
        ViegaRoomClimateEntity(
            entry.entry_id,
            room_id,
            room_config.get("name", room_id) if isinstance(room_config, dict) else room_id,
            21.5,
            22.0,
        )
        for room_id, room_config in rooms.items()
    ]
    async_add_entities(entities)


class ViegaRoomClimateEntity(ClimateEntity):
    """Minimal Home Assistant climate implementation for a room thermostat."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = ["heat"]
    _attr_supported_features = 0

    def __init__(
        self,
        entry_id: str,
        room_id: str,
        room_name: str,
        current_temperature: float,
        target_temperature: float,
    ) -> None:
        self._entry_id = entry_id
        self.room_id = room_id
        self._attr_unique_id = f"{entry_id}_{room_id}_thermostat"
        self._attr_name = room_name
        self._attr_current_temperature = current_temperature
        self._attr_target_temperature = target_temperature

    @property
    def hvac_mode(self) -> str:
        return "heat"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "Viega Fonterra Smart Control",
            "manufacturer": "Viega",
            "model": "Smart Control",
        }
