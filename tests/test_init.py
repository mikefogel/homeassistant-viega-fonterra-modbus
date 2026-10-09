"""Tests for setup/unload behavior, in particular that a module stays deletable."""

import asyncio
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus import (
    SERVICE_OVERVIEW,
    SERVICE_REDISCOVER,
    async_remove_config_entry_device,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.modbus_handler import (
    ModbusClientError,
    ViegaModbusClient,
)
from homeassistant.exceptions import ConfigEntryNotReady


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


def test_setup_entry_lets_home_assistant_retry_when_the_initial_connect_fails(monkeypatch):
    """spec.md 6c: "If the initial Modbus TCP connection cannot be
    established when a config entry is set up, the integration must signal
    Home Assistant to retry with backoff (rather than leaving the entry in
    a hard error state that requires a manual reload)." - a raised
    `ConfigEntryNotReady` is exactly that signal; anything else (a bare
    exception, or swallowing the error and continuing) would not trigger
    Home Assistant's own retry-with-backoff mechanism."""

    async def fake_connect_that_fails(self):
        raise ModbusClientError("Connection timeout after 5s")

    monkeypatch.setattr(ViegaModbusClient, "connect", fake_connect_that_fails)

    entry = _make_entry({"host": "192.168.8.20", "port": 1502})
    hass = SimpleNamespace(data={}, config_entries=_FakeConfigEntriesForSetup())

    try:
        asyncio.run(async_setup_entry(hass, entry))
    except ConfigEntryNotReady as err:
        assert "192.168.8.20" in str(err)
    else:
        raise AssertionError("expected ConfigEntryNotReady when the initial connect fails")

    # No half-initialized entry data must be left behind for a connection
    # that never actually succeeded.
    assert "entry_1" not in hass.data.get(DOMAIN, {})


# --- Domain-wide `rediscover` service (spec.md 16a) ----------------------


class _FakeServices:
    def __init__(self):
        self.registered = {}

    def async_register(self, domain, service, handler, schema=None, supports_response=None):
        self.registered[(domain, service)] = handler


class _FakeDeviceEntry:
    def __init__(self, config_entries):
        self.config_entries = config_entries


class _FakeDeviceRegistry:
    def __init__(self, devices):
        self._devices = devices

    def async_get(self, device_id):
        return self._devices.get(device_id)


def test_async_setup_registers_the_rediscover_service():
    hass = SimpleNamespace(services=_FakeServices(), data={})

    result = asyncio.run(async_setup(hass, {}))

    assert result is True
    assert (DOMAIN, SERVICE_REDISCOVER) in hass.services.registered


def test_async_setup_registers_the_overview_service():
    hass = SimpleNamespace(services=_FakeServices(), data={})

    asyncio.run(async_setup(hass, {}))

    assert (DOMAIN, SERVICE_OVERVIEW) in hass.services.registered


def test_overview_service_returns_the_multi_module_summary():
    hass = SimpleNamespace(
        services=_FakeServices(),
        data={DOMAIN: {"entry_1": {"client": None, "rooms": {}}}},
    )

    asyncio.run(async_setup(hass, {}))
    handler = hass.services.registered[(DOMAIN, SERVICE_OVERVIEW)]

    response = asyncio.run(handler(SimpleNamespace(data={})))

    assert response["modules"][0]["entry_id"] == "entry_1"


def test_rediscover_service_resolves_the_device_to_its_config_entry(monkeypatch):
    calls: list[str] = []

    async def fake_rediscover(hass, entry):
        calls.append(entry.entry_id)

    monkeypatch.setattr(
        "custom_components.viega_fonterra_modbus.async_rediscover_entry", fake_rediscover
    )
    monkeypatch.setattr(
        "custom_components.viega_fonterra_modbus.dr.async_get",
        lambda hass: _FakeDeviceRegistry({"device_1": _FakeDeviceEntry({"entry_1"})}),
    )

    entry = SimpleNamespace(entry_id="entry_1")
    hass = SimpleNamespace(
        services=_FakeServices(),
        data={DOMAIN: {"entry_1": {}}},
        config_entries=SimpleNamespace(async_get_entry=lambda entry_id: entry),
    )

    asyncio.run(async_setup(hass, {}))
    handler = hass.services.registered[(DOMAIN, SERVICE_REDISCOVER)]
    asyncio.run(handler(SimpleNamespace(data={"device_id": "device_1"})))

    assert calls == ["entry_1"]


def test_rediscover_service_is_a_noop_when_the_device_has_no_loaded_entry(monkeypatch):
    monkeypatch.setattr(
        "custom_components.viega_fonterra_modbus.dr.async_get",
        lambda hass: _FakeDeviceRegistry({"device_1": _FakeDeviceEntry({"entry_1"})}),
    )
    hass = SimpleNamespace(services=_FakeServices(), data={DOMAIN: {}})

    asyncio.run(async_setup(hass, {}))
    handler = hass.services.registered[(DOMAIN, SERVICE_REDISCOVER)]

    asyncio.run(handler(SimpleNamespace(data={"device_id": "device_1"})))  # must not raise


def test_rediscover_service_raises_for_an_unknown_device(monkeypatch):
    monkeypatch.setattr(
        "custom_components.viega_fonterra_modbus.dr.async_get",
        lambda hass: _FakeDeviceRegistry({}),
    )
    hass = SimpleNamespace(services=_FakeServices(), data={DOMAIN: {}})

    asyncio.run(async_setup(hass, {}))
    handler = hass.services.registered[(DOMAIN, SERVICE_REDISCOVER)]

    try:
        asyncio.run(handler(SimpleNamespace(data={"device_id": "unknown"})))
    except Exception:
        pass
    else:
        raise AssertionError("expected an error for an unknown device_id")


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
