"""Repairs entries for an unreachable module and base-unit errors (spec.md 16j)."""

from __future__ import annotations

import json
import re
from datetime import timedelta
from pathlib import Path

import pytest
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.issues import (
    CHECK_INTERVAL,
    REJECTED_AFTER,
    UNREACHABLE_AFTER,
)
from custom_components.viega_fonterra_modbus.registers import (
    BASE_UNIT_ERROR_CODES,
    BASE_UNIT_REGISTERS,
    ERROR_CODE_WARNINGS,
)
from tests.test_setup_lifecycle import FakeClient, _entry, fake_device  # noqa: F401

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

TRANSLATIONS = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "viega_fonterra_modbus"
    / "translations"
)


async def _setup(hass, entry=None):
    entry = entry or _entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, hass.data[DOMAIN][entry.entry_id]


def _issue(hass, issue_id):
    return ir.async_get(hass).async_get_issue(DOMAIN, issue_id)


# --- Module unreachable ---------------------------------------------------


async def test_unreachable_issue_after_30_minutes_without_a_response(hass, fake_device):
    entry, data = await _setup(hass)
    issues = data["issues"]
    issues.setup_time = dt_util.utcnow() - UNREACHABLE_AFTER - timedelta(seconds=1)

    issues.async_check_unreachable()

    issue = _issue(hass, f"{entry.entry_id}_module_unreachable")
    assert issue is not None
    assert issue.severity == ir.IssueSeverity.ERROR
    assert issue.is_fixable is False
    assert issue.translation_key == "module_unreachable"
    assert issue.translation_placeholders["device"] == "Fonterra"


async def test_no_unreachable_issue_within_30_minutes(hass, fake_device):
    entry, data = await _setup(hass)
    data["client"].last_success_time = dt_util.utcnow() - UNREACHABLE_AFTER + timedelta(minutes=1)

    data["issues"].async_check_unreachable()

    assert _issue(hass, f"{entry.entry_id}_module_unreachable") is None


async def test_unreachable_issue_clears_on_the_next_response(hass, fake_device):
    entry, data = await _setup(hass)
    issues = data["issues"]
    data["client"].last_success_time = dt_util.utcnow() - timedelta(hours=2)
    issues.async_check_unreachable()
    assert _issue(hass, f"{entry.entry_id}_module_unreachable") is not None

    data["client"].last_success_time = dt_util.utcnow()
    issues.async_check_unreachable()

    assert _issue(hass, f"{entry.entry_id}_module_unreachable") is None


async def test_unreachable_check_runs_periodically(hass, fake_device):
    entry, data = await _setup(hass)
    data["client"].last_success_time = dt_util.utcnow() - timedelta(hours=1)

    async_fire_time_changed(hass, dt_util.utcnow() + CHECK_INTERVAL + timedelta(seconds=1))
    await hass.async_block_till_done()

    assert _issue(hass, f"{entry.entry_id}_module_unreachable") is not None


# --- Base-unit error ------------------------------------------------------


async def test_error_code_raises_a_translated_issue_with_matching_severity(hass, fake_device):
    entry, data = await _setup(hass)
    issue_id = f"{entry.entry_id}_base_unit_error"

    data["issues"].async_update_base_unit_error(5)
    issue = _issue(hass, issue_id)
    assert issue.translation_key == "base_unit_error_5"
    assert issue.severity == ir.IssueSeverity.ERROR
    assert issue.translation_placeholders == {"device": "Fonterra", "code": "5"}

    # A different code replaces the issue, a warning code lowers the severity.
    data["issues"].async_update_base_unit_error(22)
    issue = _issue(hass, issue_id)
    assert issue.translation_key == "base_unit_error_22"
    assert issue.severity == ir.IssueSeverity.WARNING


async def test_unknown_error_code_uses_the_generic_issue(hass, fake_device):
    entry, data = await _setup(hass)

    data["issues"].async_update_base_unit_error(77)

    issue = _issue(hass, f"{entry.entry_id}_base_unit_error")
    assert issue.translation_key == "base_unit_error_unknown"
    assert issue.severity == ir.IssueSeverity.ERROR
    assert issue.translation_placeholders["code"] == "77"


