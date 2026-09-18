"""Tests for setup/unload behavior, in particular that a module stays deletable."""

import asyncio
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus import async_setup_entry, async_unload_entry
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


def test_setup_entry_uses_real_device_discovery_for_rooms(monkeypatch):
    """spec.md 4a: room/actor associations must come from the device's own
    actuator Raum-ID and room-name registers, not only from manually typed
    config - this was previously dead code (spec.md 14, "Automatic discovery
    was never wired to anything real")."""
    from custom_components.viega_fonterra_modbus.registers import actor_registers

    position_address = actor_registers(1)["position"]

    async def fake_connect(self):
        self._connected = True

    async def fake_read_input_registers(self, address, count=1):
        if address == position_address and count == 3:
            return [0, 193, 1]  # position=closed, return_temp=19.3, room_id=1
        if count == 3:
            # No actuator installed at any other slot.
            return [ViegaModbusClient.ERROR_SENTINEL] * 3
        if count == 12:
            # Room 1's name register.
            raw = "Wohnzimmer".encode("ascii").ljust(24, b"\x00")
            return [int.from_bytes(raw[i : i + 2], "little") for i in range(0, 24, 2)]
        return []

    monkeypatch.setattr(ViegaModbusClient, "connect", fake_connect)
    monkeypatch.setattr(ViegaModbusClient, "read_input_registers", fake_read_input_registers)

    entry = _make_entry({"host": "192.168.0.188", "port": 502})
    hass = SimpleNamespace(data={}, config_entries=_FakeConfigEntriesForSetup())

    asyncio.run(async_setup_entry(hass, entry))

    rooms = hass.data[DOMAIN]["entry_1"]["rooms"]
    assert rooms["room_1"]["name"] == "Wohnzimmer"
    assert rooms["room_1"]["actor"] == 1


def test_setup_entry_falls_back_to_configured_rooms_when_discovery_finds_nothing(monkeypatch):
    """If no actuator reports a valid room (e.g. all unreachable this cycle),
    the manually configured/options-flow room mapping must still be used -
    discovery must not silently wipe out an existing configuration."""

    async def fake_connect(self):
        self._connected = True

    async def fake_read_input_registers(self, address, count=1):
        if count == 3:
            return [ViegaModbusClient.ERROR_SENTINEL] * 3
        return []

    monkeypatch.setattr(ViegaModbusClient, "connect", fake_connect)
    monkeypatch.setattr(ViegaModbusClient, "read_input_registers", fake_read_input_registers)

    entry = _make_entry({"host": "192.168.0.188", "port": 502})
    entry.options = {"rooms": {"room_9": {"name": "Manually configured"}}}
    hass = SimpleNamespace(data={}, config_entries=_FakeConfigEntriesForSetup())

    asyncio.run(async_setup_entry(hass, entry))

    rooms = hass.data[DOMAIN]["entry_1"]["rooms"]
    assert rooms == {"room_9": {"name": "Manually configured"}}
