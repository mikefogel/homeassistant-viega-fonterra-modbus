"""Tests for the plain multi-device registry helper."""

import pytest

from custom_components.viega_fonterra_modbus.device_registry import DeviceRegistry


def test_get_device_returns_the_registered_config():
    registry = DeviceRegistry()
    registry.add_device("device_1", {"host": "192.168.1.10", "port": 502})

    assert registry.get_device("device_1") == {"host": "192.168.1.10", "port": 502}


def test_get_device_raises_for_an_unknown_device_id():
    registry = DeviceRegistry()

    with pytest.raises(KeyError):
        registry.get_device("does_not_exist")


def test_add_device_overwrites_only_the_matching_entry():
    registry = DeviceRegistry()
    registry.add_device("device_1", {"host": "192.168.1.10"})
    registry.add_device("device_2", {"host": "192.168.1.11"})

    registry.add_device("device_1", {"host": "192.168.1.99"})

    assert registry.get_device("device_1") == {"host": "192.168.1.99"}
    assert registry.get_device("device_2") == {"host": "192.168.1.11"}
