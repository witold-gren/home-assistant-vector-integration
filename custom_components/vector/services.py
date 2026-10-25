"""vector.* services: speech, animations, intents, movement and eyes."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.util import dt as dt_util
import voluptuous as vol

from .api import VectorClient, VectorError
from .const import DOMAIN
from .speak import speak

ROBOT = {vol.Optional(ATTR_DEVICE_ID): cv.string}
LOOPS = vol.All(vol.Coerce(int), vol.Range(min=1, max=10))

# service -> (schema, bridge command)
SERVICES: dict[str, tuple[vol.Schema, str]] = {
    "say_text": (
        vol.Schema(
            {
                **ROBOT,
                vol.Required("text"): cv.string,
                # default: from options; wirepod: its TTS (e.g. Piper via Wyoming); tts: HA TTS
                # engine through the robot speaker; vector: built-in, English
                vol.Optional("engine", default="default"): vol.In(
                    ["default", "wirepod", "tts", "vector"]
                ),
                vol.Optional("speed", default=1.0): vol.All(
                    vol.Coerce(float), vol.Range(min=0.5, max=2)
                ),
            }
        ),
        "say_text",
    ),
    "play_animation": (
        vol.Schema(
            {**ROBOT, vol.Required("name"): cv.string, vol.Optional("loops", default=1): LOOPS}
        ),
        "play_animation",
    ),
    "play_animation_trigger": (
        vol.Schema(
            {**ROBOT, vol.Required("name"): cv.string, vol.Optional("loops", default=1): LOOPS}
        ),
        "play_animation_trigger",
    ),
    "run_intent": (
        vol.Schema(
            {
                **ROBOT,
                vol.Required("intent"): cv.string,
                vol.Optional("param", default=""): cv.string,
            }
        ),
        "app_intent",
    ),
    "drive_straight": (
        vol.Schema(
            {
                **ROBOT,
                vol.Required("distance"): vol.All(
                    vol.Coerce(float), vol.Range(min=-1000, max=1000)
                ),
                vol.Optional("speed", default=100): vol.All(
                    vol.Coerce(float), vol.Range(min=10, max=200)
                ),
            }
        ),
        "drive_straight",
    ),
    "turn": (
        vol.Schema(
            {
                **ROBOT,
                vol.Required("angle"): vol.All(vol.Coerce(float), vol.Range(min=-360, max=360)),
                vol.Optional("speed", default=90): vol.All(
                    vol.Coerce(float), vol.Range(min=10, max=360)
                ),
            }
        ),
        "turn_in_place",
    ),
    "drive_wheels": (
        vol.Schema(
            {
                **ROBOT,
                vol.Required("left"): vol.All(vol.Coerce(float), vol.Range(min=-220, max=220)),
                vol.Required("right"): vol.All(vol.Coerce(float), vol.Range(min=-220, max=220)),
                vol.Optional("duration", default=1): vol.All(
                    vol.Coerce(float), vol.Range(min=0.1, max=10)
                ),
            }
        ),
        "drive_wheels",
    ),
    "set_eye_color": (
        vol.Schema(
            {
                **ROBOT,
                vol.Required("hue"): vol.All(vol.Coerce(float), vol.Range(min=0, max=360)),
                vol.Optional("saturation", default=100): vol.All(
                    vol.Coerce(float), vol.Range(min=0, max=100)
                ),
            }
        ),
        "set_eye_color",
    ),
    "stop": (vol.Schema(ROBOT), "stop"),
    "rename_face": (
        vol.Schema(
            {**ROBOT, vol.Required("face_id"): vol.Coerce(int), vol.Required("name"): cv.string}
        ),
        "rename_face",
    ),
    "delete_face": (vol.Schema({**ROBOT, vol.Required("face_id"): vol.Coerce(int)}), "delete_face"),
    "enroll_face": (vol.Schema({**ROBOT, vol.Required("name"): cv.string}), "enroll_face"),
    "go_to": (
        vol.Schema(
            {
                **ROBOT,
                vol.Optional("x", default=0): vol.All(
                    vol.Coerce(float), vol.Range(min=-2000, max=2000)
                ),
                vol.Optional("y", default=0): vol.All(
                    vol.Coerce(float), vol.Range(min=-2000, max=2000)
                ),
                vol.Optional("angle", default=0): vol.All(
                    vol.Coerce(float), vol.Range(min=-360, max=360)
                ),
                vol.Optional("relative", default=True): cv.boolean,
            }
        ),
        "go_to",
    ),
    "turn_towards_face": (
        vol.Schema({**ROBOT, vol.Optional("face_id", default=-1): vol.Coerce(int)}),
        "turn_towards_face",
    ),
    "go_to_cube": (
        vol.Schema(
            {
                **ROBOT,
                vol.Optional("distance", default=70): vol.All(
                    vol.Coerce(float), vol.Range(min=40, max=500)
                ),
            }
        ),
        "go_to_cube",
    ),
    # hold-to-drive: the card repeats every ~300 ms, the robot stops 0.7 s after the last call
    "move": (
        vol.Schema(
            {
                **ROBOT,
                vol.Optional("left", default=0): vol.All(
                    vol.Coerce(float), vol.Range(min=-220, max=220)
                ),
                vol.Optional("right", default=0): vol.All(
                    vol.Coerce(float), vol.Range(min=-220, max=220)
                ),
                vol.Optional("head", default=0): vol.All(
                    vol.Coerce(float), vol.Range(min=-2, max=2)
                ),
                vol.Optional("lift", default=0): vol.All(
                    vol.Coerce(float), vol.Range(min=-2, max=2)
                ),
            }
        ),
        "move",
    ),
}

LIST_ANIMATIONS_SCHEMA = vol.Schema({**ROBOT, vol.Optional("triggers", default=False): cv.boolean})
DELETE_PHOTO_SCHEMA = vol.Schema({**ROBOT, vol.Required("photo_id"): vol.Coerce(int)})


def _robot(hass: HomeAssistant, device_id: str | None) -> tuple[VectorClient, str]:
    """Client and robot ESN from `device_id`, or the only robot without it."""
    clients = [
        entry.runtime_data.client
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]
    if device_id:
        device = dr.async_get(hass).async_get(device_id)
        esn = next((i[1] for i in device.identifiers if i[0] == DOMAIN), None) if device else None
        for client in clients:
            if esn in client.robots:
                return client, esn
        raise ServiceValidationError(f"{device_id} is not a Vector robot")
    robots = [(client, esn) for client in clients for esn in client.robots]
    if len(robots) != 1:
        raise ServiceValidationError("device_id is required when there is not exactly one robot")
    return robots[0]


def _entry_for(hass: HomeAssistant, client: VectorClient):
    """Config entry owning the client (voice options)."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.state is ConfigEntryState.LOADED and entry.runtime_data.client is client:
            return entry
    raise ServiceValidationError("Vector entry not loaded")


