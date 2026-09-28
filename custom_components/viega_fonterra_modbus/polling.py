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
from .registers import known_addresses_for_topology

#: Modbus function 0x03/0x04 quantity field is one byte; a request can
#: never ask for more than this many registers in one go.
MAX_BLOCK_REGISTERS = 125


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
        """Read a register range, reusing the current polling cycle result.

        A single-register request (`count == 1`, the common case for every
        room/actuator scalar register) is grouped with any adjacent,
        individually-documented registers into one Modbus request when
        possible (spec.md 16d), so several entities' reads within the same
        polling window can be served by one request instead of one each.
        Every sub-register of that block is cached under its own
        single-register key, so a later caller asking for a different
        address inside the same block gets a cache hit instead of issuing
        its own request. A request for more than one register (e.g. a text
        field spanning several registers) is never combined with anything
        else and behaves exactly as before.
        """
        address = int(address)
        count = int(count)
        key = (bank, address, count)
        async with self._lock:
            if self._gate.is_due(hass, entry_id):
                self._values.clear()
                self.generation += 1
            if key in self._values:
                return self._values[key]
            client = hass.data[DOMAIN][entry_id]["client"]
            reader = (client.read_holding_registers if bank == "holding"
                      else client.read_input_registers)

            if count != 1:
                values = await reader(address, count)
                self._values[key] = values
                return values

            start, length = self._contiguous_block(hass, entry_id, bank, address)
            values = await reader(start, length)
            for offset, value in enumerate(values):
                self._values[(bank, start + offset, 1)] = [value]
            return self._values[key]

    def _contiguous_block(
        self, hass: HomeAssistant, entry_id: str, bank: str, address: int
    ) -> tuple[int, int]:
        """Return `(start, length)` for the block a single-register read of
        `address` should actually fetch: `address` extended with any
        adjacent addresses that are themselves documented registers this
        entry's topology reads every cycle (`registers.py`'s
        `known_addresses_for_topology`) - never an undocumented gap, and
        never mixing holding and input registers.
        """
        rooms = hass.data.get(DOMAIN, {}).get(entry_id, {}).get("rooms", {})
        holding, input_ = known_addresses_for_topology(rooms)
        known = holding if bank == "holding" else input_

        if address not in known:
            return address, 1

        start = end = address
        while (start - 1) in known and (address - (start - 1) + 1) <= MAX_BLOCK_REGISTERS:
            start -= 1
        while (end + 1) in known and ((end + 1) - start + 1) <= MAX_BLOCK_REGISTERS:
            end += 1
        return start, end - start + 1

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
