"""Photos stored on Vector in the HA media browser (Media → Vector)."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.http.auth import async_sign_path
from homeassistant.components.media_player import BrowseError, MediaClass, MediaType
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .api import VectorError
from .const import DOMAIN
from .views import PHOTO_URL, client_for

SIGN_FOR = timedelta(hours=1)


async def async_get_media_source(hass: HomeAssistant) -> VectorMediaSource:
    return VectorMediaSource(hass)


def _signed(hass: HomeAssistant, esn: str, photo_id: int, thumb: bool = False) -> str:
    path = PHOTO_URL.format(esn=esn, photo_id=photo_id)
    url = async_sign_path(hass, path, SIGN_FOR)
    return f"{url}&thumb=true" if thumb else url


class VectorMediaSource(MediaSource):
    """Robot → its photos (newest first)."""

    name = "Vector"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        esn, _, photo_id = (item.identifier or "").partition("/")
        if not photo_id.isdigit() or client_for(self.hass, esn) is None:
            raise Unresolvable(f"unknown Vector photo {item.identifier}")
        return PlayMedia(_signed(self.hass, esn, int(photo_id)), "image/jpeg")

    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        if item.identifier:
            return await self._robot(item.identifier)
        robots = [
            (esn, state.get("name") or "Vector")
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
            for esn, state in entry.runtime_data.client.robots.items()
        ]
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=None,
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.IMAGE,
            title="Vector",
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.DIRECTORY,
            children=[
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=esn,
                    media_class=MediaClass.DIRECTORY,
                    media_content_type=MediaType.IMAGE,
                    title=name,
                    can_play=False,
                    can_expand=True,
                )
                for esn, name in robots
            ],
        )

    async def _robot(self, esn: str) -> BrowseMediaSource:
        client = client_for(self.hass, esn)
        if client is None:
            raise BrowseError(f"unknown Vector {esn}")
        try:
            photos = await client.command("list_photos", esn) or []
        except VectorError as err:
            raise BrowseError(str(err)) from err
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=esn,
            media_class=MediaClass.DIRECTORY,
            media_content_type=MediaType.IMAGE,
            title=client.robots[esn].get("name") or "Vector",
            can_play=False,
            can_expand=True,
            children_media_class=MediaClass.IMAGE,
            children=[
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=f"{esn}/{p['id']}",
                    media_class=MediaClass.IMAGE,
                    media_content_type="image/jpeg",
                    title=dt_util.as_local(dt_util.utc_from_timestamp(p["at"])).strftime(
                        "%Y-%m-%d %H:%M"
                    ),
                    can_play=True,
                    can_expand=False,
                    thumbnail=_signed(self.hass, esn, p["id"], thumb=True),
                )
                for p in photos
            ],
        )
