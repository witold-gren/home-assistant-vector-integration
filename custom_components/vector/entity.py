"""Common entity base: robot device and updates from bridge events."""

from __future__ import annotations

from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .api import RobotState, VectorClient, VectorError
from .const import DOMAIN


class VectorEntity(Entity):
    """Entity of a single robot; state comes from `client.robots[esn]`."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    # The connection sensor is meaningful even when the robot is offline.
    _needs_robot = True

    def __init__(self, client: VectorClient, esn: str, key: str) -> None:
        self._bridge = client
        self._esn = esn
        state = client.robots[esn]
        self._attr_unique_id = f"{esn}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, esn)},
            name=state.get("name") or "Vector",
            manufacturer="Anki / Digital Dream Labs",
            model="Vector",
            sw_version=state.get("firmware"),
            serial_number=esn,
        )

    @property
    def state_data(self) -> RobotState:
        """Last robot state from the bridge."""
        return self._bridge.robots.get(self._esn, {})

    @property
    def available(self) -> bool:
        if not (self._bridge.connected and self._esn in self._bridge.robots):
            return False
        return not self._needs_robot or bool(self.state_data.get("connected"))

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._bridge.add_listener(self.async_write_ha_state))

    async def _command(self, command: str, **args: Any) -> Any:
        try:
            return await self._bridge.command(command, self._esn, **args)
        except VectorError as err:
            raise HomeAssistantError(f"Vector: {err}") from err
