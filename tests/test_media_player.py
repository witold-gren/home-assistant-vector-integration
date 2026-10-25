"""Speaker: TTS, URLs, announcements, volume and stop."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import ESN, FakeBridge, settle
from .test_init import setup

PLAYER = "media_player.vector_speaker"


async def test_state_and_volume(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    await setup(hass, entry)
    state = hass.states.get(PLAYER)
    assert state.state == "idle" and state.attributes["volume_level"] == 0.8

    await hass.services.async_call(
        "media_player", "volume_set", {"entity_id": PLAYER, "volume_level": 0.35}, blocking=True
    )
    await settle(hass)
    assert hass.states.get(PLAYER).attributes["volume_level"] == 0.35

    bridge.robots[ESN]["audio"].update(playing=True, duration=4.4, started=1792780000)
    await bridge.push(ESN)
    await settle(hass)
    state = hass.states.get(PLAYER)
    assert state.state == "playing" and state.attributes["media_duration"] == 4.4

    await hass.services.async_call(
        "media_player", "media_stop", {"entity_id": PLAYER}, blocking=True
    )
    assert bridge.commands[-1]["command"] == "stop_audio"


async def test_play_url_and_announce(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    await setup(hass, entry)
    url = f"http://127.0.0.1:{bridge.port}/sound.mp3"
    await hass.services.async_call(
        "media_player",
        "play_media",
        {"entity_id": PLAYER, "media_content_type": "music", "media_content_id": url},
        blocking=True,
    )
    assert bridge.audio[-1] == (b"ID3-mp3-bytes", {})

    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            "entity_id": PLAYER,
            "media_content_type": "music",
            "media_content_id": url,
            "announce": True,
        },
        blocking=True,
    )
    assert bridge.audio[-1][1] == {"interrupt": "true"}


async def test_tts(hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry) -> None:
    await setup(hass, entry)
    with patch(
        "custom_components.vector.media_player.tts.async_get_media_source_audio",
        AsyncMock(return_value=("mp3", b"piper-audio")),
    ) as get_audio:
        await hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": PLAYER,
                "media_content_type": "music",
                "media_content_id": "media-source://tts/tts.piper?message=Cze%C5%9B%C4%87",
            },
            blocking=True,
        )
    get_audio.assert_awaited_once()
    assert bridge.audio[-1][0] == b"piper-audio"
