"""Tests for the per-entry polling-interval throttle (spec.md 6c)."""

import asyncio
import itertools
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus import polling as polling_module
from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.polling import PollingGate, SharedPolling


def _fake_monotonic(monkeypatch, *times: float) -> None:
    """Patch the real `time.monotonic` (shared process-wide, not just
    `polling_module`'s reference to it) to return `times` in order, then
    repeat the last value forever. A merely-finite fake would raise
    StopIteration the moment anything else - e.g. an unrelated test-harness
    fixture - calls the real `time.monotonic()` again during the same test,
    since this patches the one global `time` module, not a private copy."""
    sequence = itertools.chain(times, itertools.repeat(times[-1]))
    monkeypatch.setattr(polling_module.time, "monotonic", lambda: next(sequence))


def test_first_call_is_always_due():
    gate = PollingGate()
    hass = SimpleNamespace(data={})

    assert gate.is_due(hass, "entry_1") is True


def test_second_call_within_the_interval_is_not_due(monkeypatch):
    _fake_monotonic(monkeypatch, 100.0, 100.5)
    gate = PollingGate()
    hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"polling_interval": 30}}})

    assert gate.is_due(hass, "entry_1") is True
    assert gate.is_due(hass, "entry_1") is False


def test_call_after_the_interval_elapses_is_due_again(monkeypatch):
    _fake_monotonic(monkeypatch, 100.0, 131.0)
    gate = PollingGate()
    hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"polling_interval": 30}}})

    assert gate.is_due(hass, "entry_1") is True
    assert gate.is_due(hass, "entry_1") is True


def test_uses_the_default_polling_interval_when_not_configured(monkeypatch):
    """Matches DEFAULT_POLLING_INTERVAL (30s) from const.py."""
    _fake_monotonic(monkeypatch, 0.0, 25.0, 31.0)
    gate = PollingGate()
    hass = SimpleNamespace(data={})

    assert gate.is_due(hass, "entry_1") is True
    assert gate.is_due(hass, "entry_1") is False
    assert gate.is_due(hass, "entry_1") is True


def test_gate_is_per_instance_not_shared_across_entities():
    """Two entities (two PollingGate instances) must be throttled independently."""
    gate_a = PollingGate()
    gate_b = PollingGate()
    hass = SimpleNamespace(data={})

    assert gate_a.is_due(hass, "entry_1") is True
    # gate_b has never fired, so it must still be due even though gate_a just
    # armed its own window.
    assert gate_b.is_due(hass, "entry_1") is True


# --- SharedPolling.generation / run_exclusive (spec.md 16c/16a) ----------


class _FakeClient:
    def __init__(self, value: int = 1):
        self._value = value

    async def read_holding_registers(self, address, count=1):
        return [self._value]

    async def read_input_registers(self, address, count=1):
        return [self._value]


def test_generation_starts_at_zero_and_survives_a_cache_hit():
    shared = SharedPolling()
    hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": _FakeClient()}}})

    assert shared.generation == 0
    asyncio.run(shared.read(hass, "entry_1", "holding", 10, 1))
    assert shared.generation == 1
    # A second read of the same key within the same window is a cache hit
    # and must not bump the generation again.
    asyncio.run(shared.read(hass, "entry_1", "holding", 10, 1))
    assert shared.generation == 1


def test_generation_increments_again_once_the_gate_reopens(monkeypatch):
    shared = SharedPolling()
    hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"client": _FakeClient(), "polling_interval": 30}}}
    )
    sequence = itertools.chain([100.0, 100.1, 131.0], itertools.repeat(131.0))
    monkeypatch.setattr(polling_module.time, "monotonic", lambda: next(sequence))

    asyncio.run(shared.read(hass, "entry_1", "holding", 10, 1))
    assert shared.generation == 1
    asyncio.run(shared.read(hass, "entry_1", "holding", 10, 1))
    assert shared.generation == 2


def test_run_exclusive_awaits_and_returns_the_action_result():
    shared = SharedPolling()

    async def action():
        return "rediscovery result"

    assert asyncio.run(shared.run_exclusive(action)) == "rediscovery result"


# --- Contiguous register-block coalescing (spec.md 16d) ------------------


class _BlockRecordingClient:
    """Records every (address, count) it was actually asked for and answers
    from a fixed value-by-address map."""

    def __init__(self, values_by_address: dict[int, int]):
        self.values_by_address = values_by_address
        self.holding_requests: list[tuple[int, int]] = []
        self.input_requests: list[tuple[int, int]] = []

    async def read_holding_registers(self, address, count=1):
        self.holding_requests.append((address, count))
        return [self.values_by_address[address + i] for i in range(count)]

    async def read_input_registers(self, address, count=1):
        self.input_requests.append((address, count))
        return [self.values_by_address[address + i] for i in range(count)]


def _hass_with_rooms(client, rooms: dict) -> SimpleNamespace:
    return SimpleNamespace(data={DOMAIN: {"entry_1": {"client": client, "rooms": rooms}}})


