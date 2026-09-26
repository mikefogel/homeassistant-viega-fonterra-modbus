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