async def test_sentinel_or_failed_reads_neither_raise_nor_clear(hass, fake_device):
    entry, data = await _setup(hass)
    issue_id = f"{entry.entry_id}_base_unit_error"

    data["issues"].async_update_base_unit_error(-99)
    data["issues"].async_update_base_unit_error(None)
    assert _issue(hass, issue_id) is None

    data["issues"].async_update_base_unit_error(4)
    data["issues"].async_update_base_unit_error(-99)
    data["issues"].async_update_base_unit_error(None)
    assert _issue(hass, issue_id) is not None


async def test_error_issue_clears_when_the_code_returns_to_zero(hass, fake_device):
    entry, data = await _setup(hass)
    data["issues"].async_update_base_unit_error(4)

    data["issues"].async_update_base_unit_error(0)

    assert _issue(hass, f"{entry.entry_id}_base_unit_error") is None


async def test_error_code_sensor_update_feeds_the_issue(hass, fake_device, monkeypatch):
    """End to end: the base-unit error-code sensor's normal poll raises the
    issue, without any extra Modbus request."""
    error_address = BASE_UNIT_REGISTERS["error_code"]

    async def read_input_registers(self, address, count=1):
        return [9 if address == error_address else 0] * count

    monkeypatch.setattr(FakeClient, "read_input_registers", read_input_registers)
    assert await async_setup_component(hass, "homeassistant", {})
    entry, _ = await _setup(hass)

    await hass.services.async_call(
        "homeassistant",
        "update_entity",
        {"entity_id": "sensor.fonterra_base_unit_error_code"},
        blocking=True,
    )

    issue = _issue(hass, f"{entry.entry_id}_base_unit_error")
    assert issue is not None and issue.translation_key == "base_unit_error_9"


# --- Lifecycle ------------------------------------------------------------


async def test_unload_removes_the_module_issues(hass, fake_device):
    entry, data = await _setup(hass)
    data["issues"].async_update_base_unit_error(4)
    data["client"].last_success_time = dt_util.utcnow() - timedelta(hours=1)
    data["issues"].async_check_unreachable()

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert _issue(hass, f"{entry.entry_id}_base_unit_error") is None
    assert _issue(hass, f"{entry.entry_id}_module_unreachable") is None


async def test_modules_have_separate_issues(hass, fake_device):
    first = _entry()
    second = MockConfigEntry(
        domain=DOMAIN,
        title="Keller",
        unique_id="192.168.1.51:502",
        data={**first.data, "host": "192.168.1.51", "device_name": "Keller"},
    )
    second.add_to_hass(hass)
    _, first_data = await _setup(hass, first)
    second_data = hass.data[DOMAIN][second.entry_id]

    first_data["issues"].async_update_base_unit_error(4)
    second_data["issues"].async_update_base_unit_error(10)

    assert _issue(hass, f"{first.entry_id}_base_unit_error").translation_key == "base_unit_error_4"
    issue = _issue(hass, f"{second.entry_id}_base_unit_error")
    assert issue.translation_key == "base_unit_error_10"
    assert issue.translation_placeholders["device"] == "Keller"


# --- Translations ---------------------------------------------------------


def test_every_issue_key_is_translated_with_title_and_description():
    expected = {"module_unreachable", "registers_not_updating", "base_unit_error_unknown"} | {
        f"base_unit_error_{code}" for code in BASE_UNIT_ERROR_CODES if code != 0
    }
    for language in ("de", "en"):
        issues = json.loads((TRANSLATIONS / f"{language}.json").read_text(encoding="utf-8"))[
            "issues"
        ]
        assert set(issues) == expected, language
        for key, value in issues.items():
            assert value["title"] and value["description"], (language, key)
        placeholders = set(
            re.findall(r"\{(\w+)\}", issues["registers_not_updating"]["description"])
        )
        assert placeholders == {"device", "since", "codes", "registers"}, language


def test_warning_codes_are_documented_codes():
    assert ERROR_CODE_WARNINGS <= set(BASE_UNIT_ERROR_CODES)


# --- Values not updating (registers rejected for 30 minutes) ---------------


