"""Solar Car Charger — custom integration."""
from __future__ import annotations
import json
import logging
from datetime import datetime
from pathlib import Path

import voluptuous as vol
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.components import websocket_api
from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.setup import async_setup_component

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

# Helper entity IDs used by both the integration and the frontend panel
AUTOMATION_BOOL = "input_boolean.solar_car_automation_enabled"
SESSION_START   = "input_text.solar_car_session_start"
SESSION_STOP    = "input_text.solar_car_session_stop"
ENERGY_TODAY    = "input_number.solar_car_energy_today"
ENERGY_BATT     = "input_number.solar_car_energy_in_battery_today"
ENERGY_TOTAL    = "input_number.solar_car_energy_total"
SESSION_MINS    = "input_number.solar_car_session_duration_minutes"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    cfg = {**entry.data, **entry.options}
    hass.data[DOMAIN]["config"] = cfg
    hass.data[DOMAIN]["entry_id"] = entry.entry_id

    await hass.async_add_executor_job(_write_config_json, hass, cfg)
    _register_websocket_commands(hass)
    await _register_panel(hass)
    await _setup_helpers(hass, cfg)

    unsubs = _setup_automation_logic(hass, cfg, entry)
    hass.data[DOMAIN]["unsubs"] = unsubs

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    try:
        hass.components.frontend.async_remove_panel(PANEL_URL)
    except Exception:
        pass
    for unsub in hass.data[DOMAIN].pop("unsubs", []):
        try:
            unsub()
        except Exception:
            pass
    hass.data[DOMAIN].pop("config", None)
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Verwijder alle helpers die de integratie aanmaakte bij permanente verwijdering.

    Deze functie wordt ALLEEN aangeroepen bij manuele verwijdering via de HA-UI,
    nooit bij een upgrade of herlaad. Helpers met energiedata worden ook verwijderd
    — de sessiehistoriek in HA storage blijft bewaard.
    """
    for domain in ("input_boolean", "input_number", "input_text"):
        await async_setup_component(hass, domain, {})

    all_helpers = [
        ("input_boolean", AUTOMATION_BOOL),
        ("input_number",  ENERGY_TODAY),
        ("input_number",  ENERGY_BATT),
        ("input_number",  ENERGY_TOTAL),
        ("input_number",  SESSION_MINS),
        ("input_number",  "input_number.solar_car_min_surplus"),
        ("input_number",  "input_number.solar_car_delay_on"),
        ("input_number",  "input_number.solar_car_delay_off"),
        ("input_number",  "input_number.solar_car_efficiency"),
        ("input_number",  "input_number.solar_car_noplug_threshold"),
        ("input_text",    SESSION_START),
        ("input_text",    SESSION_STOP),
    ]

    ent_reg = er.async_get(hass)
    removed: list[str] = []

    for domain, entity_id in all_helpers:
        reg_entry = ent_reg.async_get(entity_id)
        if reg_entry is None:
            continue
        collection = hass.data.get(domain)
        if collection is None:
            continue
        try:
            await collection.async_delete_item(reg_entry.unique_id)
            removed.append(entity_id)
            _LOGGER.debug("Helper verwijderd: %s", entity_id)
        except Exception as err:
            _LOGGER.warning("Kon %s niet verwijderen: %s", entity_id, err)

    # Persistente melding zodat de gebruiker weet wat er gebeurd is
    removed_list = "\n".join(f"- `{e}`" for e in removed) if removed else "*(geen gevonden)*"
    await hass.services.async_call(
        "persistent_notification", "create",
        {
            "title": "Solar Car Charger verwijderd",
            "message": (
                "De integratie is verwijderd en de volgende helpers zijn opgeruimd:\n\n"
                f"{removed_list}\n\n"
                "Je laadsessiehistoriek blijft bewaard in HA storage "
                f"(`{DOMAIN}_sessions`) en zit in je HA-backups."
            ),
            "notification_id": f"{DOMAIN}_removed",
        },
        blocking=False,
    )
    _LOGGER.info("Solar Car Charger: %d helpers verwijderd", len(removed))


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    _LOGGER.info("Solar Car Charger: opties gewijzigd, herladen")
    await hass.config_entries.async_reload(entry.entry_id)


def _write_config_json(hass: HomeAssistant, cfg: dict) -> None:
    """Schrijf config.json naar www/solar_car_charger/ en kopieer panel.html als dat nog niet up-to-date is."""
    import shutil

    www_dir = Path(hass.config.config_dir) / "www" / "solar_car_charger"
    www_dir.mkdir(parents=True, exist_ok=True)

    # config.json — altijd overschrijven zodat sensor-IDs actueel zijn
    config_path = www_dir / "config.json"
    with open(config_path, "w") as f:
        json.dump(cfg, f, indent=2)
    _LOGGER.debug("config.json geschreven naar %s", config_path)

    # panel.html — kopieer vanuit de integratiemap als de versie verschilt
    src = Path(__file__).parent / "www" / "panel.html"
    dst = www_dir / "panel.html"
    if src.exists() and (not dst.exists() or src.read_bytes() != dst.read_bytes()):
        shutil.copy2(src, dst)
        _LOGGER.info("panel.html gekopieerd naar %s", dst)


# ── WEBSOCKET COMMANDS ────────────────────────────────────────────────────────

def _register_websocket_commands(hass: HomeAssistant) -> None:
    """Registreer alle WebSocket commands voor het panel."""

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/get_sessions"})
    @websocket_api.async_response
    async def ws_get_sessions(hass, connection, msg):
        sessions = await async_load_sessions(hass)
        connection.send_result(msg["id"], {"sessions": sessions})

    @websocket_api.websocket_command({
        vol.Required("type"): f"{DOMAIN}/save_session",
        vol.Required("session"): dict,
    })
    @websocket_api.async_response
    async def ws_save_session(hass, connection, msg):
        await async_save_session(hass, msg["session"])
        connection.send_result(msg["id"], {"ok": True})

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/delete_all_sessions"})
    @websocket_api.async_response
    async def ws_delete_all(hass, connection, msg):
        await async_delete_all_sessions(hass)
        connection.send_result(msg["id"], {"ok": True})

    websocket_api.async_register_command(hass, ws_get_sessions)
    websocket_api.async_register_command(hass, ws_save_session)
    websocket_api.async_register_command(hass, ws_delete_all)
    _LOGGER.debug("WebSocket commands geregistreerd")


# ── PANEL ─────────────────────────────────────────────────────────────────────

async def _register_panel(hass: HomeAssistant) -> None:
    _LOGGER.debug("Panel registratie gestart — url=/local/solar_car_charger/panel.html")
    try:
        async_register_built_in_panel(
            hass,
            component_name="iframe",
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            frontend_url_path=PANEL_URL,
            config={"url": "/local/solar_car_charger/panel.html"},
            require_admin=False,
        )
        _LOGGER.info("Solar Car Charger panel geregistreerd")
    except Exception as err:
        _LOGGER.error("Panel registratie mislukt: %s", err, exc_info=True)


# ── HELPERS ───────────────────────────────────────────────────────────────────

async def _setup_helpers(hass: HomeAssistant, cfg: dict) -> None:
    """Maak alle benodigde helpers aan als ze nog niet bestaan, en stel initiële waarden in."""

    for domain in ("input_boolean", "input_number", "input_text"):
        await async_setup_component(hass, domain, {})

    # ── aanmaken ─────────────────────────────────────────────────────────────

    await _ensure_boolean(hass, "solar_car_automation_enabled",
                          "Solar Car Automation Enabled", "mdi:car-electric", initial=True)

    number_defs = [
        ("solar_car_energy_today",             "Solar Car Energy Today",             0, 999,   0.001, "kWh", 0),
        ("solar_car_energy_in_battery_today",  "Solar Car Energy In Battery Today",  0, 999,   0.001, "kWh", 0),
        ("solar_car_energy_total",             "Solar Car Energy Total",             0, 9999,  0.001, "kWh", 0),
        ("solar_car_session_duration_minutes", "Solar Car Session Duration Minutes", 0, 9999,  1,     "min", 0),
        ("solar_car_min_surplus",              "Solar Car Min Surplus",              0, 5000,  50,    "W",   cfg.get(CONF_MIN_SURPLUS, DEFAULT_MIN_SURPLUS)),
        ("solar_car_delay_on",                 "Solar Car Delay On",                 30, 600,  30,    "s",   cfg.get(CONF_DELAY_ON, DEFAULT_DELAY_ON)),
        ("solar_car_delay_off",                "Solar Car Delay Off",                30, 600,  30,    "s",   cfg.get(CONF_DELAY_OFF, DEFAULT_DELAY_OFF)),
        ("solar_car_efficiency",               "Solar Car Efficiency",               70, 100,  1,     "%",   cfg.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)),
        ("solar_car_noplug_threshold",         "Solar Car Noplug Threshold",         0,  200,  10,    "W",   50),
    ]
    for slug, name, mn, mx, step, unit, initial in number_defs:
        await _ensure_number(hass, slug, name, mn, mx, step, unit, initial)

    for slug, name in [
        ("solar_car_session_start", "Solar Car Session Start"),
        ("solar_car_session_stop",  "Solar Car Session Stop"),
    ]:
        await _ensure_text(hass, slug, name)

    # ── initiële waarden (enkel als entity al actief is in de state machine) ──

    number_values = [
        (ENERGY_TODAY,                          0),
        (ENERGY_BATT,                           0),
        (ENERGY_TOTAL,                          0),
        (SESSION_MINS,                          0),
        ("input_number.solar_car_min_surplus",  cfg.get(CONF_MIN_SURPLUS, DEFAULT_MIN_SURPLUS)),
        ("input_number.solar_car_delay_on",     cfg.get(CONF_DELAY_ON, DEFAULT_DELAY_ON)),
        ("input_number.solar_car_delay_off",    cfg.get(CONF_DELAY_OFF, DEFAULT_DELAY_OFF)),
        ("input_number.solar_car_efficiency",   cfg.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)),
        ("input_number.solar_car_noplug_threshold", 50),
    ]
    for entity_id, value in number_values:
        if hass.states.get(entity_id) is not None:
            try:
                await hass.services.async_call(
                    "input_number", "set_value",
                    {"entity_id": entity_id, "value": value},
                    blocking=False,
                )
            except Exception:
                pass

    for entity_id in [SESSION_START, SESSION_STOP]:
        if hass.states.get(entity_id) is not None:
            try:
                await hass.services.async_call(
                    "input_text", "set_value",
                    {"entity_id": entity_id, "value": ""},
                    blocking=False,
                )
            except Exception:
                pass


async def _ensure_boolean(
    hass: HomeAssistant, slug: str, name: str, icon: str, initial: bool = False
) -> None:
    """Maak een input_boolean helper aan als die nog niet bestaat."""
    entity_id = f"input_boolean.{slug}"
    if hass.states.get(entity_id) is not None:
        return
    collection = hass.data.get("input_boolean")
    if collection is None:
        _LOGGER.warning("input_boolean niet geladen — kan %s niet aanmaken", entity_id)
        return
    try:
        await collection.async_create_item({"name": name, "icon": icon, "initial": initial})
        _LOGGER.info("Helper aangemaakt: %s", entity_id)
    except Exception as err:
        _LOGGER.error("Kon %s niet aanmaken: %s", entity_id, err)


async def _ensure_number(
    hass: HomeAssistant, slug: str, name: str,
    min_val: float, max_val: float, step: float, unit: str, initial: float
) -> None:
    """Maak een input_number helper aan als die nog niet bestaat."""
    entity_id = f"input_number.{slug}"
    if hass.states.get(entity_id) is not None:
        return
    collection = hass.data.get("input_number")
    if collection is None:
        _LOGGER.warning("input_number niet geladen — kan %s niet aanmaken", entity_id)
        return
    try:
        await collection.async_create_item({
            "name": name, "min": min_val, "max": max_val,
            "step": step, "unit_of_measurement": unit,
            "mode": "box", "initial": initial,
        })
        _LOGGER.info("Helper aangemaakt: %s", entity_id)
    except Exception as err:
        _LOGGER.error("Kon %s niet aanmaken: %s", entity_id, err)


async def _ensure_text(hass: HomeAssistant, slug: str, name: str) -> None:
    """Maak een input_text helper aan als die nog niet bestaat."""
    entity_id = f"input_text.{slug}"
    if hass.states.get(entity_id) is not None:
        return
    collection = hass.data.get("input_text")
    if collection is None:
        _LOGGER.warning("input_text niet geladen — kan %s niet aanmaken", entity_id)
        return
    try:
        await collection.async_create_item({
            "name": name, "min": 0, "max": 255, "mode": "text",
        })
        _LOGGER.info("Helper aangemaakt: %s", entity_id)
    except Exception as err:
        _LOGGER.error("Kon %s niet aanmaken: %s", entity_id, err)


# ── AUTOMATION LOGIC ──────────────────────────────────────────────────────────

def _setup_automation_logic(
    hass: HomeAssistant, cfg: dict, entry: ConfigEntry
) -> list:
    """Implementeer de surplus-gestuurde laadautomatisering via HA event tracking.

    Retourneert een lijst van unsub-callbacks die op unload gecanceld moeten worden.
    """
    p1_sensor   = cfg[CONF_P1_POWER]
    switch      = cfg[CONF_CHARGER_SWITCH]
    charger_pwr = cfg.get(CONF_CHARGER_POWER, "")
    max_kw      = float(cfg.get(CONF_MAX_CHARGE_KW, DEFAULT_MAX_CHARGE_KW))
    min_surplus = int(cfg.get(CONF_MIN_SURPLUS, DEFAULT_MIN_SURPLUS))
    delay_on    = int(cfg.get(CONF_DELAY_ON, DEFAULT_DELAY_ON))
    delay_off   = int(cfg.get(CONF_DELAY_OFF, DEFAULT_DELAY_OFF))
    efficiency  = float(cfg.get(CONF_EFFICIENCY, DEFAULT_EFFICIENCY)) / 100

    # Mutable containers voor pending timer-cancel callbacks
    _timers: dict[str, object] = {"on": None, "off": None}

    # ── helpers ──────────────────────────────────────────────────────────────

    def _automation_active() -> bool:
        state = hass.states.get(AUTOMATION_BOOL)
        # Als de helper niet bestaat, behandelen we automatisering als actief
        return state is None or state.state == "on"

    def _charger_state() -> str:
        state = hass.states.get(switch)
        return state.state if state else "off"

    def _p1_watts() -> float:
        state = hass.states.get(p1_sensor)
        try:
            return float(state.state)
        except (AttributeError, ValueError, TypeError):
            return 0.0

    def _charger_watts() -> float:
        if charger_pwr:
            state = hass.states.get(charger_pwr)
            try:
                return float(state.state)
            except (AttributeError, ValueError, TypeError):
                pass
        return max_kw * 1000 if _charger_state() == "on" else 0.0

    def _float_state(entity_id: str) -> float:
        state = hass.states.get(entity_id)
        try:
            return float(state.state)
        except (AttributeError, ValueError, TypeError):
            return 0.0

    # ── acties ───────────────────────────────────────────────────────────────

    async def _do_turn_on(now=None) -> None:
        """Definitieve check en lader inschakelen na delay_on seconden overschot."""
        _timers["on"] = None
        if not _automation_active():
            return
        if _p1_watts() > -min_surplus:
            _LOGGER.debug("Solar Car: turn-on timer verlopen maar overschot verdwenen")
            return
        if _charger_state() == "on":
            return

        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": switch}, blocking=False
        )
        await hass.services.async_call(
            "input_text", "set_value",
            {"entity_id": SESSION_START, "value": datetime.now().isoformat()},
            blocking=False,
        )
        surplus_w = round(-_p1_watts())
        await hass.services.async_call(
            "notify", "persistent_notification",
            {
                "title": "Auto laden gestart",
                "message": f"Zonne-overschot: {surplus_w} W · Gestart: {datetime.now().strftime('%H:%M')}",
            },
            blocking=False,
        )
        _LOGGER.info("Solar Car: lader ingeschakeld (overschot %s W)", surplus_w)

    async def _do_turn_off(now=None) -> None:
        """Definitieve check, sessie-energie bijwerken en lader uitschakelen."""
        _timers["off"] = None
        if not _automation_active():
            return
        if _p1_watts() <= -min_surplus:
            _LOGGER.debug("Solar Car: turn-off timer verlopen maar overschot hersteld")
            return
        if _charger_state() == "off":
            return

        # Sessieduur berekenen
        duration_mins = 0
        start_iso = ""
        start_state = hass.states.get(SESSION_START)
        if start_state and start_state.state not in ("", "unknown", "unavailable"):
            start_iso = start_state.state
            try:
                start_dt = datetime.fromisoformat(start_iso)
                duration_mins = round((datetime.now() - start_dt).total_seconds() / 60)
            except ValueError:
                pass

        # Energie berekenen op basis van vermogen en duur
        kwh = round(_charger_watts() / 1000 * duration_mins / 60, 3) if duration_mins > 0 else 0.0
        kwh_batt = round(kwh * efficiency, 3)

        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": switch}, blocking=False
        )
        stop_iso = datetime.now().isoformat()
        await hass.services.async_call(
            "input_text", "set_value",
            {"entity_id": SESSION_STOP, "value": stop_iso},
            blocking=False,
        )

        if duration_mins > 0 and hass.states.get(SESSION_MINS) is not None:
            await hass.services.async_call(
                "input_number", "set_value",
                {"entity_id": SESSION_MINS, "value": duration_mins},
                blocking=False,
            )

        for entity_id in [ENERGY_TODAY, ENERGY_TOTAL]:
            if hass.states.get(entity_id) is not None:
                await hass.services.async_call(
                    "input_number", "set_value",
                    {"entity_id": entity_id, "value": round(_float_state(entity_id) + kwh, 3)},
                    blocking=False,
                )

        if hass.states.get(ENERGY_BATT) is not None:
            await hass.services.async_call(
                "input_number", "set_value",
                {"entity_id": ENERGY_BATT, "value": round(_float_state(ENERGY_BATT) + kwh_batt, 3)},
                blocking=False,
            )

        await hass.services.async_call(
            "notify", "persistent_notification",
            {
                "title": "Auto laden gestopt",
                "message": f"Gestopt om {datetime.now().strftime('%H:%M')} · {duration_mins} min · {kwh} kWh geladen",
            },
            blocking=False,
        )
        _LOGGER.info("Solar Car: lader uitgeschakeld (%s min, %s kWh)", duration_mins, kwh)

    # ── event handlers ────────────────────────────────────────────────────────

    @callback
    def _on_p1_change(event) -> None:
        """Reageer op wijzigingen van de P1 sensor.

        Surplus voldoende (p1 <= -min_surplus): schedule turn-on, cancel turn-off.
        Surplus onvoldoende: cancel turn-on, schedule turn-off als lader aan.
        """
        if not _automation_active():
            return

        p1 = _p1_watts()
        charger_on = _charger_state() == "on"

        if p1 <= -min_surplus:
            # Voldoende overschot
            if _timers["off"]:
                _timers["off"]()
                _timers["off"] = None
                _LOGGER.debug("Solar Car: turn-off timer geannuleerd (overschot hersteld)")
            if not charger_on and _timers["on"] is None:
                _timers["on"] = async_call_later(hass, delay_on, _do_turn_on)
                _LOGGER.debug("Solar Car: turn-on gepland over %s s (overschot %s W)", delay_on, round(-p1))
        else:
            # Onvoldoende overschot
            if _timers["on"]:
                _timers["on"]()
                _timers["on"] = None
                _LOGGER.debug("Solar Car: turn-on timer geannuleerd (overschot weg)")
            if charger_on and _timers["off"] is None:
                _timers["off"] = async_call_later(hass, delay_off, _do_turn_off)
                _LOGGER.debug("Solar Car: turn-off gepland over %s s", delay_off)

    async def _daily_reset(now: datetime) -> None:
        """Reset dagelijkse energie-tellers om middernacht."""
        for entity_id in [ENERGY_TODAY, ENERGY_BATT]:
            if hass.states.get(entity_id) is not None:
                await hass.services.async_call(
                    "input_number", "set_value",
                    {"entity_id": entity_id, "value": 0},
                    blocking=False,
                )
        _LOGGER.info("Solar Car: dagelijkse reset uitgevoerd")

    def _cancel_timers() -> None:
        """Cancel eventueel nog lopende delay-timers bij unload."""
        for key in ("on", "off"):
            if _timers[key]:
                _timers[key]()
                _timers[key] = None

    # ── registreer bij HA ─────────────────────────────────────────────────────

    unsub_p1 = async_track_state_change_event(hass, [p1_sensor], _on_p1_change)
    unsub_midnight = async_track_time_change(hass, _daily_reset, hour=0, minute=0, second=0)

    _LOGGER.info(
        "Solar Car automatisering actief — min_surplus=%sW delay_on=%ss delay_off=%ss",
        min_surplus, delay_on, delay_off,
    )
    return [unsub_p1, unsub_midnight, _cancel_timers]
