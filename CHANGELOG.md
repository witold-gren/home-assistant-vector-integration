# Changelog

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
