"""Tests for the sensor platform's entity classes beyond the basic
ViegaRegisterSensor happy-path already covered in test_modbus_handler.py.
"""

import asyncio
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.modbus_handler import ViegaModbusClient
from custom_components.viega_fonterra_modbus.registers import describe_error_code
from custom_components.viega_fonterra_modbus.sensor import (
    ViegaActorLinkedSensor,
    ViegaBaseUnitIdentitySensor,
    ViegaBaseUnitTemperatureSensor,
    ViegaRegisterSensor,
    _actor_temperature_sensors,
    async_setup_entry,
)


class _FakeInputClient:
    def __init__(self, values):
        self._values = values

    async def read_input_registers(self, address, count=1):
        return self._values


class _RaisingClient:
    async def read_input_registers(self, address, count=1):
        raise RuntimeError("device offline")


def _identity_sensor(sensor_key, address, count, text, client) -> ViegaBaseUnitIdentitySensor:
    entry = SimpleNamespace(entry_id="entry_1")
    sensor = ViegaBaseUnitIdentitySensor(entry, sensor_key, address, count, text)
    sensor.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": client}}})
    return sensor


def test_identity_sensor_name_is_localized_via_translation_key():
    """spec.md "localize every entity name": sensor_key matches a
    translations/*.json entity.sensor.<key>.name entry 1:1."""
    sensor = _identity_sensor("base_unit_name", 10, 12, True, _FakeInputClient([]))

    assert not hasattr(sensor, "_attr_name")
    assert sensor._attr_translation_key == "base_unit_name"


def test_actor_linked_sensor_name_is_localized_via_translation_key():
    sensor = ViegaActorLinkedSensor(
        "entry_1", "room_1", 2, "return_temperature", "Wohnzimmer", 250, unit="°C", scale=10
    )

    assert not hasattr(sensor, "_attr_name")
    assert sensor._attr_translation_key == "actuator_return_temperature"
    assert sensor._attr_translation_placeholders == {"room": "Wohnzimmer", "actor": "2"}


def test_base_unit_temperature_sensor_name_is_localized_via_translation_key():
    sensor = ViegaBaseUnitTemperatureSensor("entry_1", "flow_temperature", 25)

    assert not hasattr(sensor, "_attr_name")
    assert sensor._attr_translation_key == "flow_temperature"


def test_text_field_decodes_big_endian_ascii_and_strips_padding():
    """spec.md 3a: two ASCII chars per register, big-endian, padding stripped."""
    raw = b"Fonterra\x00\x00\x00\x00"
    values = [int.from_bytes(raw[i : i + 2], "big") for i in range(0, len(raw), 2)]
    sensor = _identity_sensor("base_unit_name", 10, len(values), True, _FakeInputClient(values))

    asyncio.run(sensor.async_update())

    assert sensor._attr_native_value == "Fonterra"


def test_error_code_sensor_stores_raw_code_and_unknown_description():
    sensor = _identity_sensor(
        "base_unit_error_code", 24, 1, False, _FakeInputClient([99])
    )

    asyncio.run(sensor.async_update())

    assert sensor._attr_native_value == 99
    assert sensor._attr_extra_state_attributes == {"description": "Unknown error (code 99)"}


def test_error_code_sensor_reports_no_error_for_zero():
    sensor = _identity_sensor(
        "base_unit_error_code", 23, 1, False, _FakeInputClient([0])
    )

    asyncio.run(sensor.async_update())

    assert sensor._attr_native_value == 0
    assert sensor._attr_extra_state_attributes == {"description": "No error"}


def test_identity_sensor_keeps_last_value_on_error_sentinel():
    sensor = _identity_sensor(
        "base_unit_error_code",
        23,
        1,
        False,
        _FakeInputClient([ViegaModbusClient.ERROR_SENTINEL]),
    )
    sensor._attr_native_value = 3

    asyncio.run(sensor.async_update())

    assert sensor._attr_native_value == 3
    assert sensor.last_error_message == "error: sensor invalid"


def test_identity_sensor_keeps_last_value_on_communication_failure():
    sensor = _identity_sensor("wlan_serial_number", 0, 5, True, _RaisingClient())
    sensor._attr_native_value = "OLD-SERIAL"

    asyncio.run(sensor.async_update())

    assert sensor._attr_native_value == "OLD-SERIAL"
    assert sensor.last_error_message == "error: communication timeout"


