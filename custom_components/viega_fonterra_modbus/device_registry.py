"""Device registry for multiple Viega Fonterra Smart Control installations."""

from __future__ import annotations


class DeviceRegistry:
    """Manage multiple device entries in a single repository."""

    def __init__(self) -> None:
        self.devices: dict[str, dict[str, object]] = {}

    def add_device(self, device_id: str, config: dict[str, object]) -> None:
        """Register a device by its ID and configuration."""
        self.devices[device_id] = config

    def get_device(self, device_id: str) -> dict[str, object]:
        """Return a previously registered device."""
        return self.devices[device_id]
