"""vector-control-card in Chrome: placeholder instead of a broken image, live view on demand, the
full-screen control view, and the robot never left driving."""

from __future__ import annotations


def _text(page, selector: str) -> str:
    return " ".join(page.locator(selector).inner_text().split())


def _calls(page, service: str | None = None) -> list[dict]:
    calls = page.evaluate("window.calls")
    return [c for c in calls if service is None or c["service"] == service]


def _moves(page) -> list[dict]:
    return [c["data"] for c in _calls(page, "move")]


def _center(page, selector: str) -> tuple[float, float]:
    target = page.locator(selector).first
    target.scroll_into_view_if_needed()
    box = target.bounding_box()
    assert box, selector
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def _press(page, selector: str) -> None:
    x, y = _center(page, selector)
    page.mouse.move(x, y)
    page.mouse.down()


def _open_fullscreen(page) -> None:
    page.locator(".cam .full").click()
    page.wait_for_selector("div.vector-fs-host", state="attached")


def _assert_stopped(page) -> None:
    """The last move call is a stop (empty move) and nothing keeps driving afterwards."""
    page.wait_for_timeout(350)
    moves = _calls(page, "move")
    assert moves and moves[-1]["data"] == {"device_id": "dev-vector"}, moves[-3:]
    stop_at = moves[-1]["t"]
    page.wait_for_timeout(700)  # > 2 repeat periods (300 ms)
    assert [c for c in _calls(page, "move") if c["t"] > stop_at] == []


def _hide_page(page) -> None:
    page.evaluate(
        """() => {
          Object.defineProperty(document, 'visibilityState', {value: 'hidden', configurable: true});
          Object.defineProperty(document, 'hidden', {value: true, configurable: true});
          document.dispatchEvent(new Event('visibilitychange'));
        }"""
    )


# --- tile ---------------------------------------------------------------------------------------


def test_offline_robot_shows_a_message_not_a_broken_image(open_card) -> None:
    page = open_card("offline=1")
    cam = page.locator(".cam")
    assert "Vector jest niedostępny" in cam.inner_text()
    assert page.locator(".cam .still").is_hidden()  # no broken-image icon over the text
    assert page.locator(".cam .play").is_hidden()
    status = _text(page, ".status")
    assert "unavailable" not in status and "Bateria —" in status
    # controls are disabled: pressing forward sends nothing
    page.locator('.dpad button[data-drive="fwd"]').dispatch_event("pointerdown")
    page.wait_for_timeout(400)
    assert _moves(page) == []


def test_available_robot_shows_the_preview_placeholder(page) -> None:
    assert "Podgląd z kamery jest wyłączony" in page.locator(".cam").inner_text()
    assert page.locator(".cam .play").is_visible()
    assert page.locator(".cam .still").is_hidden()  # no cached frame (404): placeholder stays
    assert _text(page, ".status") == "Bateria 87 % · Robi: Exploring · poza ładowarką"
    assert page.evaluate("window.streams") == 0  # the camera does not start by itself


def test_play_starts_the_live_stream_and_close_stops_it(page) -> None:
    page.locator(".cam .play").click()
    page.wait_for_function("window.streams === 1")
    live = page.locator(".cam ha-camera-stream")
    assert live.get_attribute("fit-mode") == "cover"
    assert page.locator(".cam .close").is_visible()
    page.locator(".cam .close").click()
    assert page.locator(".cam ha-camera-stream").count() == 0
    assert page.locator(".cam .play").is_visible()


def test_without_stream_the_card_falls_back_to_mjpeg(open_card) -> None:
    page = open_card("stream=0")
    page.locator(".cam .play").click()
    # the MJPEG request fails in the harness: a retry message instead of a broken image
    page.wait_for_function(
        "document.querySelector('vector-control-card').shadowRoot"
        ".querySelector('.cam .ph button') !== null"
    )
    assert "Kamera nie odpowiada" in page.locator(".cam").inner_text()
    assert page.evaluate("window.streams") == 0


