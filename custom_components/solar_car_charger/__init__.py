"""Solar Car Charger — custom integration."""
from __future__ import annotations
import json
import logging
from pathlib import Path

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components import websocket_api
from homeassistant.components.panel_custom import async_register_panel

from .const import (
    DOMAIN, PANEL_URL, PANEL_TITLE, PANEL_ICON,
    CONF_P1_POWER, CONF_SOLAR_POWER, CONF_CHARGER_SWITCH,
    CONF_CHARGER_POWER, CONF_MIN_SURPLUS, CONF_DELAY_ON,
    CONF_DELAY_OFF, CONF_EFFICIENCY, CONF_MAX_CHARGE_KW,
    DEFAULT_MIN_SURPLUS, DEFAULT_DELAY_ON, DEFAULT_DELAY_OFF,
    DEFAULT_EFFICIENCY, DEFAULT_MAX_CHARGE_KW,
)
from .storage import async_load_sessions, async_save_session, async_delete_all_sessions

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    cfg = {**entry.data, **entry.options}
    hass.data[DOMAIN]["config"] = cfg
    hass.data[DOMAIN]["entry_id"] = entry.entry_id

    # Schrijf config.json naar www zodat het panel de sensor-IDs kent
    await hass.async_add_executor_job(_write_config_json, hass, cfg)

    # Registreer WebSocket commands voor sessie opslag
    _register_websocket_commands(hass)

    await _register_panel(hass)
    await _setup_helpers(hass, cfg)
    await _setup_automations(hass, cfg, entry)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    try:
        hass.components.frontend.async_remove_panel(PANEL_URL)
    except Exception:
        pass
    hass.data[DOMAIN].pop("config", None)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    _LOGGER.info("Solar Car Charger: opties gewijzigd, herladen")
    await hass.config_entries.async_reload(entry.entry_id)


def _write_config_json(hass: HomeAssistant, cfg: dict) -> None:
    """Schrijf config.json naar www/solar_car_charger/ voor het panel."""
    www_dir = Path(hass.config.config_dir) / "www" / "solar_car_charger"
    www_dir.mkdir(parents=True, exist_ok=True)
    config_path = www_dir / "config.json"
    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)
    _LOGGER.debug("config.json geschreven naar %s", config_path)


# ── WEBSOCKET COMMANDS ────────────────────────────────────────────────────────

def _register_websocket_commands(hass: HomeAssistant) -> None:
    """Registreer alle WebSocket commands voor het panel."""

    @websocket_api.websocket_command({
        vol.Required("type"): f"{DOMAIN}/get_sessions",
    })
    @websocket_api.async_response
    async def ws_get_sessions(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Geef alle opgeslagen laadsessies terug."""
        sessions = await async_load_sessions(hass)
        connection.send_result(msg["id"], {"sessions": sessions})

    @websocket_api.websocket_command({
        vol.Required("type"): f"{DOMAIN}/save_session",
        vol.Required("session"): dict,
    })
    @websocket_api.async_response
    async def ws_save_session(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Sla een nieuwe laadsessie op."""
        await async_save_session(hass, msg["session"])
        connection.send_result(msg["id"], {"ok": True})

    @websocket_api.websocket_command({
        vol.Required("type"): f"{DOMAIN}/delete_all_sessions",
    })
    @websocket_api.async_response
    async def ws_delete_all(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict,
    ) -> None:
        """Verwijder alle sessies (reset)."""
        await async_delete_all_sessions(hass)
        connection.send_result(msg["id"], {"ok": True})

    # Registreer bij HA
    websocket_api.async_register_command(hass, ws_get_sessions)
    websocket_api.async_register_command(hass, ws_save_session)
    websocket_api.async_register_command(hass, ws_delete_all)
    _LOGGER.debug("WebSocket commands geregistreerd")


# ── PANEL ─────────────────────────────────────────────────────────────────────

async def _register_panel(hass: HomeAssistant) -> None:
    try:
        await async_register_panel(
            hass,
            component_name="solar-car-charger-panel",
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            frontend_url_path=PANEL_URL,
            webcomponent_url="/local/solar_car_charger/panel.html",
            require_admin=False,
            config={},
        )
        _LOGGER.info("Solar Car Charger panel geregistreerd")
    except Exception as err:
        _LOGGER.warning("Panel registratie mislukt: %s", err)


# ── HELPERS ───────────────────────────────────────────────────────────────────

async def _setup_helpers(hass: HomeAssistant, cfg: dict) -> None:
    helpers = [
        ("input_number.solar_car_energy_today",             0),
        ("input_number.solar_car_energy_in_battery_today",  0),
        ("input_number.solar_car_energy_total",             0),
        ("input_number.solar_car_min_surplus",              cfg.get(CONF_MIN_SURPLUS, DEFAULT_MIN_SURPLUS)),
        ("input_number.solar_car_delay_on",                 cfg.get(CONF_DELAY_ON, DEFAULT_DELAY_ON)),
        ("input_number.solar_car_delay_off",                cfg.get(CONF_DELAY_OFF, DEFAULT_DELAY_OFF)),
        ("input_number.solar_car_efficiency",               cfg.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)),
        ("input_number.solar_car_noplug_threshold",         50),
    ]
    for entity_id, value in helpers:
        if hass.states.get(entity_id) is None:
            try:
                await hass.services.async_call(
                    "input_number", "set_value",
                    {"entity_id": entity_id, "value": value},
                    blocking=False,
                )
            except Exception:
                pass

    for entity_id in [
        "input_text.solar_car_session_start",
        "input_text.solar_car_session_stop",
    ]:
        if hass.states.get(entity_id) is None:
            try:
                await hass.services.async_call(
                    "input_text", "set_value",
                    {"entity_id": entity_id, "value": ""},
                    blocking=False,
                )
            except Exception:
                pass


