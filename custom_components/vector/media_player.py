"""Vector speaker as a media player: TTS (e.g. Piper via `tts.speak`), audio files and URLs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import aiohttp
from homeassistant.components import media_source, tts
from homeassistant.components.media_player import (
    ATTR_MEDIA_ANNOUNCE,
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    async_process_play_media_url,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import VectorConfigEntry
from .api import VectorClient, VectorError
from .entity import VectorEntity

# The bridge takes a whole file (decoded by ffmpeg): endless streams are not supported.
MAX_AUDIO_BYTES = 50 * 1024 * 1024


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    client = entry.runtime_data.client
    async_add_entities(VectorSpeaker(client, esn) for esn in client.robots)


class VectorSpeaker(VectorEntity, MediaPlayerEntity):
    """Audio is queued; an announcement interrupts whatever is playing."""

    _attr_translation_key = "speaker"
    _attr_media_content_type = MediaType.MUSIC
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.MEDIA_ANNOUNCE
    )

    def __init__(self, client: VectorClient, esn: str) -> None:
        super().__init__(client, esn, "speaker")

    @property
    def _audio(self) -> dict[str, Any]:
        return self.state_data.get("audio") or {}

    @property
    def state(self) -> MediaPlayerState:
        return MediaPlayerState.PLAYING if self._audio.get("playing") else MediaPlayerState.IDLE

    @property
    def volume_level(self) -> float | None:
        volume = self._audio.get("volume")
        return None if volume is None else volume / 100

    @property
    def media_duration(self) -> float | None:
        return self._audio.get("duration") if self._audio.get("playing") else None

    @property
    def media_position(self) -> float | None:
        return 0 if self._audio.get("playing") else None

    @property
    def media_position_updated_at(self) -> datetime | None:
        started = self._audio.get("started")
        return (
            dt_util.utc_from_timestamp(started) if self._audio.get("playing") and started else None
        )

    async def async_set_volume_level(self, volume: float) -> None:
        await self._command("set_audio_volume", volume=round(volume * 100))

    async def async_media_stop(self) -> None:
        await self._command("stop_audio")

    async def async_browse_media(
        self, media_content_type: MediaType | str | None = None, media_content_id: str | None = None
    ) -> BrowseMedia:
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        data = await self._fetch(media_id)
        try:
            await self._bridge.play_audio(
                self._esn, data, interrupt=bool(kwargs.get(ATTR_MEDIA_ANNOUNCE))
            )
        except VectorError as err:
            raise HomeAssistantError(f"Vector: {err}") from err

    async def _fetch(self, media_id: str) -> bytes:
        """Whole audio: TTS straight from the engine, local files from disk, the rest via HTTP."""
        if media_source.is_media_source_id(media_id):
            if media_id.startswith(f"{media_source.URI_SCHEME}{tts.DOMAIN}/"):
                _, data = await tts.async_get_media_source_audio(self.hass, media_id)
                return data
            item = await media_source.async_resolve_media(self.hass, media_id, self.entity_id)
            if item.path is not None:
                return await self.hass.async_add_executor_job(item.path.read_bytes)
            media_id = item.url
        url = async_process_play_media_url(self.hass, media_id)
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                resp.raise_for_status()
                data = await resp.content.read(MAX_AUDIO_BYTES + 1)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise HomeAssistantError(f"Cannot fetch {media_id}: {err}") from err
        if len(data) > MAX_AUDIO_BYTES:
            raise HomeAssistantError("Audio larger than 50 MB (streams are not supported)")
        return data
