"""Text platform: session timestamps."""
from homeassistant.components.text import TextEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([
        SolarCarText("solar_car_session_start", "Solar Car Session Start"),
        SolarCarText("solar_car_session_stop",  "Solar Car Session Stop"),
    ])


class SolarCarText(TextEntity, RestoreEntity):
    _attr_has_entity_name = False
    _attr_native_min = 0
    _attr_native_max = 255

    def __init__(self, slug, name):
        self._attr_unique_id = slug
        self._attr_name = name
        self._attr_native_value = ""

    async def async_set_value(self, value: str) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        last = await self.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable"):
            self._attr_native_value = last.state