# ── AUTOMATISERINGEN ──────────────────────────────────────────────────────────

async def _setup_automations(hass: HomeAssistant, cfg: dict, entry: ConfigEntry) -> None:
    p1          = cfg[CONF_P1_POWER]
    switch      = cfg[CONF_CHARGER_SWITCH]
    charger_pwr = cfg.get(CONF_CHARGER_POWER, "")
    max_kw      = float(cfg.get(CONF_MAX_CHARGE_KW, DEFAULT_MAX_CHARGE_KW))
    min_surplus = int(cfg.get(CONF_MIN_SURPLUS, DEFAULT_MIN_SURPLUS))
    delay_on    = int(cfg.get(CONF_DELAY_ON, DEFAULT_DELAY_ON))
    delay_off   = int(cfg.get(CONF_DELAY_OFF, DEFAULT_DELAY_OFF))
    efficiency  = float(cfg.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)) / 100

    if charger_pwr:
        kwh_expr = (
            f"(((now().timestamp() - as_timestamp(states('input_text.solar_car_session_start')))"
            f" / 3600) * (states('{charger_pwr}') | float(0) / 1000)) | round(3)"
        )
    else:
        kwh_expr = (
            f"(((now().timestamp() - as_timestamp(states('input_text.solar_car_session_start')))"
            f" / 3600) * {max_kw}) | round(3)"
        )

    automations = [
        {
            "id": f"solar_car_turn_on_{entry.entry_id}",
            "alias": "Solar Car — inschakelen bij voldoende overschot",
            "mode": "single",
            "trigger": [{
                "platform": "template",
                "value_template": (
                    f"{{% set p1 = states('{p1}') | float(0) %}}"
                    f"{{{{ p1 <= {-min_surplus} }}}}"
                ),
                "for": {"seconds": delay_on},
            }],
            "condition": [
                {"condition": "state", "entity_id": "input_boolean.solar_car_automation_enabled", "state": "on"},
                {"condition": "state", "entity_id": switch, "state": "off"},
            ],
            "action": [
                {"service": "switch.turn_on", "target": {"entity_id": switch}},
                {
                    "service": "input_text.set_value",
                    "target": {"entity_id": "input_text.solar_car_session_start"},
                    "data": {"value": "{{ now().isoformat() }}"},
                },
                {
                    "service": "notify.persistent_notification",
                    "data": {
                        "title": "🌞 Auto laden gestart",
                        "message": (
                            f"Overschot: {{{{ (states('{p1}') | float(0) * -1) | round(0) }}}}W"
                            f" · Gestart: {{{{ now().strftime('%H:%M') }}}}"
                        ),
                    },
                },
            ],
        },
        {
            "id": f"solar_car_turn_off_{entry.entry_id}",
            "alias": "Solar Car — uitschakelen bij onvoldoende overschot",
            "mode": "single",
            "trigger": [{
                "platform": "template",
                "value_template": (
                    f"{{% set p1 = states('{p1}') | float(0) %}}"
                    f"{{{{ p1 > {-min_surplus} }}}}"
                ),
                "for": {"seconds": delay_off},
            }],
            "condition": [
                {"condition": "state", "entity_id": "input_boolean.solar_car_automation_enabled", "state": "on"},
                {"condition": "state", "entity_id": switch, "state": "on"},
            ],
            "action": [
                {"service": "switch.turn_off", "target": {"entity_id": switch}},
                {
                    "service": "input_text.set_value",
                    "target": {"entity_id": "input_text.solar_car_session_stop"},
                    "data": {"value": "{{ now().isoformat() }}"},
                },
                {
                    "service": "input_number.set_value",
                    "target": {"entity_id": "input_number.solar_car_energy_today"},
                    "data": {"value": (
                        f"{{{{ (states('input_number.solar_car_energy_today') | float(0)"
                        f" + {kwh_expr}) | round(3) }}}}"
                    )},
                },
                {
                    "service": "input_number.set_value",
                    "target": {"entity_id": "input_number.solar_car_energy_in_battery_today"},
                    "data": {"value": (
                        f"{{{{ (states('input_number.solar_car_energy_in_battery_today') | float(0)"
                        f" + {kwh_expr} * {efficiency}) | round(3) }}}}"
                    )},
                },
                {
                    "service": "input_number.set_value",
                    "target": {"entity_id": "input_number.solar_car_energy_total"},
                    "data": {"value": (
                        f"{{{{ (states('input_number.solar_car_energy_total') | float(0)"
                        f" + {kwh_expr}) | round(3) }}}}"
                    )},
                },
                {
                    "service": "notify.persistent_notification",
                    "data": {
                        "title": "🔌 Auto laden gestopt",
                        "message": f"Gestopt om {{{{ now().strftime('%H:%M') }}}}",
                    },
                },
            ],
        },
        {
            "id": f"solar_car_daily_reset_{entry.entry_id}",
            "alias": "Solar Car — dagelijkse reset",
            "trigger": [{"platform": "time", "at": "00:00:00"}],
            "action": [
                {"service": "input_number.set_value",
                 "target": {"entity_id": "input_number.solar_car_energy_today"}, "data": {"value": 0}},
                {"service": "input_number.set_value",
                 "target": {"entity_id": "input_number.solar_car_energy_in_battery_today"}, "data": {"value": 0}},
            ],
        },
    ]

    for automation_cfg in automations:
        _LOGGER.debug("Automatisering geregistreerd: %s", automation_cfg["alias"])
