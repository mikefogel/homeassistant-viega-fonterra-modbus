"""Tests for the register definition layer."""

import pytest

from custom_components.viega_fonterra_modbus.registers import (
    BASE_UNIT_REGISTERS,
    REGISTER_DEFINITIONS,
    actor_registers,
    describe_error_code,
    pdu_address,
    resolve_room_number,
    room_name_register,
    room_registers,
    decode_text_registers,
)


def test_register_definitions_are_loaded():
    """The integration should expose a known register map."""
    assert "temperature_flow" in REGISTER_DEFINITIONS
    assert REGISTER_DEFINITIONS["temperature_flow"]["address"] == 1000
    assert REGISTER_DEFINITIONS["temperature_flow"]["unit"] == "°C"


def test_pdu_address_matches_the_manuals_own_worked_wire_examples():
    """PDU addresses are relative to 40000 (holding) / 30000 (input) - i.e.
    the last four digits of the manual address, unchanged.

    See spec.md 5b/14 "PDU address offset, take two": this is verified
    directly against the device manual's own request/response byte examples
    (`Fonterra Smart Control-de-DE.pdf`, pages 94-95, not transcribed
    assumptions), each cross-checked below.
    """
    # Beispiel 1 ("Betriebsmodus lesen"): manual 40001 -> wire start register
    # 0x0001 = 1.
    assert pdu_address(40001) == 1
    # Beispiel 2 ("Soll-Temperatur fuer Raum 2 setzen"): manual 40053 -> wire
    # start register 0x0035 = 53.
    assert pdu_address(40053) == 53
    # Beispiel 3 ("Aktor 1 lesen"): manual 30250 -> wire start register
    # 0x00FA = 250.
    assert pdu_address(30250) == 250
    # Beispiel 4 ("Basiseinheit Bezeichnung lesen"): manual 30011 -> wire
    # start register 0x000B = 11.
    assert pdu_address(30011) == 11


def test_pdu_address_rejects_addresses_outside_the_supported_banks():
    with pytest.raises(ValueError):
        pdu_address(1000)


def test_base_unit_registers_match_the_documented_addresses():
    """Matches the register table on manual pages 89-93."""
    assert BASE_UNIT_REGISTERS["operating_mode"] == 1
    assert BASE_UNIT_REGISTERS["profile_mode"] == 2
    assert BASE_UNIT_REGISTERS["error_code"] == 24
    assert BASE_UNIT_REGISTERS["flow_temperature"] == 25


def test_room_registers_match_the_manuals_register_table():
    """Manual page 92/93: room 1 -> Leistungsstufe 40050, Soll-Temperatur 40051."""
    registers = room_registers(1)

    assert registers["power_level"] == 50
    assert registers["target_temperature"] == 51


def test_actor_registers_match_the_manuals_register_table():
    """Manual page 91: Aktor 1 -> Stellung 30250, Rücklauftemperatur 30251,
    Raum ID 30252."""
    registers = actor_registers(1)

    assert registers["position"] == 250
    assert registers["return_temperature"] == 251
    assert registers["room_id"] == 252


def test_room_name_register_matches_the_manuals_register_table():
    """Manual page 90: Raum 1 Name at 30074, Raum 2 at 30086 (12 registers
    apart, spanning the 24-character/12-register field width)."""
    assert room_name_register(1) == (74, 12)
    assert room_name_register(2) == (86, 12)


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


def test_describe_error_code_reports_documented_base_unit_and_room_codes():
    """Manual page 94 "Fehlercodes": codes 3-10 are base-unit faults/warnings,
    21/22/24 are room-scoped (thermostat connectivity/battery)."""
    assert describe_error_code(4) == "Base unit: fault on the actuator bus"
    assert describe_error_code(21) == "Room: no connection to the room thermostat"


def test_describe_error_code_reports_unknown_for_undocumented_codes():
    assert describe_error_code(99) == "Unknown error (code 99)"


def test_decode_text_registers_uses_big_endian_ascii_and_strips_padding():
    assert decode_text_registers([0x5649, 0x4547, 0x4100, 0x2020]) == "VIEGA"
