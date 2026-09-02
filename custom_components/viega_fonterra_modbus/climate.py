"""Climate platform for room thermostats."""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .registers import actor_registers, room_registers


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
            room_config,
        )
        for room_id, room_config in rooms.items()
    ]
    async_add_entities(entities)


class ViegaRoomClimateEntity(ClimateEntity):
    """Minimal Home Assistant climate implementation for a room thermostat."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = ["off", "heat"]
    def __init__(
        self,
        entry_id: str,
        room_id: str,
        room_name: str,
        current_temperature: float,
        target_temperature: float,
        room_config: dict[str, object] | int | None = None,
    ) -> None:
        if isinstance(room_config, int):
            room_config = {"target_temperature_register": room_config}
        room_config = room_config or {}
        room_number = int(room_config.get("room_number", 0))
        defaults = room_registers(room_number) if room_number else {}
        actor_number = room_config.get("actor")
        if isinstance(actor_number, list):
            actor_number = actor_number[0] if actor_number else None
        actor = actor_registers(int(actor_number)) if actor_number else {}
        self._entry_id = entry_id
        self.room_id = room_id
        self._attr_unique_id = f"{entry_id}_{room_id}_thermostat"
        self._attr_name = room_name
        self._attr_current_temperature = current_temperature
        self._attr_target_temperature = target_temperature
        self._registers = {
            **defaults,
            "target_temperature": room_config.get(
                "target_temperature_register", defaults.get("target_temperature")
            ),
            "power_level": room_config.get(
                "power_level_register", defaults.get("power_level")
            ),
            "flow_temperature": room_config.get(
                "flow_temperature_register", 24
            ),
            "return_temperature": room_config.get(
                "return_temperature_register", actor.get("return_temperature")
            ),
            "actuator_position": room_config.get(
                "actuator_position_register", actor.get("position")
            ),
            "operating_mode": room_config.get("operating_mode_register", 0),
            "profile_mode": room_config.get("profile_mode_register", 1),
            "error_code": room_config.get("error_code_register", 23),
        }
        self.room_number = room_number or room_config.get("room_id", room_id)
        self._power_level: int | None = None
        self._flow_temperature: float | None = None
        self._return_temperature: float | None = None
        self._actuator_position: int | None = None
        self._base_error_code: int | None = None
        self._operating_mode = 1
        self._profile_mode = 0
        supported_features = ClimateEntityFeature(0)
        if self._registers["target_temperature"] is not None:
            supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE
        if self._registers["profile_mode"] is not None:
            supported_features |= ClimateEntityFeature.PRESET_MODE
        self._attr_supported_features = supported_features

    @property
    def hvac_mode(self) -> str:
        return "heat" if self._operating_mode else "off"

    @property
    def preset_modes(self) -> list[str]:
        return ["manual", "profile", "setback"]

    @property
    def preset_mode(self) -> str:
        return self.preset_modes[self._profile_mode] if self._profile_mode in range(3) else "manual"

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        return {
            "room_id": self.room_number,
            "power_level": self._power_level,
            "flow_temperature": self._flow_temperature,
            "return_temperature": self._return_temperature,
            "actuator_position": self._actuator_position,
            "base_unit_error_code": self._base_error_code,
        }

    async def async_update(self) -> None:
        """Read room and controller values from the documented registers."""
        client = self.hass.data[DOMAIN][self._entry_id]["client"]
        values = await self._read_values(client)
        if values.get("current_temperature") is not None:
            self._attr_current_temperature = values["current_temperature"] / 10
        if values.get("target_temperature") is not None:
            self._attr_target_temperature = values["target_temperature"] / 10
        self._power_level = values.get("power_level")
        self._flow_temperature = self._scaled(values.get("flow_temperature"))
        self._return_temperature = self._scaled(values.get("return_temperature"))
        self._actuator_position = values.get("actuator_position")
        self._base_error_code = values.get("error_code")
        if values.get("operating_mode") is not None:
            self._operating_mode = values["operating_mode"]
        if values.get("profile_mode") is not None:
            self._profile_mode = values["profile_mode"]

    async def _read_values(self, client) -> dict[str, int | None]:
        values: dict[str, int | None] = {}
        for name, address in self._registers.items():
            if address is None:
                continue
            try:
                reader = (
                    client.read_holding_registers
                    if name in {"target_temperature", "power_level", "operating_mode", "profile_mode"}
                    else client.read_input_registers
                )
                result = await reader(int(address), 1)
                values[name] = result[0] if result else None
            except Exception:
                values[name] = None
        return values

    @staticmethod
    def _scaled(value: int | None) -> float | None:
        return value / 10 if value is not None and value != -99 else None

    async def async_set_temperature(self, **kwargs) -> None:
        """Write the requested target temperature to the room register."""
        temperature = kwargs.get("temperature")
        target_register = self._registers["target_temperature"]
        if temperature is None or target_register is None:
            return

        register_value = round(float(temperature) * 10)
        if not 0 <= register_value <= 65535:
            raise ValueError("target temperature is outside the register range")

        client = self.hass.data[DOMAIN][self._entry_id]["client"]
        await client.write_register(int(target_register), register_value)
        self._attr_target_temperature = float(temperature)

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Write the operating mode to holding register 40001."""
        if hvac_mode not in self._attr_hvac_modes:
            raise ValueError(f"unsupported HVAC mode: {hvac_mode}")
        await self.hass.data[DOMAIN][self._entry_id]["client"].write_register(
            int(self._registers["operating_mode"]), 1 if hvac_mode == "heat" else 0
        )
        self._operating_mode = 1 if hvac_mode == "heat" else 0

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Write the profile mode to holding register 40002."""
        if preset_mode not in self.preset_modes:
            raise ValueError(f"unsupported preset mode: {preset_mode}")
        value = self.preset_modes.index(preset_mode)
        await self.hass.data[DOMAIN][self._entry_id]["client"].write_register(
            int(self._registers["profile_mode"]), value
        )
        self._profile_mode = value

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._entry_id)},
            "name": "Viega Fonterra Smart Control",
            "manufacturer": "Viega",
            "model": "Smart Control",
        }
