"""HTTP views: robot photos (/api/vector/photo/<esn>/<id>, for the media browser) and the
intercom (/api/vector/intercom/<camera entity>: a recording from the control card, played on the
speaker; the card knows its camera entity, not the robot's serial)."""

from __future__ import annotations

from http import HTTPStatus

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .api import VectorClient, VectorError
from .const import DOMAIN

PHOTO_URL = "/api/vector/photo/{esn}/{photo_id}"
INTERCOM_URL = "/api/vector/intercom/{camera}"
# A held "talk" button: a few seconds of webm/mp4 audio from the browser; the add-on decodes any
# format with ffmpeg. Bigger bodies are refused before they are read.
MAX_RECORDING = 5 * 1024 * 1024
MIN_RECORDING = 800  # shorter is an accidental tap


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


class VectorIntercomView(HomeAssistantView):
    """Push-to-talk from the control card: the recording plays on Vector's speaker at once."""

    url = INTERCOM_URL
    name = "api:vector:intercom"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def post(self, request: web.Request, camera: str) -> web.Response:
        entry = er.async_get(self.hass).async_get(camera)
        esn = (
            entry.unique_id.removesuffix("_camera")
            if entry is not None
            and entry.platform == DOMAIN
            and entry.unique_id.endswith("_camera")
            else None
        )
        client = client_for(self.hass, esn) if esn else None
        if client is None or esn is None:
            return self.json_message("unknown robot", HTTPStatus.NOT_FOUND)
        if request.content_length is not None and request.content_length > MAX_RECORDING:
            return self.json_message("recording too long", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        data = await request.content.read(MAX_RECORDING + 1)
        if len(data) > MAX_RECORDING:
            return self.json_message("recording too long", HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        if len(data) < MIN_RECORDING:
            return self.json_message("recording too short", HTTPStatus.BAD_REQUEST)
        try:
            # interrupt: the user talks now, whatever Vector was playing
            await client.play_audio(esn, data, interrupt=True)
        except VectorError as err:
            return self.json_message(str(err), HTTPStatus.SERVICE_UNAVAILABLE)
        return self.json_message("ok")
