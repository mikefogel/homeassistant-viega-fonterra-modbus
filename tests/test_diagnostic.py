"""Tests for diagnosis entities that report textual unit errors."""

from custom_components.viega_fonterra_modbus.diagnostic import ViegaDiagnosticTextEntity


def test_diagnostic_entity_exposes_text_status():
    """Diagnostic values should be textual and readable by operators."""
    entity = ViegaDiagnosticTextEntity("temperature_flow", "error: sensor invalid")

    assert entity.name == "temperature_flow"
    assert entity.state == "error: sensor invalid"
