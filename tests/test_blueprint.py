"""Circulation-pump blueprint (spec.md 16k): schema validation and behaviour
of a real automation created from it."""

from __future__ import annotations

import shutil
from datetime import timedelta
from pathlib import Path

import pytest
from homeassistant.components.blueprint import models
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.core import CoreState
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import load_yaml_dict
from pytest_homeassistant_custom_component.common import async_fire_time_changed

BLUEPRINT = (
    Path(__file__).resolve().parent.parent
    / "blueprints"
    / "automation"
    / "viega_fonterra_modbus"
    / "circulation_pump.yaml"
)
INDICATOR = "binary_sensor.fonterra_circulation_pump"
PUMP = "input_boolean.heizkreispumpe"


def test_blueprint_matches_home_assistants_schema():
    blueprint = models.Blueprint(
        load_yaml_dict(str(BLUEPRINT)), expected_domain="automation", schema=BLUEPRINT_SCHEMA
    )

    assert blueprint.validate() is None
    assert set(blueprint.inputs) == {"pump_indicator", "pump_switch", "run_on_time"}
    assert blueprint.metadata["homeassistant"]["min_version"] == "2024.6.0"


async def _setup_automation(hass, tmp_path, run_on_minutes: int = 5) -> None:
    hass.config.config_dir = str(tmp_path)
    target = tmp_path / "blueprints" / "automation" / "viega_fonterra_modbus"
    target.mkdir(parents=True)
    shutil.copy(BLUEPRINT, target / BLUEPRINT.name)

    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(
        hass, "input_boolean", {"input_boolean": {"heizkreispumpe": None}}
    )
    hass.states.async_set(INDICATOR, "off")
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "use_blueprint": {
                    "path": "viega_fonterra_modbus/circulation_pump.yaml",
                    "input": {
                        "pump_indicator": INDICATOR,
                        "pump_switch": PUMP,
                        "run_on_time": {"minutes": run_on_minutes},
                    },
                }
            }
        },
    )
    await hass.async_block_till_done()


async def _indicator(hass, state: str) -> None:
    hass.states.async_set(INDICATOR, state)
    await hass.async_block_till_done()


async def _advance(hass, minutes: float) -> None:
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=minutes))
    await hass.async_block_till_done()


@pytest.fixture
def frozen(freezer):
    return freezer


async def test_pump_follows_the_indicator_with_run_on_time(hass, tmp_path, frozen):
    await _setup_automation(hass, tmp_path)

    await _indicator(hass, "on")
    assert hass.states.get(PUMP).state == "on"

    await _indicator(hass, "off")
    frozen.tick(timedelta(minutes=4))
    await _advance(hass, 0)
    assert hass.states.get(PUMP).state == "on"  # still within the run-on time

    frozen.tick(timedelta(minutes=2))
    await _advance(hass, 0)
    assert hass.states.get(PUMP).state == "off"


async def test_opening_again_during_run_on_keeps_the_pump_on(hass, tmp_path, frozen):
    await _setup_automation(hass, tmp_path)
    await _indicator(hass, "on")
    await _indicator(hass, "off")

    frozen.tick(timedelta(minutes=3))
    await _advance(hass, 0)
    await _indicator(hass, "on")
    frozen.tick(timedelta(minutes=10))
    await _advance(hass, 0)

    assert hass.states.get(PUMP).state == "on"


async def test_zero_run_on_time_switches_off_immediately(hass, tmp_path):
    await _setup_automation(hass, tmp_path, run_on_minutes=0)
    await _indicator(hass, "on")

    await _indicator(hass, "off")

    assert hass.states.get(PUMP).state == "off"


async def test_unavailable_indicator_leaves_the_pump_alone(hass, tmp_path, frozen):
    await _setup_automation(hass, tmp_path)
    await _indicator(hass, "on")

    await _indicator(hass, "unavailable")
    frozen.tick(timedelta(minutes=30))
    await _advance(hass, 0)

    assert hass.states.get(PUMP).state == "on"


async def test_restart_with_open_actuators_turns_the_pump_on(hass, tmp_path):
    hass.set_state(CoreState.not_running)
    await _setup_automation(hass, tmp_path)
    await _indicator(hass, "on")  # already on before Home Assistant has started
    assert hass.states.get(PUMP).state == "off"

    # Run Home Assistant's real startup sequence: automations are armed during
    # it, and the blueprint's start trigger fires when startup completes.
    await hass.async_start()
    await hass.async_block_till_done()

    assert hass.states.get(PUMP).state == "on"
