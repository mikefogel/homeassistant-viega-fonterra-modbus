"""Tests for setup/unload behavior, in particular that a module stays deletable."""

import asyncio
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus import (
    async_remove_config_entry_device,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.modbus_handler import ViegaModbusClient


class _FakeConfigEntriesForSetup:
    """Minimal stand-in for hass.config_entries during async_setup_entry.

    Deliberately has no async_update_entry attribute, matching the
    production getattr(..., None) fallback in async_setup_entry.
    """

    async def async_forward_entry_setups(self, entry, platforms):
        return None


def _make_entry(data):
    return SimpleNamespace(
        entry_id="entry_1",
        data=data,
        options={},
        add_update_listener=lambda callback: None,
        async_on_unload=lambda unsub: None,
    )


class _FakeConfigEntries:
    def __init__(self, unload_ok: bool = True):
        self._unload_ok = unload_ok

    async def async_unload_platforms(self, entry, platforms):
        return self._unload_ok


class _BrokenClient:
    async def disconnect(self):
        raise RuntimeError("socket already closed")


def test_unload_succeeds_even_when_disconnect_fails():
    """spec.md 6a/13: removing a module must succeed even if the device is
    offline and the socket teardown itself raises."""
    entry = SimpleNamespace(entry_id="entry_1")
    hass = SimpleNamespace(
        config_entries=_FakeConfigEntries(unload_ok=True),
        data={DOMAIN: {"entry_1": {"client": _BrokenClient()}}},
    )

    result = asyncio.run(async_unload_entry(hass, entry))

    assert result is True
    assert "entry_1" not in hass.data[DOMAIN]


def test_unload_does_not_crash_when_entry_data_is_missing():
    """A module that never finished setup (e.g. it never connected) must
    still be removable without a KeyError."""
    entry = SimpleNamespace(entry_id="entry_1")
    hass = SimpleNamespace(
        config_entries=_FakeConfigEntries(unload_ok=True),
        data={},
    )

    result = asyncio.run(async_unload_entry(hass, entry))

    assert result is True


def test_unload_disconnects_a_healthy_client():
    entry = SimpleNamespace(entry_id="entry_1")

    class HealthyClient:
        def __init__(self):
            self.disconnected = False

        async def disconnect(self):
            self.disconnected = True

    client = HealthyClient()
    hass = SimpleNamespace(
        config_entries=_FakeConfigEntries(unload_ok=True),
        data={DOMAIN: {"entry_1": {"client": client}}},
    )

    asyncio.run(async_unload_entry(hass, entry))

    assert client.disconnected is True


def test_setup_entry_does_not_call_a_removed_client_debug_toggle(monkeypatch):
    """spec.md "A working debug switch is one switch": frame-level debug
    logging is gated solely on `_LOGGER.isEnabledFor(logging.DEBUG)` inside
    `ViegaModbusClient._log_frame`, and `ViegaModbusClient` has no
    `set_debug`/`debug` attribute. `async_setup_entry` must not call a
    `set_debug()` method that no longer exists - it previously did, which
    made every setup raise `AttributeError` and crash the whole entry."""

    async def fake_connect(self):
        self._connected = True

    async def fake_read_input_registers(self, address, count=1):
        return []

    monkeypatch.setattr(ViegaModbusClient, "connect", fake_connect)
    monkeypatch.setattr(ViegaModbusClient, "read_input_registers", fake_read_input_registers)

    entry = _make_entry({"host": "192.168.8.20", "port": 1502})
    hass = SimpleNamespace(data={}, config_entries=_FakeConfigEntriesForSetup())

    result = asyncio.run(async_setup_entry(hass, entry))

    assert result is True
    client = hass.data[DOMAIN]["entry_1"]["client"]
    assert not hasattr(client, "set_debug")
    assert not hasattr(client, "debug")


def test_device_can_always_be_removed():
    """Without this hook, Home Assistant hides the device page's own
    'Delete' control while the config entry is loaded, because each config
    entry here always owns exactly one device (spec.md 6a/13)."""
    result = asyncio.run(
        async_remove_config_entry_device(
            SimpleNamespace(), SimpleNamespace(entry_id="entry_1"), SimpleNamespace()
        )
    )

    assert result is True
