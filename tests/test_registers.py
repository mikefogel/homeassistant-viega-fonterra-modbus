"""Tests for the register definition layer."""

import pytest

from custom_components.viega_fonterra_modbus.registers import (
    BASE_UNIT_REGISTERS,
    REGISTER_DEFINITIONS,
    actor_registers,
    describe_error_code,
    pdu_address,
    resolve_room_number,
    room_registers,
    decode_text_registers,
)


def test_register_definitions_are_loaded():
    """The integration should expose a known register map."""
    assert "temperature_flow" in REGISTER_DEFINITIONS
    assert REGISTER_DEFINITIONS["temperature_flow"]["address"] == 1000
    assert REGISTER_DEFINITIONS["temperature_flow"]["unit"] == "°C"


def test_pdu_address_uses_the_correct_bank_origin():
    """PDU addresses are relative to 40001 (holding) / 30001 (input), not -1.

    See spec.md 5b/14 "PDU address offset": subtracting a flat 1 from the
    full manual address produced values tens of thousands too high.
    """
    assert pdu_address(40001) == 0
    assert pdu_address(40002) == 1
    assert pdu_address(30001) == 0
    assert pdu_address(30024) == 23
    assert pdu_address(30025) == 24


def test_pdu_address_rejects_addresses_outside_the_supported_banks():
    with pytest.raises(ValueError):
        pdu_address(1000)


def test_base_unit_registers_match_the_documented_addresses():
    """Matches the worked example in spec.md 5b."""
    assert BASE_UNIT_REGISTERS["operating_mode"] == 0
    assert BASE_UNIT_REGISTERS["profile_mode"] == 1
    assert BASE_UNIT_REGISTERS["error_code"] == 23
    assert BASE_UNIT_REGISTERS["flow_temperature"] == 24


def test_room_registers_match_the_spec_worked_example():
    """spec.md 5b: room 1 -> power_level_register 49, target_temperature_register 50."""
    registers = room_registers(1)

    assert registers["power_level"] == 49
    assert registers["target_temperature"] == 50


def test_actor_registers_match_the_spec_worked_example():
    """spec.md 5b: actuator 1 -> actuator_position_register 249, return_temperature_register 250."""
    registers = actor_registers(1)

    assert registers["position"] == 249
    assert registers["return_temperature"] == 250


def test_resolve_room_number_prefers_explicit_room_number():
    assert resolve_room_number("room_1", {"room_number": 3}) == 3


def test_resolve_room_number_falls_back_to_trailing_digits_of_room_id():
    """A minimal room mapping (name/actor/sensor only, spec.md 4/6b) must still
    resolve a usable room number for the default register lookup."""
    assert resolve_room_number("room_1", {}) == 1
    assert resolve_room_number("room_12", {}) == 12


def test_resolve_room_number_defaults_to_zero_when_unresolvable():
    assert resolve_room_number("wohnzimmer", {}) == 0


def test_describe_error_code_reports_no_error_for_zero():
    assert describe_error_code(0) == "No error"


def test_describe_error_code_reports_unknown_for_undocumented_codes():
    assert describe_error_code(7) == "Unknown error (code 7)"


def test_decode_text_registers_uses_little_endian_ascii_and_strips_padding():
    assert decode_text_registers([0x5649, 0x4547, 0x4100, 0x2020]) == "VIEGA"
