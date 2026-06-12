"""Number platform: energy counters and adjustable settings."""
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    DOMAIN,
    CONF_MIN_SURPLUS, CONF_DELAY_ON, CONF_DELAY_OFF, CONF_EFFICIENCY,
    DEFAULT_MIN_SURPLUS, DEFAULT_DELAY_ON, DEFAULT_DELAY_OFF, DEFAULT_EFFICIENCY,
)


async def async_setup_entry(hass, entry, async_add_entities):
    cfg = {**entry.data, **entry.options}
    async_add_entities([
        SolarCarNumber("solar_charger_energy_today",             "Solar Charger Energy Today",             0,  999,  0.001, "kWh", 0),
        SolarCarNumber("solar_charger_energy_in_battery_today",  "Solar Charger Energy In Battery Today",  0,  999,  0.001, "kWh", 0),
        SolarCarNumber("solar_charger_energy_total",             "Solar Charger Energy Total",             0, 9999,  0.001, "kWh", 0),
        SolarCarNumber("solar_charger_session_duration_minutes", "Solar Charger Session Duration Minutes", 0, 9999,  1,     "min", 0),
        SolarCarNumber("solar_charger_min_surplus",              "Solar Charger Min Surplus",              0, 5000, 50,     "W",   cfg.get(CONF_MIN_SURPLUS, DEFAULT_MIN_SURPLUS)),
        SolarCarNumber("solar_charger_delay_on",                 "Solar Charger Delay On",                30,  600, 30,     "s",   cfg.get(CONF_DELAY_ON, DEFAULT_DELAY_ON)),
        SolarCarNumber("solar_charger_delay_off",                "Solar Charger Delay Off",               30,  600, 30,     "s",   cfg.get(CONF_DELAY_OFF, DEFAULT_DELAY_OFF)),
        SolarCarNumber("solar_charger_efficiency",               "Solar Charger Efficiency",              70,  100,  1,     "%",   cfg.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)),
        SolarCarNumber("solar_charger_noplug_threshold",         "Solar Charger Noplug Threshold",         0,  200, 10,     "W",   50),
    ])


class SolarCarNumber(NumberEntity, RestoreEntity):
    _attr_has_entity_name = False
    _attr_mode = NumberMode.BOX

    def __init__(self, slug, name, min_val, max_val, step, unit, initial):
        self._attr_unique_id = slug
        self._attr_name = name
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_native_value = initial
        self._initial = initial

    async def async_set_native_value(self, value: float) -> None:
        self._attr_native_value = value
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last and last.state not in (None, "unknown", "unavailable"):
            try:
                self._attr_native_value = float(last.state)
            except ValueError:
                self._attr_native_value = self._initial
