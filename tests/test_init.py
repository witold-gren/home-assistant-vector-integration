"""Entry setup, entities, commands, events and services against the fake bridge."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.vector.const import DOMAIN

from .conftest import ESN, FakeBridge, settle


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_entities(hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry) -> None:
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.vector_battery").state == "78"
    assert hass.states.get("binary_sensor.vector_charging").state == "on"
    assert hass.states.get("binary_sensor.vector_on_charger").state == "on"
    assert hass.states.get("binary_sensor.vector_touched").state == "off"
    assert hass.states.get("sensor.vector_activity").state == "ObservingOnCharger"
    assert hass.states.get("sensor.vector_stimulation").state == "40"
    face = hass.states.get("sensor.vector_last_face")
    assert face.state == "Alice" and face.attributes["face_id"] == 1
    assert hass.states.get("sensor.vector_distance_driven").state == "826.8"
    assert hass.states.get("select.vector_volume").state == "medium_low"
    assert hass.states.get("select.vector_eye_color").state == "lime"
    assert hass.states.get("number.vector_head_angle").state == "21"
    assert hass.states.get("switch.vector_manual_control").state == "off"
    assert hass.states.get("light.vector_eyes").state == "off"
    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, ESN)})
    assert device.sw_version == "2.0.1.6076ep" and device.serial_number == ESN


async def test_state_push_and_robot_offline(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    await setup(hass, entry)
    bridge.robots[ESN]["touched"] = True
    await bridge.push(ESN)
    await settle(hass)
    assert hass.states.get("binary_sensor.vector_touched").state == "on"

    bridge.robots[ESN]["connected"] = False
    await bridge.push(ESN)
    await settle(hass)
    assert hass.states.get("sensor.vector_battery").state == STATE_UNAVAILABLE
    # the robot connection sensor still reports a state
    assert hass.states.get("binary_sensor.vector_connectivity").state == "off"


async def test_commands(hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry) -> None:
    await setup(hass, entry)
    await hass.services.async_call(
        "button", "press", {"entity_id": "button.vector_dance"}, blocking=True
    )
    assert bridge.commands[-1]["command"] == "app_intent"
    assert bridge.commands[-1]["args"] == {"intent": "intent_imperative_dance"}
    assert bridge.commands[-1]["robot"] == ESN

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": "select.vector_volume", "option": "high"},
        blocking=True,
    )
    await settle(hass)
    assert hass.states.get("select.vector_volume").state == "high"

    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.vector_head_angle", "value": 30}, blocking=True
    )
    assert bridge.commands[-1] == {
        "id": bridge.commands[-1]["id"],
        "command": "set_head_angle",
        "args": {"angle": 30.0},
        "robot": ESN,
    }

    await hass.services.async_call(
        "light", "turn_on", {"entity_id": "light.vector_eyes", "hs_color": [180, 50]}, blocking=True
    )
    await settle(hass)
    eyes = hass.states.get("light.vector_eyes")
    assert eyes.state == "on" and tuple(eyes.attributes["hs_color"]) == (180.0, 50.0)
    await hass.services.async_call(
        "light", "turn_off", {"entity_id": "light.vector_eyes"}, blocking=True
    )
    assert bridge.commands[-1]["args"] == {"eye_color": "lime"}

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": "switch.vector_manual_control"}, blocking=True
    )
    assert bridge.commands[-1]["args"] == {"seconds": 600}
    await settle(hass)
    assert hass.states.get("switch.vector_manual_control").state == "on"


async def test_services(hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry) -> None:
    await setup(hass, entry)
    await hass.services.async_call(DOMAIN, "say_text", {"text": "Hello"}, blocking=True)
    assert bridge.commands[-1]["args"] == {"text": "Hello", "engine": "wirepod"}

    await hass.services.async_call(
        DOMAIN, "set_eye_color", {"hue": 90, "saturation": 50}, blocking=True
    )
    assert bridge.commands[-1]["args"] == {"hue": 0.25, "saturation": 0.5}

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, ESN)})
    await hass.services.async_call(
        DOMAIN, "turn", {"device_id": device.id, "angle": 90}, blocking=True
    )
    assert bridge.commands[-1]["command"] == "turn_in_place"
    assert bridge.commands[-1]["args"] == {"angle": 90.0, "speed": 90}

    response = await hass.services.async_call(
        DOMAIN, "list_animations", {"triggers": True}, blocking=True, return_response=True
    )
    assert response == {"animations": ["GreetAfterLongTime", "PounceSuccess"]}

    with pytest.raises(HomeAssistantError, match="robot not connected"):
        await hass.services.async_call(DOMAIN, "say_text", {"text": "fail"}, blocking=True)


async def test_robot_events(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    await setup(hass, entry)
    fired = async_capture_events(hass, "vector_face_seen")
    await bridge.event("face_seen", {"name": "Alice", "face_id": 1})
    await bridge.event("wake_word", {"phase": "begin"})
    await bridge.event("touched")
    await settle(hass)
    assert fired[0].data["name"] == "Alice" and fired[0].data["esn"] == ESN
    assert fired[0].data["device_id"] is not None
    assert hass.states.get("event.vector_face").attributes["event_type"] == "face_seen"
    assert hass.states.get("event.vector_wake_word").attributes["event_type"] == "begin"
    assert hass.states.get("event.vector_interaction").attributes["event_type"] == "touched"


async def test_bridge_reconnect(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    await setup(hass, entry)
    await bridge.drop_clients()
    await settle(hass)
    for _ in range(20):
        await settle(hass)
        if bridge.sockets:
            break
    assert bridge.sockets, "integration did not reconnect"
    assert hass.states.get("sensor.vector_battery").state == "78"
