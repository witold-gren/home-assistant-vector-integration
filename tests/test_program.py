"""A child's program (Robots Code Studio, add-on 0.3.0+): binary sensor, event entity and bus
events, from hello, state pushes and the program_started / program_ended events."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from .conftest import ESN, FakeBridge, settle
from .test_init import setup

PROGRAM = {"owner": "rcs", "since": 1795428977, "limit": 300}


async def test_no_program(hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry) -> None:
    """An older add-on (no `program` field, no features) shows no program."""
    await setup(hass, entry)
    state = hass.states.get("binary_sensor.vector_program")
    assert state.state == "off"
    assert "owner" not in state.attributes
    assert entry.runtime_data.client.features == set()


async def test_program_from_hello(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    bridge.robots[ESN]["program"] = dict(PROGRAM)
    bridge.features = ["program"]
    await setup(hass, entry)
    state = hass.states.get("binary_sensor.vector_program")
    assert state.state == "on"
    assert state.attributes["owner"] == "rcs"
    assert state.attributes["limit"] == 300
    assert state.attributes["since"].startswith("2026-11-2")
    assert entry.runtime_data.client.features == {"program"}


async def test_program_events(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    await setup(hass, entry)
    started = async_capture_events(hass, "vector_program_started")
    ended = async_capture_events(hass, "vector_program_ended")

    await bridge.event("program_started", {**PROGRAM, "heartbeat": 3})
    await settle(hass)
    # shown at once, without waiting for the next state push
    assert hass.states.get("binary_sensor.vector_program").state == "on"
    assert hass.states.get("binary_sensor.vector_program").attributes["owner"] == "rcs"
    assert started[0].data["owner"] == "rcs" and started[0].data["esn"] == ESN
    assert started[0].data["device_id"] is not None
    event = hass.states.get("event.vector_program")
    assert event.attributes["event_type"] == "program_started"

    await bridge.event(
        "program_ended",
        {"owner": "rcs", "reason": "control_lost", "cause": "cliff", "duration": 12.5},
    )
    await settle(hass)
    assert hass.states.get("binary_sensor.vector_program").state == "off"
    assert ended[0].data["reason"] == "control_lost" and ended[0].data["cause"] == "cliff"
    event = hass.states.get("event.vector_program")
    assert event.attributes["event_type"] == "program_ended"
    assert event.attributes["reason"] == "control_lost"


async def test_program_from_state_push(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    await setup(hass, entry)
    bridge.robots[ESN]["program"] = dict(PROGRAM)
    await bridge.push(ESN)
    await settle(hass)
    assert hass.states.get("binary_sensor.vector_program").state == "on"
    bridge.robots[ESN]["program"] = None
    await bridge.push(ESN)
    await settle(hass)
    assert hass.states.get("binary_sensor.vector_program").state == "off"


async def test_stop_service_during_a_program(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    """The card's STOP calls vector.stop: it goes to the add-on, which ends the program."""
    bridge.robots[ESN]["program"] = dict(PROGRAM)
    await setup(hass, entry)
    await hass.services.async_call("vector", "stop", {}, blocking=True)
    assert bridge.commands[-1]["command"] == "stop"
