"""Constants for the Vector integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "vector"

DEFAULT_PORT: Final = 3012

# Options: Assist agent for what Vector heard, and whether Vector speaks the answer.
CONF_AGENT: Final = "agent_id"
CONF_RESPOND: Final = "respond"
DEFAULT_AGENT: Final = "conversation.home_assistant"
# Sentences containing these phrases stay with Vector (wire-pod), even if Assist could handle them.
CONF_KEEP: Final = "keep_on_vector"
DEFAULT_KEEP: Final[dict[str, tuple[str, ...]]] = {
    "en": (
        "what time is it",
        "what's the time",
        "weather",
        "timer",
        "take a photo",
        "take a picture",
        "dance",
        "go to sleep",
        "go to your charger",
        "good night",
        "good morning",
        "hello",
    ),
    "pl": (
        "która godzina",
        "która jest godzina",
        "jaka jest godzina",
        "pogoda",
        "minutnik",
        "timer",
        "zrób zdjęcie",
        "zrób mi zdjęcie",
        "zatańcz",
        "tańcz",
        "idź spać",
        "do ładowarki",
        "dobranoc",
        "dzień dobry",
        "cześć",
    ),
}
# Answer voice: wirepod = its TTS (e.g. Piper via Wyoming); tts = an HA TTS engine,
# played on the robot speaker (add-on). Plus the agent for the wire-pod LLM (proxy).
CONF_VOICE: Final = "voice"
VOICE_WIREPOD: Final = "wirepod"
VOICE_TTS: Final = "tts"
CONF_TTS_ENGINE: Final = "tts_engine"
CONF_TTS_LANGUAGE: Final = "tts_language"
CONF_TTS_VOICE: Final = "tts_voice"
CONF_LLM_AGENT: Final = "llm_agent"
# The bridge waits 8 s for a decision; Assist gets a bit less.
VOICE_BUDGET: Final = 7

# Robot actions (driving to the charger, animations) can take tens of seconds.
COMMAND_TIMEOUT: Final = 120
RECONNECT_DELAYS: Final = (1, 2, 5, 10, 30)

# Bridge events forwarded to the HA bus as `vector_<name>`.
BRIDGE_EVENTS: Final = (
    "wake_word",
    "touched",
    "picked_up",
    "cliff",
    "button_pressed",
    "face_seen",
    "intent",
    "cube_tapped",
    "control_lost",
    "photo_taken",
    "audio_started",
    "audio_finished",
)
# (vector_speech is fired by voice.py, with the text, the decision and the Assist answer)

# Order = Vector enum values (Volume, EyeColor).
VOLUMES: Final = ["mute", "low", "medium_low", "medium", "medium_high", "high"]
EYE_COLORS: Final = ["teal", "orange", "yellow", "lime", "sapphire", "purple", "green"]


def _language(language: str | None) -> str:
    """Two-letter language code ("pl-PL" -> "pl")."""
    return (language or "en")[:2].lower()


def default_keep(language: str | None) -> tuple[str, ...]:
    """Default "Keep on Vector" phrases for the HA language (fallback: English)."""
    return DEFAULT_KEEP.get(_language(language), DEFAULT_KEEP["en"])
