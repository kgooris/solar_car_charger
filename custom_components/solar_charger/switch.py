"""Switch platform: automation enabled/disabled."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([SolarCarAutomationSwitch()])


class SolarCarAutomationSwitch(SwitchEntity, RestoreEntity):
    _attr_has_entity_name = False
    _attr_unique_id = "solar_charger_automation_enabled"
    _attr_name = "SolarCharge Automation Enabled"
    _attr_icon = "mdi:battery-charging"

    def __init__(self):
        self._is_on = True

    @property
    def is_on(self):
        return self._is_on

    async def async_turn_on(self, **kwargs):
        self._is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs):
        self._is_on = False
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        last = await self.async_get_last_state()
        if last:
            self._is_on = last.state != "off"
