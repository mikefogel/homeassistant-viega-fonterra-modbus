"""Tests for the power-level Number platform beyond the address-resolution
and write-path tests already in test_entity_fixes.py.
"""

import asyncio
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.modbus_handler import ViegaModbusClient
from custom_components.viega_fonterra_modbus.number import (
    ViegaPowerLevelNumber,
    async_setup_entry,
)


class _FakeClient:
    def __init__(self, values=None, raises=False):
        self._values = values
        self._raises = raises

    async def read_holding_registers(self, address, count=1):
        if self._raises:
            raise RuntimeError("device offline")
        return self._values


def test_async_update_reads_the_current_power_level():
    entity = ViegaPowerLevelNumber("entry_1", "room_1", {"name": "Wohnzimmer"})
    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": _FakeClient([4])}}})

    asyncio.run(entity.async_update())

    assert entity._attr_native_value == 4


def test_async_update_ignores_the_error_sentinel():
    entity = ViegaPowerLevelNumber("entry_1", "room_1", {"name": "Wohnzimmer"})
    entity._attr_native_value = 3
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": _FakeClient([ViegaModbusClient.ERROR_SENTINEL])}}}
    )

    asyncio.run(entity.async_update())

    assert entity._attr_native_value == 3


def test_async_update_does_not_crash_on_communication_failure():
    entity = ViegaPowerLevelNumber("entry_1", "room_1", {"name": "Wohnzimmer"})
    entity._attr_native_value = 2
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": _FakeClient(raises=True)}}}
    )

    asyncio.run(entity.async_update())

    assert entity._attr_native_value == 2


def test_async_update_is_a_noop_without_a_resolvable_address():
    entity = ViegaPowerLevelNumber("entry_1", "wohnzimmer", {"name": "Wohnzimmer"})
    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": _FakeClient([4])}}})

    asyncio.run(entity.async_update())

    assert entity._attr_native_value is None


def test_setup_entry_only_adds_entities_with_a_resolvable_register():
    hass = SimpleNamespace(
        data={
            DOMAIN: {
                "entry_1": {
                    "rooms": {
                        "room_1": {"name": "Wohnzimmer"},
                        "wohnzimmer": {"name": "Ohne Registernummer"},
                        "room_2": "not a dict",
                    }
                }
            }
        }
    )
    entry = SimpleNamespace(entry_id="entry_1")
    added: list = []

    asyncio.run(async_setup_entry(hass, entry, added.extend))

    assert len(added) == 1
    assert added[0]._room_id == "room_1"