async def _setup_rejecting(hass, monkeypatch, rejected_addresses):
    from custom_components.viega_fonterra_modbus.modbus_handler import ModbusClientError

    async def read_input_registers(self, address, count=1):
        if set(range(address, address + count)) & rejected_addresses:
            raise ModbusClientError("exception", exception_code=4)
        return [0] * count

    monkeypatch.setattr(FakeClient, "read_input_registers", read_input_registers)
    return await _setup(hass)


async def test_registers_rejected_for_30_minutes_raise_values_not_updating(hass, fake_device, monkeypatch):
    error_register = BASE_UNIT_REGISTERS["error_code"]
    entry, data = await _setup_rejecting(hass, monkeypatch, {error_register})
    coordinator = data["polling"]
    issue_id = f"{entry.entry_id}_registers_not_updating"

    data["issues"].async_check_rejected()
    assert _issue(hass, issue_id) is None  # rejected, but not for 30 minutes yet

    for key in coordinator.rejected_since:
        coordinator.rejected_since[key] -= REJECTED_AFTER
    data["issues"].async_check_rejected()

    issue = _issue(hass, issue_id)
    assert issue.severity == ir.IssueSeverity.ERROR
    assert issue.translation_key == "registers_not_updating"
    assert issue.translation_placeholders["registers"] == "base_unit.error_code"
    assert issue.translation_placeholders["codes"] == "4"
    assert issue.translation_placeholders["device"] == "Fonterra"


async def test_values_not_updating_clears_when_registers_are_read_again(hass, fake_device, monkeypatch):
    rejected = {BASE_UNIT_REGISTERS["error_code"]}
    entry, data = await _setup_rejecting(hass, monkeypatch, rejected)
    coordinator = data["polling"]
    for key in coordinator.rejected_since:
        coordinator.rejected_since[key] -= REJECTED_AFTER
    data["issues"].async_check_rejected()
    assert _issue(hass, f"{entry.entry_id}_registers_not_updating") is not None

    rejected.clear()  # the module answers again
    await coordinator.async_refresh()
    data["issues"].async_check_rejected()

    assert _issue(hass, f"{entry.entry_id}_registers_not_updating") is None


async def test_invalid_values_and_transport_failures_do_not_raise_it(hass, fake_device, monkeypatch):
    entry, data = await _setup(hass)
    coordinator = data["polling"]

    async def sentinel(self, address, count=1):
        return [-99] * count

    monkeypatch.setattr(FakeClient, "read_input_registers", sentinel)
    await coordinator.async_refresh()

    async def offline(self, address, count=1):
        raise OSError("unreachable")

    monkeypatch.setattr(FakeClient, "read_input_registers", offline)
    await coordinator.async_refresh()
    data["issues"].async_check_rejected()

    assert coordinator.rejected_since == {}
    assert _issue(hass, f"{entry.entry_id}_registers_not_updating") is None


async def test_long_register_lists_are_shortened(hass, fake_device, monkeypatch):
    from custom_components.viega_fonterra_modbus.issues import MAX_LISTED_REGISTERS

    entry, data = await _setup(hass)
    coordinator = data["polling"]
    old = dt_util.utcnow() - REJECTED_AFTER - timedelta(minutes=1)
    keys = [("input", 300 + i, 1) for i in range(MAX_LISTED_REGISTERS + 3)]
    coordinator.rejected_now = {key: 4 for key in keys}
    coordinator.rejected_since = {key: old for key in keys}

    data["issues"].async_check_rejected()

    registers = _issue(hass, f"{entry.entry_id}_registers_not_updating").translation_placeholders["registers"]
    assert registers.endswith("(+3)")
    assert registers.count(",") == MAX_LISTED_REGISTERS - 1


async def test_periodic_check_raises_values_not_updating(hass, fake_device, monkeypatch):
    entry, data = await _setup_rejecting(hass, monkeypatch, {BASE_UNIT_REGISTERS["flow_temperature"]})
    coordinator = data["polling"]
    for key in coordinator.rejected_since:
        coordinator.rejected_since[key] -= REJECTED_AFTER

    async_fire_time_changed(hass, dt_util.utcnow() + CHECK_INTERVAL + timedelta(seconds=1))
    await hass.async_block_till_done()

    assert _issue(hass, f"{entry.entry_id}_registers_not_updating") is not None
