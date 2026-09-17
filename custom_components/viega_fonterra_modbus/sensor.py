"""Sensor platform for the Viega Fonterra Modbus integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant

from .const import DOMAIN, MIN_SCAN_INTERVAL
from .device import build_device_info
from .diagnostic import ViegaDiagnosticTextEntity
from .modbus_handler import ViegaModbusClient
from .polling import PollingGate
from .registers import (
    BASE_UNIT_REGISTERS,
    REGISTER_DEFINITIONS,
    actor_registers,
    describe_error_code,
    resolve_room_number,
    decode_text_registers,
)

SCAN_INTERVAL = timedelta(seconds=MIN_SCAN_INTERVAL)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the sensor entities from a config entry."""

    # First, set up regular sensors (existing logic)
    entities = [
        ViegaRegisterSensor(
            entry,
            sensor_key,
            details["name"],
            details["unit"],
            details["address"],
        )
        for sensor_key, details in REGISTER_DEFINITIONS.items()
    ]

    rooms = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("rooms", {})
    identity = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("identity", {})

    entities.extend(
        _identity_entity(entry, key, name, address, count, text, identity)
        for key, name, address, count, text in (
            (
                "wlan_serial_number",
                "WLAN module serial number",
                BASE_UNIT_REGISTERS["wlan_serial_number"],
                5,
                True,
            ),
            (
                "base_unit_serial_number",
                "Base unit serial number",
                BASE_UNIT_REGISTERS["base_unit_serial_number"],
                5,
                True,
            ),
            (
                "base_unit_name",
                "Base unit name",
                BASE_UNIT_REGISTERS["base_unit_name"],
                12,
                True,
            ),
            (
                "base_unit_error_code",
                "Base unit error code",
                BASE_UNIT_REGISTERS["error_code"],
                1,
                False,
            ),
        )
    )

    entities.extend(_extra_actor_sensors(entry, rooms))

    # NEW: Add diagnostic text entities
    rooms = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("rooms", {})
    entities.extend(
        ViegaDiagnosticTextEntity(
            entry.entry_id,
            f"{room_config.get('name', room_id)} diagnostic",
            room_id=room_id,
        )
        for room_id, room_config in rooms.items()
    )

    async_add_entities(entities)


def _identity_entity(entry, key, name, address, count, text, identity):
    entity = ViegaBaseUnitIdentitySensor(entry, key, name, address, count, text)
    if isinstance(identity, dict) and identity.get(key) is not None:
        entity._attr_native_value = identity[key]
    return entity


def _extra_actor_sensors(entry: ConfigEntry, rooms: dict[str, object]) -> list["ViegaActorLinkedSensor"]:
    """Build linked sensors for actuators beyond the first in a multi-actor room."""

    sensors: list[ViegaActorLinkedSensor] = []
    for room_id, room_config in rooms.items():
        if not isinstance(room_config, dict):
            continue
        actors = room_config.get("actor")
        if not isinstance(actors, list) or len(actors) <= 1:
            continue
        room_name = room_config.get("name", room_id)
        for actor_number in actors[1:]:
            try:
                actor_number = int(actor_number)
                registers = actor_registers(actor_number)
            except (TypeError, ValueError):
                continue
            sensors.append(
                ViegaActorLinkedSensor(
                    entry.entry_id,
                    room_id,
                    actor_number,
                    "position",
                    f"{room_name} actuator {actor_number} position",
                    registers["position"],
                    unit="%",
                )
            )
            sensors.append(
                ViegaActorLinkedSensor(
                    entry.entry_id,
                    room_id,
                    actor_number,
                    "return_temperature",
                    f"{room_name} actuator {actor_number} return temperature",
                    registers["return_temperature"],
                    unit="°C",
                    scale=10,
                )
            )
    return sensors


