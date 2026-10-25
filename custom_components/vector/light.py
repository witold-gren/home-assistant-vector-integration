"""Vector eyes as a light: any color (HS); turning off restores the color from settings."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_HS_COLOR, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VectorConfigEntry
from .api import VectorClient
from .const import EYE_COLORS
from .entity import VectorEntity

DEFAULT_HS = (0.0, 100.0)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    client = entry.runtime_data.client
    async_add_entities(VectorEyes(client, esn) for esn in client.robots)


class VectorEyes(VectorEntity, LightEntity):
    """Custom eye color (Vector does not report it; the bridge keeps it until a robot restart)."""

    _attr_translation_key = "eyes"
    _attr_color_mode = ColorMode.HS
    _attr_supported_color_modes = frozenset({ColorMode.HS})

    def __init__(self, client: VectorClient, esn: str) -> None:
        super().__init__(client, esn, "eyes")

    @property
    def is_on(self) -> bool:
        return self.state_data.get("custom_eye") is not None

    @property
    def hs_color(self) -> tuple[float, float] | None:
        eye = self.state_data.get("custom_eye")
        if not eye:
            return None
        return (round(eye["hue"] * 360, 1), round(eye["saturation"] * 100, 1))

    async def async_turn_on(self, **kwargs: Any) -> None:
        hue, sat = kwargs.get(ATTR_HS_COLOR) or self.hs_color or DEFAULT_HS
        await self._command("set_eye_color", hue=hue / 360, saturation=sat / 100)

    async def async_turn_off(self, **kwargs: Any) -> None:
        # Writing the settings color again restores the normal eyes.
        preset = (self.state_data.get("settings") or {}).get("eye_color", 0)
        index = int(preset) if isinstance(preset, int | float) else 0
        await self._command(
            "update_settings", eye_color=EYE_COLORS[min(index, len(EYE_COLORS) - 1)]
        )
