"""Robot photos served by HA (for the media browser): /api/vector/photo/<esn>/<id>."""

from __future__ import annotations

from http import HTTPStatus

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .api import VectorClient, VectorError
from .const import DOMAIN

PHOTO_URL = "/api/vector/photo/{esn}/{photo_id}"


def client_for(hass: HomeAssistant, esn: str) -> VectorClient | None:
    """Bridge client that knows robot `esn`."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED and esn in entry.runtime_data.client.robots:
            return entry.runtime_data.client
    return None


class VectorPhotoView(HomeAssistantView):
    """Photo or thumbnail (?thumb=true); URLs are signed by the media browser."""

    url = PHOTO_URL
    name = "api:vector:photo"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request, esn: str, photo_id: str) -> web.Response:
        client = client_for(self.hass, esn)
        if client is None or not photo_id.isdigit():
            return web.Response(status=HTTPStatus.NOT_FOUND)
        try:
            image = await client.photo(esn, int(photo_id), request.query.get("thumb") == "true")
        except VectorError as err:
            return web.Response(status=HTTPStatus.SERVICE_UNAVAILABLE, text=str(err))
        if image is None:
            return web.Response(status=HTTPStatus.NOT_FOUND)
        return web.Response(
            body=image, content_type="image/jpeg", headers={"Cache-Control": "max-age=86400"}
        )
