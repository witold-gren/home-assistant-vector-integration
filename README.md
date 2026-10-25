# Vector for Home Assistant

🇵🇱 [Polska wersja](README.pl.md)

A Home Assistant custom integration for the **Anki / Digital Dream Labs Vector** robot. It talks to
the robot through the [Vector add-on](https://github.com/witold-gren/home-assistant-vector-addon)
(the `vector-bridge`), which runs next to [wire-pod](https://github.com/kercre123/wire-pod) and
exposes a local WebSocket API. Everything stays on your network — no cloud.

With it you can watch Vector's sensors, drive him from a dashboard, use his camera and speaker, and
let him control your home: "Hey Vector, turn on the living room light" goes to Assist.

## Contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Entities](#entities)
- [Services](#services)
- [Voice → Assist](#voice--assist)
- [Custom voice commands](#custom-voice-commands)
- [Events](#events)
- [Dashboard examples](#dashboard-examples)
- [Limitations](#limitations)

## Requirements

- Home Assistant 2026.2 or newer.
- A Vector robot (Vector 1.0 or 2.0) set up with **wire-pod**.
- The **Vector add-on** from
  [home-assistant-vector-addon](https://github.com/witold-gren/home-assistant-vector-addon)
  (Home Assistant OS / Supervised), or another reachable `vector-bridge` instance.

## Installation

### HACS (recommended)

1. In HACS open the menu → **Custom repositories**.
2. Add `https://github.com/witold-gren/home-assistant-vector-integration` with category
   **Integration**.
3. Install **Vector** and restart Home Assistant.

### Manual

Copy `custom_components/vector` into `<config>/custom_components/vector` and restart Home Assistant.

## Configuration

When the Vector add-on is running, Home Assistant discovers it through the Supervisor and offers to
set it up under **Settings → Devices & services**. Without the Supervisor, add the **Vector**
integration manually and enter the bridge host, port (default `3012`) and token.

Every robot known to wire-pod becomes a device. When a new robot is added in wire-pod, the
integration reloads and creates its entities.

Integration options (**Configure**):

| Option | Meaning |
| --- | --- |
| Assist agent | Conversation agent that receives what Vector heard. |
| Vector says the answer | Whether Vector says the Assist response. |
| Keep on Vector | Phrases that always stay with wire-pod (one per line). |
| Answer voice | wire-pod (its own TTS, e.g. Piper) or a Home Assistant TTS engine. |
| TTS engine / language / voice | Used when the answer voice is a Home Assistant TTS engine. |
| Agent for wire-pod LLM questions | Answers wire-pod's LLM questions when that switch is on. |

## Entities

Entity IDs below assume an English Home Assistant install and a robot named "Vector".

| Platform | Entities |
| --- | --- |
| Binary sensor | Connection, charging, on charger, picked up, touched, cliff, sleeping, listening, cube |
| Sensor | Battery, battery voltage, battery level, activity, stimulation, last face, known faces, photos, last speech, time alive, petting time, distance driven, wake word reactions, cube battery |
| Button | Go to charger, drive off charger, stop, dance, explore, go to sleep, come here, look at me, fist bump, do a trick, take a photo, turn to last face, refresh state, refresh camera image, cube actions |
| Number | Head angle, lift height |
| Select | Volume, eye color, robot language, back button, play animation |
| Light | Eyes (any custom color) |
| Switch | Manual control, Voice → Home Assistant, wire-pod LLM → Home Assistant, 24-hour clock, metric units, Fahrenheit |
| Text | Time zone, weather location |
| Camera | MJPEG stream on demand, cached snapshot |
| Image | Last photo |
| Media player | Vector's speaker (`tts.speak`, media files, audio URLs) |
| Event | Wake word, interaction, face, photo, speech |

Cube entities are disabled by default until the robot knows a cube. Vector's photos are also
available in the media browser under **Media → Vector**.

## Services

All services accept an optional `device_id` (required only with more than one robot).

| Service | Description |
| --- | --- |
| `vector.say_text` | Vector says the text (`engine`: default, wirepod, tts, vector). |
| `vector.play_animation` | Play an animation by name. |
| `vector.play_animation_trigger` | Play a random animation of a trigger group. |
| `vector.list_animations` | Return the animation (or trigger) names the robot knows. |
| `vector.run_intent` | Run a voice-command behavior, e.g. `intent_imperative_dance`. |
| `vector.drive_straight` | Drive forward or back. |
| `vector.turn` | Turn in place. |
| `vector.drive_wheels` | Run both wheels for a while, then stop. |
| `vector.move` | Wheels, head and lift at given speeds; stops 0.7 s after the last call. |
| `vector.go_to` | Drive to a point, avoiding obstacles. |
| `vector.turn_towards_face` | Turn to a known face (default: the last one seen). |
| `vector.go_to_cube` | Drive to the connected cube. |
| `vector.set_eye_color` | Custom eye color until the next settings change or reboot. |
| `vector.stop` | Stop the current action and give control back to Vector. |
| `vector.list_photos` | Photos stored on the robot, newest first. |
| `vector.delete_photo` | Delete a photo stored on the robot. |
| `vector.list_faces` | Faces Vector knows by name. |
| `vector.rename_face` | Rename a known face. |
| `vector.delete_face` | Vector forgets a face. |
| `vector.enroll_face` | Vector learns the face in front of him under a name. |

## Voice → Assist

With the **Voice → Home Assistant** switch on, every sentence Vector hears (transcribed by wire-pod)
is checked in this order:

1. **Custom voice commands** (see below) — matched locally, handled by Home Assistant.
2. **Keep on Vector** — if the sentence contains one of these phrases, it goes straight back to
   wire-pod. The defaults depend on the Home Assistant language (English: "what time is it",
   "weather", "timer", "take a photo", "dance", "go to sleep", "good night", …) and can be edited in
   the options.
3. **Assist** — the configured agent gets the sentence. If it understands it, Home Assistant acts
   and Vector speaks the answer (via wire-pod's TTS or a Home Assistant TTS engine, see *Answer
   voice*). If it does not understand or does not answer in time (~7 s), wire-pod handles the
   sentence as usual (time, weather, its own LLM…).

The **wire-pod LLM → Home Assistant** switch goes one step further: questions wire-pod would send to
its own LLM are answered by a Home Assistant conversation agent instead.

The `Last speech` sensor, the `Speech` event entity and the `vector_speech` event show what was
heard and what happened to it.

## Custom voice commands

Add commands under **Settings → Devices & services → Vector → Add command**. Each command has:

- **Sentences**, one per line, in Assist syntax:
  - `good night [vector]` — `[...]` is optional,
  - `(turn off|switch off) everything` — `(a|b)` are alternatives,
  - `play {song}` — `{slot}` matches any text.
- An optional **response** Vector says; `{song}` in the response is replaced with the matched value.
- An optional **script**, started with the variables `text`, `slots`, `esn` and `device_id`.
- An optional **robot reaction** (dance, sleep, fist bump, …) or an **animation** group.

Every match also fires the `vector_command` event. Commands are checked before *Keep on Vector*
and before Assist.

## Events

| Event | Fired when |
| --- | --- |
| `vector_wake_word` | Vector hears the wake word. |
| `vector_touched` | Vector's back is touched. |
| `vector_picked_up` | Vector is picked up. |
| `vector_cliff` | Vector detects a cliff. |
| `vector_button_pressed` | The back button is pressed. |
| `vector_face_seen` | Vector sees a face. |
| `vector_intent` | Vector recognizes a voice intent. |
| `vector_cube_tapped` | The cube is tapped. |
| `vector_control_lost` | Behavior control is taken back by the robot. |
| `vector_photo_taken` | Vector takes a photo. |
| `vector_audio_started` | Audio starts playing on the speaker. |
| `vector_audio_finished` | Audio finishes playing. |
| `vector_speech` | A sentence went through the voice router (text, decision, answer). |
| `vector_command` | A custom voice command matched (command, slots, text). |

## Dashboard examples

### Control card

The integration serves the `custom:vector-control-card` automatically — no Lovelace resource is
needed. Its UI is English, or Polish when Home Assistant is set to Polish.

```yaml
type: custom:vector-control-card
camera: camera.vector
# speed: 120      # mm/s forward (optional)
# hold: true      # take control while the card is open (default)
```

- **Hold to drive**: the arrows, head and lift buttons move Vector only while pressed. The card
  repeats `vector.move` every 300 ms and Vector stops 0.7 s after the last call, so he also stops
  when the network drops or the window closes. **STOP** stops everything.
- **Auto hold**: while the card is open it turns on the *Manual control* switch, so Vector stands
  still and waits for commands. The hold is renewed every 5 minutes and released when the card
  closes. Use `hold: false` to disable it, or the **Hold** toggle on the card.
- **On the charger** a bar with **Drive off charger** appears, and the forward arrow drives Vector
  off the charger.
- **Camera**: the stream runs only while the card is open; closing the card stops the camera.

### Popup with browser_mod

With [browser_mod](https://github.com/thomasloven/hass-browser_mod), a tile can open the card plus
a few behavior buttons in a popup:

```yaml
type: tile
entity: sensor.vector_battery
name: Vector
icon: mdi:robot-happy
tap_action:
  action: fire-dom-event
  browser_mod:
    service: browser_mod.popup
    data:
      title: Vector
      content:
        type: vertical-stack
        cards:
          - type: custom:vector-control-card
            camera: camera.vector
          - type: grid
            columns: 4
            square: false
            cards:
              - type: tile
                entity: button.vector_dance
                vertical: true
                hide_state: true
                tap_action:
                  action: perform-action
                  perform_action: button.press
                  target:
                    entity_id: button.vector_dance
              # … same for button.vector_look_at_me, button.vector_fist_bump, button.vector_go_to_sleep
```

Entity IDs depend on the Home Assistant language at the time the integration was set up (for
example, a Polish install gets Polish entity IDs). Check yours under **Settings → Entities**.

## Limitations

- **Face screen images** are not supported: on Vector 2.0 writing images to the face screen crashes
  the robot.
- **Camera** runs at about 2 frames per second (MJPEG through the bridge).
- **Camera on the charger**: while Vector sits on the charger the camera needs behavior control, so
  Vector holds still while someone watches the stream.
- Long or endless audio streams are not supported on the speaker; the bridge plays whole files
  (up to 50 MB).

## License

[MIT](LICENSE)
