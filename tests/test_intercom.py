"""Intercom: a recording from the control card plays on Vector's speaker at once."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vector.views import MAX_RECORDING

from .conftest import FakeBridge
from .test_init import setup


async def _client(hass: HomeAssistant, entry: MockConfigEntry, hass_client):
    assert await async_setup_component(hass, "http", {})
    await setup(hass, entry)
    return await hass_client()


async def test_recording_plays_on_the_speaker_right_away(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry, hass_client
) -> None:
    client = await _client(hass, entry, hass_client)
    resp = await client.post(
        "/api/vector/intercom/camera.vector",
        data=b"x" * 4000,
        headers={"Content-Type": "audio/mp4"},
    )
    assert resp.status == 200
    data, query = bridge.audio[-1]
    assert len(data) == 4000
    assert query.get("interrupt") == "true"  # the user talks now, over whatever was playing


@pytest.mark.parametrize(("body", "status"), [(b"x" * 100, 400), (b"x" * (MAX_RECORDING + 1), 413)])
async def test_bad_recordings_are_refused(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry, hass_client, body, status
) -> None:
    client = await _client(hass, entry, hass_client)
    resp = await client.post("/api/vector/intercom/camera.vector", data=body)
    assert resp.status == status
    assert bridge.audio == []


async def test_unknown_camera_is_404(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry, hass_client
) -> None:
    client = await _client(hass, entry, hass_client)
    resp = await client.post("/api/vector/intercom/camera.kitchen", data=b"x" * 4000)
    assert resp.status == 404


async def test_intercom_needs_auth(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry, hass_client_no_auth
) -> None:
    assert await async_setup_component(hass, "http", {})
    await setup(hass, entry)
    client = await hass_client_no_auth()
    resp = await client.post("/api/vector/intercom/camera.vector", data=b"x" * 4000)
    assert resp.status == 401


async def test_slow_recording_plays_whole(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry, hass_client
) -> None:
    import asyncio

    async def pieces():
        for _ in range(40):
            yield b"x" * 1000
            await asyncio.sleep(0.005)

    client = await _client(hass, entry, hass_client)
    resp = await client.post("/api/vector/intercom/camera.vector", data=pieces())
    assert resp.status == 200
    assert len(bridge.audio[-1][0]) == 40000
