"""Fake vector-bridge: hello protocol, commands, state and robot events."""

from __future__ import annotations

import asyncio
import copy
from typing import Any
from unittest.mock import patch

from aiohttp import WSMsgType, web
from aiohttp.test_utils import TestServer
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vector.const import DOMAIN

TOKEN = "secret"
JPEG = b"\xff\xd8fake-jpeg\xff\xd9"
ESN = "00a1b2c3"

ROBOT = {
    "esn": ESN,
    "name": "Vector",
    "ip": "192.168.1.50",
    "connected": True,
    "firmware": "2.0.1.6076ep",
    "battery": {
        "level": "nominal",
        "volts": 3.99,
        "percent": 78,
        "charging": True,
        "on_charger": True,
    },
    "picked_up": False,
    "held": False,
    "cliff": False,
    "sleeping": False,
    "touched": False,
    "listening": False,
    "activity": "ObservingOnCharger",
    "stimulation": 0.4,
    "last_face": {"name": "Alice", "id": 1, "at": 1792776551},
    "head_angle": 21,
    "lift_height": 0,
    "settings": {
        "master_volume": 2,
        "eye_color": 3,
        "locale": "en-US",
        "time_zone": "Europe/Paris",
        "default_location": "Warsaw, Poland",
        "clock_24_hour": True,
        "dist_is_metric": True,
        "temp_is_fahrenheit": False,
        "button_wakeword": 0,
    },
    "faces": [{"id": 1, "name": "Alice", "last_seen": 1792776551}],
    "cube": None,
    "stats": {
        "Alive.seconds": 24158335,
        "Pet.ms": 5214170,
        "Odom.Body": 826811017879,
        "BStat.ReactedToTriggerWord": 1053,
    },
    "control": "none",
    "camera": False,
    "audio": {"playing": False, "duration": 0, "started": 0, "volume": 80},
    "photos": 1,
    "last_photo": {"id": 2, "at": 1687187545},
    "custom_eye": None,
    "updated": 0,
}


