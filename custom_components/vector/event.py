"""Robot events as event entities: wake word, contact (touch, pick-up…) and face."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VectorConfigEntry
from .api import VectorClient
from .entity import VectorEntity
from .speech import VectorSpeechEvent

# entity -> bridge events it shows (event type = name, for wake word: the phase)
EVENT_ENTITIES: dict[str, list[str]] = {
    "wake_word": ["begin", "end"],
    "interaction": ["touched", "picked_up", "button_pressed", "cliff", "cube_tapped"],
    "face": ["face_seen"],
    "photo": ["photo_taken"],
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    client = entry.runtime_data.client
    entities: list[EventEntity] = [
        VectorEvent(client, esn, key, types)
        for esn in client.robots
        for key, types in EVENT_ENTITIES.items()
    ]
    if client.voice_router is not None:
        entities += [
            VectorSpeechEvent(client, esn, entry.runtime_data.voice) for esn in client.robots
        ]
    async_add_entities(entities)


class VectorEvent(VectorEntity, EventEntity):
    """Last event of a given kind."""

    def __init__(self, client: VectorClient, esn: str, key: str, types: list[str]) -> None:
        super().__init__(client, esn, key)
        self._key = key
        self._attr_translation_key = key
        self._attr_event_types = types

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._bridge.add_event_listener(self._on_event))

    @callback
    def _on_event(self, esn: str, event: str, data: dict[str, Any]) -> None:
        if esn != self._esn:
            return
        if self._key == "wake_word" and event == "wake_word":
            event_type = data.get("phase")
        elif event in self._attr_event_types and self._key != "wake_word":
            event_type = event
        else:
            return
        if event_type not in self._attr_event_types:
            return
        self._trigger_event(event_type, data)
        self.async_write_ha_state()
