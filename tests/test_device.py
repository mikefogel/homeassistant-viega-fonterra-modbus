"""Tests for the shared device_info builder (spec.md 6a: configured module
name must be used as the HA device name, not a fixed string)."""

from types import SimpleNamespace

from custom_components.viega_fonterra_modbus.const import DEFAULT_NAME, DOMAIN
from custom_components.viega_fonterra_modbus.device import build_device_info


def test_device_info_uses_the_configured_device_name():
    hass = SimpleNamespace(
        data={DOMAIN: {"entry_1": {"device_name": "Heizung Wohnzimmer"}}}
    )

    info = build_device_info(hass, "entry_1")

    assert info["name"] == "Heizung Wohnzimmer"
    assert info["identifiers"] == {(DOMAIN, "entry_1")}
    assert info["manufacturer"] == "Viega"
    assert info["model"] == "Smart Control"


def test_device_info_falls_back_to_default_name_when_not_configured():
    hass = SimpleNamespace(data={DOMAIN: {"entry_1": {}}})

    info = build_device_info(hass, "entry_1")

    assert info["name"] == DEFAULT_NAME


def test_device_info_falls_back_to_default_name_when_entry_missing():
    hass = SimpleNamespace(data={})

    info = build_device_info(hass, "entry_1")

    assert info["name"] == DEFAULT_NAME


def test_two_modules_get_distinct_device_identifiers_and_names():
    """spec.md 7: every module must have its own, distinguishable device."""
    hass = SimpleNamespace(
        data={
            DOMAIN: {
                "entry_1": {"device_name": "Heizung Wohnzimmer"},
                "entry_2": {"device_name": "Heizung Keller"},
            }
        }
    )

    info_1 = build_device_info(hass, "entry_1")
    info_2 = build_device_info(hass, "entry_2")

    assert info_1["identifiers"] != info_2["identifiers"]
    assert info_1["name"] != info_2["name"]
