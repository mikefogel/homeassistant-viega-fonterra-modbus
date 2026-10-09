"""Full config/options-flow tests driven through Home Assistant's real flow
manager, using pytest-homeassistant-custom-component (spec.md 12a).

test_config_flow.py covers the flow's pure-logic helpers
(`_rooms_from_input`, `_parse_actor_field`, `_format_actor_field`) without a
real `hass`. This file covers what only the real flow manager can verify:
actual form/abort semantics, config-entry creation, and the unique-ID
duplicate check (spec.md 6a) - none of that is reachable by calling the
step methods directly with a `SimpleNamespace` stand-in for `hass`.
"""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.viega_fonterra_modbus.const import DOMAIN

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

USER_INPUT = {
    "host": "192.168.1.50",
    "port": 502,
    "device_name": "Fonterra",
    "polling_interval": 30,
    "modbus_timeout": 5,
}


def _mock_connect_ok():
    return patch(
        "custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient.connect",
        new=AsyncMock(return_value=None),
    )


def _mock_disconnect_ok():
    return patch(
        "custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient.disconnect",
        new=AsyncMock(return_value=None),
    )


async def test_user_flow_creates_an_entry_on_a_successful_connection(hass):
    with _mock_connect_ok(), _mock_disconnect_ok():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Fonterra"
    assert result["data"]["host"] == "192.168.1.50"

    entries = hass.config_entries.async_entries(DOMAIN)
    assert len(entries) == 1
    assert entries[0].unique_id == "192.168.1.50:502"


async def test_user_flow_shows_cannot_connect_and_creates_no_entry(hass):
    """A failed connection must redisplay the form with a translated error
    key, not create a config entry (spec.md 6a)."""
    with patch(
        "custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient.connect",
        new=AsyncMock(side_effect=OSError("unreachable")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert hass.config_entries.async_entries(DOMAIN) == []


async def test_user_flow_rejects_a_duplicate_host_and_port(hass):
    """spec.md 6a / 14 "The setup form never prevented adding the same
    device twice": adding a module whose host/port already belongs to an
    existing entry must abort instead of creating a second, uncoordinated
    set of entities and connections."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.50:502",
        data=dict(USER_INPUT),
        options={"rooms": {}, "device_id": "fonterra_192.168.1.50"},
    ).add_to_hass(hass)

    with _mock_connect_ok(), _mock_disconnect_ok():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_a_second_module_with_a_different_host_is_not_rejected(hass):
    """The uniqueness check is on host+port, not on the domain alone - a
    second, genuinely different module must still be addable (spec.md 6a
    "Multiple modules")."""
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.50:502",
        data=dict(USER_INPUT),
        options={"rooms": {}, "device_id": "fonterra_192.168.1.50"},
    ).add_to_hass(hass)

    other_input = {**USER_INPUT, "host": "192.168.1.60", "device_name": "Keller"}
    with _mock_connect_ok(), _mock_disconnect_ok():
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], other_input
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2


async def test_options_flow_updates_settings_and_round_trips_a_multi_actuator_room(
    hass,
):
    """spec.md 6a / 14 "Options-flow room editing could not represent a
    multi-actuator room": saving the options form for an unrelated field
    (here: host/polling interval) must not collapse `room_1`'s two
    actuators down to one."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.50:502",
        data=dict(USER_INPUT),
        options={
            "rooms": {"room_1": {"name": "Wohnzimmer", "actor": [3, 4], "sensor": 1}},
            "device_id": "fonterra_192.168.1.50",
        },
    )
    entry.add_to_hass(hass)

    with _mock_connect_ok(), _mock_disconnect_ok():
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == data_entry_flow.FlowResultType.FORM
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "host": "192.168.1.50",
                "port": 502,
                "device_name": "Fonterra",
                "polling_interval": 45,
                "modbus_timeout": 5,
                "room_name_room_1": "Wohnzimmer",
                "room_actor_room_1": "3, 4",
                "room_sensor_room_1": 1,
                "room_target_register_room_1": 0,
            },
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data["polling_interval"] == 45
    assert entry.options["rooms"]["room_1"]["actor"] == [3, 4]


async def test_options_flow_shows_cannot_connect_and_does_not_save(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.1.50:502",
        data=dict(USER_INPUT),
        options={"rooms": {}, "device_id": "fonterra_192.168.1.50"},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.viega_fonterra_modbus.config_flow.ViegaModbusClient.connect",
        new=AsyncMock(side_effect=OSError("unreachable")),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                "host": "192.168.1.50",
                "port": 502,
                "device_name": "Fonterra",
                "polling_interval": 30,
                "modbus_timeout": 5,
            },
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.data["polling_interval"] == 30
