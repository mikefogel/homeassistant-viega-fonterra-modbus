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


def test_room_scoped_diagnostic_name_is_localized_via_translation_key():
    """spec.md "localize every entity name": once room_id and room_name are
    given (the real sensor.py call shape), the name comes from
    translations/*.json entity.sensor.room_diagnostic, not the raw `name`
    string - which remains only as the fallback for the room-id-less shape
    covered by test_diagnostic_entity_exposes_text_status above."""
    entity = ViegaDiagnosticTextEntity(
        "entry_1",
        "Wohnzimmer diagnostic",
        room_id="room_1",
        room_name="Wohnzimmer",
    )

    assert not hasattr(entity, "_attr_name")
    assert entity._attr_translation_key == "room_diagnostic"
    assert entity._attr_translation_placeholders == {"room": "Wohnzimmer"}


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
    # Room-scoped diagnostic entities are localized via translation_key +
    # placeholders (translations/*.json entity.sensor.room_diagnostic), not
    # a hardcoded `.name` string - see test_diagnostic_entity_exposes_text_status
    # for the (room_id-less) fallback shape that still sets `.name` directly.
    rooms_shown = {entity._attr_translation_placeholders["room"] for entity in added}
    assert rooms_shown == {"Wohnzimmer", "room_2"}
    assert all(entity._attr_translation_key == "room_diagnostic" for entity in added)
    assert all(entity.status == "error: sensor invalid" for entity in added)


# --- State restoration across restarts (spec.md 15) ---------------------


def test_restores_last_status_text_on_add():
    entity = ViegaDiagnosticTextEntity(
        "entry_1", "Wohnzimmer diagnostic", room_id="room_1", room_name="Wohnzimmer"
    )

    async def _fake_last_state():
        return SimpleNamespace(state="No error", attributes={})

    entity.async_get_last_state = _fake_last_state

    asyncio.run(entity.async_added_to_hass())

    assert entity.status == "No error"
    assert entity.state == "No error"


def test_ignores_unknown_restored_status():
    entity = ViegaDiagnosticTextEntity(
        "entry_1", "Wohnzimmer diagnostic", room_id="room_1", room_name="Wohnzimmer"
    )

    async def _fake_last_state():
        return SimpleNamespace(state="unknown", attributes={})

    entity.async_get_last_state = _fake_last_state

    asyncio.run(entity.async_added_to_hass())

    assert entity.status == "error: sensor invalid"
