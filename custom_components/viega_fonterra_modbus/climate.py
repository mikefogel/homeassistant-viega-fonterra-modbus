"""Climate platform for room thermostats."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, MIN_SCAN_INTERVAL
from .device import build_device_info
from .polling import PollingGate
from .registers import (
    BASE_UNIT_REGISTERS,
    actor_registers,
    resolve_room_number,
    room_actor_numbers,
    room_registers,
)

SCAN_INTERVAL = timedelta(seconds=MIN_SCAN_INTERVAL)

_LOGGER = logging.getLogger(__name__)

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


class ViegaRoomClimateEntity(ClimateEntity, RestoreEntity):
    """Minimal Home Assistant climate implementation for a room thermostat."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = ["off", "heat", "cool"]
    _attr_translation_key = "room"

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
        room_number = resolve_room_number(room_id, room_config)
        defaults = room_registers(room_number) if room_number else {}
        actor_numbers = room_actor_numbers(room_config)
        actor = actor_registers(actor_numbers[0]) if actor_numbers else {}
        self._entry_id = entry_id
        self.room_id = room_id
        self._polling_gate = PollingGate()
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
                "flow_temperature_register", BASE_UNIT_REGISTERS["flow_temperature"]
            ),
            "return_temperature": room_config.get(
                "return_temperature_register", actor.get("return_temperature")
            ),
            "actuator_position": room_config.get(
                "actuator_position_register", actor.get("position")
            ),
            "operating_mode": room_config.get(
                "operating_mode_register", BASE_UNIT_REGISTERS["operating_mode"]
            ),
            "profile_mode": room_config.get(
                "profile_mode_register", BASE_UNIT_REGISTERS["profile_mode"]
            ),
            "error_code": room_config.get(
                "error_code_register", BASE_UNIT_REGISTERS["error_code"]
            ),
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

    async def async_added_to_hass(self) -> None:
        """Restore last known state on startup (spec.md 15).

        On system/integration restart we must NOT use a default, unavailable,
        or unknown state. The previous valid value must be retained exactly,
        so a restart is not visible through the displayed values - which for
        a Climate entity means not just current/target temperature but also
        the HVAC mode and preset mode (the entity's `state` and
        `preset_mode` attribute, both otherwise silently reset to this
        class's `__init__` defaults of "heat"/"manual" on every restart) and
        every value surfaced via `extra_state_attributes`.
        """
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in ("unknown", "unavailable"):
            return

        if last_state.state in {"off", "heat", "cool"}:
            self._operating_mode = {"off": 0, "heat": 1, "cool": 2}[last_state.state]

        attributes = last_state.attributes
        if attributes.get("current_temperature") is not None:
            self._attr_current_temperature = float(attributes["current_temperature"])
        if attributes.get("temperature") is not None:
            self._attr_target_temperature = float(attributes["temperature"])
        if attributes.get("preset_mode") in self.preset_modes:
            self._profile_mode = self.preset_modes.index(attributes["preset_mode"])
        if attributes.get("power_level") is not None:
            self._power_level = attributes["power_level"]
        if attributes.get("flow_temperature") is not None:
            self._flow_temperature = float(attributes["flow_temperature"])
        if attributes.get("return_temperature") is not None:
            self._return_temperature = float(attributes["return_temperature"])
        if attributes.get("actuator_position") is not None:
            self._actuator_position = attributes["actuator_position"]
        if attributes.get("base_unit_error_code") is not None:
            self._base_error_code = attributes["base_unit_error_code"]

    @property
    def hvac_mode(self) -> str:
        return {0: "off", 1: "heat", 2: "cool"}.get(self._operating_mode, "off")

    @property
    def min_temp(self) -> float:
        """Return the Viega-valid lower setpoint for the active mode."""
        return 16.0 if self.hvac_mode == "cool" else 5.0

    @property
    def max_temp(self) -> float:
        """Return the Viega-valid upper setpoint for the active mode."""
        return 30.0

    @property
    def target_temperature_step(self) -> float:
        """Viega room setpoints are specified in half-degree increments."""
        return 0.5

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
        if "polling" not in self.hass.data.get(DOMAIN, {}).get(self._entry_id, {}):
            if not self._polling_gate.is_due(self.hass, self._entry_id):
                return
        client = self.hass.data[DOMAIN][self._entry_id]["client"]
        values = await self._read_values(client)
        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "Room %s (%s): raw register values=%s registers(PDU)=%s",
                self.room_id,
                self._attr_name,
                values,
                self._registers,
            )
        current_temperature = self._scaled(values.get("current_temperature"))
        if current_temperature is not None:
            self._attr_current_temperature = current_temperature
        target_temperature = self._scaled(values.get("target_temperature"))
        if target_temperature is not None:
            self._attr_target_temperature = target_temperature
        self._power_level = self._valid(values.get("power_level"), self._power_level)
        flow_temperature = self._scaled(values.get("flow_temperature"))
        if flow_temperature is not None:
            self._flow_temperature = flow_temperature
        return_temperature = self._scaled(values.get("return_temperature"))
        if return_temperature is not None:
            self._return_temperature = return_temperature
        self._actuator_position = self._valid(
            values.get("actuator_position"), self._actuator_position
        )
        self._base_error_code = self._valid(values.get("error_code"), self._base_error_code)
        operating_mode = self._valid(values.get("operating_mode"), None)
        if operating_mode is not None:
            self._operating_mode = operating_mode
        profile_mode = self._valid(values.get("profile_mode"), None)
        if profile_mode is not None:
            self._profile_mode = profile_mode

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
                shared = self.hass.data[DOMAIN][self._entry_id].get("polling")
                result = await (
                    shared.read(
                        self.hass,
                        self._entry_id,
                        "holding" if name in {
                            "target_temperature",
                            "power_level",
                            "operating_mode",
                            "profile_mode",
                        }
                        else "input",
                        int(address),
                        1,
                    )
                    if shared
                    else reader(int(address), 1)
                )
                values[name] = result[0] if result else None
            except Exception:
                values[name] = None
        return values

    @staticmethod
    def _scaled(value: int | None) -> float | None:
        """Convert a raw tenths-of-a-degree register value, or `None` if the
        read failed or returned the `-99` error sentinel (spec.md 10) - the
        caller must keep its previous value in that case rather than divide
        `-99` by 10 into a fabricated `-9.9`.
        """
        return value / 10 if value is not None and value != -99 else None

    @staticmethod
    def _valid(value: int | None, previous: int | None) -> int | None:
        """Return `value` unless it is a failed read or the `-99` error
        sentinel, in which case the previous value is kept (spec.md 10):
        a failed/`-99` read must never overwrite a room's last known-good
        power level, actuator position, or error code with `None`/`-99`.
        """
        return value if value is not None and value != -99 else previous

    async def async_set_temperature(self, **kwargs) -> None:
        """Write the requested target temperature to the room register."""
        temperature = kwargs.get("temperature")
        target_register = self._registers["target_temperature"]
        if temperature is None or target_register is None:
            return

        temperature = float(temperature)
        low, high = (16, 30) if self.hvac_mode == "cool" else (5, 30)
        if not low <= temperature <= high:
            raise ValueError(f"target temperature must be between {low} and {high} °C")
        register_value = round(temperature * 10)

        client = self.hass.data[DOMAIN][self._entry_id]["client"]
        await client.write_register(int(target_register), register_value)
        self._attr_target_temperature = float(temperature)

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Write the operating mode to holding register 40001."""
        if hvac_mode not in self._attr_hvac_modes:
            raise ValueError(f"unsupported HVAC mode: {hvac_mode}")
        await self.hass.data[DOMAIN][self._entry_id]["client"].write_register(
            int(self._registers["operating_mode"]),
            {"off": 0, "heat": 1, "cool": 2}[hvac_mode],
        )
        self._operating_mode = {"off": 0, "heat": 1, "cool": 2}[hvac_mode]

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
        return build_device_info(self.hass, self._entry_id)