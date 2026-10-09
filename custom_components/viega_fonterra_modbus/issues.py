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
#: How often the unreachable condition is re-evaluated.
CHECK_INTERVAL = timedelta(minutes=1)

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

    @callback
    def async_start(self) -> CALLBACK_TYPE:
        """Start the periodic unreachable check; returns its cancel callback."""
        return async_track_time_interval(
            self.hass, self.async_check_unreachable, CHECK_INTERVAL
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
