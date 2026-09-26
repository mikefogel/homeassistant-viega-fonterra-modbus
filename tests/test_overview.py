"""Tests for the optional multi-module overview (spec.md 16g)."""

from types import SimpleNamespace

from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.overview import async_multi_module_overview


class _FakeClient:
    def __init__(self, connected=True, last_success_time=None, consecutive_failures=0):
        self._connected = connected
        self.last_success_time = last_success_time
        self.consecutive_failures = consecutive_failures


def _hass(entries: dict) -> SimpleNamespace:
    return SimpleNamespace(data={DOMAIN: entries})


def test_overview_is_empty_when_no_module_is_loaded():
    result = async_multi_module_overview(_hass({}))

    assert result == {"modules": []}


def test_overview_reports_room_and_actuator_counts_per_module():
    hass = _hass(
        {
            "entry_1": {
                "device_name": "Fonterra",
                "client": _FakeClient(),
                "rooms": {
                    "room_1": {"name": "Wohnzimmer", "actor": [1, 2]},
                    "room_2": {"name": "Bad", "actor": 3},
                },
            }
        }
    )

    result = async_multi_module_overview(hass)

    module = result["modules"][0]
    assert module["entry_id"] == "entry_1"
    assert module["device_name"] == "Fonterra"
    assert module["room_count"] == 2
    assert module["actuator_count"] == 3


def test_overview_skips_non_dict_room_entries_when_counting():
    hass = _hass(
        {
            "entry_1": {
                "client": _FakeClient(),
                "rooms": {"room_1": {"name": "Wohnzimmer"}, "room_2": "not a dict"},
            }
        }
    )

    result = async_multi_module_overview(hass)

    assert result["modules"][0]["room_count"] == 1


def test_overview_never_merges_same_named_rooms_from_different_modules():
    hass = _hass(
        {
            "entry_1": {
                "device_name": "Erdgeschoss",
                "client": _FakeClient(),
                "rooms": {"room_1": {"name": "Wohnzimmer", "actor": 1}},
            },
            "entry_2": {
                "device_name": "Obergeschoss",
                "client": _FakeClient(),
                "rooms": {"room_1": {"name": "Wohnzimmer", "actor": 1}},
            },
        }
    )

    result = async_multi_module_overview(hass)

    all_rooms = [room for module in result["modules"] for room in module["rooms"]]
    assert len(all_rooms) == 2
    entry_ids = {room["entry_id"] for room in all_rooms}
    assert entry_ids == {"entry_1", "entry_2"}
    assert all(room["name"] == "Wohnzimmer" for room in all_rooms)


def test_overview_reports_reachable_from_the_clients_connection_state():
    hass = _hass(
        {
            "entry_1": {"client": _FakeClient(connected=True), "rooms": {}},
            "entry_2": {"client": _FakeClient(connected=False), "rooms": {}},
        }
    )

    result = async_multi_module_overview(hass)

    by_entry = {m["entry_id"]: m for m in result["modules"]}
    assert by_entry["entry_1"]["reachable"] is True
    assert by_entry["entry_2"]["reachable"] is False


def test_overview_reports_stale_or_failed_when_never_succeeded():
    hass = _hass({"entry_1": {"client": _FakeClient(last_success_time=None), "rooms": {}}})

    result = async_multi_module_overview(hass)

    assert result["modules"][0]["stale_or_failed"] is True


def test_overview_reports_stale_or_failed_on_consecutive_failures():
    hass = _hass(
        {
            "entry_1": {
                "client": _FakeClient(last_success_time="2026-01-01", consecutive_failures=3),
                "rooms": {},
            }
        }
    )

    result = async_multi_module_overview(hass)

    assert result["modules"][0]["stale_or_failed"] is True


def test_overview_is_not_stale_after_a_recent_success_with_no_failures():
    hass = _hass(
        {
            "entry_1": {
                "client": _FakeClient(last_success_time="2026-01-01", consecutive_failures=0),
                "rooms": {},
            }
        }
    )

    result = async_multi_module_overview(hass)

    assert result["modules"][0]["stale_or_failed"] is False


def test_overview_reports_has_base_unit_error_from_entry_data():
    hass = _hass(
        {
            "entry_1": {"client": _FakeClient(), "rooms": {}, "base_unit_error_code": 7},
            "entry_2": {"client": _FakeClient(), "rooms": {}, "base_unit_error_code": 0},
            "entry_3": {"client": _FakeClient(), "rooms": {}},
        }
    )

    result = async_multi_module_overview(hass)

    by_entry = {m["entry_id"]: m for m in result["modules"]}
    assert by_entry["entry_1"]["has_base_unit_error"] is True
    assert by_entry["entry_2"]["has_base_unit_error"] is False
    assert by_entry["entry_3"]["has_base_unit_error"] is None  # unknown, never read yet


def test_overview_isolates_one_modules_failure_from_the_others():
    hass = _hass(
        {
            "entry_bad": None,  # malformed entry: summarizing it must raise internally
            "entry_good": {"client": _FakeClient(), "rooms": {"room_1": {"name": "Bad"}}},
        }
    )

    result = async_multi_module_overview(hass)

    by_entry = {m["entry_id"]: m for m in result["modules"]}
    assert "error" in by_entry["entry_bad"]
    assert by_entry["entry_good"]["room_count"] == 1
    assert "error" not in by_entry["entry_good"]
