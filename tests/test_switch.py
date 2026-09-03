"""Tests for the switch platform (spec.md 8: simple on/off state flow).

Unique-ID stability (spec.md 5a) is covered separately in
test_entity_fixes.py.
"""

import asyncio
from types import SimpleNamespace

from custom_components.viega_fonterra_modbus.const import DEFAULT_NAME, DOMAIN
from custom_components.viega_fonterra_modbus.switch import (
    ViegaBasicSwitchEntity,
    async_setup_entry,
)


def test_switch_entity_starts_off_and_toggles():
    entity = ViegaBasicSwitchEntity("entry_1", "room_1", "Wohnzimmer")

    assert entity._attr_is_on is False

    asyncio.run(entity.async_turn_on())
    assert entity._attr_is_on is True

    asyncio.run(entity.async_turn_off())
    assert entity._attr_is_on is False


def test_switch_entity_uses_the_configured_room_name_as_display_name():
    entity = ViegaBasicSwitchEntity("entry_1", "room_1", "Wohnzimmer")

    assert entity._attr_name == "Wohnzimmer"


def test_switch_entity_device_info_uses_the_configured_device_name():
    entity = ViegaBasicSwitchEntity("entry_1", "room_1", "Wohnzimmer")
    entity.hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"device_name": "Heizung Wohnzimmer"}}}
    )

    assert entity.device_info["name"] == "Heizung Wohnzimmer"


def test_setup_entry_creates_one_switch_per_room():
    hass = SimpleNamespace(
        data={
            DOMAIN: {
                "entry_1": {
                    "rooms": {
                        "room_1": {"name": "Wohnzimmer"},
                        "room_2": {"name": "Schlafzimmer"},
                    }
                }
            }
        }
    )
    entry = SimpleNamespace(entry_id="entry_1")
    added: list = []

    asyncio.run(async_setup_entry(hass, entry, added.extend))

    assert len(added) == 2
    unique_ids = {entity._attr_unique_id for entity in added}
    assert unique_ids == {"entry_1_room_1_switch", "entry_1_room_2_switch"}


def test_setup_entry_falls_back_to_room_id_as_name_without_a_dict_config():
    hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"rooms": {"room_1": "not a dict"}}}}
    )
    entry = SimpleNamespace(entry_id="entry_1")
    added: list = []

    asyncio.run(async_setup_entry(hass, entry, added.extend))

    assert added[0]._attr_name == "room_1"
