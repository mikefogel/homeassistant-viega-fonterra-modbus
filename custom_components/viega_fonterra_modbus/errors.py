"""Translated errors for user-triggered actions (spec.md 10a).

Background polling never raises (spec.md 10). Actions a user triggers -
setting a temperature, mode, preset or power level, rediscovery - report
failures through Home Assistant's own exception classes with a translation
key, so the user sees a localized sentence instead of a raw Python error:

- `ServiceValidationError` when the request itself is invalid; nothing is
  sent to the device and Home Assistant logs no traceback;
- `HomeAssistantError` when a valid request could not be carried out.

The messages live in the `exceptions` section of `translations/*.json`.
"""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import DOMAIN
from .modbus_handler import ModbusClientError

_LOGGER = logging.getLogger(__name__)


def _placeholders(values: dict[str, object]) -> dict[str, str]:
    return {key: str(value) for key, value in values.items()}


def invalid_request(translation_key: str, **placeholders: object) -> ServiceValidationError:
    """Build the error for a request that is invalid in itself."""
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=translation_key,
        translation_placeholders=_placeholders(placeholders),
    )


def action_failed(translation_key: str, **placeholders: object) -> HomeAssistantError:
    """Build the error for a valid request that could not be carried out."""
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=translation_key,
        translation_placeholders=_placeholders(placeholders),
    )


async def async_write_register(
    hass: HomeAssistant, entry_id: str, address: int, value: int
) -> None:
    """Write one register, turning any transport failure into a translated
    `HomeAssistantError` that names the module.

    The underlying error stays chained and is logged at DEBUG only: an
    ordinary communication failure is not a crash and must not produce an
    ERROR-level traceback (spec.md 10a).
    """
    entry_data = hass.data[DOMAIN][entry_id]
    try:
        await entry_data["client"].write_register(address, value)
    except (ModbusClientError, ValueError, OSError) as err:
        _LOGGER.debug(
            "Writing %s to register %s failed", value, address, exc_info=True
        )
        raise action_failed(
            "write_failed",
            device=entry_data.get("device_name", "Fonterra"),
            error=err,
        ) from err