def test_hold_to_drive_then_release_stops(page) -> None:
    _press(page, '.dpad button[data-drive="fwd"]')
    page.wait_for_timeout(700)
    moves = _moves(page)
    assert len(moves) >= 2 and moves[-1]["left"] == 120 and moves[-1]["right"] == 120
    page.mouse.up()
    _assert_stopped(page)


def test_hidden_page_mid_drive_stops_the_robot_and_the_live_view(page) -> None:
    page.locator(".cam .play").click()
    page.wait_for_function("window.streams === 1")
    _press(page, '.dpad button[data-drive="left"]')
    page.wait_for_timeout(350)
    _hide_page(page)
    _assert_stopped(page)
    assert page.locator(".cam ha-camera-stream").count() == 0
    page.mouse.up()


def test_rebuilding_the_card_mid_drive_stops_the_robot(page) -> None:
    _press(page, '.dpad button[data-drive="back"]')
    page.wait_for_timeout(350)
    page.evaluate("card.setConfig({type: 'custom:vector-control-card', camera: 'camera.vector'})")
    _assert_stopped(page)
    page.mouse.up()


# --- full screen --------------------------------------------------------------------------------


def test_fullscreen_covers_the_screen_and_back_removes_it(page) -> None:
    _open_fullscreen(page)
    box = page.locator("div.vector-fs-host").bounding_box()
    assert box == {"x": 0, "y": 0, "width": 874, "height": 402}
    assert page.locator("#fs-play").is_visible()
    page.locator("#fs-back").click()
    assert page.locator("div.vector-fs-host").count() == 0


def test_fullscreen_layout_pad_left_lift_and_listen_right(page) -> None:
    _open_fullscreen(page)
    pad = page.locator(".fs-pad").bounding_box()
    rail = page.locator(".fs-rail").bounding_box()
    bottom = page.locator(".fs-bottom").bounding_box()
    assert pad["x"] < 874 * 0.3 and rail["x"] > 874 * 0.8
    assert pad["y"] >= 0 and pad["y"] + pad["height"] <= 402
    assert rail["y"] >= 0 and rail["y"] + rail["height"] <= 402
    assert bottom["y"] + bottom["height"] <= 402
    # nothing overlaps: pad and the bottom pill are apart
    assert pad["x"] + pad["width"] < bottom["x"] or pad["y"] + pad["height"] < bottom["y"]
    assert page.locator('.fs-pills button[data-lift="1"]').is_visible()
    assert page.locator(".fs-rail #fs-talk").is_visible()


def test_fullscreen_head_and_lift_side_by_side_at_mid_height(page) -> None:
    """One right thumb reaches both: the head and lift pills sit next to each other, centred
    vertically (asked for the iPad; the same layout fits the phone)."""
    _open_fullscreen(page)
    head = page.locator('.fs-pills button[data-head="1"]').bounding_box()
    lift = page.locator('.fs-pills button[data-lift="1"]').bounding_box()
    pills = page.locator(".fs-pills").bounding_box()
    talk = page.locator("#fs-talk").bounding_box()
    assert abs(head["y"] - lift["y"]) < 2  # same row
    assert head["x"] + head["width"] < lift["x"]  # head left of lift
    middle = pills["y"] + pills["height"] / 2
    assert abs(middle - 402 / 2) < 12
    assert talk["y"] + talk["height"] < pills["y"]  # the mic stays above them
    assert pills["x"] + pills["width"] <= 874


def test_fullscreen_lift_hold_and_closing_mid_drive_stops(page) -> None:
    _open_fullscreen(page)
    _press(page, '.fs-pills button[data-lift="1"]')
    page.wait_for_timeout(400)
    assert _moves(page)[-1]["lift"] == 1.5
    page.mouse.up()
    _assert_stopped(page)

    _press(page, '.fs-pad button[data-drive="right"]')
    page.wait_for_timeout(350)
    page.evaluate("card._closeFull()")  # "back" tapped with the other hand
    _assert_stopped(page)
    page.mouse.up()


