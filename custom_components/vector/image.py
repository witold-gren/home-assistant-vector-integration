"""Vector images: the last photo taken by Vector (the "Take photo" button or a voice command),
and the last frame of the live view (kept in Home Assistant, always available — the card's
full-screen background while Vector is off)."""

from __future__ import annotations

from datetime import UTC, datetime

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VectorConfigEntry
from .api import VectorClient, VectorError
from .entity import VectorEntity
from .last_frame import LastFrameStore


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    client = entry.runtime_data.client
    entities: list[ImageEntity] = [VectorLastPhoto(hass, client, esn) for esn in client.robots]
    entities += [
        VectorLastFrame(hass, client, esn, store)
        for esn, store in entry.runtime_data.frames.items()
    ]
    async_add_entities(entities)


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


class VectorLastFrame(VectorEntity, ImageEntity):
    """Last frame of the live view, uploaded by the control card. Always available."""

    _attr_translation_key = "last_frame"
    _attr_content_type = "image/jpeg"

    def __init__(
        self, hass: HomeAssistant, client: VectorClient, esn: str, store: LastFrameStore
    ) -> None:
        VectorEntity.__init__(self, client, esn, "last_frame")
        ImageEntity.__init__(self, hass)
        self._attr_unique_id = f"{esn}_last_frame"
        self._store = store

    @property
    def available(self) -> bool:
        return True  # the picture shown while Vector is off

    @property
    def image_last_updated(self) -> datetime | None:
        return self._store.updated_at

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._store.add_listener(self._frame_updated))

    @callback
    def _frame_updated(self) -> None:
        self.async_write_ha_state()

    async def async_image(self) -> bytes | None:
        return self._store.jpeg
