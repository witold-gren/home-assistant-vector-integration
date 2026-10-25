"""Custom voice commands: subentry flow and sentence handling."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_mock_service,
)

from custom_components.vector.const import DOMAIN

from .conftest import TOKEN, FakeBridge, settle
from .test_init import setup
from .test_voice import commands


async def test_command_flow(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    await setup(hass, entry)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "command"), context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "Good night", "sentences": "good night (vector", "behavior": "none"},
    )
    assert result.get("errors") == {"sentences": "invalid_sentences"}, result
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Good night",
            "sentences": "good night [vector]\n\n  sleep well  ",
            "response": "Good night!",
            "behavior": "sleep",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    sub = next(iter(entry.subentries.values()))
    assert sub.title == "Good night"
    assert sub.data["sentences"] == ["good night [vector]", "sleep well"]
    assert sub.data["behavior"] == "sleep"

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, "command"),
        context={"source": "reconfigure", "subentry_id": sub.subentry_id},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {"name": "Good night", "sentences": "good night", "response": "", "behavior": "none"},
    )
    assert result["reason"] == "reconfigure_successful"
    sub = entry.subentries[sub.subentry_id]
    assert sub.data["sentences"] == ["good night"] and sub.data["behavior"] is None


async def test_command_runs(hass: HomeAssistant, bridge: FakeBridge) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="addon-uuid",
        data={"host": "127.0.0.1", "port": bridge.port, "token": TOKEN},
        subentries_data=[
            ConfigSubentryData(
                subentry_type="command",
                title="Music",
                unique_id=None,
                data={
                    "sentences": ["play {song} [in the living room]"],
                    "response": "Playing {song}",
                    "script": "script.vector_music",
                    "behavior": "dance",
                    "animation": "",
                },
            )
        ],
    )
    await setup(hass, entry)
    assert await async_setup_component(hass, "script", {})
    scripts = async_mock_service(hass, "script", "turn_on")
    fired = async_capture_events(hass, "vector_command")
    converse = AsyncMock()
    with patch("custom_components.vector.voice.conversation.async_converse", converse):
        await bridge.event("speech", {"id": 3, "text": "play jazz in the living room"})
        for _ in range(3):
            await settle(hass)

    converse.assert_not_awaited()
    assert commands(bridge, "speech_decision")[-1]["args"] == {"id": 3, "handled": True}
    assert fired[0].data["command"] == "Music" and fired[0].data["slots"] == {"song": "jazz"}
    assert scripts[0].data["entity_id"] == "script.vector_music"
    assert scripts[0].data["variables"]["slots"] == {"song": "jazz"}
    names = [c["command"] for c in bridge.commands]
    # answer first, then the dance
    assert names.index("say_text") < names.index("app_intent")
    assert commands(bridge, "say_text")[-1]["args"]["text"] == "Playing jazz"
    assert commands(bridge, "app_intent")[-1]["args"] == {"intent": "intent_imperative_dance"}
    assert hass.states.get("sensor.vector_last_speech").attributes["command"] == "Music"
