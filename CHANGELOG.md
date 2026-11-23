# Changelog

## 0.3.0 - 2026-11-23

- **Child's program (Robots Code Studio, add-on 0.3.0+):** new **Program** binary sensor
  (`binary_sensor.vector_program`, attributes `owner`, `since`, `limit`) and **Program** event
  entity (`program_started` / `program_ended` with `reason` and `cause`); bus events
  `vector_program_started` and `vector_program_ended` for automations. The state comes from the
  add-on's hello, its state pushes and the program events (shown at once).
- **Control card during a program:** the controls are greyed out with "Child's program running";
  **STOP** stays and ends the program (the add-on answers every stop, reason `ha_stop`). A program
  that starts while somebody drives from the card stops that driving and the card's hold.
- The add-on's `hello.features` is read (`client.features`), so newer add-on features can be
  detected.
- README: section *Child's program* with FAQ (card does nothing, program stopped by itself,
  silent announcements).

## 0.2.6 - 2026-11-22

- **Fix: half-grey background (last frame), cut intercom messages and cut audio.** Home Assistant
  read only the part of an upload that had arrived so far (`content.read(n)`), so a phone
  uploading slowly left a cut JPEG (grey lower part) or a cut recording; the media player could
  cut downloaded audio the same way. The whole body is read now; a JPEG without its end marker is
  refused, and a cut frame saved by an older version is not used.

## 0.2.5 - 2026-11-22

- **Full screen like the small card:** the play button says "Camera preview is off · Tap ▶ to
  watch live" (was "Start live view"); the background is the stored last frame (fallback: the
  camera snapshot) and follows the robot — no picture while Vector is unavailable, back as soon
  as it returns. Before, a last-frame image that was never stored left the background blank.

## 0.2.4 - 2026-11-22

- **Full screen (iPad and phone): head and lift side by side at mid-height** — one right thumb
  reaches both; the microphone stays in the top-right corner.
- **Last frame kept in Home Assistant:** while the full-screen live view runs, the card sends the
  current frame (960 px JPEG) every 10 s and when the view closes
  (`POST /api/vector/last_frame/<camera>`); it is stored on disk per robot and shown by the new,
  always-available **Last frame** image. It is the full-screen background — the same on every
  device, after a restart, and while Vector is off.

## 0.2.3 - 2026-11-21

- **Talk through Vector:** hold 🎙 (in the full-screen view and on the tile) and speak; the
  recording plays on Vector's speaker right away (`/api/vector/intercom/<camera>`).
- No "listen" button any more: Vector's firmware sends a 1 kHz test tone instead of its microphone
  to the SDK (`sdkComponent.cpp`), so the live view only beeped.
- **Fix (iPhone): buttons over the live picture vanished** — overlays now sit on their own layers
  above the `<video>`.

## 0.2.2 - 2026-11-21

- **Fix: the full-screen view stayed black.** Home Assistant 2026's camera player takes its config
  and connection from Lit context, which only reaches elements inside `<home-assistant>`; the
  full-screen view lived in `<body>`, so the player rendered nothing. It now lives inside
  `<home-assistant>` (checked on a real Home Assistant).
- **Live view that keeps playing.** Before handing the browser's WebRTC offer to Home Assistant's
  go2rtc, the camera asks the add-on to start the stream (`warm_stream`, add-on 0.2.2); the
  browser's ICE candidates sent meanwhile are kept and forwarded. No HLS fallback any more (it
  failed the same way).
- **Card:**
  - Loader until the first frame.
  - 🔊 button on the tile, so sound works in portrait too.
  - Behavior control is taken while you steer (full screen, first drive in the tile) and given
    back when the view closes, a minute after the last drive, or when the page is hidden —
    instead of for as long as the card is open.
  - "Forward" on the charger asks Vector to drive off at most every 8 s, with a message (every tap
    used to fail with BEHAVIOR_WONT_ACTIVATE_STATE).

## 0.2.1 - 2026-11-21

- Polish translation of the custom voice command form used `{utwór}` instead of `{song}`; Home
  Assistant logged "Validation of translation placeholders … failed" on every start. A new test
  checks that every translation uses exactly the placeholders of `strings.json`.

## 0.2.0 - 2026-11-21

- **Live camera.** With the Vector add-on 0.2.0+ the camera entity has a real stream (WebRTC through
  Home Assistant's go2rtc, with Vector's microphone) instead of reloaded JPEG frames; with older
  add-ons it stays MJPEG.
