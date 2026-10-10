"""Shared behaviour of entities that get their values from the module's
polling coordinator (spec.md 16i)."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.entity import Entity

from .const import DOMAIN


class ViegaCoordinatedEntity(Entity):
    """Updated by the module's `ViegaDataCoordinator` instead of being
    polled by Home Assistant.

    After every polling cycle the coordinator notifies the entity, which
    runs its own `async_update()` - now only a lookup in the cycle's data,
    never a device read - and writes its state. Without a coordinator (an
    entity used on its own) it falls back to being polled.
    """

    _entry_id: str | None

    @property
    def _coordinator(self):
        hass = getattr(self, "hass", None)
        if hass is None or self._entry_id is None:
            return None
        coordinator = hass.data.get(DOMAIN, {}).get(self._entry_id, {}).get("polling")
        return coordinator if hasattr(coordinator, "async_add_listener") else None

    @property
    def should_poll(self) -> bool:
        return self._coordinator is None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        coordinator = self._coordinator
        if coordinator is not None:
            self.async_on_remove(
                coordinator.async_add_listener(self._handle_coordinator_update)
            )

    @callback
    def _handle_coordinator_update(self) -> None:
        self.hass.async_create_task(
            self._async_update_from_coordinator(),
            f"{DOMAIN} update {self.entity_id}",
        )

    async def _async_after_write(self) -> None:
        """Show an acknowledged write right away and read it back soon
        (spec.md 16c).

        Home Assistant only refreshes an entity's state after a service call
        when the entity is polled, which these entities are not - so the new
        value is reported here; otherwise it would only appear after the
        next polling cycle, and a second quick change would start from the
        old value.
        """
        if self.hass is not None and self.platform is not None and self.entity_id:
            self.async_write_ha_state()
        coordinator = self._coordinator
        if coordinator is not None:
            await coordinator.async_request_refresh()

    async def _async_update_from_coordinator(self) -> None:
        await self.async_update()
        if self.hass is not None and self.entity_id is not None:
            self.async_write_ha_state()
