"""Tests for the base-unit error indicator (spec.md 13: a non-zero
base-unit error code activates the base-unit error indicator)."""

import asyncio
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus.binary_sensor import (
    ViegaBaseUnitErrorBinarySensor,
    async_setup_entry,
)
from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.modbus_handler import ViegaModbusClient


class _FakeClient:
    def __init__(self, values=None, raises=False):
        self._values = values
        self._raises = raises

    async def read_input_registers(self, address, count=1):
        if self._raises:
            raise RuntimeError("device offline")
        return self._values


def _entity_with_client(client) -> ViegaBaseUnitErrorBinarySensor:
    entity = ViegaBaseUnitErrorBinarySensor("entry_1")
    entity.hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": client}}})
    return entity


def test_stays_off_and_does_not_crash_on_communication_failure():
    entity = _entity_with_client(_FakeClient(raises=True))

    asyncio.run(entity.async_update())

    assert entity._attr_is_on is False


def test_keeps_last_state_on_error_sentinel():
    """-99 must not be misread as a real (non-zero, thus "error") code."""
    entity = _entity_with_client(_FakeClient(values=[ViegaModbusClient.ERROR_SENTINEL]))
    entity._attr_is_on = True  # simulate a previously known state

    asyncio.run(entity.async_update())

    assert entity._attr_is_on is True


def test_turns_on_for_a_nonzero_error_code():
    entity = _entity_with_client(_FakeClient(values=[7]))

    asyncio.run(entity.async_update())

    assert entity._attr_is_on is True


def test_turns_off_for_error_code_zero():
    entity = _entity_with_client(_FakeClient(values=[7]))
    asyncio.run(entity.async_update())
    assert entity._attr_is_on is True

    entity.hass.data[DOMAIN]["entry_1"]["client"] = _FakeClient(values=[0])
    entity._polling_gate._next_due = 0.0  # force the next update to actually read

    asyncio.run(entity.async_update())

    assert entity._attr_is_on is False


def test_setup_entry_creates_a_single_indicator_per_module():
    hass = SimpleNamespace(data={DOMAIN: {"entry_1": {}}})
    entry = SimpleNamespace(entry_id="entry_1")
    added: list = []

    asyncio.run(async_setup_entry(hass, entry, added.extend))

    assert len(added) == 1
    assert added[0]._attr_unique_id == "entry_1_base_unit_error"
