"""Vector camera: live stream (WebRTC via go2rtc), MJPEG fallback and a cached snapshot."""

from __future__ import annotations

import logging

import aiohttp
from aiohttp import web
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.camera.webrtc import (
    CameraWebRTCProvider,
    WebRTCSendMessage,
    async_get_supported_provider,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_aiohttp_proxy_web, async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from webrtc_models import RTCIceCandidateInit

from . import VectorConfigEntry
from .api import VectorClient, VectorError
from .entity import VectorEntity

_LOGGER = logging.getLogger(__name__)


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
        # session id -> go2rtc provider (None while the stream warms up)
        self._webrtc: dict[str, CameraWebRTCProvider | None] = {}
        # ICE candidates the browser sent during the warm-up, forwarded after the offer
        self._early_candidates: dict[str, list[RTCIceCandidateInit]] = {}

    @property
    def supported_features(self) -> CameraEntityFeature:
        # Add-on 0.2.0+: a real stream (H.264 + the robot's microphone) that HA's go2rtc serves
        # as WebRTC. Older add-ons: MJPEG only (the frontend then reloads pictures).
        if self._bridge.stream_url():
            return CameraEntityFeature.STREAM
        return CameraEntityFeature(0)

    async def stream_source(self) -> str | None:
        return self._bridge.stream_url()

    # --- WebRTC: warm the stream up, then hand the offer to Home Assistant's go2rtc ---------
    # Home Assistant's go2rtc waits only 5 s for the stream description (hard-coded in go2rtc);
    # Vector's camera needs longer on the charger (it takes behavior control first). The live
    # view then failed, fell back to HLS (failing the same way) and retried in a loop.
    # Overriding the offer makes Home Assistant treat this camera as native WebRTC (no HLS
    # fallback): the add-on starts the stream first, then the go2rtc provider gets the offer.
    # Home Assistant sends the browser the session id before calling us, so the browser's ICE
    # candidates arrive during the warm-up: they are kept and forwarded after the offer.

    async def async_handle_async_webrtc_offer(
        self, offer_sdp: str, session_id: str, send_message: WebRTCSendMessage
    ) -> None:
        self._webrtc[session_id] = None
        self._early_candidates[session_id] = []
        try:
            await self._bridge.warm_stream()
        except VectorError as err:
            # older add-on (no warm_stream) or the camera did not start: try anyway
            _LOGGER.warning("Vector live view: could not start the stream first: %s", err)
        if session_id not in self._webrtc:
            return  # the browser closed the live view during the warm-up
        provider = await async_get_supported_provider(self.hass, self)
        if provider is None:
            self._webrtc.pop(session_id, None)
            self._early_candidates.pop(session_id, None)
            raise HomeAssistantError("Vector camera: no WebRTC provider (is go2rtc set up?)")
        self._webrtc[session_id] = provider
        await provider.async_handle_async_webrtc_offer(self, offer_sdp, session_id, send_message)
        for candidate in self._early_candidates.pop(session_id, []):
            await provider.async_on_webrtc_candidate(session_id, candidate)

    async def async_on_webrtc_candidate(
        self, session_id: str, candidate: RTCIceCandidateInit
    ) -> None:
        provider = self._webrtc.get(session_id)
        if provider is not None:
            await provider.async_on_webrtc_candidate(session_id, candidate)
        elif session_id in self._early_candidates:
            self._early_candidates[session_id].append(candidate)  # still warming up

    def close_webrtc_session(self, session_id: str) -> None:
        self._early_candidates.pop(session_id, None)
        provider = self._webrtc.pop(session_id, None)
        if provider is not None:
            provider.async_close_session(session_id)

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
