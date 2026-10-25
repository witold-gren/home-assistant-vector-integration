"""Last utterance to Vector: a text sensor and an event entity (handled / passed)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback

from .api import VectorClient
from .entity import VectorEntity
from .voice import VoiceRouter


class VectorLastSpeech(VectorEntity, SensorEntity):
    """What Vector last heard (via the voice router) and what Assist answered."""

    _attr_translation_key = "last_speech"
    _needs_robot = False

    def __init__(self, client: VectorClient, esn: str, voice: VoiceRouter) -> None:
        super().__init__(client, esn, "last_speech")
        self._voice = voice

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._voice.add_listener(self._heard))

    @callback
    def _heard(self, esn: str) -> None:
        if esn == self._esn:
            self.async_write_ha_state()

    @property
    def native_value(self) -> str | None:
        heard = self._voice.last.get(self._esn)
        return heard.text[:255] if heard else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        heard = self._voice.last.get(self._esn)
        if heard is None:
            return None
        return {
            "handled": heard.handled,
            "kept_on_vector": heard.kept,
            "command": heard.command,
            "response": heard.response,
            "at": heard.at.isoformat(),
        }


class VectorSpeechEvent(VectorEntity, EventEntity):
    """handled: done by Home Assistant; passed: handed back to wire-pod."""

    _attr_translation_key = "speech"
    _needs_robot = False

    def __init__(self, client: VectorClient, esn: str, voice: VoiceRouter) -> None:
        super().__init__(client, esn, "speech")
        self._voice = voice
        self._attr_event_types = ["handled", "passed"]

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._voice.add_listener(self._heard))

    @callback
    def _heard(self, esn: str) -> None:
        heard = self._voice.last.get(esn)
        if esn != self._esn or heard is None:
            return
        self._trigger_event(
            "handled" if heard.handled else "passed",
            {"text": heard.text, "response": heard.response},
        )
        self.async_write_ha_state()
