"""Stand still (add-on 0.5.0+): the switch keeps Vector still between programs."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import ESN, FakeBridge, settle
from .test_init import setup

ENTITY = "switch.vector_stand_still"


async def test_unavailable_on_an_older_add_on(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    """No `stay_still` in hello.features: the switch exists but is unavailable."""
    bridge.features = ["program"]
    await setup(hass, entry)
    assert hass.states.get(ENTITY).state == "unavailable"


async def test_switch_turns_stand_still_on_and_off(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    bridge.features = ["program", "stay_still"]
    await setup(hass, entry)
    state = hass.states.get(ENTITY)
    assert state.state == "off"
    assert state.name == "Vector Stand still"

    await hass.services.async_call("switch", "turn_on", {"entity_id": ENTITY}, blocking=True)
    assert bridge.commands[-1]["command"] == "stay_still"
    assert bridge.commands[-1]["args"] == {"on": True}
    await settle(hass)
    assert hass.states.get(ENTITY).state == "on"

    await hass.services.async_call("switch", "turn_off", {"entity_id": ENTITY}, blocking=True)
    assert bridge.commands[-1]["args"] == {"on": False}
    await settle(hass)
    assert hass.states.get(ENTITY).state == "off"


async def test_state_follows_the_add_on(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry
) -> None:
    """The add-on switches it itself (a studio program, battery low, timeout): state pushes."""
    bridge.features = ["program", "stay_still"]
    await setup(hass, entry)
    bridge.robots[ESN]["stay_still"] = True
    await bridge.push(ESN)
    await settle(hass)
    assert hass.states.get(ENTITY).state == "on"
    bridge.robots[ESN]["stay_still"] = False
    await bridge.push(ESN)
    await settle(hass)
    assert hass.states.get(ENTITY).state == "off"


async def test_refused_by_the_add_on(
    hass: HomeAssistant, bridge: FakeBridge, entry: MockConfigEntry, monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge.features = ["program", "stay_still"]
    await setup(hass, entry)
    original = bridge._handle

    async def refuse(req):
        if req["command"] == "stay_still":
            return {"type": "result", "id": req["id"], "success": False, "error": "battery low"}
        return await original(req)

    monkeypatch.setattr(bridge, "_handle", refuse)
    with pytest.raises(HomeAssistantError, match="battery low"):
        await hass.services.async_call("switch", "turn_on", {"entity_id": ENTITY}, blocking=True)
