"""Faces, settings, cube, LLM proxy and speech via HA TTS."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vector.const import CONF_TTS_ENGINE, CONF_VOICE, DOMAIN

from .conftest import FakeBridge, settle
from .test_init import setup
from .test_voice import commands, result


async def test_settings_entities(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    await setup(hass, entry)
    assert hass.states.get("text.vector_time_zone").state == "Europe/Paris"
    assert hass.states.get("select.vector_robot_language").state == "en-US"
    assert hass.states.get("select.vector_back_button").state == "hey_vector"
    assert hass.states.get("switch.vector_24_hour_clock").state == "on"
    assert hass.states.get("sensor.vector_known_faces").state == "1"

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.vector_24_hour_clock"}, blocking=True
    )
    assert commands(bridge, "set_clock_24h")[-1]["args"] == {"on": False}
    await hass.services.async_call(
        "text",
        "set_value",
        {"entity_id": "text.vector_time_zone", "value": " Europe/Warsaw "},
        blocking=True,
    )
    assert commands(bridge, "update_settings")[-1]["args"] == {"time_zone": "Europe/Warsaw"}

    # no cube: its entities exist but are disabled by default
    reg = er.async_get(hass)
    assert (
        reg.async_get("button.vector_connect_cube").disabled_by
        is er.RegistryEntryDisabler.INTEGRATION
    )

    response = await hass.services.async_call(
        DOMAIN, "list_faces", {}, blocking=True, return_response=True
    )
    assert response["faces"][0]["name"] == "Alice"


async def test_animation_select(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    await setup(hass, entry)
    await settle(hass)
    state = hass.states.get("select.vector_play_animation")
    assert state.attributes["options"] == ["GreetAfterLongTime", "PounceSuccess"]
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.vector_play_animation", "option": "PounceSuccess"},
        blocking=True,
    )
    assert commands(bridge, "play_animation_trigger")[-1]["args"] == {"name": "PounceSuccess"}


async def test_llm_proxy(hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry) -> None:
    await setup(hass, entry)
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.vector_wire_pod_llm_home_assistant"},
        blocking=True,
    )
    await settle(hass)
    assert hass.states.get("switch.vector_wire_pod_llm_home_assistant").state == "on"
    converse = AsyncMock(return_value=result("Stolica Polski to Warszawa."))
    with patch("custom_components.vector.voice.conversation.async_converse", converse):
        await bridge.event("llm", {"id": 4, "text": "jaka jest stolica polski"})
        await settle(hass)
    assert commands(bridge, "llm_reply")[-1]["args"] == {
        "id": 4,
        "text": "Stolica Polski to Warszawa.",
    }


async def test_answer_with_ha_tts(hass: HomeAssistant, bridge: FakeBridge) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="addon-uuid",
        data={"host": "127.0.0.1", "port": bridge.port, "token": "secret"},
        options={CONF_VOICE: "tts", CONF_TTS_ENGINE: "tts.piper"},
    )
    await setup(hass, entry)
    with (
        patch(
            "custom_components.vector.speak.tts.generate_media_source_id",
            return_value="media-source://tts/x",
        ),
        patch(
            "custom_components.vector.speak.tts.async_get_media_source_audio",
            AsyncMock(return_value=("mp3", b"piper")),
        ),
    ):
        task = hass.async_create_task(
            hass.services.async_call(DOMAIN, "say_text", {"text": "Hello"}, blocking=True)
        )
        # settle() would wait for the task itself: here we only yield to the loop
        for _ in range(100):
            await asyncio.sleep(0.02)
            if bridge.audio:
                break
        assert bridge.audio[-1] == (b"piper", {"interrupt": "true"})
        await asyncio.sleep(0.2)
        assert not task.done(), "say_text waits until the audio finished"
        await bridge.event("audio_finished", {"interrupted": False})
        async with asyncio.timeout(3):
            await task
