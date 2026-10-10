"""The per-module polling coordinator (spec.md 16i), including the
contiguous block reads it inherited from the former per-entity polling
(spec.md 16d)."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.viega_fonterra_modbus import coordinator as coordinator_module
from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.coordinator import (
    MAX_BLOCK_REGISTERS,
    REQUEST_TTL_CYCLES,
    ViegaDataCoordinator,
    contiguous_runs,
)
from custom_components.viega_fonterra_modbus.errors import async_write_register
from custom_components.viega_fonterra_modbus.modbus_handler import ModbusClientError
from custom_components.viega_fonterra_modbus.registers import BASE_UNIT_REGISTERS


class _BlockRecordingClient:
    """Records every (address, count) it was asked for; answers from a
    value-by-address map (missing addresses read as 0)."""

    def __init__(self, values_by_address: dict[int, int] | None = None, fail_banks=()):
        self.values_by_address = values_by_address or {}
        self.fail_banks = set(fail_banks)
        self.requests: list[tuple[str, int, int]] = []
        self.writes: list[tuple[int, int]] = []

    async def _read(self, bank, address, count):
        self.requests.append((bank, address, count))
        if bank in self.fail_banks:
            raise ModbusClientError("device offline")
        return [self.values_by_address.get(address + i, 0) for i in range(count)]

    async def read_holding_registers(self, address, count=1):
        return await self._read("holding", address, count)

    async def read_input_registers(self, address, count=1):
        return await self._read("input", address, count)

    async def write_register(self, address, value):
        self.writes.append((address, value))


def _coordinator(hass, client, rooms, polling_interval=30) -> ViegaDataCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, data={"polling_interval": polling_interval})
    entry.add_to_hass(hass)
    coordinator = ViegaDataCoordinator(hass, entry, client, polling_interval)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "rooms": rooms,
        "polling": coordinator,
    }
    return coordinator


TWO_ROOMS = {
    "room_1": {"name": "Wohnzimmer", "room_number": 1},
    "room_2": {"name": "Bad", "room_number": 2},
}


# --- Block planning (spec.md 16d) -----------------------------------------


def test_contiguous_runs_never_bridge_a_gap():
    assert contiguous_runs({250, 251, 253, 254}) == [(250, 2), (253, 2)]


def test_contiguous_runs_cap_at_the_modbus_quantity_limit():
    runs = contiguous_runs(set(range(300)))
    assert all(length <= MAX_BLOCK_REGISTERS for _, length in runs)
    assert sum(length for _, length in runs) == 300


async def test_one_cycle_reads_adjacent_registers_of_several_rooms_in_one_request(hass):
    """Room 1 uses holding 50/51 (power/target), room 2 uses 52/53."""
    client = _BlockRecordingClient({50: 1, 51: 2, 52: 3, 53: 4})
    coordinator = _coordinator(hass, client, TWO_ROOMS)

    await coordinator.async_refresh()

    holding = [r for r in client.requests if r[0] == "holding"]
    assert ("holding", 50, 4) in holding
    assert await coordinator.read(hass, coordinator.entry_id, "holding", 53, 1) == [4]


async def test_banks_are_never_combined_and_gaps_never_bridged(hass):
    """Actuator 1 (250/251) and actuator 2 (253/254) are separated by
    actuator 1's Raum-ID register at 252, which is not polled every cycle."""
    client = _BlockRecordingClient()
    coordinator = _coordinator(hass, client, {"room_1": {"name": "W", "actor": [1, 2]}})

    await coordinator.async_refresh()

    inputs = [r for r in client.requests if r[0] == "input"]
    assert ("input", 250, 2) in inputs and ("input", 253, 2) in inputs
    assert not any(start <= 252 < start + count for _, start, count in inputs)


async def test_a_multi_register_range_is_read_on_its_own(hass):
    client = _BlockRecordingClient()
    coordinator = _coordinator(hass, client, {})
    address = BASE_UNIT_REGISTERS["base_unit_name"]
    await coordinator.async_refresh()

    with pytest.raises(ModbusClientError):
        await coordinator.read(hass, coordinator.entry_id, "input", address, 12)
    await coordinator.async_refresh()

    assert ("input", address, 12) in client.requests
    assert await coordinator.read(hass, coordinator.entry_id, "input", address, 12) == [0] * 12


# --- Entity-facing read() -------------------------------------------------


async def test_read_never_touches_the_device(hass):
    client = _BlockRecordingClient({50: 5})
    coordinator = _coordinator(hass, client, TWO_ROOMS)
    await coordinator.async_refresh()
    requests_after_refresh = len(client.requests)

    for _ in range(5):
        assert await coordinator.read(hass, coordinator.entry_id, "holding", 50, 1) == [5]

    assert len(client.requests) == requests_after_refresh


