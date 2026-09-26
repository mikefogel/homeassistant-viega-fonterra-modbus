"""Sensor platform for the Viega Fonterra Modbus integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from types import SimpleNamespace

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, MIN_SCAN_INTERVAL
from .device import build_device_info
from .diagnostic import ViegaDiagnosticTextEntity, _room_error_address
from .entity_tracking import register_platform
from .modbus_handler import ViegaModbusClient
from .polling import PollingGate
from .registers import (
    BASE_UNIT_REGISTERS,
    actor_registers,
    describe_error_code,
    decode_text_registers,
    room_actor_numbers,
)

SCAN_INTERVAL = timedelta(seconds=MIN_SCAN_INTERVAL)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities,
) -> None:
    """Set up the sensor entities from a config entry.

    Does *not* instantiate `REGISTER_DEFINITIONS` (temperature_flow/return/
    room, system_pressure, pump_state) as live entities: those addresses
    (1000/1001/1002/1010/1020) are illustrative placeholders from spec.md 9's
    initial/example register schema, not real Viega registers - the actual
    device map (confirmed against `Fonterra Smart Control-de-DE.pdf`) only
    spans roughly PDU 0-285. Creating entities at those addresses against
    real hardware reads undefined registers, producing wrong or unavailable
    values. `ViegaRegisterSensor`/`REGISTER_DEFINITIONS` remain available for
    genuinely mapped registers to be added later.
    """
    entities: list[SensorEntity] = []

    rooms = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("rooms", {})
    identity = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("identity", {})

    entities.extend(
        _identity_entity(entry, key, address, count, text, identity)
        for key, address, count, text in (
            (
                "wlan_serial_number",
                BASE_UNIT_REGISTERS["wlan_serial_number"],
                5,
                True,
            ),
            (
                "base_unit_serial_number",
                BASE_UNIT_REGISTERS["base_unit_serial_number"],
                5,
                True,
            ),
            (
                "base_unit_name",
                BASE_UNIT_REGISTERS["base_unit_name"],
                12,
                True,
            ),
            (
                "base_unit_error_code",
                BASE_UNIT_REGISTERS["error_code"],
                1,
                False,
            ),
        )
    )

    entities.append(
        ViegaBaseUnitTemperatureSensor(
            entry.entry_id,
            "flow_temperature",
            BASE_UNIT_REGISTERS["flow_temperature"],
        )
    )

    entities.extend(
        ViegaConnectionHealthSensor(entry.entry_id, metric_key)
        for metric_key in ViegaConnectionHealthSensor.METRIC_KEYS
    )

    registry = register_platform(hass, entry.entry_id, "sensor", async_add_entities)
    for room_id, room_config in rooms.items():
        registry.add_room(room_id, build_room_entities(entry.entry_id, room_id, room_config))

    if _LOGGER.isEnabledFor(logging.DEBUG):
        _LOGGER.debug(
            "Entry %s: sensor platform created %d entities: %s",
            entry.entry_id, len(entities), [e.unique_id for e in entities if hasattr(e, "unique_id")],
        )
    async_add_entities(entities)


def build_room_entities(entry_id: str, room_id: str, room_config: object) -> list[SensorEntity]:
    """Build every sensor-platform entity a single room contributes.

    Shared by the initial `async_setup_entry` above and by the explicit
    rediscovery action (`rediscovery.py`, spec.md 16a), which needs to
    (re)build just one room's entities after a live topology change without
    reloading the whole config entry.
    """
    if not isinstance(room_config, dict):
        return []
    room_name = room_config.get("name", room_id)
    entities: list[SensorEntity] = list(
        _actor_temperature_sensors(SimpleNamespace(entry_id=entry_id), {room_id: room_config})
    )
    entities.append(
        ViegaDiagnosticTextEntity(
            entry_id,
            f"{room_name} diagnostic",
            room_id=room_id,
            address=_room_error_address(room_id, room_config),
            room_name=room_name,
        )
    )
    return entities


def _identity_entity(entry, key, address, count, text, identity):
    entity = ViegaBaseUnitIdentitySensor(entry, key, address, count, text)
    if isinstance(identity, dict) and identity.get(key) is not None:
        entity._attr_native_value = identity[key]
    return entity


def _actor_temperature_sensors(
    entry: ConfigEntry, rooms: dict[str, object]
) -> list["ViegaActorLinkedSensor"]:
    """Build a return-temperature sensor for every actuator of every room.

    Every actuator (the room's primary one and any additional actuators in
    a multi-actor room, spec.md 4) gets its own linked temperature sensor
    for its Rücklauftemperatur register (manual 30251/30254/...), not just
    the extra actuators beyond the first - spec.md 5a requires "Show
    actuator return temperature" as a linked entity for the room, and the
    Climate entity only ever tracks the primary actuator's value as an
    attribute (climate.py), which is not a substitute for a real entity.
    Actuator *position* is exposed separately as a binary sensor
    (binary_sensor.py), matching the manual's 0=closed/1=open encoding
    rather than a percentage.
    """

    sensors: list[ViegaActorLinkedSensor] = []
    for room_id, room_config in rooms.items():
        if not isinstance(room_config, dict):
            continue
        room_name = room_config.get("name", room_id)
        for actor_number in room_actor_numbers(room_config):
            try:
                registers = actor_registers(actor_number)
            except ValueError:
                continue
            sensors.append(
                ViegaActorLinkedSensor(
                    entry.entry_id,
                    room_id,
                    actor_number,
                    "return_temperature",
                    room_name,
                    registers["return_temperature"],
                    unit=UnitOfTemperature.CELSIUS,
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


class ViegaBaseUnitIdentitySensor(SensorEntity, RestoreEntity):
    """Expose base-unit identity and error registers as diagnostic sensors."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        entry: ConfigEntry,
        sensor_key: str,
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

        # No _attr_name here: sensor_key matches a translations/*.json
        # entity.sensor.<key>.name entry 1:1, so Home Assistant's
        # translation_key mechanism supplies the localized name instead of a
        # hardcoded English string (spec.md "localize every entity name").
        self._attr_translation_key = sensor_key
        self._attr_native_value = None
        initial = getattr(entry, "options", {}).get("_identity", {}).get(sensor_key)
        if initial is not None:
            self._attr_native_value = initial
        self.last_error_message = ""

        self._polling_gate = PollingGate()

    async def async_added_to_hass(self) -> None:
        """Restore the last known value across restarts (spec.md 15)."""
        await super().async_added_to_hass()
        if self._attr_native_value is not None:
            return
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in ("unknown", "unavailable"):
            return
        if self._text:
            self._attr_native_value = last_state.state
        else:
            try:
                value = int(last_state.state)
            except (TypeError, ValueError):
                return
            self._attr_native_value = value
            if self._sensor_key == "base_unit_error_code":
                self._attr_extra_state_attributes = {
                    "description": describe_error_code(value)
                }

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


