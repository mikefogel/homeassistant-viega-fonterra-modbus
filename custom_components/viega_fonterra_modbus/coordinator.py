"""One polling cycle per module (spec.md 16i).

`ViegaDataCoordinator` reads every register the module's entities need once
per `polling_interval`, in contiguous block reads (spec.md 16d), and then
notifies all of the module's entities together. Entities no longer poll the
device themselves: they look their registers up in the coordinator's latest
data through `read()`, the same call shape the per-entity polling used, so
their value handling (`-99`, keeping the last valid value, read-after-write
verification) is unchanged.

A failed read never fails the whole cycle and never raises `UpdateFailed`:
the affected registers are simply missing from that cycle's data, every
entity keeps its last valid value (spec.md 10) and stays available, and the
transport reconnects on its own (spec.md 11c).
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, TypeVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .modbus_handler import ModbusClientError
from .registers import known_addresses_for_topology

_LOGGER = logging.getLogger(__name__)

#: Modbus function 0x03/0x04 quantity field is one byte; a request can never
#: ask for more than this many registers in one go.
MAX_BLOCK_REGISTERS = 125

#: A register an entity asked for outside the topology's known set is kept
#: in the polling plan until it has not been asked for in this many cycles
#: (e.g. after rediscovery removed the room that needed it).
REQUEST_TTL_CYCLES = 3

ReadKey = tuple[str, int, int]  # (bank, address, count)
_T = TypeVar("_T")


def contiguous_runs(addresses: set[int]) -> list[tuple[int, int]]:
    """Group addresses into `(start, length)` runs of adjacent registers,
    each at most `MAX_BLOCK_REGISTERS` long - never spanning a gap, so no
    undocumented register is ever read (spec.md 16d)."""
    runs: list[tuple[int, int]] = []
    for address in sorted(addresses):
        if runs:
            start, length = runs[-1]
            if address == start + length and length < MAX_BLOCK_REGISTERS:
                runs[-1] = (start, length + 1)
                continue
        runs.append((address, 1))
    return runs


class ViegaDataCoordinator(DataUpdateCoordinator[dict[ReadKey, list[int]]]):
    """Polls one Viega module and hands the result to all its entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: Any,
        polling_interval: float,
    ) -> None:
        kwargs: dict[str, Any] = {
            "name": f"{DOMAIN} {entry.entry_id}",
            "update_interval": timedelta(seconds=float(polling_interval)),
        }
        # `config_entry` became a constructor argument in newer Home
        # Assistant versions; older ones (hacs.json minimum) do not accept it.
        if "config_entry" in inspect.signature(DataUpdateCoordinator.__init__).parameters:
            kwargs["config_entry"] = entry
        super().__init__(hass, _LOGGER, **kwargs)
        self.entry_id = entry.entry_id
        self.client = client
        #: Incremented once per completed cycle. Read-after-write
        #: verification (spec.md 16c) only judges a value from a cycle newer
        #: than the write, and the circulation-pump debounce (spec.md 5c)
        #: counts each cycle once.
        self.generation = 0
        self._requested: dict[ReadKey, int] = {}
        self._lock = asyncio.Lock()

    async def read(
        self, hass: HomeAssistant, entry_id: str, bank: str, address: int, count: int = 1
    ) -> list[int]:
        """Return a register range from the latest cycle.

        Never touches the device. A range that was not part of the latest
        cycle (not polled yet, or its block read failed) raises
        `ModbusClientError`, exactly like a failed live read, so the caller
        keeps its last valid value; it is also added to the plan of the
        next cycle.
        """
        key: ReadKey = (bank, int(address), int(count))
        self._requested[key] = self.generation
        data = self.data or {}
        if key in data:
            return data[key]
        raise ModbusClientError(f"{bank} register {address} (x{count}) not in the latest poll")

    async def run_exclusive(self, action: Callable[[], Awaitable[_T]]) -> _T:
        """Run `action` without a polling cycle in between (rediscovery,
        spec.md 16a): it shares the connection with the cycle's reads."""
        async with self._lock:
            return await action()

    def _plan(self) -> tuple[dict[str, set[int]], set[ReadKey]]:
        rooms = self.hass.data.get(DOMAIN, {}).get(self.entry_id, {}).get("rooms", {})
        holding, input_ = known_addresses_for_topology(rooms)
        singles: dict[str, set[int]] = {"holding": set(holding), "input": set(input_)}
        multis: set[ReadKey] = set()
        for key, last_asked in list(self._requested.items()):
            if self.generation - last_asked > REQUEST_TTL_CYCLES:
                del self._requested[key]
                continue
            bank, address, count = key
            if count == 1:
                singles.setdefault(bank, set()).add(address)
            else:
                multis.add(key)
        return singles, multis

    async def _async_update_data(self) -> dict[ReadKey, list[int]]:
        async with self._lock:
            singles, multis = self._plan()
            data: dict[ReadKey, list[int]] = {}
            for bank, addresses in singles.items():
                reader = self._reader(bank)
                for start, length in contiguous_runs(addresses):
                    values = await self._try_read(reader, bank, start, length)
                    if values is None:
                        continue
                    for offset, value in enumerate(values):
                        data[(bank, start + offset, 1)] = [value]
            for bank, address, count in sorted(multis):
                values = await self._try_read(self._reader(bank), bank, address, count)
                if values is not None:
                    data[(bank, address, count)] = values
            self.generation += 1
            return data

    def _reader(self, bank: str):
        return (
            self.client.read_holding_registers
            if bank == "holding"
            else self.client.read_input_registers
        )

    async def _try_read(self, reader, bank: str, address: int, count: int) -> list[int] | None:
        try:
            return await reader(address, count)
        except Exception:  # noqa: BLE001 - one failed block must not fail the cycle
            _LOGGER.debug(
                "Entry %s: reading %s registers %s-%s failed",
                self.entry_id, bank, address, address + count - 1, exc_info=True,
            )
            return None
