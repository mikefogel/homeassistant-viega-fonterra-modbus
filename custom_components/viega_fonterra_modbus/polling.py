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
import asyncio

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


class SharedPolling:
    """Per-entry cache that ensures entities share each Modbus poll."""

    def __init__(self) -> None:
        self._gate = PollingGate()
        self._values: dict[tuple[str, int, int], list[int]] = {}
        self._lock = asyncio.Lock()
        #: Incremented every time the cache is cleared for a new polling
        #: window. Used by write-verification (spec.md 16c) to tell a
        #: freshly fetched register value apart from one still sitting in
        #: the cache from before a write was issued.
        self.generation = 0

    async def read(self, hass: HomeAssistant, entry_id: str, bank: str, address: int, count: int = 1):
        """Read a register range, reusing the current polling cycle result."""
        key = (bank, int(address), int(count))
        async with self._lock:
            if self._gate.is_due(hass, entry_id):
                self._values.clear()
                self.generation += 1
            if key in self._values:
                return self._values[key]
            client = hass.data[DOMAIN][entry_id]["client"]
            reader = (client.read_holding_registers if bank == "holding"
                      else client.read_input_registers)
            values = await reader(int(address), int(count))
            self._values[key] = values
            return values

    async def run_exclusive(self, action):
        """Run `action` (a zero-arg async callable) while holding this
        entry's shared polling lock.

        Used by the explicit rediscovery action (spec.md 16a) so its own
        run of raw Modbus reads over the shared connection cannot interleave
        with a normal entity poll cycle's cache population - it reuses the
        same lock every regular `read()` call already goes through, instead
        of opening a second connection or running a second poller.
        """
        async with self._lock:
            return await action()