def test_actor_linked_sensor_applies_scale():
    sensor = ViegaActorLinkedSensor(
        "entry_1", "room_1", 2, "return_temperature", "name", 250, unit="°C", scale=10
    )
    sensor.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": _FakeInputClient([215])}}})

    asyncio.run(sensor.async_update())

    assert sensor._attr_native_value == 21.5


def test_actor_linked_sensor_ignores_the_error_sentinel():
    sensor = ViegaActorLinkedSensor(
        "entry_1", "room_1", 2, "return_temperature", "name", 250, unit="°C", scale=10
    )
    sensor.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": _FakeInputClient([ViegaModbusClient.ERROR_SENTINEL])}}}
    )

    asyncio.run(sensor.async_update())

    assert sensor._attr_native_value is None


def test_actor_temperature_sensors_created_for_every_actuator_in_a_room():
    """spec.md 5a: every actuator's return temperature is a linked sensor,
    not just the extra actuators beyond the primary one (spec.md 4)."""
    entry = SimpleNamespace(entry_id="entry_1")
    rooms = {"room_1": {"name": "Wohnzimmer", "actor": [1, 2, 3]}}

    sensors = _actor_temperature_sensors(entry, rooms)

    unique_ids = {s._attr_unique_id for s in sensors}
    assert unique_ids == {
        "entry_1_room_1_actor1_return_temperature",
        "entry_1_room_1_actor2_return_temperature",
        "entry_1_room_1_actor3_return_temperature",
    }


def test_actor_temperature_sensors_created_for_a_single_actor_room():
    entry = SimpleNamespace(entry_id="entry_1")
    rooms = {"room_1": {"name": "Wohnzimmer", "actor": 1}}

    sensors = _actor_temperature_sensors(entry, rooms)

    assert {s._attr_unique_id for s in sensors} == {
        "entry_1_room_1_actor1_return_temperature"
    }


def test_base_unit_temperature_sensor_applies_scale():
    sensor = ViegaBaseUnitTemperatureSensor("entry_1", "flow_temperature", 25)
    sensor.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": _FakeInputClient([264])}}})

    asyncio.run(sensor.async_update())

    assert sensor._attr_native_value == 26.4


def test_base_unit_temperature_sensor_ignores_the_error_sentinel():
    sensor = ViegaBaseUnitTemperatureSensor("entry_1", "flow_temperature", 25)
    sensor.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": _FakeInputClient([ViegaModbusClient.ERROR_SENTINEL])}}}
    )

    asyncio.run(sensor.async_update())

    assert sensor._attr_native_value is None


def test_register_sensor_icon_reflects_sensor_kind():
    entry = SimpleNamespace(entry_id="entry_1")

    temperature = ViegaRegisterSensor(entry, "temperature_flow", "Flow temperature", "°C", 1000)
    pressure = ViegaRegisterSensor(entry, "system_pressure", "System pressure", "bar", 1010)
    other = ViegaRegisterSensor(entry, "pump_state", "Pump state", None, 1020)

    assert temperature.icon == "mdi:thermometer"
    assert pressure.icon == "mdi:gauge"
    assert other.icon == "mdi:information-outline"


def test_register_sensor_device_info_uses_the_configured_device_name():
    entry = SimpleNamespace(entry_id="entry_1")
    sensor = ViegaRegisterSensor(entry, "temperature_flow", "Flow temperature", "°C", 1000)
    sensor.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"device_name": "Heizung Wohnzimmer"}}}
    )

    assert sensor.device_info["name"] == "Heizung Wohnzimmer"


def test_setup_entry_does_not_create_the_placeholder_register_definitions_sensors():
    """REGISTER_DEFINITIONS (temperature_flow/return/room, system_pressure,
    pump_state at addresses 1000-1020) are spec.md 9 illustrative
    placeholders, not real Viega registers - the actual device map
    (confirmed against `Fonterra Smart Control-de-DE.pdf`) only spans
    roughly PDU 0-285. They must not be instantiated as live entities that
    read undefined registers on real hardware."""
    hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"rooms": {}, "identity": {}}}})
    entry = SimpleNamespace(entry_id="entry_1")
    added: list = []

    asyncio.run(async_setup_entry(hass, entry, added.extend))

    sensor_keys = {getattr(entity, "_sensor_key", None) for entity in added}
    assert sensor_keys.isdisjoint(
        {"temperature_flow", "temperature_return", "temperature_room", "system_pressure", "pump_state"}
    )