class ViegaRegisterSensor(SensorEntity):
    """Expose a register-backed sensor entity."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry: ConfigEntry,
        sensor_key: str,
        name: str,
        unit: str | None,
        address: int,
    ) -> None:
        self._entry_id = entry.entry_id
        self._sensor_key = sensor_key
        self._attr_unique_id = f"{entry.entry_id}_{sensor_key}"
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._address = address
        self._attr_native_value = 0
        self.last_error_message = ""

        self._polling_gate = PollingGate()

    async def async_update(self) -> None:
        """Read the current register value from the Modbus client."""

        if not self._polling_gate.is_due(self.hass, self._entry_id):
            return

        client = self.hass.data[DOMAIN].get(self._entry_id, {}).get("client")
        if client is None:
            self._attr_native_value = 0
            self.last_error_message = "error: communication timeout"
            return

        try:
            shared = self.hass.data[DOMAIN][self._entry_id].get("polling")
            values = await (shared.read(self.hass, self._entry_id, "holding", self._address, 1)
                            if shared else client.read_holding_registers(self._address, 1))
        except Exception:
            self.last_error_message = "error: communication timeout"
            return

        if not values:
            self.last_error_message = "error: sensor invalid"
            return

        value = values[0]
        if value == ViegaModbusClient.ERROR_SENTINEL:
            self.last_error_message = "error: sensor invalid"
            return

        self.last_error_message = ""
        self._attr_native_value = value

    @property
    def state(self) -> str:
        """Return the current sensor reading."""
        return self._attr_native_value

    @property
    def unique_id(self) -> str:
        return self._attr_unique_id

    @property
    def icon(self) -> str:
        if "temperature" in self._sensor_key:
            return "mdi:thermometer"
        if "pressure" in self._sensor_key:
            return "mdi:gauge"
        return "mdi:information-outline"

    @property
    def device_info(self):
        return build_device_info(self.hass, self._entry_id)


class ViegaBaseUnitIdentitySensor(SensorEntity):
    """Expose base-unit identity and error registers as diagnostic sensors."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        entry: ConfigEntry,
        sensor_key: str,
        name: str,
        address: int,
        count: int,
        text: bool,
    ) -> None:
        self._entry_id = entry.entry_id
        self._sensor_key = sensor_key
        self._address = address
        self._count = count
        self._text = text
        self._attr_unique_id = f"{entry.entry_id}_{sensor_key}"

        self._attr_name = name
        self._attr_native_value = None
        initial = getattr(entry, "options", {}).get("_identity", {}).get(sensor_key)
        if initial is not None:
            self._attr_native_value = initial
        self.last_error_message = ""

        self._polling_gate = PollingGate()

    async def async_update(self) -> None:
        """Read and decode the identity or base-unit error register."""

        if not self._polling_gate.is_due(self.hass, self._entry_id):
            return

        client = self.hass.data[DOMAIN][self._entry_id]["client"]
        try:
            shared = self.hass.data[DOMAIN][self._entry_id].get("polling")

            values = await (shared.read(self.hass, self._entry_id, "input", self._address, self._count)
                            if shared else client.read_input_registers(self._address, self._count))
        except Exception:
            self.last_error_message = "error: communication timeout"
            return

        if not values or values[0] == ViegaModbusClient.ERROR_SENTINEL:
            self.last_error_message = "error: sensor invalid"
            return

        if self._text:
            self._attr_native_value = decode_text_registers(values)
        else:
            self._attr_native_value = values[0]

            if self._sensor_key == "base_unit_error_code":
                self._attr_extra_state_attributes = {
                    "description": describe_error_code(values[0])
                }

        self.last_error_message = ""

    @property
    def device_info(self):
        return build_device_info(self.hass, self._entry_id)


class ViegaActorLinkedSensor(SensorEntity):
    """Expose a register for an actuator beyond the first in a room."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry_id: str,
        room_id: str,
        actor_number: int,
        kind: str,
        name: str,
        address: int,
        unit: str | None = None,
        scale: int | None = None,
    ) -> None:
        self._entry_id = entry_id
        self._address = address
        self._scale = scale
        self._attr_unique_id = f"{entry_id}_{room_id}_actor{actor_number}_{kind}"
        self._attr_name = name
        self._attr_native_unit_of_measurement = unit
        self._attr_native_value = None
        self._polling_gate = PollingGate()

    async def async_update(self) -> None:
        if not self._polling_gate.is_due(self.hass, self._entry_id):
            return

        client = self.hass.data[DOMAIN][self._entry_id]["client"]
        try:
            shared = self.hass.data[DOMAIN][self._entry_id].get("polling")

            values = await (shared.read(self.hass, self._entry_id, "input", self._address, 1)
                            if shared else client.read_input_registers(self._address, 1))
        except Exception:
            return

        if not values or values[0] == ViegaModbusClient.ERROR_SENTINEL:
            return

        value = values[0]
        self._attr_native_value = value / self._scale if self._scale else value

    @property
    def device_info(self):
        return build_device_info(self.hass, self._entry_id)