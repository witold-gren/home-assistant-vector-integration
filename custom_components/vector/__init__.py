"""Vector: the Anki Vector robot via the vector-bridge add-on (wire-pod) and its WebSocket API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import VectorAuthError, VectorClient, VectorError
from .const import BRIDGE_EVENTS, DOMAIN
from .frontend import async_register_card
from .services import async_setup_services
from .views import VectorPhotoView
from .voice import VoiceRouter

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CAMERA,
    Platform.EVENT,
    Platform.IMAGE,
    Platform.LIGHT,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


@dataclass
class VectorData:
    """Entry data stored in runtime_data."""

    client: VectorClient
    voice: VoiceRouter


type VectorConfigEntry = ConfigEntry[VectorData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Domain services (they act on the robot selected by device)."""
    async_setup_services(hass)
    hass.http.register_view(VectorPhotoView(hass))
    await async_register_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: VectorConfigEntry) -> bool:
    """Connect to the bridge and create entities for the robots in its hello."""
    client = VectorClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data.get(CONF_TOKEN),
    )
    try:
        await client.connect()
    except VectorAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except VectorError as err:
        raise ConfigEntryNotReady(str(err)) from err
    voice = VoiceRouter(hass, entry, client)
    entry.runtime_data = VectorData(client, voice)
    entry.async_on_unload(client.close)
    entry.async_on_unload(client.add_event_listener(voice.on_event))
    # option changes (Assist agent, answers) apply at once: VoiceRouter reads entry.options

    # New robot in wire-pod: the entry reloads and the entities are recreated.
    esns = set(client.robots)

    @callback
    def _check_robots() -> None:
        if client.connected and set(client.robots) != esns:
            hass.config_entries.async_schedule_reload(entry.entry_id)

    entry.async_on_unload(client.add_listener(_check_robots))

    # Robot events on the HA bus: vector_touched, vector_face_seen, vector_wake_word…
    registry = dr.async_get(hass)

    @callback
    def _fire(esn: str, event: str, data: dict[str, Any]) -> None:
        if event not in BRIDGE_EVENTS:
            return
        device = registry.async_get_device(identifiers={(DOMAIN, esn)})
        hass.bus.async_fire(
            f"{DOMAIN}_{event}",
            {"esn": esn, "device_id": device.id if device else None, **data},
        )

    entry.async_on_unload(client.add_event_listener(_fire))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VectorConfigEntry) -> bool:
    """Unload platforms; the client is closed via async_on_unload."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
