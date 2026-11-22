"""The last frame of the live view, kept in Home Assistant (on disk) so the full-screen view
always has a background — on every device, after a restart, and while the robot is off or the
add-on is down. The Lovelace card uploads it while the live view runs
(POST /api/vector/last_frame/<camera>).
"""

from __future__ import annotations

from collections.abc import Callable
import contextlib
from datetime import UTC, datetime
import os

from homeassistant.core import HomeAssistant

MAX_FRAME = 1024 * 1024  # a 960 px JPEG is ~50-150 kB; refuse anything bigger than 1 MB
JPEG_MAGIC = b"\xff\xd8"
JPEG_END = b"\xff\xd9"


def is_complete_jpeg(data: bytes) -> bool:
    """Starts with SOI and ends with EOI: a cut upload shows a grey lower part in the browser."""
    return data[:2] == JPEG_MAGIC and data.rstrip(b"\x00")[-2:] == JPEG_END


class LastFrameStore:
    """One JPEG on disk + listeners (the image entity)."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.jpeg: bytes | None = None
        self.updated_at: datetime | None = None
        self._listeners: list[Callable[[], None]] = []

    def add_listener(self, cb: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(cb)
        return lambda: self._listeners.remove(cb)

    async def async_load(self, hass: HomeAssistant) -> None:
        def _read() -> tuple[bytes, float] | None:
            try:
                with open(self.path, "rb") as fh:
                    return fh.read(), os.path.getmtime(self.path)
            except OSError:
                return None

        found = await hass.async_add_executor_job(_read)
        if found and is_complete_jpeg(found[0]):  # a cut frame from older versions is skipped
            self.jpeg = found[0]
            self.updated_at = datetime.fromtimestamp(found[1], UTC)

    async def async_save(self, hass: HomeAssistant, jpeg: bytes) -> None:
        if jpeg[:2] != JPEG_MAGIC:
            raise ValueError("not a JPEG")
        if not is_complete_jpeg(jpeg):
            raise ValueError("incomplete JPEG")
        if len(jpeg) > MAX_FRAME:
            raise ValueError("frame too big")

        def _write() -> None:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = f"{self.path}.tmp"
            with open(tmp, "wb") as fh:
                fh.write(jpeg)
            os.replace(tmp, self.path)

        await hass.async_add_executor_job(_write)
        self.jpeg = jpeg
        self.updated_at = datetime.now(UTC)
        for cb in list(self._listeners):
            cb()

    async def async_remove(self, hass: HomeAssistant) -> None:
        def _rm() -> None:
            with contextlib.suppress(OSError):
                os.remove(self.path)

        await hass.async_add_executor_job(_rm)


def frame_path(hass: HomeAssistant, domain: str, key: str) -> str:
    """On-disk place of one robot's last frame (key = robot serial)."""
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in key)
    return hass.config.path(".storage", f"{domain}.last_frame.{safe}.jpg")
