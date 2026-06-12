"""Sessie opslag via HA Storage API.

Data wordt bewaard in config/.storage/solar_charger_sessions
en wordt meegenomen in HA backups.
"""
from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

_LOGGER = logging.getLogger(__name__)

STORAGE_KEY     = "solar_charger_sessions"
STORAGE_VERSION = 1
MAX_SESSIONS    = 200


def _get_store(hass: HomeAssistant) -> Store:
    return Store(hass, STORAGE_VERSION, STORAGE_KEY)


async def async_load_sessions(hass: HomeAssistant) -> list[dict]:
    """Laad alle sessies uit de HA storage."""
    store = _get_store(hass)
    data = await store.async_load()
    if not data or "sessions" not in data:
        return []
    return data["sessions"]


async def async_save_session(hass: HomeAssistant, session: dict) -> None:
    """Voeg een nieuwe sessie toe aan de opslag."""
    store = _get_store(hass)
    data = await store.async_load() or {"sessions": []}
    sessions = data.get("sessions", [])
    sessions.insert(0, session)
    # Maximaal 200 sessies bewaren
    if len(sessions) > MAX_SESSIONS:
        sessions = sessions[:MAX_SESSIONS]
    await store.async_save({"sessions": sessions})
    _LOGGER.debug("Sessie opgeslagen: %s", session.get("startIso", "?"))


async def async_delete_all_sessions(hass: HomeAssistant) -> None:
    """Verwijder alle sessies (voor debug/reset)."""
    store = _get_store(hass)
    await store.async_save({"sessions": []})
    _LOGGER.info("Alle SolarCharge sessies verwijderd")
