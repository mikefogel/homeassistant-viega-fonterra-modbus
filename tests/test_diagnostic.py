"""Tests for diagnosis entities that report textual unit errors."""

import asyncio
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus.const import DOMAIN
from custom_components.viega_fonterra_modbus.diagnostic import (
    ViegaDiagnosticTextEntity,
    async_setup_entry,
)


def test_diagnostic_entity_exposes_text_status():
    """Diagnostic values should be textual and readable by operators."""
    entity = ViegaDiagnosticTextEntity(None, "temperature_flow", "error: sensor invalid")

    assert entity.name == "temperature_flow"
    assert entity.state == "error: sensor invalid"


def test_diagnostic_entity_defaults_to_sensor_invalid_status():
    """Without an explicit status, the entity defaults to a sensible message."""
    entity = ViegaDiagnosticTextEntity(None, "temperature_flow")

    assert entity.status == "error: sensor invalid"


def test_diagnostic_entity_setup_call_shape_resolves_entry_and_name():
    """The call shape used by async_setup_entry (entry_id, name) must not be
    misread as (name, status) - this was the root cause of a bug where the
    entry_id ended up as the entity name and the name as the status."""
    entity = ViegaDiagnosticTextEntity("entry_1", "Wohnzimmer diagnostic")

    assert entity._entry_id == "entry_1"
    assert entity.name == "Wohnzimmer diagnostic"
    assert entity.status == "error: sensor invalid"
    assert entity._attr_unique_id == "entry_1_Wohnzimmer diagnostic_diagnostic"


def test_device_info_is_none_for_a_standalone_entity_without_an_entry_id():
    entity = ViegaDiagnosticTextEntity(None, "temperature_flow")

    assert entity.device_info is None


def test_device_info_uses_the_configured_device_name():
    entity = ViegaDiagnosticTextEntity("entry_1", "Wohnzimmer diagnostic")
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"device_name": "Heizung Wohnzimmer"}}}
    )

    assert entity.device_info["name"] == "Heizung Wohnzimmer"


def test_setup_entry_creates_one_diagnostic_entity_per_room_with_a_default_status():
    hass = SimpleNamespace(
        data={
            DOMAIN: {
                "entry_1": {
                    "rooms": {
                        "room_1": {"name": "Wohnzimmer"},
                        "room_2": "not a dict",
                    }
                }
            }
        }
    )
    entry = SimpleNamespace(entry_id="entry_1")
    added: list = []

    asyncio.run(async_setup_entry(hass, entry, added.extend))

    assert len(added) == 2
    names = {entity.name for entity in added}
    assert names == {"Wohnzimmer diagnostic", "room_2 diagnostic"}
    assert all(entity.status == "error: sensor invalid" for entity in added)