class FakeBridge:
    """A real WebSocket server on localhost."""

    def __init__(self) -> None:
        self.robots: dict[str, dict[str, Any]] = {ESN: copy.deepcopy(ROBOT)}
        self.commands: list[dict[str, Any]] = []
        self.sockets: list[web.WebSocketResponse] = []
        self.closing = False
        self.cached: bytes | None = JPEG
        self.photos: dict[int, int] = {2: 1687187545}
        self.mjpeg_requests = 0
        self.audio: list[tuple[bytes, dict[str, str]]] = []
        self.voice_router = {"enabled": True, "hook": "http://192.168.1.10:8790"}
        app = web.Application()
        app.router.add_get("/ws", self._ws)
        app.router.add_get("/snapshot/{esn}", self._snapshot)
        app.router.add_get("/mjpeg/{esn}", self._mjpeg)
        app.router.add_get("/photo/{esn}/{id}", self._photo)
        app.router.add_post("/audio/{esn}", self._audio)
        app.router.add_get("/sound.mp3", self._sound)
        self.server = TestServer(app)

    @property
    def port(self) -> int:
        return self.server.port

    async def _ws(self, request: web.Request) -> web.StreamResponse:
        if self.closing:
            raise web.HTTPServiceUnavailable
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            raise web.HTTPUnauthorized
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self.sockets.append(ws)
        await ws.send_json(
            {
                "type": "hello",
                "version": "test",
                "api": 1,
                "robots": list(self.robots.values()),
                "voice_router": self.voice_router,
            }
        )
        async for msg in ws:
            if msg.type is not WSMsgType.TEXT:
                continue
            req = msg.json()
            self.commands.append(req)
            await ws.send_json(await self._handle(req))
        self.sockets.remove(ws)
        return ws

    async def _handle(self, req: dict[str, Any]) -> dict[str, Any]:
        if req["command"] == "speech_decision":
            return {"type": "result", "id": req["id"], "success": True, "result": None}
        if req["command"] in ("llm_reply",):
            return {"type": "result", "id": req["id"], "success": True, "result": None}
        if req["command"] == "set_llm_proxy":
            self.voice_router["llm"] = req["args"]["enabled"]
            for ws in list(self.sockets):
                await ws.send_json(
                    {"type": "event", "event": "voice_router", "data": self.voice_router}
                )
            return {"type": "result", "id": req["id"], "success": True, "result": self.voice_router}
        if req["command"] == "set_voice_router":
            self.voice_router["enabled"] = req["args"]["enabled"]
            for ws in list(self.sockets):
                await ws.send_json(
                    {"type": "event", "event": "voice_router", "data": self.voice_router}
                )
            return {"type": "result", "id": req["id"], "success": True, "result": self.voice_router}
        robot = self.robots.get(req.get("robot", ""))
        if robot is None:
            return {"type": "result", "id": req["id"], "success": False, "error": "unknown robot"}
        args = req.get("args", {})
        cmd = req["command"]
        result: Any = None
        if cmd == "update_settings":
            if "master_volume" in args:
                robot["settings"]["master_volume"] = [
                    "mute",
                    "low",
                    "medium_low",
                    "medium",
                    "medium_high",
                    "high",
                ].index(args["master_volume"])
            if "eye_color" in args:
                robot["custom_eye"] = None
        elif cmd == "set_eye_color":
            robot["custom_eye"] = {"hue": args["hue"], "saturation": args["saturation"]}
        elif cmd == "hold_control":
            robot["control"] = "held"
        elif cmd == "release_control":
            robot["control"] = "none"
        elif cmd == "list_animation_triggers":
            result = ["GreetAfterLongTime", "PounceSuccess"]
        elif cmd == "list_faces":
            result = [{"id": 1, "name": "Alice", "last_seen": 1792776551}]
        elif cmd == "list_photos":
            result = [{"id": i, "at": at} for i, at in sorted(self.photos.items(), reverse=True)]
        elif cmd == "delete_photo":
            if self.photos.pop(args["id"], None) is None:
                return {
                    "type": "result",
                    "id": req["id"],
                    "success": False,
                    "error": "no such photo",
                }
        elif cmd == "set_audio_volume":
            robot["audio"]["volume"] = args["volume"]
        elif cmd == "stop_audio":
            robot["audio"]["playing"] = False
        elif cmd == "camera_snapshot":
            self.cached = b"\xff\xd8fresh\xff\xd9"
        elif cmd == "say_text" and args.get("text") == "fail":
            return {
                "type": "result",
                "id": req["id"],
                "success": False,
                "error": "robot not connected",
            }
        await self.push(robot["esn"])
        return {"type": "result", "id": req["id"], "success": True, "result": result}

    def _auth(self, request: web.Request) -> None:
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            raise web.HTTPUnauthorized

    async def _snapshot(self, request: web.Request) -> web.Response:
        self._auth(request)
        assert request.query.get("cached") == "true", "the integration must never wake the camera"
        if self.cached is None:
            raise web.HTTPNotFound
        return web.Response(body=self.cached, content_type="image/jpeg")

    async def _mjpeg(self, request: web.Request) -> web.StreamResponse:
        self._auth(request)
        self.mjpeg_requests += 1
        resp = web.StreamResponse(
            headers={"Content-Type": "multipart/x-mixed-replace; boundary=frame"}
        )
        await resp.prepare(request)
        part = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + JPEG + b"\r\n"
        await resp.write(part)
        await resp.write_eof()
        return resp

    async def _photo(self, request: web.Request) -> web.Response:
        self._auth(request)
        photo_id = int(request.match_info["id"])
        if photo_id not in self.photos:
            raise web.HTTPNotFound
        thumb = request.query.get("thumb") == "true"
        return web.Response(body=b"thumb" if thumb else b"photo", content_type="image/jpeg")

    async def _audio(self, request: web.Request) -> web.Response:
        self._auth(request)
        self.audio.append((await request.read(), dict(request.query)))
        return web.json_response({"queued": len(self.audio)}, status=202)

    async def _sound(self, request: web.Request) -> web.Response:
        return web.Response(body=b"ID3-mp3-bytes", content_type="audio/mpeg")

    async def push(self, esn: str) -> None:
        for ws in list(self.sockets):
            await ws.send_json(
                {"type": "event", "event": "state", "robot": esn, "state": self.robots[esn]}
            )

    async def event(self, name: str, data: dict[str, Any] | None = None) -> None:
        for ws in list(self.sockets):
            await ws.send_json({"type": "event", "event": name, "robot": ESN, "data": data or {}})

    async def drop_clients(self) -> None:
        for ws in list(self.sockets):
            await ws.close()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let HA see custom_components in tests."""


@pytest.fixture(autouse=True)
def fast_reconnect():
    with patch("custom_components.vector.api.RECONNECT_DELAYS", (0.01,)):
        yield


@pytest.fixture
async def bridge(socket_enabled: None) -> FakeBridge:
    fake = FakeBridge()
    await fake.server.start_server()
    yield fake
    fake.closing = True
    await fake.drop_clients()
    await fake.server.close()


@pytest.fixture
def entry(bridge: FakeBridge) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Vector",
        unique_id="addon-uuid",
        data={"host": "127.0.0.1", "port": bridge.port, "token": TOKEN},
    )


async def settle(hass) -> None:
    """Let events from the socket reach HA."""
    for _ in range(5):
        await asyncio.sleep(0.05)
        await hass.async_block_till_done()
