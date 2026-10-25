"""Robot time zone and location (weather)."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VectorConfigEntry
from .api import VectorClient
from .entity import VectorEntity

# robot text settings (examples are in the entity descriptions)
TEXT_SETTINGS = ("time_zone", "default_location")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    client = entry.runtime_data.client
    async_add_entities(
        VectorSettingText(client, esn, key) for esn in client.robots for key in TEXT_SETTINGS
    )


class VectorSettingText(VectorEntity, TextEntity):
    """Robot text setting."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_max = 100

    def __init__(self, client: VectorClient, esn: str, key: str) -> None:
        super().__init__(client, esn, key)
        self._key = key
        self._attr_translation_key = key

    @property
    def native_value(self) -> str | None:
        return (self.state_data.get("settings") or {}).get(self._key)

    async def async_set_value(self, value: str) -> None:
        await self._command("update_settings", **{self._key: value.strip()})
