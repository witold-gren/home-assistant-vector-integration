"""Go to charger, drive off charger, stop, refresh and Vector behaviors (intents)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VectorConfigEntry
from .api import VectorClient
from .entity import VectorEntity


@dataclass(frozen=True, kw_only=True)
class VectorButtonDescription(ButtonEntityDescription):
    """Bridge command and its arguments."""

    command: str
    args: dict[str, Any] | None = None
    cube: bool = False  # cube entity: enabled by default only when the robot knows a cube


def _intent(key: str, intent: str) -> VectorButtonDescription:
    # Behavior as after a voice command: Vector does it himself, without taking control.
    return VectorButtonDescription(
        key=key, translation_key=key, command="app_intent", args={"intent": intent}
    )


BUTTONS: tuple[VectorButtonDescription, ...] = (
    VectorButtonDescription(
        key="drive_on_charger", translation_key="drive_on_charger", command="drive_on_charger"
    ),
    VectorButtonDescription(
        key="drive_off_charger", translation_key="drive_off_charger", command="drive_off_charger"
    ),
    VectorButtonDescription(key="stop", translation_key="stop", command="stop"),
    _intent("dance", "intent_imperative_dance"),
    _intent("explore", "intent_explore_start"),
    _intent("sleep", "intent_system_sleep"),
    _intent("come_here", "intent_imperative_come"),
    _intent("look_at_me", "intent_imperative_lookatme"),
    _intent("fist_bump", "intent_play_fistbump"),
    _intent("trick", "intent_play_anytrick"),
    _intent("take_photo", "intent_photo_take_extend"),
    VectorButtonDescription(
        key="connect_cube", translation_key="connect_cube", command="connect_cube", cube=True
    ),
    VectorButtonDescription(
        key="disconnect_cube",
        translation_key="disconnect_cube",
        command="disconnect_cube",
        cube=True,
    ),
    VectorButtonDescription(
        key="flash_cube", translation_key="flash_cube", command="flash_cube", cube=True
    ),
    VectorButtonDescription(
        key="pickup_cube", translation_key="pickup_cube", command="pickup_cube", cube=True
    ),
    VectorButtonDescription(
        key="roll_cube", translation_key="roll_cube", command="roll_cube", cube=True
    ),
    VectorButtonDescription(
        key="dock_with_cube", translation_key="dock_with_cube", command="dock_with_cube", cube=True
    ),
    VectorButtonDescription(
        key="turn_towards_face", translation_key="turn_towards_face", command="turn_towards_face"
    ),
    VectorButtonDescription(
        key="refresh_camera", translation_key="refresh_camera", command="camera_snapshot"
    ),
    VectorButtonDescription(
        key="refresh",
        translation_key="refresh",
        command="refresh",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    client = entry.runtime_data.client
    async_add_entities(
        VectorButton(client, esn, description) for esn in client.robots for description in BUTTONS
    )


class VectorButton(VectorEntity, ButtonEntity):
    """One-shot command."""

    entity_description: VectorButtonDescription

    def __init__(
        self, client: VectorClient, esn: str, description: VectorButtonDescription
    ) -> None:
        super().__init__(client, esn, description.key)
        self.entity_description = description
        if description.cube:
            self._attr_entity_registry_enabled_default = bool(client.robots[esn].get("cube"))

    async def async_press(self) -> None:
        await self._command(self.entity_description.command, **(self.entity_description.args or {}))
