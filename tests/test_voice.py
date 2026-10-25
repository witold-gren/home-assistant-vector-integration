"""Voice → Home Assistant: Assist decision, Vector answer, switch and options."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant.components.conversation import ConversationResult
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.vector.const import CONF_AGENT, CONF_KEEP, CONF_RESPOND, default_keep
from custom_components.vector.voice import llm_fallback

from .conftest import FakeBridge, settle
from .test_init import setup


def result(speech: str, error: intent.IntentResponseErrorCode | None = None) -> ConversationResult:
    response = intent.IntentResponse(language="en")
    if error is None:
        response.async_set_speech(speech)
    else:
        response.async_set_error(error, speech)
    return ConversationResult(response=response)


def commands(bridge: FakeBridge, name: str) -> list[dict]:
    return [c for c in bridge.commands if c["command"] == name]


async def test_handled_speech(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    await setup(hass, entry)
    fired = async_capture_events(hass, "vector_speech")
    converse = AsyncMock(return_value=result("Turned on the light"))
    with patch("custom_components.vector.voice.conversation.async_converse", converse):
        await bridge.event("speech", {"id": 7, "text": "turn on the light in the living room"})
        await settle(hass)
        await settle(hass)

    assert converse.await_args.args[1] == "turn on the light in the living room"
    assert converse.await_args.kwargs["agent_id"] == "conversation.home_assistant"
    assert commands(bridge, "speech_decision")[-1]["args"] == {"id": 7, "handled": True}
    say = commands(bridge, "say_text")[-1]
    assert say["args"] == {"text": "Turned on the light", "engine": "wirepod"}
    assert fired[0].data["handled"] is True and fired[0].data["response"] == "Turned on the light"

    sensor = hass.states.get("sensor.vector_last_speech")
    assert (
        sensor.state == "turn on the light in the living room"
        and sensor.attributes["handled"] is True
    )
    assert hass.states.get("event.vector_speech").attributes["event_type"] == "handled"


async def test_not_understood_goes_back_to_wirepod(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    await setup(hass, entry)
    converse = AsyncMock(
        return_value=result(
            "Sorry, I couldn't understand that", intent.IntentResponseErrorCode.NO_INTENT_MATCH
        )
    )
    with patch("custom_components.vector.voice.conversation.async_converse", converse):
        await bridge.event("speech", {"id": 8, "text": "what time is it"})
        await settle(hass)
    assert commands(bridge, "speech_decision")[-1]["args"] == {"id": 8, "handled": False}
    assert not commands(bridge, "say_text")
    assert hass.states.get("event.vector_speech").attributes["event_type"] == "passed"


async def test_switch_and_options(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    await setup(hass, entry)
    assert hass.states.get("switch.vector_voice_home_assistant").state == "on"
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.vector_voice_home_assistant"}, blocking=True
    )
    await settle(hass)
    assert hass.states.get("switch.vector_voice_home_assistant").state == "off"

    flow = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        flow["flow_id"],
        {
            CONF_AGENT: "conversation.assist_fallback",
            CONF_RESPOND: False,
            CONF_KEEP: "dance\n  \nend of the world",
        },
    )
    await hass.async_block_till_done()
    await settle(hass)
    converse = AsyncMock(return_value=result("Done"))
    with patch("custom_components.vector.voice.conversation.async_converse", converse):
        await bridge.event("speech", {"id": 9, "text": "do something"})
        await settle(hass)
    assert converse.await_args.kwargs["agent_id"] == "conversation.assist_fallback"
    assert not commands(bridge, "say_text"), "respond off: Vector stays silent"
    assert entry.options[CONF_KEEP] == ["dance", "end of the world"]


async def test_keep_on_vector(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    await setup(hass, entry)
    converse = AsyncMock(return_value=result("It is 8:33 PM"))
    with patch("custom_components.vector.voice.conversation.async_converse", converse):
        await bridge.event("speech", {"id": 10, "text": "what time is it"})
        await settle(hass)
    converse.assert_not_awaited()
    assert commands(bridge, "speech_decision")[-1]["args"] == {"id": 10, "handled": False}
    assert hass.states.get("sensor.vector_last_speech").attributes["kept_on_vector"] is True


def test_language_defaults() -> None:
    assert "what time is it" in default_keep("en")
    assert "która godzina" in default_keep("pl-PL")
    assert default_keep("xx") == default_keep(None) == default_keep("en")
    assert llm_fallback("pl") == "Przepraszam, nie znam odpowiedzi."
    assert llm_fallback("de-DE") == "Sorry, I don't know the answer."
