"""Shared Home Assistant device_info builder for all platforms.

Centralizing this avoids every platform hard-coding a fixed device name,
which previously made the configured `device_name` (spec.md 6a) invisible
in the Home Assistant device registry.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .const import DEFAULT_NAME, DOMAIN


def build_device_info(hass: HomeAssistant, entry_id: str) -> dict[str, object]:
    """Return the device_info dict for a config entry's HA device.

    Uses the module's configured display name so renaming a module through
    the options flow (spec.md 6a) is reflected in the device registry.
    """
    entry_data = hass.data.get(DOMAIN, {}).get(entry_id, {})
    name = entry_data.get("device_name") or DEFAULT_NAME
    return {
        "identifiers": {(DOMAIN, entry_id)},
        "name": name,
        "manufacturer": "Viega",
        "model": "Smart Control",
    }
