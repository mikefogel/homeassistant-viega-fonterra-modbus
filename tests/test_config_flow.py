"""Tests for the pure-logic parts of the config/options flow.

The flow classes themselves (`ViegaFonterraConfigFlow`,
`ViegaFonterraOptionsFlow`) subclass Home Assistant's `FlowHandler` and rely
on being instantiated by HA's flow manager (`self.hass`, `self.flow_id`,
`async_show_form`/`async_create_entry` plumbing) to exercise the full step
methods - see `tests/test_config_flow_flows.py` (spec.md 12a) for those,
using the `pytest-homeassistant-custom-component` test harness (a real
`hass` fixture, see `requirements-test.txt` and `tests/conftest.py`). This
file covers only the parts that are plain functions or `@staticmethod`s and
need no Home Assistant runtime at all.
"""

from custom_components.viega_fonterra_modbus.config_flow import (
    ViegaFonterraOptionsFlow,
    _format_actor_field,
    _parse_actor_field,
)


def test_rooms_from_input_updates_name_actor_sensor_and_target_register():
    current_rooms = {"room_1": {"name": "Wohnzimmer", "actor": 1, "sensor": 10}}
    user_input = {
        "room_name_room_1": "Living Room",
        "room_actor_room_1": 2,
        "room_sensor_room_1": 12,
        "room_target_register_room_1": 50,
    }

    rooms = ViegaFonterraOptionsFlow._rooms_from_input(user_input, current_rooms)

    assert rooms == {
        "room_1": {
            "name": "Living Room",
            "actor": 2,
            "sensor": 12,
            "target_temperature_register": 50,
        }
    }


def test_rooms_from_input_keeps_existing_values_when_field_missing():
    current_rooms = {
        "room_1": {
            "name": "Wohnzimmer",
            "actor": 1,
            "sensor": 10,
            "target_temperature_register": 50,
        }
    }

    rooms = ViegaFonterraOptionsFlow._rooms_from_input({}, current_rooms)

    assert rooms == current_rooms


def test_rooms_from_input_skips_non_dict_room_entries():
    current_rooms = {"room_1": "not a dict"}

    rooms = ViegaFonterraOptionsFlow._rooms_from_input({}, current_rooms)

    assert rooms == {}


# --- Multi-actuator rooms through the options-flow text field -----------
# (spec.md 4: a room may map to more than one actuator; the field must not
# silently collapse it down to just the first one on every options save.)


def test_format_actor_field_renders_a_list_as_a_comma_separated_string():
    assert _format_actor_field([3, 4]) == "3, 4"
    assert _format_actor_field(1) == "1"


def test_parse_actor_field_keeps_a_single_number_as_a_plain_int():
    assert _parse_actor_field("1") == 1
    assert _parse_actor_field(1) == 1


def test_parse_actor_field_reads_multiple_numbers_into_a_list():
    assert _parse_actor_field("3, 4") == [3, 4]
    assert _parse_actor_field("3 4") == [3, 4]
    assert _parse_actor_field([3, 4]) == [3, 4]


def test_parse_actor_field_treats_blank_input_as_unset():
    assert _parse_actor_field("") == 0
    assert _parse_actor_field("   ") == 0


def test_rooms_from_input_preserves_a_multi_actuator_room_round_trip():
    """The previous `vol.Coerce(int)` field could only ever submit one
    number, so saving the options form for a multi-actuator room (however
    unrelated the actual edit) silently dropped every actuator but the
    first. The field is now a string parsed back into a list."""
    current_rooms = {
        "room_1": {"name": "Wohnzimmer", "actor": [3, 4], "sensor": 1}
    }
    user_input = {
        "room_name_room_1": "Wohnzimmer",
        "room_actor_room_1": "3, 4",
        "room_sensor_room_1": 1,
        "room_target_register_room_1": 50,
    }

    rooms = ViegaFonterraOptionsFlow._rooms_from_input(user_input, current_rooms)

    assert rooms["room_1"]["actor"] == [3, 4]


def test_rooms_from_input_keeps_a_multi_actuator_room_when_the_field_is_missing():
    current_rooms = {"room_1": {"name": "Wohnzimmer", "actor": [3, 4], "sensor": 1}}

    rooms = ViegaFonterraOptionsFlow._rooms_from_input({}, current_rooms)

    assert rooms["room_1"]["actor"] == [3, 4]
