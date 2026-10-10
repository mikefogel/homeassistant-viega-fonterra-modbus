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
from datetime import datetime, timedelta
from typing import Any, TypeVar

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .modbus_handler import ModbusClientError
from .registers import known_addresses_for_topology, register_labels

_LOGGER = logging.getLogger(__name__)

#: Modbus function 0x03/0x04 quantity field is one byte; a request can never
#: ask for more than this many registers in one go.
MAX_BLOCK_REGISTERS = 125

#: Cooldown between cycles requested after writes (spec.md 16c): short, so a
#: second change is read back promptly, instead of Home Assistant's 10 s.
REQUEST_REFRESH_COOLDOWN = 1.0

#: A register an entity asked for outside the topology's known set is kept
#: in the polling plan until it has not been asked for in this many cycles
#: (e.g. after rediscovery removed the room that needed it).
REQUEST_TTL_CYCLES = 3

ReadKey = tuple[str, int, int]  # (bank, address, count)

#: The device's "value not available" sentinel (spec.md 10).
ERROR_SENTINEL = -99
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
            "request_refresh_debouncer": Debouncer(
                hass, _LOGGER, cooldown=REQUEST_REFRESH_COOLDOWN, immediate=True
            ),
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
        #: Registers that were `-99` in the latest cycle, and in how many
        #: cycles each register has been `-99` since setup (spec.md 16b).
        self.invalid_now: set[ReadKey] = set()
        self.invalid_cycles: dict[ReadKey, int] = {}
        #: Registers the module answered with a Modbus exception even when
        #: read alone (key -> exception code), and in how many cycles
        #: (spec.md 16d).
        self.rejected_now: dict[ReadKey, int] = {}
        self.rejected_cycles: dict[ReadKey, int] = {}
        #: Since when each currently rejected register has been rejected in
        #: every cycle (UTC); drives the "values not updating" repair issue.
        self.rejected_since: dict[ReadKey, datetime] = {}
        #: Registers of a rejected block; read one by one from then on.
        self._read_singly: set[tuple[str, int]] = set()
        self._warned_rejected: set[ReadKey] = set()

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
            rejected: dict[ReadKey, int] = {}
            for bank, addresses in singles.items():
                reader = self._reader(bank)
                one_by_one = {a for a in addresses if (bank, a) in self._read_singly}
                for start, length in contiguous_runs(addresses - one_by_one):
                    values, exception_code = await self._try_read(reader, bank, start, length)
                    if values is not None:
                        for offset, value in enumerate(values):
                            data[(bank, start + offset, 1)] = [value]
                    elif exception_code is not None and length > 1:
                        # The module rejects this block: read its registers
                        # one by one, now and in later cycles (spec.md 16d).
                        _LOGGER.warning(
                            "Entry %s: the module rejected reading %s registers %s-%s "
                            "(Modbus exception %s); reading them one by one",
                            self.entry_id, bank, start, start + length - 1, exception_code,
                        )
                        block = set(range(start, start + length))
                        self._read_singly.update((bank, a) for a in block)
                        one_by_one |= block
                    elif exception_code is not None:
                        rejected[(bank, start, 1)] = exception_code
                for address in sorted(one_by_one):
                    values, exception_code = await self._try_read(reader, bank, address, 1)
                    if values is not None:
                        data[(bank, address, 1)] = values
                    elif exception_code is not None:
                        rejected[(bank, address, 1)] = exception_code
            for bank, address, count in sorted(multis):
                values, exception_code = await self._try_read(
                    self._reader(bank), bank, address, count
                )
                if values is not None:
                    data[(bank, address, count)] = values
                elif exception_code is not None:
                    rejected[(bank, address, count)] = exception_code
            self.generation += 1
            self._track_invalid(data)
            self._track_rejected(rejected)
            return data

    def _track_rejected(self, rejected: dict[ReadKey, int]) -> None:
        self.rejected_now = rejected
        now = dt_util.utcnow()
        self.rejected_since = {
            key: self.rejected_since.get(key, now) for key in rejected
        }
        for key, exception_code in rejected.items():
            self.rejected_cycles[key] = self.rejected_cycles.get(key, 0) + 1
            if key not in self._warned_rejected:
                self._warned_rejected.add(key)
                _LOGGER.warning(
                    "Entry %s: the module rejects reading %s (%s register %s, "
                    "Modbus exception %s); its value cannot be updated",
                    self.entry_id, self._label(key)[0], key[0], key[1], exception_code,
                )

    def rejected_labels(self, keys) -> list[str]:
        """Identifiers with room name, e.g. `room_2.error_code (Bad)`."""
        labels = []
        for key in sorted(keys):
            identifier, room = self._label(key)
            labels.append(f"{identifier} ({room})" if room else identifier)
        return labels

    def rejected_register_ids(self) -> list[str]:
        """Identifiers of the registers the module rejected in the latest cycle."""
        return sorted(self._label(key)[0] for key in self.rejected_now)

    def rejected_registers_report(self) -> list[dict[str, Any]]:
        """Every register the module has rejected, for the diagnostics export."""
        report = []
        for key, cycles in sorted(self.rejected_cycles.items()):
            bank, address, count = key
            identifier, room = self._label(key)
            report.append({
                "register": identifier,
                "room": room,
                "bank": bank,
                "address": address,
                "manual_address": (40000 if bank == "holding" else 30000) + address,
                "count": count,
                "exception_code": self.rejected_now.get(key),
                "rejected_cycles": cycles,
                "rejected_now": key in self.rejected_now,
            })
        return report

    def _track_invalid(self, data: dict[ReadKey, list[int]]) -> None:
        self.invalid_now = {
            key for key, values in data.items() if values and values[0] == ERROR_SENTINEL
        }
        for key in self.invalid_now:
            self.invalid_cycles[key] = self.invalid_cycles.get(key, 0) + 1

    def _label(self, key: ReadKey) -> tuple[str, str | None]:
        rooms = self.hass.data.get(DOMAIN, {}).get(self.entry_id, {}).get("rooms", {})
        bank, address, _ = key
        return register_labels(rooms).get((bank, address), (f"{bank}_{address}", None))

    def invalid_register_ids(self) -> list[str]:
        """Identifiers of the registers that were `-99` in the latest cycle."""
        return sorted(self._label(key)[0] for key in self.invalid_now)

    def invalid_registers_report(self) -> list[dict[str, Any]]:
        """Every register that has been `-99` at least once, for the
        diagnostics export (spec.md 16e)."""
        report = []
        for key, cycles in sorted(self.invalid_cycles.items()):
            bank, address, count = key
            identifier, room = self._label(key)
            report.append({
                "register": identifier,
                "room": room,
                "bank": bank,
                "address": address,
                "manual_address": (40000 if bank == "holding" else 30000) + address,
                "count": count,
                "invalid_cycles": cycles,
                "invalid_now": key in self.invalid_now,
            })
        return report

    def _reader(self, bank: str):
        return (
            self.client.read_holding_registers
            if bank == "holding"
            else self.client.read_input_registers
        )

    async def _try_read(
        self, reader, bank: str, address: int, count: int
    ) -> tuple[list[int] | None, int | None]:
        """Return `(values, None)`, or `(None, exception_code)` - the code is
        set only when the module answered with a Modbus exception response,
        not for transport failures."""
        try:
            return await reader(address, count), None
        except Exception as err:  # noqa: BLE001 - one failed block must not fail the cycle
            _LOGGER.debug(
                "Entry %s: reading %s registers %s-%s failed",
                self.entry_id, bank, address, address + count - 1, exc_info=True,
            )
            return None, getattr(err, "exception_code", None)