async def test_a_register_outside_the_topology_is_polled_from_the_next_cycle(hass):
    client = _BlockRecordingClient({999: 7})
    coordinator = _coordinator(hass, client, {})
    await coordinator.async_refresh()

    with pytest.raises(ModbusClientError):
        await coordinator.read(hass, coordinator.entry_id, "holding", 999, 1)
    await coordinator.async_refresh()

    assert await coordinator.read(hass, coordinator.entry_id, "holding", 999, 1) == [7]


async def test_a_register_nobody_asks_for_anymore_drops_out_of_the_plan(hass):
    client = _BlockRecordingClient()
    coordinator = _coordinator(hass, client, {})
    with pytest.raises(ModbusClientError):
        await coordinator.read(hass, coordinator.entry_id, "holding", 999, 1)

    for _ in range(REQUEST_TTL_CYCLES + 2):
        await coordinator.async_refresh()
    client.requests.clear()
    await coordinator.async_refresh()

    assert not any(address == 999 for _, address, _ in client.requests)


# --- Failures (spec.md 10/16i) --------------------------------------------


async def test_a_failed_block_only_drops_its_own_registers(hass):
    client = _BlockRecordingClient({BASE_UNIT_REGISTERS["error_code"]: 4}, fail_banks={"holding"})
    coordinator = _coordinator(hass, client, TWO_ROOMS)

    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    with pytest.raises(ModbusClientError):
        await coordinator.read(hass, coordinator.entry_id, "holding", 50, 1)
    error = BASE_UNIT_REGISTERS["error_code"]
    assert await coordinator.read(hass, coordinator.entry_id, "input", error, 1) == [4]


async def test_a_cycle_where_every_read_fails_does_not_make_entities_unavailable(hass):
    client = _BlockRecordingClient(fail_banks={"holding", "input"})
    coordinator = _coordinator(hass, client, TWO_ROOMS)

    await coordinator.async_refresh()

    assert coordinator.last_update_success is True
    assert coordinator.data == {}


# --- Cycle bookkeeping ----------------------------------------------------


async def test_generation_increments_once_per_cycle(hass):
    coordinator = _coordinator(hass, _BlockRecordingClient(), TWO_ROOMS)
    assert coordinator.generation == 0

    await coordinator.async_refresh()
    await coordinator.async_refresh()

    assert coordinator.generation == 2


async def test_update_interval_is_the_modules_polling_interval(hass):
    coordinator = _coordinator(hass, _BlockRecordingClient(), {}, polling_interval=45)

    assert coordinator.update_interval == timedelta(seconds=45)


async def test_run_exclusive_does_not_interleave_with_a_cycle(hass):
    """Rediscovery (spec.md 16a) and a polling cycle share the connection;
    their Modbus traffic must not interleave."""
    log: list[str] = []

    class _SlowClient(_BlockRecordingClient):
        async def _read(self, bank, address, count):
            log.append("cycle-start")
            await asyncio.sleep(0.01)
            log.append("cycle-end")
            return [0] * count

    coordinator = _coordinator(hass, _SlowClient(), {})

    async def rediscovery():
        log.append("rediscovery")
        return "done"

    results = await asyncio.gather(
        coordinator.async_refresh(), coordinator.run_exclusive(rediscovery)
    )

    assert results[1] == "done"
    index = log.index("rediscovery")
    assert log[:index].count("cycle-start") == log[:index].count("cycle-end")


async def test_write_helper_only_writes(hass, monkeypatch):
    """The early cycle is requested by the entity after it has shown the new
    value (spec.md 16c), not by the write helper itself."""
    client = _BlockRecordingClient()
    coordinator = _coordinator(hass, client, TWO_ROOMS)
    requested: list[bool] = []

    async def fake_request_refresh():
        requested.append(True)

    monkeypatch.setattr(coordinator, "async_request_refresh", fake_request_refresh)

    await async_write_register(hass, coordinator.entry_id, 51, 215)

    assert client.writes == [(51, 215)]
    assert requested == []


async def test_requested_cycles_use_a_short_cooldown(hass):
    coordinator = _coordinator(hass, _BlockRecordingClient(), TWO_ROOMS)

    assert coordinator._debounced_refresh.cooldown == coordinator_module.REQUEST_REFRESH_COOLDOWN == 1.0


def test_module_exposes_the_quantity_limit():
    assert coordinator_module.MAX_BLOCK_REGISTERS == 125
