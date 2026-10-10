"""Blocks the module rejects with a Modbus exception (spec.md 16d)."""

from __future__ import annotations

import logging

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.coordinator import ViegaDataCoordinator
from custom_components.viega_fonterra_modbus.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.viega_fonterra_modbus.modbus_handler import ModbusClientError
from custom_components.viega_fonterra_modbus.registers import actor_registers, room_registers
from tests.test_setup_lifecycle import FakeClient, _entry, fake_device  # noqa: F401

ROOMS = {
    "room_1": {"name": "Esszimmer", "room_number": 1, "actor": [1, 2]},
    "room_2": {"name": "Bad", "room_number": 2, "actor": 6},
}
BAD_ERROR = room_registers(2)["error_code"]
BAD_TEMPERATURE = room_registers(2)["current_temperature"]
ACTUATOR_6 = actor_registers(6)["position"]


class _Module:
    """Answers input registers with their address; rejects (exception 4)
    any request touching `bad`, and with `no_blocks` any request for more
    than one register."""

    def __init__(self, bad: set[int] = frozenset(), no_blocks: bool = False):
        self.bad = set(bad)
        self.no_blocks = no_blocks
        self.requests: list[tuple[int, int]] = []

    async def read_input_registers(self, address, count=1):
        self.requests.append((address, count))
        span = set(range(address, address + count))
        if span & self.bad or (self.no_blocks and count > 1):
            raise ModbusClientError("exception", exception_code=4)
        return list(range(address, address + count))

    async def read_holding_registers(self, address, count=1):
        return [0] * count


def _coordinator(hass, module) -> ViegaDataCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    coordinator = ViegaDataCoordinator(hass, entry, module, 30)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"rooms": ROOMS, "polling": coordinator}
    return coordinator


async def _value(coordinator, address):
    return await coordinator.read(coordinator.hass, coordinator.entry_id, "input", address, 1)


async def test_one_rejected_register_no_longer_blocks_its_neighbours(hass, caplog):
    module = _Module(bad={BAD_ERROR})
    coordinator = _coordinator(hass, module)

    with caplog.at_level(logging.WARNING):
        await coordinator.async_refresh()

    # Same cycle: the neighbours of the rejected register have fresh values.
    assert await _value(coordinator, BAD_TEMPERATURE) == [BAD_TEMPERATURE]
    assert await _value(coordinator, room_registers(1)["error_code"]) == [
        room_registers(1)["error_code"]]
    assert coordinator.rejected_register_ids() == ["room_2.error_code"]
    assert "rejected reading input registers" in caplog.text
    assert "room_2.error_code" in caplog.text


async def test_rejected_block_is_read_one_by_one_in_later_cycles_without_new_warnings(hass, caplog):
    module = _Module(bad={BAD_ERROR})
    coordinator = _coordinator(hass, module)
    await coordinator.async_refresh()
    caplog.clear()
    module.requests.clear()

    with caplog.at_level(logging.WARNING):
        await coordinator.async_refresh()

    assert (BAD_ERROR, 1) in module.requests
    assert not any(start <= BAD_ERROR < start + count and count > 1
                   for start, count in module.requests)
    assert caplog.text == ""  # warned once only
    report = {row["register"]: row for row in coordinator.rejected_registers_report()}
    assert report["room_2.error_code"]["exception_code"] == 4
    assert report["room_2.error_code"]["rejected_cycles"] == 2


async def test_a_module_that_rejects_all_block_reads_still_delivers_every_value(hass):
    coordinator = _coordinator(hass, _Module(no_blocks=True))

    await coordinator.async_refresh()
    await coordinator.async_refresh()

    assert coordinator.rejected_register_ids() == []
    assert await _value(coordinator, ACTUATOR_6) == [ACTUATOR_6]
    assert await _value(coordinator, BAD_ERROR) == [BAD_ERROR]


async def test_transport_failures_are_not_reported_as_rejected(hass):
    class _Offline(_Module):
        async def read_input_registers(self, address, count=1):
            raise ModbusClientError("Modbus read timeout after 5s")

    coordinator = _coordinator(hass, _Offline())
    await coordinator.async_refresh()

    assert coordinator.rejected_register_ids() == []


@pytest.mark.usefixtures("enable_custom_integrations")
async def test_sensor_and_diagnostics_show_rejected_registers(hass, fake_device, monkeypatch):
    rejected = room_registers(1)["error_code"]

    async def read_input_registers(self, address, count=1):
        if rejected in range(address, address + count):
            raise ModbusClientError("exception", exception_code=4)
        return [0] * count

    monkeypatch.setattr(FakeClient, "read_input_registers", read_input_registers)
    entry = _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.fonterra_invalid_registers")
    assert state.state == "1"
    assert state.attributes["rejected_registers"] == ["room_1.error_code"]
    assert state.attributes["invalid_registers"] == []

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    (row,) = diagnostics["extended"]["rejected_registers"]
    assert row["register"] == "room_1.error_code"
    assert row["exception_code"] == 4
    assert row["room"] == "Wohnzimmer"
    # The room's temperature next to it is fresh: the climate state shows 0.0.
    assert hass.states.get("climate.fonterra_wohnzimmer").attributes["current_temperature"] == 0.0
