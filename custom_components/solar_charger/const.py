"""Constanten voor SolarCharge."""

DOMAIN = "solar_charger"
PANEL_URL = "solar-charger"
PANEL_TITLE = "SolarCharge"
PANEL_ICON = "mdi:battery-charging"

# Config entry sleutels — sensoren
CONF_P1_POWER = "p1_power_sensor"
CONF_SOLAR_POWER = "solar_power_sensor"
CONF_CHARGER_SWITCH = "charger_switch"
CONF_CHARGER_POWER = "charger_power_sensor"

# Config entry sleutels — standaardwaarden (aanpasbaar via options flow)
CONF_MIN_SURPLUS = "min_surplus_w"
CONF_DELAY_ON = "delay_on_seconds"
CONF_DELAY_OFF = "delay_off_seconds"
CONF_EFFICIENCY = "efficiency_percent"
CONF_MAX_CHARGE_KW = "max_charge_kw"

# Standaardwaarden
DEFAULT_MIN_SURPLUS = 500
DEFAULT_DELAY_ON = 120
DEFAULT_DELAY_OFF = 180
DEFAULT_EFFICIENCY = 90
DEFAULT_MAX_CHARGE_KW = 2.3
