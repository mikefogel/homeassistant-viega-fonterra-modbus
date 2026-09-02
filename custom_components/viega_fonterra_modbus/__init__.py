"""The Viega Fonterra Modbus integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .modbus_handler import ViegaModbusClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Viega Fonterra from a config entry."""
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    timeout = float(entry.data.get("modbus_timeout", 5))
    client = ViegaModbusClient(entry.data["host"], entry.data["port"], timeout=timeout)
    await client.connect()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "host": entry.data["host"],
        "port": entry.data["port"],
        "client": client,
        "device_name": entry.data.get("device_name", "Fonterra"),
        "polling_interval": entry.data.get("polling_interval", 30),
        "modbus_timeout": timeout,
        "rooms": entry.options.get("rooms", {}),
        "device_id": entry.options.get("device_id", ""),
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("Set up Viega Fonterra entry %s", entry.entry_id)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry after settings are changed in the UI."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        client = hass.data[DOMAIN].get(entry.entry_id, {}).get("client")
        if client is not None:
            await client.disconnect()
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