def test_fullscreen_speed_and_charger_buttons(page) -> None:
    _open_fullscreen(page)
    page.locator('.fs-bottom button[data-speed="fast"]').click()
    assert "on" in page.locator('.fs-bottom button[data-speed="fast"]').get_attribute("class")
    page.locator('.fs-bottom button[data-press="drive_on_charger"]').click()
    presses = _calls(page, "press")
    assert presses[-1]["data"] == {"entity_id": "button.vector_go_to_charger"}
    _press(page, '.fs-pad button[data-drive="fwd"]')
    page.wait_for_timeout(200)
    assert _moves(page)[-1]["left"] == 192  # 120 mm/s × 1.6 (fast)
    page.mouse.up()


def test_fullscreen_offline_shows_the_message_and_no_play(open_card) -> None:
    page = open_card("offline=1")
    _open_fullscreen(page)
    assert page.locator(".fs-off").is_visible()
    assert page.locator("#fs-play").is_hidden()


def test_portrait_asks_to_rotate(open_card) -> None:
    page = open_card(viewport={"width": 402, "height": 874})
    _open_fullscreen(page)
    assert page.locator(".fs-rotate").is_visible()
    assert page.locator(".fs-pad").is_hidden()


def test_removing_the_card_removes_the_fullscreen_view(page) -> None:
    _open_fullscreen(page)
    page.evaluate("card.remove()")
    assert page.locator("div.vector-fs-host").count() == 0


TILE = "document.querySelector('vector-control-card').shadowRoot"


def _video_ready(page, root: str) -> None:
    page.evaluate(
        f"""() => {{
          const v = {root}.querySelector('ha-camera-stream').shadowRoot.querySelector('video');
          Object.defineProperty(v, 'readyState', {{value: 4}});
          Object.defineProperty(v, 'videoWidth', {{value: 800}});
        }}"""
    )


def test_loader_until_the_first_frame(page) -> None:
    page.locator(".cam .play").click()
    page.wait_for_function("window.streams === 1")
    assert page.locator(".cam .cam-load").is_visible()
    _video_ready(page, TILE)
    page.wait_for_function(f"!{TILE}.querySelector('.cam-load').classList.contains('show')")


def test_control_is_taken_only_while_steering(page) -> None:
    """Not on opening the card any more: the full screen takes it, closing gives it back."""
    assert [c for c in _calls(page) if c["domain"] == "switch"] == []
    _open_fullscreen(page)
    sw = [c for c in _calls(page) if c["domain"] == "switch"]
    assert sw[-1]["service"] == "turn_on"
    page.locator("#fs-back").click()
    sw = [c for c in _calls(page) if c["domain"] == "switch"]
    assert sw[-1]["service"] == "turn_off"


def test_tile_drive_takes_control(page) -> None:
    _press(page, '.dpad button[data-drive="left"]')
    page.wait_for_timeout(200)
    page.mouse.up()
    sw = [c["service"] for c in _calls(page) if c["domain"] == "switch"]
    assert "turn_on" in sw


def test_forward_on_the_charger_asks_once(page) -> None:
    """Every tap used to send drive_off_charger: a stack of BEHAVIOR_WONT_ACTIVATE errors."""
    page.evaluate(
        """() => {
          hass.states['binary_sensor.vector_on_charger'].state = 'on';
          card.hass = hass;
        }"""
    )
    for _ in range(4):
        page.locator('.dpad button[data-drive="fwd"]').dispatch_event("pointerdown")
        page.locator('.dpad button[data-drive="fwd"]').dispatch_event("pointerup")
    presses = [c for c in _calls(page, "press")]
    assert len(presses) == 1
    assert presses[0]["data"] == {"entity_id": "button.vector_drive_off_charger"}
    assert "zjeżdża" in page.locator(".cam-toast").inner_text()


