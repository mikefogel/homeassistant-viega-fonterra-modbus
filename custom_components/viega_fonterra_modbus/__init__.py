"""The Viega Fonterra Modbus integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .modbus_handler import ViegaModbusClient

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Viega Fonterra from a config entry."""
    client = ViegaModbusClient(entry.data["host"], entry.data["port"])
    await client.connect()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "host": entry.data["host"],
        "port": entry.data["port"],
        "client": client,
    }

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    _LOGGER.debug("Set up Viega Fonterra entry %s", entry.entry_id)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        client = hass.data[DOMAIN].get(entry.entry_id, {}).get("client")
        if client is not None:
            await client.disconnect()
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
