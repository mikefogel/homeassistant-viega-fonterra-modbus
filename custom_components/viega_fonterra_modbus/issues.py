"""Entries in Home Assistant's Settings -> Repairs list (spec.md 16j).

Raised for problems that need attention and do not fix themselves within a
few poll cycles, so a user who is not watching the dashboard - or has no
physical access to the installation - still notices them. Every issue clears
itself once the problem is gone; none of them has a repair flow.

Only values the integration already reads are used; nothing here issues a
Modbus request of its own.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .registers import BASE_UNIT_ERROR_CODES, ERROR_CODE_WARNINGS

#: A module without any successful response for this long is reported.
UNREACHABLE_AFTER = timedelta(minutes=30)
#: A register the module keeps rejecting for this long is reported.
REJECTED_AFTER = timedelta(minutes=30)
#: How often both conditions are re-evaluated.
CHECK_INTERVAL = timedelta(minutes=1)
#: At most this many registers are named in the issue text.
MAX_LISTED_REGISTERS = 10

ERROR_SENTINEL = -99


class ModuleIssues:
    """Raise and clear the repair issues of one configured module."""

    def __init__(self, hass: HomeAssistant, entry_id: str, device_name: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.device_name = device_name
        self.setup_time = dt_util.utcnow()
        self.unreachable_issue_id = f"{entry_id}_module_unreachable"
        self.error_issue_id = f"{entry_id}_base_unit_error"
        self.stale_issue_id = f"{entry_id}_registers_not_updating"

    @callback
    def async_start(self) -> CALLBACK_TYPE:
        """Start the periodic checks; returns their cancel callback."""
        return async_track_time_interval(self.hass, self._async_check, CHECK_INTERVAL)

    @callback
    def _async_check(self, now: datetime | None = None) -> None:
        self.async_check_unreachable(now)
        self.async_check_rejected(now)

    @callback
    def async_check_rejected(self, now: datetime | None = None) -> None:
        """Raise "values not updating" when the reachable module has rejected
        a register in every cycle for `REJECTED_AFTER` (spec.md 16j); clear
        it once every register is read again."""
        entry_data = self.hass.data.get(DOMAIN, {}).get(self.entry_id)
        coordinator = entry_data.get("polling") if entry_data else None
        rejected_since = getattr(coordinator, "rejected_since", {})
        current = dt_util.utcnow()
        stale = {
            key: since for key, since in rejected_since.items()
            if current - since >= REJECTED_AFTER
        }
        if not stale:
            ir.async_delete_issue(self.hass, DOMAIN, self.stale_issue_id)
            return
        labels = coordinator.rejected_labels(stale)
        listed = ", ".join(labels[:MAX_LISTED_REGISTERS])
        if len(labels) > MAX_LISTED_REGISTERS:
            listed += f" (+{len(labels) - MAX_LISTED_REGISTERS})"
        codes = sorted({
            coordinator.rejected_now[key] for key in stale if key in coordinator.rejected_now
        })
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self.stale_issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="registers_not_updating",
            translation_placeholders={
                "device": self.device_name,
                "registers": listed,
                "codes": ", ".join(str(code) for code in codes),
                "since": dt_util.as_local(min(stale.values())).strftime("%Y-%m-%d %H:%M"),
            },
        )

    @callback
    def async_check_unreachable(self, now: datetime | None = None) -> None:
        """Raise the issue after `UNREACHABLE_AFTER` without a successful
        response (counted from setup if there has never been one); clear it
        as soon as a response arrives."""
        entry_data = self.hass.data.get(DOMAIN, {}).get(self.entry_id)
        if entry_data is None:
            return
        last_success = getattr(entry_data.get("client"), "last_success_time", None)
        since = last_success or self.setup_time
        if dt_util.utcnow() - since < UNREACHABLE_AFTER:
            ir.async_delete_issue(self.hass, DOMAIN, self.unreachable_issue_id)
            return
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self.unreachable_issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="module_unreachable",
            translation_placeholders={
                "device": self.device_name,
                "since": dt_util.as_local(since).strftime("%Y-%m-%d %H:%M"),
            },
        )

    @callback
    def async_update_base_unit_error(self, code: int | None) -> None:
        """Mirror the base-unit error code (spec.md 3b) into the issue list.

        A failed or `-99` read neither raises nor clears the issue (spec.md
        10). Each known code has its own translation key, so the text is
        fully translated; unknown codes share one generic key.
        """
        if code is None or code == ERROR_SENTINEL:
            return
        if code == 0:
            ir.async_delete_issue(self.hass, DOMAIN, self.error_issue_id)
            return
        known = code in BASE_UNIT_ERROR_CODES
        ir.async_create_issue(
            self.hass,
            DOMAIN,
            self.error_issue_id,
            is_fixable=False,
            severity=(
                ir.IssueSeverity.WARNING
                if code in ERROR_CODE_WARNINGS
                else ir.IssueSeverity.ERROR
            ),
            translation_key=f"base_unit_error_{code}" if known else "base_unit_error_unknown",
            translation_placeholders={"device": self.device_name, "code": str(code)},
        )

    @callback
    def async_remove_all(self) -> None:
        """Delete this module's issues (unload/removal)."""
        ir.async_delete_issue(self.hass, DOMAIN, self.unreachable_issue_id)
        ir.async_delete_issue(self.hass, DOMAIN, self.error_issue_id)
        ir.async_delete_issue(self.hass, DOMAIN, self.stale_issue_id)
