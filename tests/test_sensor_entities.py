"""Tests for the sensor platform's entity classes beyond the basic
ViegaRegisterSensor happy-path already covered in test_modbus_handler.py.
"""

import asyncio
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.modbus_handler import ViegaModbusClient
from custom_components.viega_fonterra_modbus.sensor import (
    ViegaActorLinkedSensor,
    ViegaBaseUnitIdentitySensor,
    ViegaRegisterSensor,
    _extra_actor_sensors,
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
    sensor = ViegaBaseUnitIdentitySensor(entry, sensor_key, sensor_key, address, count, text)
    sensor.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": client}}})
    return sensor


def test_text_field_decodes_little_endian_ascii_and_strips_padding():
    """spec.md 3a: two ASCII chars per register, little-endian, padding stripped."""
    raw = b"Fonterra\x00\x00\x00\x00"
    values = [int.from_bytes(raw[i : i + 2], "little") for i in range(0, len(raw), 2)]
    sensor = _identity_sensor("base_unit_name", 10, len(values), True, _FakeInputClient(values))

    asyncio.run(sensor.async_update())

    assert sensor._attr_native_value == "Fonterra"


def test_error_code_sensor_stores_raw_code_and_unknown_description():
    sensor = _identity_sensor(
        "base_unit_error_code", 23, 1, False, _FakeInputClient([7])
    )

    asyncio.run(sensor.async_update())

    assert sensor._attr_native_value == 7
    assert sensor._attr_extra_state_attributes == {"description": "Unknown error (code 7)"}


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


def test_actor_linked_sensor_without_scale_keeps_the_raw_value():
    sensor = ViegaActorLinkedSensor("entry_1", "room_1", 2, "position", "name", 249, unit="%")
    sensor.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": _FakeInputClient([42])}}})

    asyncio.run(sensor.async_update())

    assert sensor._attr_native_value == 42


def test_actor_linked_sensor_ignores_the_error_sentinel():
    sensor = ViegaActorLinkedSensor("entry_1", "room_1", 2, "position", "name", 249)
    sensor.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": _FakeInputClient([ViegaModbusClient.ERROR_SENTINEL])}}}
    )

    asyncio.run(sensor.async_update())

    assert sensor._attr_native_value is None


def test_extra_actor_sensors_created_for_additional_actors_in_a_room():
    """spec.md 4: additional actuators in a multi-actor room must not be
    silently dropped."""
    entry = SimpleNamespace(entry_id="entry_1")
    rooms = {"room_1": {"name": "Wohnzimmer", "actor": [1, 2, 3]}}

    sensors = _extra_actor_sensors(entry, rooms)

    # Actor 1 is the primary one (handled by climate.py); actors 2 and 3
    # each get a position and a return-temperature sensor.
    assert len(sensors) == 4
    unique_ids = {s._attr_unique_id for s in sensors}
    assert unique_ids == {
        "entry_1_room_1_actor2_position",
        "entry_1_room_1_actor2_return_temperature",
        "entry_1_room_1_actor3_position",
        "entry_1_room_1_actor3_return_temperature",
    }


def test_extra_actor_sensors_skipped_when_actor_is_a_single_int():
    entry = SimpleNamespace(entry_id="entry_1")
    rooms = {"room_1": {"name": "Wohnzimmer", "actor": 1}}

    assert _extra_actor_sensors(entry, rooms) == []


def test_extra_actor_sensors_skipped_for_a_single_item_actor_list():
    entry = SimpleNamespace(entry_id="entry_1")
    rooms = {"room_1": {"name": "Wohnzimmer", "actor": [1]}}

    assert _extra_actor_sensors(entry, rooms) == []


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
