"""Camera, last photo, media browser and photo services."""

from __future__ import annotations

from homeassistant.components import media_source
from homeassistant.components.camera import async_get_image
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.vector.const import DOMAIN

from .conftest import ESN, JPEG, FakeBridge, settle
from .test_init import setup


async def test_camera_uses_cached_frames(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    await setup(hass, entry)
    assert hass.states.get("camera.vector").state == "idle"
    image = await async_get_image(hass, "camera.vector")
    assert image.content == JPEG

    await hass.services.async_call(
        "button", "press", {"entity_id": "button.vector_refresh_camera_image"}, blocking=True
    )
    assert (await async_get_image(hass, "camera.vector")).content == b"\xff\xd8fresh\xff\xd9"

    bridge.robots[ESN]["camera"] = True
    await bridge.push(ESN)
    await settle(hass)
    assert hass.states.get("camera.vector").state == "streaming"


async def test_mjpeg_proxy(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry, hass_client
) -> None:
    await setup(hass, entry)
    client = await hass_client()
    resp = await client.get("/api/camera_proxy_stream/camera.vector")
    assert resp.status == 200
    assert JPEG in await resp.read()
    assert bridge.mjpeg_requests == 1


async def test_last_photo_image(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry, hass_client
) -> None:
    await setup(hass, entry)
    state = hass.states.get("image.vector_last_photo")
    assert state.state == "2023-06-19T15:12:25+00:00"
    client = await hass_client()
    resp = await client.get(state.attributes["entity_picture"])
    assert await resp.read() == b"photo"


async def test_photo_services_and_event(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    await setup(hass, entry)
    fired = async_capture_events(hass, "vector_photo_taken")
    await bridge.event("photo_taken", {"photo_id": 3, "at": 1792780000})
    await settle(hass)
    assert fired[0].data["photo_id"] == 3
    assert hass.states.get("event.vector_photo").attributes["event_type"] == "photo_taken"

    response = await hass.services.async_call(
        DOMAIN, "list_photos", {}, blocking=True, return_response=True
    )
    assert response == {"photos": [{"photo_id": 2, "taken": "2023-06-19T15:12:25+00:00"}]}
    await hass.services.async_call(DOMAIN, "delete_photo", {"photo_id": 2}, blocking=True)
    assert bridge.photos == {}


async def test_media_source(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry, hass_client
) -> None:
    await setup(hass, entry)
    assert await async_setup_component(hass, "media_source", {})
    await hass.async_block_till_done()
    root = await media_source.async_browse_media(hass, f"media-source://{DOMAIN}")
    assert [c.title for c in root.children] == ["Vector"]
    robot = await media_source.async_browse_media(hass, f"media-source://{DOMAIN}/{ESN}")
    assert len(robot.children) == 1 and robot.children[0].thumbnail.endswith("&thumb=true")

    played = await media_source.async_resolve_media(hass, f"media-source://{DOMAIN}/{ESN}/2", None)
    assert played.mime_type == "image/jpeg"
    client = await hass_client()
    resp = await client.get(played.url)
    assert resp.status == 200 and await resp.read() == b"photo"
    resp = await client.get(robot.children[0].thumbnail)
    assert await resp.read() == b"thumb"
