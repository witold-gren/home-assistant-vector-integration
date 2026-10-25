"""Manual behavior control (up to 10 minutes) and the voice router (Vector → Home Assistant)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VectorConfigEntry
from .api import VectorClient
from .entity import VectorEntity

HOLD_SECONDS = 600

# robot setting (jdoc ROBOT_SETTINGS) -> command; 24 h clock only via wire-pod
SETTING_SWITCHES = (
    ("clock_24_hour", "set_clock_24h"),
    ("dist_is_metric", "update_settings"),
    ("temp_is_fahrenheit", "update_settings"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    client = entry.runtime_data.client
    entities: list[SwitchEntity] = [VectorControlSwitch(client, esn) for esn in client.robots]
    if client.voice_router is not None:
        entities += [VectorVoiceRouterSwitch(client, esn) for esn in client.robots]
        entities += [VectorLLMProxySwitch(client, esn) for esn in client.robots]
    entities += [
        VectorSettingSwitch(client, esn, key, command)
        for esn in client.robots
        for key, command in SETTING_SWITCHES
    ]
    async_add_entities(entities)


class VectorControlSwitch(VectorEntity, SwitchEntity):
    """On: the bridge holds behavior control; off: Vector does what he likes."""

    _attr_translation_key = "hold_control"

    def __init__(self, client: VectorClient, esn: str) -> None:
        super().__init__(client, esn, "hold_control")

    @property
    def is_on(self) -> bool:
        return self.state_data.get("control") == "held"

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._command("hold_control", seconds=HOLD_SECONDS)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._command("release_control")


class VectorVoiceRouterSwitch(VectorEntity, SwitchEntity):
    """On: wire-pod first hands what Vector heard to Assist (ha_router intent)."""

    _attr_translation_key = "voice_router"
    _needs_robot = False

    def __init__(self, client: VectorClient, esn: str) -> None:
        super().__init__(client, esn, "voice_router")

    @property
    def available(self) -> bool:
        return self._bridge.connected and self._bridge.voice_router is not None

    @property
    def is_on(self) -> bool:
        return bool((self._bridge.voice_router or {}).get("enabled"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"hook": (self._bridge.voice_router or {}).get("hook")}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._command("set_voice_router", enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._command("set_voice_router", enabled=False)


class VectorLLMProxySwitch(VectorEntity, SwitchEntity):
    """On: the wire-pod LLM asks an HA agent (wire-pod settings are saved and restored)."""

    _attr_translation_key = "llm_proxy"
    _attr_entity_category = EntityCategory.CONFIG
    _needs_robot = False

    def __init__(self, client: VectorClient, esn: str) -> None:
        super().__init__(client, esn, "llm_proxy")

    @property
    def available(self) -> bool:
        return self._bridge.connected and self._bridge.voice_router is not None

    @property
    def is_on(self) -> bool:
        return bool((self._bridge.voice_router or {}).get("llm"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._command("set_llm_proxy", enabled=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._command("set_llm_proxy", enabled=False)


class VectorSettingSwitch(VectorEntity, SwitchEntity):
    """Yes/no setting from the robot settings."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, client: VectorClient, esn: str, key: str, command: str) -> None:
        super().__init__(client, esn, key)
        self._key = key
        self._cmd = command
        self._attr_translation_key = key

    @property
    def is_on(self) -> bool | None:
        value = (self.state_data.get("settings") or {}).get(self._key)
        return None if value is None else bool(value)

    async def _set(self, on: bool) -> None:
        if self._cmd == "set_clock_24h":
            await self._command("set_clock_24h", on=on)
        else:
            await self._command("update_settings", **{self._key: on})

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)
