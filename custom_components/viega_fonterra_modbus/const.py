"""Constants for the Viega Fonterra Modbus integration."""

from __future__ import annotations

DOMAIN = "viega_fonterra_modbus"
DEFAULT_NAME = "Viega Fonterra Smart Control"
DEFAULT_HOST = "192.168.0.188"
DEFAULT_PORT = 502
DEFAULT_POLLING_INTERVAL = 30  # seconds
DEFAULT_MODBUS_TIMEOUT = 5  # seconds
MIN_SCAN_INTERVAL = 5  # seconds; also the minimum accepted `polling_interval`
# "diagnostic" is not a real Home Assistant platform/integration domain (unlike
# sensor/binary_sensor/switch/climate/number) and must never be added here:
# diagnostic.py's entities are created directly by sensor.py's
# async_setup_entry instead of being forwarded as their own platform.
PLATFORMS = ["sensor", "binary_sensor", "switch", "climate", "number"]

CONF_DEVICE_NAME = "device_name"
CONF_POLLING_INTERVAL = "polling_interval"
CONF_MODBUS_TIMEOUT = "modbus_timeout"

# Example register layout for the Fonterra system; the canonical registry is
# held in a dedicated module so it can be extended cleanly without mixing it
# into the HA constants layer.