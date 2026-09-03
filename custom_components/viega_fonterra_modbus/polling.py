"""Per-entry polling-interval throttling shared by all entities.

Home Assistant platforms poll entities at a fixed `SCAN_INTERVAL`. To honor
each config entry's user-configured `polling_interval` (spec.md 3/6b,
minimum 5 seconds) without a full DataUpdateCoordinator rewrite, every
platform sets `SCAN_INTERVAL` to the spec-mandated minimum (5 seconds) and
each entity holds a `PollingGate` that skips the actual Modbus read until
the configured interval has elapsed, keeping the last known value in the
meantime.
"""

from __future__ import annotations

import time

from homeassistant.core import HomeAssistant

from .const import DEFAULT_POLLING_INTERVAL, DOMAIN


class PollingGate:
    """Track whether enough time has passed to justify a real device read."""

    def __init__(self) -> None:
        self._next_due = 0.0

    def is_due(self, hass: HomeAssistant, entry_id: str) -> bool:
        """Return True (and arm the next window) if a read should happen now."""
        now = time.monotonic()
        if now < self._next_due:
            return False
        interval = hass.data.get(DOMAIN, {}).get(entry_id, {}).get(
            "polling_interval", DEFAULT_POLLING_INTERVAL
        )
        self._next_due = now + float(interval)
        return True
