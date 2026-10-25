"""Volume, eye color, language and back button (settings), plus an animation to play."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import VectorConfigEntry
from .api import VectorClient, VectorError
from .const import EYE_COLORS, VOLUMES
from .entity import VectorEntity

# robot languages (his own answers, weather, units); speech recognition is done by wire-pod
LOCALES = ["en-US", "en-GB", "en-AU", "de-DE", "fr-FR", "ja-JP"]
WAKEWORDS = ["hey_vector", "alexa"]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VectorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    client = entry.runtime_data.client
    async_add_entities(
        entity
        for esn in client.robots
        for entity in (
            VectorSettingSelect(client, esn, "master_volume", VOLUMES),
            VectorSettingSelect(client, esn, "eye_color", EYE_COLORS),
            VectorNamedSettingSelect(client, esn, "locale", LOCALES),
            VectorWakewordSelect(client, esn),
            VectorAnimationSelect(client, esn),
        )
    )


class VectorSettingSelect(VectorEntity, SelectEntity):
    """Setting from a list; Vector stores it as an index."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, client: VectorClient, esn: str, key: str, options: list[str]) -> None:
        super().__init__(client, esn, key)
        self._key = key
        self._attr_translation_key = key
        self._attr_options = options

    @property
    def current_option(self) -> str | None:
        value = (self.state_data.get("settings") or {}).get(self._key)
        if isinstance(value, int | float) and 0 <= int(value) < len(self._attr_options):
            return self._attr_options[int(value)]
        return None

    async def async_select_option(self, option: str) -> None:
        await self._command("update_settings", **{self._key: option})


class VectorNamedSettingSelect(VectorEntity, SelectEntity):
    """Setting stored on the robot as text (e.g. locale)."""

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, client: VectorClient, esn: str, key: str, options: list[str]) -> None:
        super().__init__(client, esn, key)
        self._key = key
        self._attr_translation_key = key
        self._attr_options = options

    @property
    def current_option(self) -> str | None:
        value = (self.state_data.get("settings") or {}).get(self._key)
        return value if value in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        await self._command("update_settings", **{self._key: option})


class VectorWakewordSelect(VectorEntity, SelectEntity):
    """What the back button does: "Hey Vector" or Alexa."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "button_wakeword"
    _attr_options = WAKEWORDS

    def __init__(self, client: VectorClient, esn: str) -> None:
        super().__init__(client, esn, "button_wakeword")

    @property
    def current_option(self) -> str | None:
        value = (self.state_data.get("settings") or {}).get("button_wakeword")
        return None if value is None else WAKEWORDS[1 if value == 1 else 0]

    async def async_select_option(self, option: str) -> None:
        await self._command("update_settings", button_wakeword=option)


class VectorAnimationSelect(VectorEntity, SelectEntity):
    """Selecting an animation group from the robot list plays it (list loaded on connect)."""

    _attr_translation_key = "animation"

    def __init__(self, client: VectorClient, esn: str) -> None:
        super().__init__(client, esn, "animation")
        self._attr_options: list[str] = []
        self._attr_current_option = None

    @property
    def available(self) -> bool:
        return super().available and bool(self._attr_options)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._bridge.add_listener(self._maybe_load))
        self._maybe_load()

    def _maybe_load(self) -> None:
        if self._attr_options or getattr(self, "_loading", False) or not super().available:
            return
        self._loading = True
        self.hass.async_create_task(self._load())

    async def _load(self) -> None:
        try:
            names = await self._bridge.command("list_animation_triggers", self._esn)
            self._attr_options = sorted(names or [])
            self.async_write_ha_state()
        except VectorError:
            pass
        finally:
            self._loading = False

    async def async_select_option(self, option: str) -> None:
        self._attr_current_option = option
        self.async_write_ha_state()
        await self._command("play_animation_trigger", name=option)