class ViegaActorLinkedSensor(SensorEntity, RestoreEntity):
    """Expose a register linked to one of a room's actuators."""

    _attr_has_entity_name = True

    def __init__(
        self,
        entry_id: str,
        room_id: str,
        actor_number: int,
        kind: str,
        room_name: str,
        address: int,
        unit: str | None = None,
        scale: int | None = None,
    ) -> None:
        self._entry_id = entry_id
        self._address = address
        self._scale = scale
        self._attr_unique_id = f"{entry_id}_{room_id}_actor{actor_number}_{kind}"
        # translation_key "actuator_<kind>" (e.g. "actuator_return_temperature")
        # matches a translations/*.json entity.sensor entry whose name string
        # uses the {room}/{actor} placeholders below.
        self._attr_translation_key = f"actuator_{kind}"
        self._attr_translation_placeholders = {
            "room": str(room_name),
            "actor": str(actor_number),
        }
        self._attr_native_unit_of_measurement = unit
        self._attr_native_value = None
        if unit == UnitOfTemperature.CELSIUS:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            self._attr_state_class = SensorStateClass.MEASUREMENT
        self._polling_gate = PollingGate()

    async def async_added_to_hass(self) -> None:
        """Restore the last known value across restarts (spec.md 15)."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in ("unknown", "unavailable"):
            return
        try:
            self._attr_native_value = float(last_state.state)
        except (TypeError, ValueError):
            return

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


class ViegaBaseUnitTemperatureSensor(SensorEntity, RestoreEntity):
    """Expose a base-unit-level temperature register (e.g. manifold flow).

    Unlike room/actuator registers, this value is measured once for the
    whole base unit (manual 30025 "Vorlauftemperatur", page 89) and is
    therefore a single entity on the module's device, not one per room -
    climate.py's per-room `flow_temperature` attribute reads the same
    shared register redundantly for convenience, but this is the entity
    spec.md 5a requires ("Show manifold flow temperature | Linked
    temperature sensor").
    """

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    def __init__(self, entry_id: str, sensor_key: str, address: int) -> None:
        self._entry_id = entry_id
        self._address = address
        self._attr_unique_id = f"{entry_id}_{sensor_key}"
        self._attr_translation_key = sensor_key
        self._attr_native_value = None
        self._polling_gate = PollingGate()

    async def async_added_to_hass(self) -> None:
        """Restore the last known value across restarts (spec.md 15)."""
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is None or last_state.state in ("unknown", "unavailable"):
            return
        try:
            self._attr_native_value = float(last_state.state)
        except (TypeError, ValueError):
            return

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

        self._attr_native_value = values[0] / 10

    @property
    def device_info(self):
        return build_device_info(self.hass, self._entry_id)


class ViegaConnectionHealthSensor(SensorEntity):
    """One connection-health metric, read straight off the shared client's
    own bookkeeping (spec.md 16b) - no register read of its own is ever
    issued for this entity, since every metric is already a byproduct of
    whatever other entity most recently used the shared connection.

    Not a `RestoreEntity`: the metrics live on `ViegaModbusClient`, a fresh
    instance created on every setup, so they always start back at their
    natural defaults (`None`/`0`) when the integration reloads or Home
    Assistant restarts - restoring a stale prior value here would disagree
    with that fresh client state and could never be corrected until the
    metric changes again.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    #: Every metric this entity can expose, and how to present it. Matches
    #: the attribute names `ViegaModbusClient` tracks them under 1:1.
    METRIC_KEYS = (
        "last_success_time",
        "last_failure_time",
        "consecutive_failures",
        "invalid_value_count",
        "last_exception_code",
        "last_success_duration",
    )
    _DEVICE_CLASS = {
        "last_success_time": SensorDeviceClass.TIMESTAMP,
        "last_failure_time": SensorDeviceClass.TIMESTAMP,
    }
    _UNIT = {"last_success_duration": UnitOfTime.SECONDS}
    _STATE_CLASS = {
        "consecutive_failures": SensorStateClass.MEASUREMENT,
        "invalid_value_count": SensorStateClass.TOTAL_INCREASING,
        "last_success_duration": SensorStateClass.MEASUREMENT,
    }

    def __init__(self, entry_id: str, metric_key: str) -> None:
        self._entry_id = entry_id
        self._metric_key = metric_key
        self._attr_unique_id = f"{entry_id}_health_{metric_key}"
        self._attr_translation_key = f"health_{metric_key}"
        self._attr_device_class = self._DEVICE_CLASS.get(metric_key)
        self._attr_native_unit_of_measurement = self._UNIT.get(metric_key)
        self._attr_state_class = self._STATE_CLASS.get(metric_key)
        self._attr_native_value = None

    async def async_update(self) -> None:
        """Copy the current metric value off the shared client.

        Deliberately not gated by a `PollingGate`: there is nothing to
        throttle since reading these attributes never touches the wire
        (spec.md 16b "without an additional polling request").
        """
        client = self.hass.data[DOMAIN][self._entry_id]["client"]
        self._attr_native_value = getattr(client, self._metric_key, None)

    @property
    def device_info(self):
        return build_device_info(self.hass, self._entry_id)