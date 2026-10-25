"""Custom Vector voice commands ("Command" subentries): hassil sentences → response and actions.

Sentences as in Assist: `good night [vector]`, `(turn off|switch off) everything`, `play {song}` —
each `{slot}` accepts any text and is passed to the script and the `vector_command` event.
Commands are checked before the "Keep on Vector" list and before Assist.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import logging
import re
from typing import Any

from hassil import Intents, recognize
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Context, HomeAssistant

from .api import VectorClient, VectorError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SUBENTRY_COMMAND = "command"
CONF_SENTENCES = "sentences"
CONF_RESPONSE = "response"
CONF_SCRIPT = "script"
CONF_BEHAVIOR = "behavior"
CONF_ANIMATION = "animation"

# Vector behaviors as after a voice command (app_intent); key = option in the form.
BEHAVIORS: dict[str, str] = {
    "dance": "intent_imperative_dance",
    "explore": "intent_explore_start",
    "sleep": "intent_system_sleep",
    "charger": "intent_system_charger",
    "come_here": "intent_imperative_come",
    "look_at_me": "intent_imperative_lookatme",
    "fist_bump": "intent_play_fistbump",
    "trick": "intent_play_anytrick",
    "take_photo": "intent_photo_take_extend",
    "happy": "intent_imperative_praise",
    "love": "intent_imperative_love",
    "hello": "intent_greeting_hello",
}

SLOT = re.compile(r"\{([^{}:]+)(?::[^{}]*)?\}")


def split_sentences(raw: str | list[str]) -> list[str]:
    """Sentences from a multiline field (one per line)."""
    lines = raw if isinstance(raw, list) else raw.splitlines()
    return [line.strip() for line in lines if line.strip()]


def build_intents(commands: dict[str, list[str]], language: str) -> Intents:
    """hassil: one intent per command, each {slot} as free text."""
    slots = {
        name.strip()
        for sentences in commands.values()
        for s in sentences
        for name in SLOT.findall(s)
    }
    intents = Intents.from_dict(
        {
            "language": language,
            "intents": {cid: {"data": [{"sentences": s}]} for cid, s in commands.items() if s},
            "lists": {name: {"wildcard": True} for name in slots},
        }
    )
    # hassil parses sentences lazily: force it here so syntax errors show up at once
    for item in intents.intents.values():
        for data in item.data:
            _ = data.sentences
    return intents


def validate_sentences(sentences: list[str], language: str) -> str | None:
    """Sentence syntax error (for the form) or None."""
    if not sentences:
        return "no_sentences"
    try:
        build_intents({"check": sentences}, language)
    except Exception:
        return "invalid_sentences"
    return None


@dataclass
class Match:
    """Matched command."""

    subentry_id: str
    title: str
    data: dict[str, Any]
    slots: dict[str, str]


class CommandMatcher:
    """Match a sentence against the entry commands; recompile after subentries change."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._key: tuple | None = None
        self._intents: Intents | None = None

    def _commands(self) -> dict[str, Any]:
        return {
            sid: sub
            for sid, sub in self.entry.subentries.items()
            if sub.subentry_type == SUBENTRY_COMMAND
        }

    def match(self, text: str) -> Match | None:
        commands = self._commands()
        if not commands:
            return None
        key = tuple((sid, tuple(sub.data.get(CONF_SENTENCES, []))) for sid, sub in commands.items())
        if key != self._key:
            try:
                self._intents = build_intents(
                    {
                        sid: split_sentences(sub.data.get(CONF_SENTENCES, []))
                        for sid, sub in commands.items()
                    },
                    self.hass.config.language,
                )
            except Exception:
                _LOGGER.exception("Invalid Vector command sentences")
                self._intents = None
            self._key = key
        if self._intents is None:
            return None
        result = recognize(text, self._intents)
        if result is None:
            return None
        sub = commands[result.intent.name]
        return Match(
            sub.subentry_id,
            sub.title,
            dict(sub.data),
            {name: str(entity.value).strip() for name, entity in result.entities.items()},
        )


async def run_command(
    hass: HomeAssistant,
    client: VectorClient,
    esn: str,
    device_id: str | None,
    text: str,
    match: Match,
    speak: Callable[[str], Awaitable[None]] | None,
) -> str | None:
    """Fire the event and start the script at once, then answer (`speak`), then move the robot.

    Return the spoken response.
    """
    data = match.data
    variables = {"text": text, "slots": match.slots, "esn": esn, "device_id": device_id}
    hass.bus.async_fire(
        f"{DOMAIN}_command",
        {"command": match.title, "subentry_id": match.subentry_id, **variables},
    )
    if script := data.get(CONF_SCRIPT):
        hass.async_create_task(
            hass.services.async_call(
                "script",
                "turn_on",
                {"entity_id": script, "variables": variables},
                context=Context(),
            )
        )
    response = (data.get(CONF_RESPONSE) or "").strip()
    # {slot} in the response → value from the sentence
    response = SLOT.sub(lambda m: match.slots.get(m.group(1).strip(), m.group(0)), response)
    if response and speak is not None:
        await speak(response)
    try:
        if behavior := BEHAVIORS.get(data.get(CONF_BEHAVIOR) or ""):
            await client.command("app_intent", esn, intent=behavior)
        elif animation := (data.get(CONF_ANIMATION) or "").strip():
            await client.command("play_animation_trigger", esn, name=animation)
    except VectorError as err:
        _LOGGER.warning("Vector command %s: %s", match.title, err)
    return response or None
