"""Tests for setup/unload behavior, in particular that a module stays deletable."""

import asyncio
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus import async_setup_entry, async_unload_entry
from custom_components.viega_fonterra_modbus.const import CONF_MODBUS_DEBUG, DOMAIN
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


def test_setup_entry_enables_client_debug_logging_when_configured(monkeypatch):
    """The modbus_debug option must actually reach the client, otherwise
    users have no way to turn on the TX/RX frame logging documented in the
    README - the client's set_debug()/debug flag was previously dead code
    outside of unit tests."""

    async def fake_connect(self):
        self._connected = True

    async def fake_read_input_registers(self, address, count=1):
        return []

    monkeypatch.setattr(ViegaModbusClient, "connect", fake_connect)
    monkeypatch.setattr(ViegaModbusClient, "read_input_registers", fake_read_input_registers)

    entry = _make_entry(
        {"host": "192.168.8.20", "port": 1502, CONF_MODBUS_DEBUG: True}
    )
    hass = SimpleNamespace(data={}, config_entries=_FakeConfigEntriesForSetup())

    asyncio.run(async_setup_entry(hass, entry))

    client = hass.data[DOMAIN]["entry_1"]["client"]
    assert client.debug is True


def test_setup_entry_leaves_client_debug_logging_disabled_by_default(monkeypatch):
    async def fake_connect(self):
        self._connected = True

    async def fake_read_input_registers(self, address, count=1):
        return []

    monkeypatch.setattr(ViegaModbusClient, "connect", fake_connect)
    monkeypatch.setattr(ViegaModbusClient, "read_input_registers", fake_read_input_registers)

    entry = _make_entry({"host": "192.168.8.20", "port": 1502})
    hass = SimpleNamespace(data={}, config_entries=_FakeConfigEntriesForSetup())

    asyncio.run(async_setup_entry(hass, entry))

    client = hass.data[DOMAIN]["entry_1"]["client"]
    assert client.debug is False
