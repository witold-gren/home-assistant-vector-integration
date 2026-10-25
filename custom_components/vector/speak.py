"""Vector speech: via wire-pod (its TTS) or an HA TTS engine through the robot speaker."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components import tts
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .api import VectorClient, VectorError
from .const import (
    CONF_TTS_ENGINE,
    CONF_TTS_LANGUAGE,
    CONF_TTS_VOICE,
    CONF_VOICE,
    VOICE_TTS,
    VOICE_WIREPOD,
)

_LOGGER = logging.getLogger(__name__)

# /api-sdk/say_text limit in wire-pod
MAX_WIREPOD_TEXT = 590


def default_voice(entry: ConfigEntry) -> str:
    """Voice from options: HA TTS only when an engine is selected."""
    if entry.options.get(CONF_VOICE) == VOICE_TTS and entry.options.get(CONF_TTS_ENGINE):
        return VOICE_TTS
    return VOICE_WIREPOD


async def _wait_audio_finished(client: VectorClient, esn: str, timeout: float) -> None:
    done: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    @callback
    def _on(event_esn: str, event: str, data: dict[str, Any]) -> None:
        if event_esn == esn and event == "audio_finished" and not done.done():
            done.set_result(None)

    remove = client.add_event_listener(_on)
    try:
        async with asyncio.timeout(timeout):
            await done
    except TimeoutError:
        pass
    finally:
        remove()


async def speak(
    hass: HomeAssistant,
    entry: ConfigEntry,
    client: VectorClient,
    esn: str,
    text: str,
    engine: str | None = None,
    wait: bool = True,
) -> None:
    """Vector says `text`. engine: wirepod | vector | tts | None (= from options).

    With `wait`, return once spoken (wire-pod does it itself; for TTS wait for audio_finished).
    """
    engine = engine or default_voice(entry)
    if engine == VOICE_TTS:
        options = entry.options
        tts_engine = options.get(CONF_TTS_ENGINE)
        if not tts_engine:
            raise HomeAssistantError("Vector: choose a TTS engine in the integration options")
        extra = {"voice": options[CONF_TTS_VOICE]} if options.get(CONF_TTS_VOICE) else None
        media_id = tts.generate_media_source_id(
            hass,
            text,
            engine=tts_engine,
            language=options.get(CONF_TTS_LANGUAGE) or None,
            options=extra,
        )
        _, data = await tts.async_get_media_source_audio(hass, media_id)
        waiter = (
            asyncio.ensure_future(_wait_audio_finished(client, esn, 30 + len(text) / 5))
            if wait
            else None
        )
        try:
            await client.play_audio(esn, data, interrupt=True)
        except VectorError:
            if waiter:
                waiter.cancel()
            raise
        if waiter:
            await waiter
        return
    await client.command(
        "say_text", esn, text=text[:MAX_WIREPOD_TEXT], engine=engine if engine else VOICE_WIREPOD
    )
