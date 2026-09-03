"""Regression tests for entity-level bug fixes found during code review."""

import asyncio
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus.binary_sensor import (
    ViegaBaseUnitErrorBinarySensor,
)
from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.number import ViegaPowerLevelNumber
from custom_components.viega_fonterra_modbus.switch import ViegaBasicSwitchEntity


def test_switch_unique_id_is_based_on_room_id_not_display_name():
    """spec.md 5a: renaming a room must not change its unique_id.

    The switch previously built its unique_id from the (editable) display
    name instead of the stable room_id, so a rename created a duplicate
    entity instead of just changing the shown name.
    """
    entity = ViegaBasicSwitchEntity("entry_1", "room_1", "Wohnzimmer")

    assert entity._attr_unique_id == "entry_1_room_1_switch"


def test_switch_unique_id_is_stable_across_a_room_rename():
    before = ViegaBasicSwitchEntity("entry_1", "room_1", "Wohnzimmer")
    after = ViegaBasicSwitchEntity("entry_1", "room_1", "Living Room")

    assert before._attr_unique_id == after._attr_unique_id


def test_power_level_number_without_resolvable_register_has_no_address():
    """A room with no room_number/power_level_register must not silently
    default to register 0, which collides with the base unit's
    operating_mode register (spec.md 5b)."""
    entity = ViegaPowerLevelNumber("entry_1", "wohnzimmer", {"name": "Wohnzimmer"})

    assert entity.address is None


def test_power_level_number_resolves_register_from_room_id():
    """"room_1" resolves room_number=1, which has a real power_level register."""
    entity = ViegaPowerLevelNumber("entry_1", "room_1", {"name": "Wohnzimmer"})

    assert entity.address == 49


def test_power_level_number_setting_value_without_address_raises():
    entity = ViegaPowerLevelNumber("entry_1", "wohnzimmer", {"name": "Wohnzimmer"})

    try:
        asyncio.run(entity.async_set_native_value(5))
    except ValueError:
        pass
    else:
        raise AssertionError("expected a ValueError when no register is configured")


class _FakeClient:
    def __init__(self):
        self.writes: list[tuple[int, int]] = []

    async def read_holding_registers(self, address, count=1):
        return [3]

    async def write_register(self, address, value):
        self.writes.append((address, value))


def test_power_level_number_writes_to_the_resolved_register():
    entity = ViegaPowerLevelNumber("entry_1", "room_1", {"name": "Wohnzimmer"})
    client = _FakeClient()
    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": client}}})

    asyncio.run(entity.async_set_native_value(5))

    assert client.writes == [(49, 5)]


class _FakeInputClient:
    def __init__(self, value: int):
        self._value = value

    async def read_input_registers(self, address, count=1):
        return [self._value]


def test_base_unit_error_binary_sensor_is_off_for_zero_code():
    entity = ViegaBaseUnitErrorBinarySensor("entry_1")
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": _FakeInputClient(0)}}}
    )

    asyncio.run(entity.async_update())

    assert entity._attr_is_on is False


def test_base_unit_error_binary_sensor_is_on_for_nonzero_code():
    """spec.md 13: a non-zero base-unit error code activates the indicator."""
    entity = ViegaBaseUnitErrorBinarySensor("entry_1")
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": _FakeInputClient(7)}}}
    )

    asyncio.run(entity.async_update())

    assert entity._attr_is_on is True