def test_fullscreen_lives_inside_home_assistant_when_present(page) -> None:
    page.evaluate(
        """() => {
          const ha = document.createElement('home-assistant');
          ha.attachShadow({mode: 'open'});
          document.body.appendChild(ha);
        }"""
    )
    page.locator(".cam .full").click()
    assert page.evaluate(
        "!!document.querySelector('home-assistant').shadowRoot.querySelector('.vector-fs-host')"
    )


def _hold_talk(page, selector: str) -> None:
    btn = page.locator(selector)
    btn.scroll_into_view_if_needed()
    box = btn.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()


def test_tile_talk_sends_the_recording_to_the_robot(page) -> None:
    """Vector's SDK has no real microphone feed (1 kHz test tone), so the card talks instead."""
    _hold_talk(page, ".actions .talk")
    page.wait_for_function("window.micGrants.length === 1")
    page.evaluate("window.micGrants[0]()")
    page.wait_for_function("window.recorders === 1")
    page.mouse.up()
    page.wait_for_function("window.fetches.length === 1")
    sent = page.evaluate("window.fetches[0]")
    assert sent == {"url": "/api/vector/intercom/camera.vector", "type": "audio/mp4"}
    page.wait_for_function(f"{TILE}.querySelector('.cam-toast').textContent.includes('mówi')")


def test_fullscreen_talk_button_and_release_before_permission(page) -> None:
    _open_fullscreen(page)
    _hold_talk(page, "#fs-talk")
    page.wait_for_function("window.micGrants.length === 1")
    page.mouse.up()  # released before the permission prompt was answered
    page.evaluate("window.micGrants[0]()")
    page.wait_for_timeout(100)
    assert page.evaluate("window.recorders") == 0
    assert page.evaluate("window.stoppedTracks") == 1
    assert page.evaluate("window.fetches.length") == 0


def _fs_bg(page) -> str:
    return page.evaluate(
        "document.querySelector('.vector-fs-host').shadowRoot.getElementById('fs-still')"
        ".style.backgroundImage"
    )


def test_fullscreen_background_is_the_last_frame_when_available(page) -> None:
    """Available: the "Last frame" image kept in HA is the background, and the play button says
    the same as the small card (user, 2026-11-22)."""
    _open_fullscreen(page)
    assert "/last-frame.jpg" in _fs_bg(page)
    text = " ".join(page.locator("#fs-play").inner_text().split())
    assert "Podgląd z kamery jest wyłączony" in text
    assert "Dotknij ▶, aby oglądać na żywo" in text


def test_fullscreen_offline_has_no_background_only_the_message(open_card) -> None:
    page = open_card("offline=1")
    _open_fullscreen(page)
    assert _fs_bg(page) in ("none", "")
    assert page.locator(".fs-off").is_visible()
    assert page.locator("#fs-play").is_hidden()


def test_live_frame_is_sent_to_home_assistant(page) -> None:
    _open_fullscreen(page)
    page.evaluate(
        """() => {
          const v = document.createElement('video');
          Object.defineProperty(v, 'videoWidth', {value: 320});
          Object.defineProperty(v, 'videoHeight', {value: 240});
          const host = document.createElement('div');
          host.appendChild(v);
          card._rememberFrame(host);
        }"""
    )
    page.wait_for_function(
        "window.fetches.some(f => f.url === '/api/vector/last_frame/camera.vector'"
        " && f.type === 'image/jpeg')",
        timeout=3000,
    )


# --- child's program (Robots Code Studio, add-on 0.3.0+) ---------------------------------------


def _set_program(page, on: bool) -> None:
    """The add-on reports a program starting / ending: the binary sensor changes."""
    page.evaluate(
        """(on) => {
          const id = 'binary_sensor.vector_program';
          const sensor = {entity_id: id, state: on ? 'on' : 'off', attributes: {}};
          const states = Object.assign({}, window.hass.states, {[id]: sensor});
          window.hass = Object.assign({}, window.hass, {states});
          window.card.hass = window.hass;
        }""",
        on,
    )


