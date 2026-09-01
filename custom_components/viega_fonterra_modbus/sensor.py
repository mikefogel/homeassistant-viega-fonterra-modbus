from homeassistant.components.sensor import SensorEntity
from .const import DOMAIN

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ViegaDummySensor()])

class ViegaDummySensor(SensorEntity):
    @property
    def name(self):
        return "Viega Dummy Sensor"

    @property
    def state(self):
        return 42

