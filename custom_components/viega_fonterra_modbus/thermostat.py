"""Room thermostat models for Viega Fonterra Smart Control rooms."""

from __future__ import annotations


class ViegaRoomThermostatEntity:
    """Represent a room thermostat entity in Home Assistant terms."""

    def __init__(self, room_id: str, current_temperature: float, target_temperature: float) -> None:
        self.room_id = room_id
        self.current_temperature = current_temperature
        self.target_temperature = target_temperature

    @property
    def device_class(self) -> str:
        return "temperature"
