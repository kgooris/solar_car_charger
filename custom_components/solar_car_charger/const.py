"""Constanten voor Solar Car Charger."""

DOMAIN = "solar_car_charger"
PANEL_URL = "solar-car-charger"
PANEL_TITLE = "Solar Car Charger and Monitor"
PANEL_ICON = "mdi:car-electric"

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
CONF_DAILY_GOAL = "daily_goal_kwh"

# Standaardwaarden
DEFAULT_MIN_SURPLUS = 500
DEFAULT_DELAY_ON = 120
DEFAULT_DELAY_OFF = 180
DEFAULT_EFFICIENCY = 90
DEFAULT_MAX_CHARGE_KW = 2.3
DEFAULT_DAILY_GOAL = 10
