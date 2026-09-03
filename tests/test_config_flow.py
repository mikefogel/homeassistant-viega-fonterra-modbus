"""Tests for the pure-logic parts of the config/options flow.

The flow classes themselves (`ViegaFonterraConfigFlow`,
`ViegaFonterraOptionsFlow`) subclass Home Assistant's `FlowHandler` and rely
on being instantiated by HA's flow manager (`self.hass`, `self.flow_id`,
`async_show_form`/`async_create_entry` plumbing). Exercising the full step
methods therefore needs the `pytest-homeassistant-custom-component` test
harness (a real `hass` fixture) rather than the lightweight SimpleNamespace
mocking used elsewhere in this test suite. That harness is not set up in
this repo yet, so this file only covers the parts that are plain functions
or `@staticmethod`s and need no Home Assistant runtime at all.
"""

from custom_components.viega_fonterra_modbus.config_flow import (
    ViegaFonterraOptionsFlow,
    parse_rooms_input,
)


def test_parse_rooms_input_passes_through_an_already_parsed_dict():
    rooms = {"room_1": {"name": "Wohnzimmer", "actor": 1, "sensor": 10}}

    parsed, error = parse_rooms_input(rooms)

    assert parsed == rooms
    assert error is None


def test_parse_rooms_input_parses_a_json_string():
    parsed, error = parse_rooms_input('{"room_1": {"name": "Wohnzimmer"}}')

    assert parsed == {"room_1": {"name": "Wohnzimmer"}}
    assert error is None


def test_parse_rooms_input_rejects_invalid_json():
    parsed, error = parse_rooms_input("{not valid json")

    assert parsed == {}
    assert error == "invalid_rooms"


def test_parse_rooms_input_rejects_a_json_value_that_is_not_an_object():
    parsed, error = parse_rooms_input("[1, 2, 3]")

    assert parsed == {}
    assert error == "invalid_rooms"


def test_parse_rooms_input_rejects_non_string_non_dict_values():
    parsed, error = parse_rooms_input(None)

    assert parsed == {}
    assert error == "invalid_rooms"


def test_parse_rooms_input_defaults_to_empty_dict_when_field_missing():
    """Mirrors `user_input.get("rooms", {})` when the field was never shown."""
    parsed, error = parse_rooms_input({})

    assert parsed == {}
    assert error is None


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
