"""Tests for setup/unload behavior, in particular that a module stays deletable."""

import asyncio
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus import async_unload_entry
from custom_components.viega_fonterra_modbus.const import DOMAIN


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
