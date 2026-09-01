"""Constants for the Viega Fonterra Modbus integration."""

from __future__ import annotations

DOMAIN = "viega_fonterra_modbus"
DEFAULT_NAME = "Viega Fonterra Smart Control"
DEFAULT_PORT = 502
PLATFORMS = ["sensor"]

# Example register layout for the Fonterra system; the canonical registry is
# held in a dedicated module so it can be extended cleanly without mixing it
# into the HA constants layer.