def test_two_rooms_adjacent_power_and_target_registers_are_read_in_one_request():
    """Room 1 uses holding 50/51 (power/target) and room 2 uses 52/53 -
    contiguous across both rooms - so a single request should satisfy all
    four individual single-register reads within one polling window."""
    client = _BlockRecordingClient({50: 1, 51: 2, 52: 3, 53: 4})
    rooms = {
        "room_1": {"name": "Wohnzimmer", "room_number": 1},
        "room_2": {"name": "Bad", "room_number": 2},
    }
    hass = _hass_with_rooms(client, rooms)
    shared = SharedPolling()

    result_50 = asyncio.run(shared.read(hass, "entry_1", "holding", 50, 1))
    result_53 = asyncio.run(shared.read(hass, "entry_1", "holding", 53, 1))

    assert result_50 == [1]
    assert result_53 == [4]
    assert len(client.holding_requests) == 1
    address, count = client.holding_requests[0]
    assert address == 50 and count == 4


def test_input_and_holding_registers_are_never_combined():
    client = _BlockRecordingClient({24: 0, 25: 264})
    hass = _hass_with_rooms(client, {})
    shared = SharedPolling()

    asyncio.run(shared.read(hass, "entry_1", "input", 24, 1))
    asyncio.run(shared.read(hass, "entry_1", "input", 25, 1))

    assert client.input_requests == [(24, 2)]
    assert client.holding_requests == []


def test_an_undocumented_gap_is_never_bridged():
    """Actuator 1's position/return (250/251) must not be merged with
    actuator 2's position/return (253/254) across the gap at 252 (actuator
    1's Raum-ID register, which is deliberately excluded from the known
    per-cycle set - see test_registers.py)."""
    client = _BlockRecordingClient({250: 1, 251: 200, 253: 0, 254: 210})
    rooms = {"room_1": {"name": "Wohnzimmer", "actor": [1, 2]}}
    hass = _hass_with_rooms(client, rooms)
    shared = SharedPolling()

    asyncio.run(shared.read(hass, "entry_1", "input", 250, 1))
    asyncio.run(shared.read(hass, "entry_1", "input", 253, 1))

    assert sorted(client.input_requests) == [(250, 2), (253, 2)]


def test_an_address_outside_the_known_topology_reads_alone():
    client = _BlockRecordingClient({999: 7})
    hass = _hass_with_rooms(client, {})
    shared = SharedPolling()

    result = asyncio.run(shared.read(hass, "entry_1", "holding", 999, 1))

    assert result == [7]
    assert client.holding_requests == [(999, 1)]


def test_a_multi_register_request_is_never_combined_with_anything_else():
    client = _BlockRecordingClient({1: 10, 2: 20, 24: 0, 25: 264})
    hass = _hass_with_rooms(client, {})
    shared = SharedPolling()

    values = asyncio.run(shared.read(hass, "entry_1", "holding", 1, 2))

    assert values == [10, 20]
    assert client.holding_requests == [(1, 2)]


def test_a_failed_block_read_does_not_cache_any_of_its_addresses():
    class _FailingClient:
        async def read_holding_registers(self, address, count=1):
            raise RuntimeError("device offline")

    rooms = {
        "room_1": {"name": "Wohnzimmer", "room_number": 1},
        "room_2": {"name": "Bad", "room_number": 2},
    }
    hass = _hass_with_rooms(_FailingClient(), rooms)
    shared = SharedPolling()

    try:
        asyncio.run(shared.read(hass, "entry_1", "holding", 50, 1))
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected the underlying read failure to propagate")

    assert shared._values == {}


def test_contiguous_block_caps_at_the_modbus_quantity_limit(monkeypatch):
    """The real register map (<=12 rooms/actuators) never produces a run
    anywhere near the 125-register protocol limit - this exercises the cap
    itself with a synthetic, artificially huge contiguous known set."""
    huge_run = set(range(0, 300))
    monkeypatch.setattr(
        polling_module, "known_addresses_for_topology", lambda rooms: (huge_run, set())
    )
    shared = SharedPolling()
    hass = _hass_with_rooms(object(), {})

    start, length = shared._contiguous_block(hass, "entry_1", "holding", 150)

    assert length <= polling_module.MAX_BLOCK_REGISTERS
    assert start <= 150 < start + length


def test_run_exclusive_serializes_against_a_concurrent_read():
    """A concurrent regular poll (`read`) and an explicit rediscovery scan
    (`run_exclusive`) must not run their Modbus traffic interleaved - both
    go through the same lock (spec.md 16a "reuse ... the polling lock")."""
    order: list[str] = []

    class _RecordingClient:
        async def read_holding_registers(self, address, count=1):
            order.append("read-start")
            await asyncio.sleep(0)
            order.append("read-end")
            return [1]

    shared = SharedPolling()
    hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"client": _RecordingClient()}}})

    async def slow_action():
        order.append("exclusive-start")
        await asyncio.sleep(0.02)
        order.append("exclusive-end")
        return None

    async def run() -> None:
        await asyncio.gather(
            shared.run_exclusive(slow_action),
            shared.read(hass, "entry_1", "holding", 20, 1),
        )

    asyncio.run(run())

    # Whichever task acquires the lock first must fully finish (both of its
    # own start/end markers) before the other task's markers appear at all.
    assert order in (
        ["exclusive-start", "exclusive-end", "read-start", "read-end"],
        ["read-start", "read-end", "exclusive-start", "exclusive-end"],
    )