def test_setup_entry_creates_the_base_unit_flow_temperature_sensor():
    """spec.md 5a: manifold flow temperature is a single, device-level
    linked sensor (manual 30025), not a per-room value."""
    hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"rooms": {}, "identity": {}}}})
    entry = SimpleNamespace(entry_id="entry_1")
    added: list = []

    asyncio.run(async_setup_entry(hass, entry, added.extend))

    unique_ids = {getattr(entity, "_attr_unique_id", None) for entity in added}
    assert "entry_1_flow_temperature" in unique_ids


def test_setup_entry_creates_return_temperature_sensors_for_room_actuators():
    hass = SimpleNamespace(
        data={
            DOMAIN: {
                "entry_1": {
                    "rooms": {"room_1": {"name": "Wohnzimmer", "actor": 1}},
                    "identity": {},
                }
            }
        }
    )
    entry = SimpleNamespace(entry_id="entry_1")
    added: list = []

    asyncio.run(async_setup_entry(hass, entry, added.extend))

    unique_ids = {getattr(entity, "_attr_unique_id", None) for entity in added}
    assert "entry_1_room_1_actor1_return_temperature" in unique_ids


# --- State restoration across restarts (spec.md 15) ---------------------


def _with_restored_state(entity, state):
    """Stub RestoreEntity.async_get_last_state() without a real hass/store."""

    async def _fake_last_state():
        return None if state is None else SimpleNamespace(state=state, attributes={})

    entity.async_get_last_state = _fake_last_state
    return entity


def test_identity_sensor_restores_last_text_value():
    sensor = _identity_sensor("base_unit_name", 10, 12, True, _FakeInputClient([]))
    _with_restored_state(sensor, "Fonterra")

    asyncio.run(sensor.async_added_to_hass())

    assert sensor._attr_native_value == "Fonterra"


def test_identity_sensor_restores_error_code_and_its_description():
    sensor = _identity_sensor(
        "base_unit_error_code", 23, 1, False, _FakeInputClient([])
    )
    _with_restored_state(sensor, "7")

    asyncio.run(sensor.async_added_to_hass())

    assert sensor._attr_native_value == 7
    assert sensor._attr_extra_state_attributes == {
        "description": describe_error_code(7)
    }


def test_identity_sensor_ignores_unknown_and_unavailable_restored_state():
    sensor = _identity_sensor("base_unit_name", 10, 12, True, _FakeInputClient([]))
    _with_restored_state(sensor, "unavailable")

    asyncio.run(sensor.async_added_to_hass())

    assert sensor._attr_native_value is None


def test_identity_sensor_does_not_restore_over_an_already_known_value():
    """A pre-populated value (from the config-entry options cache written by
    __init__.py) must win over a stale restored state, not be clobbered."""
    sensor = _identity_sensor("base_unit_name", 10, 12, True, _FakeInputClient([]))
    sensor._attr_native_value = "CURRENT"
    _with_restored_state(sensor, "STALE")

    asyncio.run(sensor.async_added_to_hass())

    assert sensor._attr_native_value == "CURRENT"


def test_actor_linked_sensor_restores_last_numeric_value():
    sensor = ViegaActorLinkedSensor(
        "entry_1", "room_1", 2, "return_temperature", "name", 250, unit="°C", scale=10
    )
    _with_restored_state(sensor, "21.5")

    asyncio.run(sensor.async_added_to_hass())

    assert sensor._attr_native_value == 21.5


def test_base_unit_temperature_sensor_restores_last_numeric_value():
    sensor = ViegaBaseUnitTemperatureSensor("entry_1", "flow_temperature", 25)
    _with_restored_state(sensor, "42.3")

    asyncio.run(sensor.async_added_to_hass())

    assert sensor._attr_native_value == 42.3
