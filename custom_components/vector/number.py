"""Head angle and lift height."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import DEGREE, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VectorConfigEntry
from .api import VectorClient
from .entity import VectorEntity


@dataclass(frozen=True, kw_only=True)
class VectorNumberDescription(NumberEntityDescription):
    """State field and bridge command."""

    state_key: str
    command: str
    arg: str


NUMBERS: tuple[VectorNumberDescription, ...] = (
    VectorNumberDescription(
        key="head_angle",
        translation_key="head_angle",
        native_min_value=-22,
        native_max_value=45,
        native_step=1,
        native_unit_of_measurement=DEGREE,
        mode=NumberMode.SLIDER,
        state_key="head_angle",
        command="set_head_angle",
        arg="angle",
    ),
    VectorNumberDescription(
        key="lift_height",
        translation_key="lift_height",
        native_min_value=0,
        native_max_value=100,
        native_step=5,
        native_unit_of_measurement=PERCENTAGE,
        mode=NumberMode.SLIDER,
        state_key="lift_height",
        command="set_lift_height",
        arg="height",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    client = entry.runtime_data.client
    async_add_entities(
        VectorNumber(client, esn, description) for esn in client.robots for description in NUMBERS
    )


class VectorNumber(VectorEntity, NumberEntity):
    """Head or lift position (Vector moves it himself later; the value is the current state)."""

    entity_description: VectorNumberDescription

    def __init__(
        self, client: VectorClient, esn: str, description: VectorNumberDescription
    ) -> None:
        super().__init__(client, esn, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        return self.state_data.get(self.entity_description.state_key)

    async def async_set_native_value(self, value: float) -> None:
        d = self.entity_description
        await self._command(d.command, **{d.arg: value})
