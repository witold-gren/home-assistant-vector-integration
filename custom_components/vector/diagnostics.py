"""Diagnostics: robot state from the bridge, without the token."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_TOKEN
from homeassistant.core import HomeAssistant

from . import VectorConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VectorConfigEntry
) -> dict[str, Any]:
    client = entry.runtime_data.client
    return {
        "entry": async_redact_data(dict(entry.data), {CONF_TOKEN}),
        "bridge_version": client.version,
        "connected": client.connected,
        "robots": client.robots,
    }
