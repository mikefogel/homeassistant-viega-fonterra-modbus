"""The Viega Fonterra Modbus Home Integration."""
import asyncio
import logging
import threading
from datetime import timedelta
from typing import Optional

import voluptuous as vol
from pymodbus.client import ModbusTcpClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder

import homeassistant.helpers.config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from .const import (
    DOMAIN,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_MODBUS_ADDRESS,
    CONF_MODBUS_ADDRESS,
    MODBUS_STATUS,
)

_LOGGER = logging.getLogger(__name__)

VIEGA_FONTERRA_MODBUS_SCHEMA = vol.Schema (
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT): cv.string,
        vol.Optional(
            CONF_MODBUS_ADDRESS, default=DEFAULT_MODBUS_ADDRESS
        ): cv.positive_int,
        vol.Optional(
            CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
        ): cv.positive_int,
    }
)
CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({cv.slug: VIEGA_FONTERRA_MODBUS_SCHEMA})}, extra=vol.ALLOW_EXTRA
)

PLATFORMS = ["sensor"]

async def async_setup(hass, config):
    """Set up the Ingeteam modbus component."""
    hass.data[DOMAIN] = {}
    return True