"""Constants for the Viega Fonterra Modbus integration."""

from __future__ import annotations

DOMAIN = "viega_fonterra_modbus"
DEFAULT_NAME = "Viega Fonterra Smart Control"
DEFAULT_HOST = "192.168.8.20"
DEFAULT_PORT = 1502
DEFAULT_POLLING_INTERVAL = 30  # seconds
DEFAULT_MODBUS_TIMEOUT = 5  # seconds
DEFAULT_MODBUS_DEBUG = False
MIN_SCAN_INTERVAL = 5  # seconds; also the minimum accepted `polling_interval`
PLATFORMS = ["sensor", "binary_sensor", "switch", "climate", "number"]

CONF_DEVICE_NAME = "device_name"
CONF_POLLING_INTERVAL = "polling_interval"
CONF_MODBUS_TIMEOUT = "modbus_timeout"
CONF_MODBUS_DEBUG = "modbus_debug"

# Example register layout for the Fonterra system; the canonical registry is
# held in a dedicated module so it can be extended cleanly without mixing it
# into the HA constants layer.