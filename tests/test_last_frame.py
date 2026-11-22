"""The last live-view frame kept in Home Assistant: the card uploads it, it is stored on disk per
robot and shown by an always-available "Last frame" image (full-screen background while off)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vector.last_frame import MAX_FRAME

from .conftest import FakeBridge
from .test_init import setup

JPEG = b"\xff\xd8" + b"x" * 800


def _frame_entity(hass: HomeAssistant) -> str:
    images = hass.states.async_all("image")
    return next(s.entity_id for s in images if s.entity_id.endswith("last_frame"))


async def test_upload_is_stored_and_shown(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry, hass_client
) -> None:
    assert await async_setup_component(hass, "http", {})
    await setup(hass, entry)
    client = await hass_client()
    resp = await client.post(
        "/api/vector/last_frame/camera.vector", data=JPEG, headers={"Content-Type": "image/jpeg"}
    )
    assert resp.status == 200
    await hass.async_block_till_done()
    state = hass.states.get(_frame_entity(hass))
    assert state.state != "unavailable"
    img = await client.get(state.attributes["entity_picture"])
    assert img.status == 200 and await img.read() == JPEG
    # kept on disk: a new store for the same robot reads it back
    from custom_components.vector.last_frame import LastFrameStore, frame_path

    esn = next(iter(entry.runtime_data.frames))
    again = LastFrameStore(frame_path(hass, "vector", esn))
    await again.async_load(hass)
    assert again.jpeg == JPEG


async def test_bad_frames_and_unknown_camera(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry, hass_client
) -> None:
    assert await async_setup_component(hass, "http", {})
    await setup(hass, entry)
    client = await hass_client()
    url = "/api/vector/last_frame/camera.vector"
    assert (await client.post(url, data=b"GIF89a")).status == 400
    big = b"\xff\xd8" + b"x" * (MAX_FRAME + 1)
    assert (await client.post(url, data=big)).status == 413
    assert (await client.post("/api/vector/last_frame/camera.kitchen", data=JPEG)).status == 404


async def test_frame_image_stays_available_when_the_bridge_is_gone(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    await setup(hass, entry)
    entry.runtime_data.client.connected = False
    entry.runtime_data.client._notify()
    await hass.async_block_till_done()
    assert hass.states.get(_frame_entity(hass)).state != "unavailable"