- **Control card:**
  - The camera area shows a proper "preview is off" screen (or "Vector is unavailable"), never the
    browser's broken-image icon; ▶ starts the live view, ✕ stops it.
  - The live view stops after 5 minutes without a touch and when the page goes to the background.
  - Battery and activity show "—" instead of "unavailable %"; controls are disabled while the robot
    is unavailable.
  - **Full-screen control view** (⛶), like the Loona app: landscape, the camera fills the screen,
    driving pad on the left, listening (🔊 Vector's microphone), head and lift on the right, speed and
    charger at the bottom; keeps clear of the iPhone's Dynamic Island.
  - Driving always ends with a stop: on release, lost pointer, closing the full screen, the page
    going to the background or the card being rebuilt.
- Browser tests of the card (Playwright + Chrome, `tests/browser`, run separately:
  `.venv/bin/python -m pytest tests/browser -p no:homeassistant`).

## 0.1.2 - 2026-10-25

- Entity ids are English in every Home Assistant language (`sensor.vector_battery` instead of
  `sensor.vector_bateria` in a Polish installation); displayed names stay translated.
- Dark-theme brand images (`dark_icon`, `dark_logo`): the robot gets a light outline, so it
  is visible on dark backgrounds.

## 0.1.0 - 2026-10-25

First public release.

- **State and sensors**: connection, battery (level, voltage and estimated percentage), charging,
  on charger, picked up, touched, cliff, sleeping, listening, activity, stimulation, last face,
  known faces, photo count and lifetime statistics (time alive, petting time, distance driven,
  wake word reactions).
- **Behavior buttons**: go to charger, drive off charger, stop, dance, explore, go to sleep,
  come here, look at me, fist bump, do a trick, take a photo, turn to last face, refresh state and
  refresh camera image.
- **Head and lift** as number entities, **volume** as a select.
- **Eye color**: the preset colors as a select, plus an `Eyes` light for any custom color
  (turning it off restores the color from the settings).
- **Manual control** switch: the bridge holds behavior control (up to 10 minutes), so Vector stands
  still and waits for commands.
- **Events** on the Home Assistant bus (`vector_*`) and as event entities (wake word, interaction,
  face, photo, speech).
- **Services** for movement (`drive_straight`, `turn`, `drive_wheels`, `move`, `go_to`,
  `turn_towards_face`, `go_to_cube`, `stop`), animations (`play_animation`,
  `play_animation_trigger`, `list_animations`), intents (`run_intent`), eyes (`set_eye_color`) and
  speech (`say_text`).
- **Answer voice**: via wire-pod (its own TTS, e.g. Piper over Wyoming) or any Home Assistant TTS
  engine played on Vector's speaker; `vector.say_text` accepts an `engine` override.
- **Camera**: on-demand MJPEG stream (~2 fps) and a snapshot cached by the bridge that does not wake
  the camera.
- **Photos**: last photo as an image entity, Vector's photos in the media browser
  (**Media → Vector**), `vector.list_photos` and `vector.delete_photo`.
- **Speaker** as a `media_player`: `tts.speak` with any engine, media files and audio URLs, queue,
  announcements interrupt what is playing, volume and stop.
- **Voice → Assist**: what Vector hears (wire-pod) goes to an Assist agent first; if Assist
  understands it, Home Assistant acts and Vector speaks the answer, otherwise wire-pod handles the
  sentence as usual. A **Keep on Vector** phrase list (language-dependent defaults) sends things like
  the time, weather or dancing straight to wire-pod. Includes the `Last speech` sensor, the `Speech`
  event entity and the `vector_speech` event.
- **Custom voice commands** as config subentries: Assist-style sentences with `[optional]`,
  `(alternatives)` and `{slots}`, a spoken response, a script, a robot behavior or an animation, and
  the `vector_command` event.
- **Control card** `custom:vector-control-card` (served automatically, English and Polish UI):
  camera stream, hold-to-drive pad, head and lift, speed, charger buttons; backed by the
  `vector.move` service.
- **wire-pod LLM → Home Assistant** switch: questions wire-pod would send to its LLM are answered by
  a Home Assistant conversation agent.
- **Faces**: known faces sensor and `list_faces`, `rename_face`, `delete_face`, `enroll_face`.
- **Cube**: connection and battery entities, buttons to connect, disconnect, flash lights, pick up,
  roll and dock (disabled by default until the robot knows a cube).
- **Play animation** select with the robot's animation groups.
- **Robot settings**: language, back button (Hey Vector / Alexa), 24-hour clock, metric units,
  Fahrenheit, time zone and weather location.
- Diagnostics (token redacted), English and Polish translations.

Known limitation: images on Vector's face screen are not supported on Vector 2.0 (they crash the
robot), so the integration does not offer them.
