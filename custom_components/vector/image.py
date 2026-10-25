"""Last photo taken by Vector (the "Take photo" button or a voice command)."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VectorConfigEntry
from .api import VectorClient, VectorError
from .entity import VectorEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    client = entry.runtime_data.client
    async_add_entities(VectorLastPhoto(hass, client, esn) for esn in client.robots)


class VectorLastPhoto(VectorEntity, ImageEntity):
    """Newest photo stored on the robot."""

    _attr_translation_key = "last_photo"
    _attr_content_type = "image/jpeg"

    def __init__(self, hass: HomeAssistant, client: VectorClient, esn: str) -> None:
        VectorEntity.__init__(self, client, esn, "last_photo")
        ImageEntity.__init__(self, hass)
        self._attr_unique_id = f"{esn}_last_photo"

    @property
    def _photo(self) -> dict | None:
        return self.state_data.get("last_photo")

    @property
    def image_last_updated(self) -> datetime | None:
        photo = self._photo
        return datetime.fromtimestamp(photo["at"], UTC) if photo and photo.get("at") else None

    async def async_image(self) -> bytes | None:
        photo = self._photo
        if not photo:
            return None
        try:
            return await self._bridge.photo(self._esn, photo["id"])
        except VectorError:
            return None
