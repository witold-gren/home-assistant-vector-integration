"""Vector camera: on-demand MJPEG stream (~2 fps) and a snapshot cached by the bridge."""

from __future__ import annotations

import aiohttp
from aiohttp import web
from homeassistant.components.camera import Camera
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_aiohttp_proxy_web, async_get_clientsession
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
    async_add_entities(VectorCamera(client, esn) for esn in client.robots)


class VectorCamera(VectorEntity, Camera):
    """The camera only runs while the stream is watched (on the charger the robot holds still).

    The snapshot (cards, `camera.snapshot`) is the last frame cached by the bridge: it does not
    wake the camera. The "Refresh camera image" button stores a fresh frame.
    """

    _attr_translation_key = "camera"
    _attr_name = None

    def __init__(self, client: VectorClient, esn: str) -> None:
        VectorEntity.__init__(self, client, esn, "camera")
        Camera.__init__(self)
        self._attr_unique_id = f"{esn}_camera"

    @property
    def is_streaming(self) -> bool:
        return bool(self.state_data.get("camera"))

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        try:
            return await self._bridge.snapshot(self._esn, cached=True)
        except VectorError:
            return None

    async def handle_async_mjpeg_stream(self, request: web.Request) -> web.StreamResponse | None:
        session = async_get_clientsession(self.hass)
        return await async_aiohttp_proxy_web(
            self.hass,
            request,
            session.get(
                self._bridge.url(f"/mjpeg/{self._esn}"),
                headers=self._bridge.headers,
                # the stream lasts while someone is watching
                timeout=aiohttp.ClientTimeout(total=None, sock_connect=10),
            ),
            # first frame: the camera starts (on the charger with behavior control) in up to ~10 s
            timeout=30,
        )
