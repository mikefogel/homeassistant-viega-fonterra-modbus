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


def test_name_is_localized_via_translation_key_not_hardcoded():
    """spec.md "localize every entity name": the display name must come
    from translations/*.json (entity.number.power_level), not a hardcoded
    English string, so it can be shown in German too."""
    entity = ViegaPowerLevelNumber("entry_1", "room_1", {"name": "Wohnzimmer"})

    assert not hasattr(entity, "_attr_name")
    assert entity._attr_translation_key == "power_level"
    assert entity._attr_translation_placeholders == {"room": "Wohnzimmer"}


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


# --- Read-after-write verification (spec.md 16c) -------------------------


class _FakeSharedPolling:
    def __init__(self, client):
        self._client = client
        self.generation = 0

    def bump(self) -> None:
        self.generation += 1

    async def read(self, hass, entry_id, bank, address, count=1):
        return await self._client.read_holding_registers(address, count)


class _WriteThenReadClient:
    def __init__(self):
        self.value = None

    async def write_register(self, address, value):
        self.value = value

    async def read_holding_registers(self, address, count=1):
        return [self.value if self.value is not None else 0]


def test_matching_verification_leaves_no_error_message():
    entity = ViegaPowerLevelNumber("entry_1", "room_1", {"name": "Wohnzimmer"})
    client = _WriteThenReadClient()
    shared = _FakeSharedPolling(client)
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": client, "polling": shared}}}
    )

    asyncio.run(entity.async_set_native_value(4))
    shared.bump()
    asyncio.run(entity.async_update())

    assert entity.last_error_message == ""
    assert entity._attr_native_value == 4


def test_mismatched_verification_reports_a_warning_and_keeps_the_device_value():
    entity = ViegaPowerLevelNumber("entry_1", "room_1", {"name": "Wohnzimmer"})
    client = _WriteThenReadClient()
    shared = _FakeSharedPolling(client)
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": client, "polling": shared}}}
    )

    asyncio.run(entity.async_set_native_value(4))
    client.value = 7  # the device actually kept/reports a different level
    shared.bump()
    asyncio.run(entity.async_update())

    assert entity._attr_native_value == 7
    assert "power_level" in entity.last_error_message
    assert "warning" in entity.last_error_message


def test_verification_ignores_a_read_from_the_same_write_time_generation():
    entity = ViegaPowerLevelNumber("entry_1", "room_1", {"name": "Wohnzimmer"})
    client = _WriteThenReadClient()
    shared = _FakeSharedPolling(client)
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": client, "polling": shared}}}
    )

    asyncio.run(entity.async_set_native_value(4))
    client.value = 7
    asyncio.run(entity.async_update())  # no bump: still the write-time generation

    assert entity.last_error_message == ""
    assert entity._pending_write is not None


# --- State restoration across restarts (spec.md 15) ---------------------


def test_restores_last_numeric_value_on_add():
    entity = ViegaPowerLevelNumber("entry_1", "room_1", {"name": "Wohnzimmer"})

    async def _fake_last_state():
        return SimpleNamespace(state="5", attributes={})

    entity.async_get_last_state = _fake_last_state

    asyncio.run(entity.async_added_to_hass())

    assert entity._attr_native_value == 5.0


def test_ignores_unavailable_restored_state():
    entity = ViegaPowerLevelNumber("entry_1", "room_1", {"name": "Wohnzimmer"})

    async def _fake_last_state():
        return SimpleNamespace(state="unavailable", attributes={})

    entity.async_get_last_state = _fake_last_state

    asyncio.run(entity.async_added_to_hass())

    assert entity._attr_native_value is None
