"""Connection, charging, on charger, picked up, touched, cliff, sleeping and listening."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VectorConfigEntry
from .api import VectorClient
from .entity import VectorEntity


@dataclass(frozen=True, kw_only=True)
class VectorBinaryDescription(BinarySensorEntityDescription):
    """Binary sensor description."""

    value: Callable[[dict[str, Any]], bool | None]
    needs_robot: bool = True
    cube: bool = False  # cube entity: enabled by default only when the robot knows a cube


def _battery(key: str) -> Callable[[dict[str, Any]], bool | None]:
    return lambda s: None if s.get("battery") is None else bool(s["battery"].get(key))


BINARY_SENSORS: tuple[VectorBinaryDescription, ...] = (
    VectorBinaryDescription(
        key="connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda s: bool(s.get("connected")),
        needs_robot=False,
    ),
    VectorBinaryDescription(
        key="charging",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value=_battery("charging"),
    ),
    VectorBinaryDescription(
        key="on_charger",
        translation_key="on_charger",
        device_class=BinarySensorDeviceClass.PLUG,
        value=_battery("on_charger"),
    ),
    VectorBinaryDescription(
        key="picked_up", translation_key="picked_up", value=lambda s: s.get("picked_up")
    ),
    VectorBinaryDescription(
        key="touched", translation_key="touched", value=lambda s: s.get("touched")
    ),
    VectorBinaryDescription(
        key="cliff",
        translation_key="cliff",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value=lambda s: s.get("cliff"),
    ),
    VectorBinaryDescription(
        key="sleeping", translation_key="sleeping", value=lambda s: s.get("sleeping")
    ),
    VectorBinaryDescription(
        key="listening", translation_key="listening", value=lambda s: s.get("listening")
    ),
    VectorBinaryDescription(
        key="cube_connected",
        translation_key="cube_connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value=lambda s: bool((s.get("cube") or {}).get("connected")),
        cube=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    client = entry.runtime_data.client
    async_add_entities(
        VectorBinarySensor(client, esn, description)
        for esn in client.robots
        for description in BINARY_SENSORS
    )


class VectorBinarySensor(VectorEntity, BinarySensorEntity):
    """Binary sensor from the robot state."""

    entity_description: VectorBinaryDescription

    def __init__(
        self, client: VectorClient, esn: str, description: VectorBinaryDescription
    ) -> None:
        super().__init__(client, esn, description.key)
        self.entity_description = description
        self._needs_robot = description.needs_robot
        if description.cube:
            self._attr_entity_registry_enabled_default = bool(client.robots[esn].get("cube"))

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value(self.state_data)