def test_program_greys_out_controls_but_stop_ends_it(open_card) -> None:
    page = open_card("program=1")
    banner = page.locator("ha-card .prog")
    assert banner.is_visible() and "Program dziecka działa" in banner.inner_text()
    # driving, head, Hold and the action buttons do nothing
    for selector in (
        '.dpad button[data-drive="fwd"]',
        'button[data-head="1"]',
        'button[data-lift="-1"]',
    ):
        page.locator(selector).dispatch_event("pointerdown")
    page.wait_for_timeout(400)
    assert _moves(page) == []
    assert page.locator(".speed").evaluate("e => getComputedStyle(e).pointerEvents") == "none"
    assert page.locator(".actions").evaluate("e => getComputedStyle(e).pointerEvents") == "none"
    assert _calls(page, "turn_on") == []  # no hold taken
    # STOP is still live and ends the program
    stop = page.locator(".dpad button.stop")
    assert stop.evaluate("e => getComputedStyle(e).pointerEvents") != "none"
    stop.click()
    assert [c["data"] for c in _calls(page, "stop")] == [{"device_id": "dev-vector"}]


def test_program_starting_stops_our_driving(page) -> None:
    assert page.locator("ha-card .prog").is_hidden()
    _press(page, '.dpad button[data-drive="fwd"]')
    page.wait_for_timeout(400)
    assert _moves(page), "driving started"
    _set_program(page, True)
    # the repeat stops at once (no final empty move: the add-on refuses it during a program and
    # stopped the card's driving itself when the program began)
    page.wait_for_timeout(50)
    count = len(_moves(page))
    page.wait_for_timeout(700)
    page.mouse.up()
    page.wait_for_timeout(100)
    assert len(_moves(page)) == count
    assert page.locator("ha-card .prog").is_visible()
    # the hold the card took is forgotten: no renewals, nothing sent on its behalf
    before = len(_calls(page, "turn_on"))
    page.locator('.dpad button[data-drive="fwd"]').dispatch_event("pointerdown")
    page.wait_for_timeout(400)
    assert len(_calls(page, "turn_on")) == before
    _set_program(page, False)
    assert page.locator("ha-card .prog").is_hidden()


def test_program_in_full_screen(open_card) -> None:
    page = open_card("program=1")
    _open_fullscreen(page)
    fs = page.locator("div.vector-fs-host .fs")
    assert "program" in (fs.get_attribute("class") or "")
    banner = page.locator("div.vector-fs-host .fs-prog")
    assert banner.is_visible() and "Program dziecka działa" in banner.inner_text()
    assert (
        page.locator("div.vector-fs-host .fs-pills").evaluate(
            "e => getComputedStyle(e).pointerEvents"
        )
        == "none"
    )
    assert _calls(page, "turn_on") == []  # opening the view takes no control during a program
    page.locator("div.vector-fs-host #fs-stop").click()
    assert len(_calls(page, "stop")) == 1


# --- stand still (add-on 0.5.0+) -----------------------------------------------------------------


def test_stand_still_button_hidden_without_the_switch(page) -> None:
    assert not page.locator(".speed .still-t").is_visible()


def test_stand_still_button_toggles_the_switch(open_card) -> None:
    page = open_card("still=off")
    button = page.locator(".speed .still-t")
    assert button.is_visible() and "Stój w miejscu" in button.inner_text()
    button.click()
    assert [(c["domain"], c["data"]) for c in _calls(page, "turn_on")] == [
        ("switch", {"entity_id": "switch.vector_stand_still"})
    ]
    page = open_card("still=on")
    button = page.locator(".speed .still-t")
    assert "Stoi w miejscu" in button.inner_text()
    assert "on" in (button.get_attribute("class") or "")
    button.click()
    assert [c["data"] for c in _calls(page, "turn_off")] == [
        {"entity_id": "switch.vector_stand_still"}
    ]
