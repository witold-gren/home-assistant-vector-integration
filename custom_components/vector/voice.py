"""Voice → Home Assistant: a sentence heard by Vector (wire-pod) goes to Assist.

Assist understood it (anything but "no intent match") → the bridge tells wire-pod to stay quiet
and Vector speaks the answer (via wire-pod, i.e. its TTS voice, e.g. Piper). Not understood or too
slow → wire-pod handles the sentence itself (time, dance, its LLM).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
import logging
from typing import Any

from homeassistant.components import conversation
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, intent
from homeassistant.util import dt as dt_util

from .api import VectorClient, VectorError
from .commands import CommandMatcher, run_command
from .const import (
    CONF_AGENT,
    CONF_KEEP,
    CONF_LLM_AGENT,
    CONF_RESPOND,
    DEFAULT_AGENT,
    DOMAIN,
    VOICE_BUDGET,
    default_keep,
)
from .speak import speak

_LOGGER = logging.getLogger(__name__)


@dataclass
class Heard:
    """Last utterance heard by the robot and what was done with it."""

    text: str
    handled: bool
    response: str | None
    kept: bool = False  # kept on Vector without asking Assist
    command: str | None = None  # name of the matched custom command
    at: Any = field(default_factory=dt_util.utcnow)


# wire-pod waits 25 s for the proxy
LLM_BUDGET = 20
LLM_FALLBACK: dict[str, str] = {
    "en": "Sorry, I don't know the answer.",
    "pl": "Przepraszam, nie znam odpowiedzi.",
}


def llm_fallback(language: str | None) -> str:
    """Answer for a failed LLM question in the HA language (fallback: English)."""
    return LLM_FALLBACK.get((language or "en")[:2].lower(), LLM_FALLBACK["en"])


class VoiceRouter:
    """Handle bridge `speech` events for one config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: VectorClient) -> None:
        self.hass = hass
        self.entry = entry
        self.client = client
        self.last: dict[str, Heard] = {}
        self.commands = CommandMatcher(hass, entry)
        self._listeners: list[Callable[[str], None]] = []

    def add_listener(self, listener: Callable[[str], None]) -> Callable[[], None]:
        """Call `listener(esn)` after every utterance (sensor, event entity)."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def on_event(self, esn: str, event: str, data: dict[str, Any]) -> None:
        if event == "speech" and data.get("text"):
            self.entry.async_create_background_task(
                self.hass, self._handle(esn, data["id"], data["text"]), "vector-speech"
            )
        elif event == "llm" and data.get("text"):
            self.entry.async_create_background_task(
                self.hass, self._handle_llm(data["id"], data["text"]), "vector-llm"
            )

    async def _handle_llm(self, request_id: int, text: str) -> None:
        """A question wire-pod would ask its LLM: answered by the agent from options."""
        agent_id = (
            self.entry.options.get(CONF_LLM_AGENT)
            or self.entry.options.get(CONF_AGENT)
            or DEFAULT_AGENT
        )
        answer = llm_fallback(self.hass.config.language)
        try:
            async with asyncio.timeout(LLM_BUDGET):
                result = await conversation.async_converse(
                    self.hass,
                    text,
                    None,
                    Context(),
                    language=self.hass.config.language,
                    agent_id=agent_id,
                )
            answer = (result.response.speech.get("plain") or {}).get("speech") or answer
        except TimeoutError:
            _LOGGER.warning("LLM agent %s did not answer %r in %ss", agent_id, text, LLM_BUDGET)
        except Exception:
            _LOGGER.exception("LLM agent %s failed for %r", agent_id, text)
        try:
            await self.client.command("llm_reply", id=request_id, text=answer)
        except VectorError as err:
            _LOGGER.warning("LLM answer for %r not delivered: %s", text, err)

    def keep_on_vector(self, text: str) -> bool:
        """Sentence containing a phrase from the "Keep on Vector" list (time, dance…)."""
        phrases = self.entry.options.get(CONF_KEEP)
        if phrases is None:
            phrases = default_keep(self.hass.config.language)
        lowered = text.lower()
        return any(p.strip().lower() in lowered for p in phrases if p.strip())

    async def _ask_assist(
        self, text: str, agent_id: str, device_id: str | None
    ) -> tuple[bool, str | None]:
        """(handled, answer); not understood, too slow or failed → (False, …)."""
        try:
            async with asyncio.timeout(VOICE_BUDGET):
                result = await conversation.async_converse(
                    self.hass,
                    text,
                    None,
                    Context(),
                    language=self.hass.config.language,
                    agent_id=agent_id,
                    device_id=device_id,
                )
        except TimeoutError:
            _LOGGER.warning(
                "Assist did not answer %r within %ss, wire-pod handles it", text, VOICE_BUDGET
            )
            return False, None
        except Exception:
            _LOGGER.exception("Assist failed for %r", text)
            return False, None
        response = result.response
        handled = not (
            response.response_type is intent.IntentResponseType.ERROR
            and response.error_code is intent.IntentResponseErrorCode.NO_INTENT_MATCH
        )
        return handled, (response.speech.get("plain") or {}).get("speech") or None

    async def _speak(self, esn: str, text: str) -> None:
        """Speak the answer with the voice from options (wire-pod or HA TTS); return once spoken."""
        # give wire-pod a moment to send the robot intent_system_noaudio
        await asyncio.sleep(0.3)
        try:
            await speak(self.hass, self.entry, self.client, esn, text)
        except (VectorError, HomeAssistantError) as err:
            _LOGGER.warning("Vector could not say the answer: %s", err)

    async def _handle(self, esn: str, request_id: int, text: str) -> None:
        device = dr.async_get(self.hass).async_get_device(identifiers={(DOMAIN, esn)})
        device_id = device.id if device else None
        agent_id = self.entry.options.get(CONF_AGENT) or DEFAULT_AGENT
        respond = self.entry.options.get(CONF_RESPOND, True)
        handled, speech, kept = False, None, False
        # order: custom commands → "Keep on Vector" → Assist
        match = self.commands.match(text)
        if match is not None:
            handled = True
        elif not (kept := self.keep_on_vector(text)):
            handled, speech = await self._ask_assist(text, agent_id, device_id)

        try:
            await self.client.command("speech_decision", id=request_id, handled=handled)
        except VectorError as err:
            # too late: wire-pod already handled the sentence itself
            _LOGGER.warning("Speech decision for %r not delivered: %s", text, err)
            handled = False

        if match is not None and handled:
            speak = (lambda reply: self._speak(esn, reply)) if respond else None
            speech = await run_command(self.hass, self.client, esn, device_id, text, match, speak)

        self.last[esn] = Heard(text, handled, speech, kept, match.title if match else None)
        self.hass.bus.async_fire(
            f"{DOMAIN}_speech",
            {
                "esn": esn,
                "device_id": device_id,
                "text": text,
                "handled": handled,
                "response": speech,
                "agent_id": agent_id,
                "kept_on_vector": kept,
                "command": match.title if match else None,
            },
        )
        for listener in list(self._listeners):
            listener(esn)

        if match is None and handled and speech and respond:
            await self._speak(esn, speech)
