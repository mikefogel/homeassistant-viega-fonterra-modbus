"""Tests for the register definition layer."""

from custom_components.viega_fonterra_modbus.registers import REGISTER_DEFINITIONS


def test_register_definitions_are_loaded():
    """The integration should expose a known register map."""
    assert "temperature_flow" in REGISTER_DEFINITIONS
    assert REGISTER_DEFINITIONS["temperature_flow"]["address"] == 1000
    assert REGISTER_DEFINITIONS["temperature_flow"]["unit"] == "°C"
