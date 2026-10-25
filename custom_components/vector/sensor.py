"""Battery, activity, stimulation, last face and robot statistics."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricPotential,
    UnitOfLength,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VectorConfigEntry
from .api import VectorClient
from .entity import VectorEntity
from .speech import VectorLastSpeech


@dataclass(frozen=True, kw_only=True)
class VectorSensorDescription(SensorEntityDescription):
    """Sensor description."""

    value: Callable[[dict[str, Any]], Any]
    attrs: Callable[[dict[str, Any]], dict[str, Any] | None] = lambda _: None
    cube: bool = False  # cube entity: enabled by default only when the robot knows a cube


def _battery(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda s: (s.get("battery") or {}).get(key)


def _stat(key: str, scale: float = 1) -> Callable[[dict[str, Any]], Any]:
    def value(s: dict[str, Any]) -> Any:
        raw = (s.get("stats") or {}).get(key)
        return None if raw is None else round(raw * scale, 1)

    return value


def _face_seen(s: dict[str, Any]) -> dict[str, Any] | None:
    face = s.get("last_face")
    if not face:
        return None
    return {
        "face_id": face.get("id"),
        "seen_at": datetime.fromtimestamp(face["at"], UTC).isoformat() if face.get("at") else None,
    }


SENSORS: tuple[VectorSensorDescription, ...] = (
    VectorSensorDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        # Vector only reports voltage and level; the percentage is estimated from the voltage.
        value=_battery("percent"),
    ),
    VectorSensorDescription(
        key="battery_voltage",
        translation_key="battery_voltage",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=_battery("volts"),
    ),
    VectorSensorDescription(
        key="battery_level",
        translation_key="battery_level",
        device_class=SensorDeviceClass.ENUM,
        options=["unknown", "low", "nominal", "full"],
        entity_category=EntityCategory.DIAGNOSTIC,
        value=_battery("level"),
    ),
    VectorSensorDescription(
        key="activity", translation_key="activity", value=lambda s: s.get("activity") or None
    ),
    VectorSensorDescription(
        key="stimulation",
        translation_key="stimulation",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda s: None if s.get("stimulation") is None else round(s["stimulation"] * 100),
    ),
    VectorSensorDescription(
        key="last_face",
        translation_key="last_face",
        value=lambda s: (s.get("last_face") or {}).get("name") or None,
        attrs=_face_seen,
    ),
    VectorSensorDescription(
        key="photos",
        translation_key="photos",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda s: s.get("photos"),
    ),
    VectorSensorDescription(
        key="known_faces",
        translation_key="known_faces",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda s: len(s.get("faces") or []),
        attrs=lambda s: {
            "faces": [{"face_id": f["id"], "name": f["name"]} for f in s.get("faces") or []]
        },
    ),
    VectorSensorDescription(
        key="cube_battery",
        translation_key="cube_battery",
        device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=lambda s: (s.get("cube") or {}).get("battery_volts") or None,
        cube=True,
    ),
    VectorSensorDescription(
        key="alive_time",
        translation_key="alive_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=_stat("Alive.seconds", 1 / 86400),
    ),
    VectorSensorDescription(
        key="petting_time",
        translation_key="petting_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=_stat("Pet.ms", 1 / 60000),
    ),
    VectorSensorDescription(
        key="distance_driven",
        translation_key="distance_driven",
        device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.METERS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        # Odom.Body: 826811017879 after ~4 years of robot life, i.e. nanometers (826 m)
        value=_stat("Odom.Body", 1e-9),
    ),
    VectorSensorDescription(
        key="wake_word_count",
        translation_key="wake_word_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value=_stat("BStat.ReactedToTriggerWord"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    client = entry.runtime_data.client
    entities: list[SensorEntity] = [
        VectorSensor(client, esn, description) for esn in client.robots for description in SENSORS
    ]
    if client.voice_router is not None:
        entities += [
            VectorLastSpeech(client, esn, entry.runtime_data.voice) for esn in client.robots
        ]
    async_add_entities(entities)


class VectorSensor(VectorEntity, SensorEntity):
    """Sensor from the robot state."""

    entity_description: VectorSensorDescription

    def __init__(
        self, client: VectorClient, esn: str, description: VectorSensorDescription
    ) -> None:
        super().__init__(client, esn, description.key)
        self.entity_description = description
        if description.cube:
            self._attr_entity_registry_enabled_default = bool(client.robots[esn].get("cube"))

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.state_data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        return self.entity_description.attrs(self.state_data)
