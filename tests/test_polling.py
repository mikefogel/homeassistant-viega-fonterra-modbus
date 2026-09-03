"""Tests for the per-entry polling-interval throttle (spec.md 6c)."""

from types import SimpleNamespace

from custom_components.viega_fonterra_modbus import polling as polling_module
from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.polling import PollingGate


def test_first_call_is_always_due():
    gate = PollingGate()
    hass = SimpleNamespace(data={})

    assert gate.is_due(hass, "entry_1") is True


def test_second_call_within_the_interval_is_not_due(monkeypatch):
    times = iter([100.0, 100.5])
    monkeypatch.setattr(polling_module.time, "monotonic", lambda: next(times))
    gate = PollingGate()
    hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"polling_interval": 30}}})

    assert gate.is_due(hass, "entry_1") is True
    assert gate.is_due(hass, "entry_1") is False


def test_call_after_the_interval_elapses_is_due_again(monkeypatch):
    times = iter([100.0, 131.0])
    monkeypatch.setattr(polling_module.time, "monotonic", lambda: next(times))
    gate = PollingGate()
    hass = SimpleNamespace(data={DOMAIN: {"entry_1": {"polling_interval": 30}}})

    assert gate.is_due(hass, "entry_1") is True
    assert gate.is_due(hass, "entry_1") is True


def test_uses_the_default_polling_interval_when_not_configured(monkeypatch):
    """Matches DEFAULT_POLLING_INTERVAL (30s) from const.py."""
    times = iter([0.0, 25.0, 31.0])
    monkeypatch.setattr(polling_module.time, "monotonic", lambda: next(times))
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
