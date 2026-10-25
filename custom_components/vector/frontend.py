"""Control card (`custom:vector-control-card`) served by the integration.

Added to every HA page via ``add_extra_js_url`` — no need to list it under
``lovelace: resources``; ``?v=<version>`` forces a fresh download after an update.
"""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

CARD_DIR = Path(__file__).parent / "www"
CARD_URL_BASE = "/vector_static"
CARD_FILENAME = "vector-control-card.js"


async def async_register_card(hass: HomeAssistant) -> None:
    """Register the card file and add it to the frontend (once per HA start)."""
    if "frontend" not in hass.config.components or hass.http is None:
        return
    integration = await async_get_integration(hass, DOMAIN)
    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL_BASE, str(CARD_DIR), cache_headers=True)]
    )
    add_extra_js_url(hass, f"{CARD_URL_BASE}/{CARD_FILENAME}?v={integration.version}")