def _args(service: str, data: dict[str, Any]) -> dict[str, Any]:
    args = {k: v for k, v in data.items() if k != ATTR_DEVICE_ID}
    if service == "set_eye_color":
        # HA: hue 0–360°, saturation 0–100 %; Vector: 0–1
        args = {"hue": args["hue"] / 360, "saturation": args["saturation"] / 100}
    return args


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the domain services."""

    async def _call(call: ServiceCall) -> None:
        _, command = SERVICES[call.service]
        client, esn = _robot(hass, call.data.get(ATTR_DEVICE_ID))
        if call.service == "say_text":
            engine = call.data["engine"]
            try:
                await speak(
                    hass,
                    _entry_for(hass, client),
                    client,
                    esn,
                    call.data["text"],
                    None if engine == "default" else engine,
                )
            except VectorError as err:
                raise HomeAssistantError(f"Vector: {err}") from err
            return
        try:
            await client.command(command, esn, **_args(call.service, dict(call.data)))
        except VectorError as err:
            raise HomeAssistantError(f"Vector: {err}") from err

    async def _list_animations(call: ServiceCall) -> ServiceResponse:
        client, esn = _robot(hass, call.data.get(ATTR_DEVICE_ID))
        command = "list_animation_triggers" if call.data["triggers"] else "list_animations"
        try:
            names = await client.command(command, esn)
        except VectorError as err:
            raise HomeAssistantError(f"Vector: {err}") from err
        return {"animations": names or []}

    async def _list_faces(call: ServiceCall) -> ServiceResponse:
        client, esn = _robot(hass, call.data.get(ATTR_DEVICE_ID))
        try:
            faces = await client.command("list_faces", esn)
        except VectorError as err:
            raise HomeAssistantError(f"Vector: {err}") from err
        return {
            "faces": [
                {
                    "face_id": f["id"],
                    "name": f["name"],
                    "last_seen": dt_util.utc_from_timestamp(f["last_seen"]).isoformat()
                    if f.get("last_seen")
                    else None,
                }
                for f in faces or []
            ]
        }

    hass.services.async_register(
        DOMAIN,
        "list_faces",
        _list_faces,
        schema=vol.Schema(ROBOT),
        supports_response=SupportsResponse.ONLY,
    )

    async def _list_photos(call: ServiceCall) -> ServiceResponse:
        client, esn = _robot(hass, call.data.get(ATTR_DEVICE_ID))
        try:
            photos = await client.command("list_photos", esn)
        except VectorError as err:
            raise HomeAssistantError(f"Vector: {err}") from err
        return {
            "photos": [
                {"photo_id": p["id"], "taken": dt_util.utc_from_timestamp(p["at"]).isoformat()}
                for p in photos or []
            ]
        }

    async def _delete_photo(call: ServiceCall) -> None:
        client, esn = _robot(hass, call.data.get(ATTR_DEVICE_ID))
        try:
            await client.command("delete_photo", esn, id=call.data["photo_id"])
        except VectorError as err:
            raise HomeAssistantError(f"Vector: {err}") from err

    hass.services.async_register(
        DOMAIN,
        "list_photos",
        _list_photos,
        schema=vol.Schema(ROBOT),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(DOMAIN, "delete_photo", _delete_photo, schema=DELETE_PHOTO_SCHEMA)
    for service, (schema, _) in SERVICES.items():
        hass.services.async_register(DOMAIN, service, _call, schema=schema)
    hass.services.async_register(
        DOMAIN,
        "list_animations",
        _list_animations,
        schema=LIST_ANIMATIONS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
