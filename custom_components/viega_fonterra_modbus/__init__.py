"""The Viega Fonterra Modbus integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_MODBUS_DEBUG, DOMAIN, PLATFORMS
from .modbus_handler import ModbusClientError, ViegaModbusClient
from .polling import SharedPolling
from .room_mapping import RoomMappingDiscovery
from .registers import BASE_UNIT_REGISTERS, decode_text_registers

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Viega Fonterra from a config entry."""
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    timeout = float(entry.data.get("modbus_timeout", 5))
    client = ViegaModbusClient(entry.data["host"], entry.data["port"], timeout=timeout)
    client.set_debug(bool(entry.data.get(CONF_MODBUS_DEBUG, False)))
    try:
        await client.connect()
    except ModbusClientError as err:
        # Let Home Assistant retry with backoff instead of leaving the entry
        # stuck in a hard error state (spec.md 6a: a failed module must not
        # block the rest of the setup or require a manual reload).
        raise ConfigEntryNotReady(
            f"Could not connect to {entry.data['host']}:{entry.data['port']}: {err}"
        ) from err

    # Discovery is deliberately completed before forwarding platforms: entity
    # constructors must only see the persisted, resolved topology.
    rooms = entry.options.get("rooms", {})
    discover = (
        getattr(client, "discover", None)
        or getattr(client, "discover_rooms", None)
        or getattr(client, "read_discovery", None)
        or getattr(client, "read_device_configuration", None)
    )
    if discover is not None:
        try:
            payload = await discover()
            discovered = RoomMappingDiscovery.discover(payload)
            if discovered:
                rooms = discovered
        except Exception:
            _LOGGER.debug("Initial room discovery failed", exc_info=True)
    identity: dict[str, object] = {}
    for key, count in (("wlan_serial_number", 5), ("base_unit_serial_number", 5), ("base_unit_name", 12)):
        try:
            values = await client.read_input_registers(BASE_UNIT_REGISTERS[key], count)
            if values and values[0] != ViegaModbusClient.ERROR_SENTINEL:
                identity[key] = decode_text_registers(values)
        except Exception:
            _LOGGER.debug("Initial identity read failed for %s", key, exc_info=True)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "host": entry.data["host"],
        "port": entry.data["port"],
        "client": client,
        "device_name": entry.data.get("device_name", "Fonterra"),
        "polling_interval": entry.data.get("polling_interval", 30),
        "modbus_timeout": timeout,
        "rooms": rooms,
        "device_id": entry.options.get("device_id", ""),
        "polling": SharedPolling(),
        "identity": identity,
    }

    update_entry = getattr(hass.config_entries, "async_update_entry", None)
    if update_entry and (
        rooms != entry.options.get("rooms", {}) or identity
    ):
        update_entry(
            entry,
            options={**entry.options, "rooms": rooms, "_identity": identity},
        )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("Set up Viega Fonterra entry %s", entry.entry_id)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry after settings are changed in the UI."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry so the module (and its device) can be removed.

    Must succeed even when the device is offline or its socket is already
    broken (spec.md 6a/13: a module must always be deletable through the
    Home Assistant UI).
    """
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        client = entry_data.get("client") if entry_data else None
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                # A disconnect failure must never block removal.
                _LOGGER.warning(
                    "Error disconnecting Viega client for %s", entry.entry_id, exc_info=True
                )
    return unload_ok
