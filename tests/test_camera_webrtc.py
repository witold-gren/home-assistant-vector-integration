"""Live view: the camera starts the add-on's stream before handing the WebRTC offer to go2rtc.

Home Assistant's go2rtc waits only 5 s for the stream description; Vector on the charger needs
longer. The browser's ICE candidates arrive during the warm-up and must not be lost.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

from homeassistant.components.camera import StreamType
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.vector.api import VectorError
from custom_components.vector.camera import VectorCamera

ESN = "00a1b2c3"


class FakeClient:
    """What VectorCamera touches: robots, listeners, the stream URL and warm_stream."""

    def __init__(self, stream: bool = True) -> None:
        self.robots: dict[str, dict[str, Any]] = {ESN: {"esn": ESN, "connected": True}}
        self.connected = True
        self.calls: list[str] = []
        self.warm_error: Exception | None = None
        self.release: asyncio.Event | None = None
        self._stream = stream

    def stream_url(self) -> str | None:
        return "rtsp://vector:t@local-vector:8554/vector" if self._stream else None

    async def warm_stream(self) -> None:
        self.calls.append("warm_stream")
        if self.release is not None:
            await self.release.wait()
        if self.warm_error is not None:
            raise self.warm_error

    def add_listener(self, cb):  # pragma: no cover - not used here
        return lambda: None


class FakeProvider:
    def __init__(self, client: FakeClient) -> None:
        self.client = client
        self.offers: list[str] = []
        self.candidates: list[tuple[str, Any]] = []
        self.closed: list[str] = []

    async def async_handle_async_webrtc_offer(self, camera, offer_sdp, session_id, send_message):
        assert "warm_stream" in self.client.calls  # the stream already runs
        self.offers.append(session_id)

    async def async_on_webrtc_candidate(self, session_id, candidate):
        self.candidates.append((session_id, candidate))

    def async_close_session(self, session_id):
        self.closed.append(session_id)


def _camera(hass: HomeAssistant, client: FakeClient) -> VectorCamera:
    cam = VectorCamera(client, ESN)  # type: ignore[arg-type]
    cam.hass = hass
    return cam


def _provider(provider):
    return patch(
        "custom_components.vector.camera.async_get_supported_provider", return_value=provider
    )


async def test_offer_warms_the_stream_then_goes_to_go2rtc(hass: HomeAssistant) -> None:
    client = FakeClient()
    cam = _camera(hass, client)
    provider = FakeProvider(client)
    with _provider(provider):
        await cam.async_handle_async_webrtc_offer("v=0", "s1", lambda m: None)
    assert provider.offers == ["s1"]
    await cam.async_on_webrtc_candidate("s1", {"candidate": "c"})
    cam.close_webrtc_session("s1")
    cam.close_webrtc_session("s1")
    assert provider.candidates == [("s1", {"candidate": "c"})]
    assert provider.closed == ["s1"]


async def test_native_webrtc_only_when_the_add_on_streams(hass: HomeAssistant) -> None:
    assert _camera(hass, FakeClient()).camera_capabilities.frontend_stream_types == {
        StreamType.WEB_RTC
    }
    # older add-on: no stream at all, the card uses MJPEG
    assert (
        _camera(hass, FakeClient(stream=False)).camera_capabilities.frontend_stream_types == set()
    )


async def test_candidates_during_the_warm_up_reach_go2rtc(hass: HomeAssistant) -> None:
    client = FakeClient()
    client.release = asyncio.Event()
    cam = _camera(hass, client)
    provider = FakeProvider(client)
    with _provider(provider):
        offer = asyncio.create_task(
            cam.async_handle_async_webrtc_offer("v=0", "s2", lambda m: None)
        )
        await asyncio.sleep(0)
        await cam.async_on_webrtc_candidate("s2", {"candidate": "early"})
        assert provider.candidates == []
        client.release.set()
        await offer
    assert provider.candidates == [("s2", {"candidate": "early"})]


async def test_closing_during_the_warm_up_sends_no_offer(hass: HomeAssistant) -> None:
    client = FakeClient()
    client.release = asyncio.Event()
    cam = _camera(hass, client)
    provider = FakeProvider(client)
    with _provider(provider):
        offer = asyncio.create_task(
            cam.async_handle_async_webrtc_offer("v=0", "s3", lambda m: None)
        )
        await asyncio.sleep(0)
        cam.close_webrtc_session("s3")
        client.release.set()
        await offer
    assert provider.offers == []


async def test_offer_goes_through_when_the_warm_up_fails(hass: HomeAssistant) -> None:
    client = FakeClient()
    client.warm_error = VectorError("unknown command warm_stream")  # add-on 0.2.1
    cam = _camera(hass, client)
    provider = FakeProvider(client)
    with _provider(provider):
        await cam.async_handle_async_webrtc_offer("v=0", "s4", lambda m: None)
    assert provider.offers == ["s4"]


async def test_no_go2rtc_is_a_readable_error(hass: HomeAssistant) -> None:
    cam = _camera(hass, FakeClient())
    with _provider(None), pytest.raises(HomeAssistantError, match="go2rtc"):
        await cam.async_handle_async_webrtc_offer("v=0", "s5", lambda m: None)
