"""WebSocket API client for the vector-bridge (Vector add-on)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
import itertools
import logging
from typing import Any

import aiohttp

from .const import COMMAND_TIMEOUT, RECONNECT_DELAYS

_LOGGER = logging.getLogger(__name__)

type RobotState = dict[str, Any]
type EventListener = Callable[[str, str, dict[str, Any]], None]


class VectorError(Exception):
    """Bridge connection error or rejected command."""


class VectorAuthError(VectorError):
    """The bridge rejected the token."""


class VectorClient:
    """A single WebSocket connection: robot state, events and commands."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        token: str | None,
    ) -> None:
        self._session = session
        self._base = f"http://{host}:{port}"
        self._token = token or None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future[Any]] = {}
        self._listeners: list[Callable[[], None]] = []
        self._event_listeners: list[EventListener] = []
        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self.robots: dict[str, RobotState] = {}
        # bridge voice router: {"enabled": bool, "hook": str}; None when the bridge has none
        self.voice_router: dict[str, Any] | None = None
        self.version: str | None = None
        self.connected = False

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call `listener` on every state change; return an unsubscribe function."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def add_event_listener(self, listener: EventListener) -> Callable[[], None]:
        """Call `listener(esn, event, data)` for robot events (touch, face…)."""
        self._event_listeners.append(listener)
        return lambda: self._event_listeners.remove(listener)

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    async def connect(self) -> None:
        """First connection: wait for `hello` and raise errors (config flow, entry setup)."""
        await self._open()
        self._task = asyncio.create_task(self._run(), name="vector-ws")

    async def _open(self) -> None:
        try:
            ws = await self._session.ws_connect(
                f"{self._base}/ws", headers=self._headers, heartbeat=30
            )
        except aiohttp.WSServerHandshakeError as err:
            if err.status == 401:
                raise VectorAuthError("invalid token") from err
            raise VectorError(f"handshake failed: {err.status}") from err
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            raise VectorError(f"cannot connect to {self._base}: {err}") from err
        try:
            hello = await ws.receive_json(timeout=15)
        except (TimeoutError, ValueError, TypeError) as err:
            await ws.close()
            raise VectorError("no hello from the bridge") from err
        if hello.get("type") != "hello":
            await ws.close()
            raise VectorError(f"unexpected first message: {hello.get('type')}")
        self._ws = ws
        self.version = hello.get("version")
        self.robots = {r["esn"]: r for r in hello.get("robots", []) if r.get("esn")}
        self.voice_router = hello.get("voice_router")
        self.connected = True
        self._notify()

    async def _run(self) -> None:
        """Receive messages; reconnect with increasing delays after a disconnect."""
        attempt = 0
        while not self._stopping:
            if self._ws is not None:
                attempt = 0
                await self._receive(self._ws)
                self._ws = None
                self.connected = False
                self._fail_pending(VectorError("connection lost"))
                self._notify()
            if self._stopping:
                break
            delay = RECONNECT_DELAYS[min(attempt, len(RECONNECT_DELAYS) - 1)]
            attempt += 1
            await asyncio.sleep(delay)
            with contextlib.suppress(VectorError):
                await self._open()

    async def _receive(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        async for msg in ws:
            if msg.type is not aiohttp.WSMsgType.TEXT:
                continue
            try:
                data = msg.json()
            except ValueError:
                continue
            kind = data.get("type")
            if kind == "event":
                self._on_event(data)
            elif kind == "result":
                future = self._pending.pop(data.get("id"), None)
                if future is not None and not future.done():
                    if data.get("success"):
                        future.set_result(data.get("result"))
                    else:
                        future.set_exception(VectorError(data.get("error") or "command failed"))

    def _on_event(self, data: dict[str, Any]) -> None:
        esn = data.get("robot") or ""
        event = data.get("event")
        if event == "state":
            self.robots[esn] = data["state"]
            self._notify()
            return
        if event == "voice_router":
            self.voice_router = data.get("data")
            self._notify()
            return
        for listener in list(self._event_listeners):
            listener(esn, event, data.get("data") or {})

    def _fail_pending(self, err: Exception) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(err)
        self._pending.clear()

    async def command(self, command: str, robot: str | None = None, **args: Any) -> Any:
        """Send a command and wait for its result."""
        if self._ws is None:
            raise VectorError("not connected to the bridge")
        request_id = next(self._ids)
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        payload: dict[str, Any] = {"id": request_id, "command": command, "args": args}
        if robot is not None:
            payload["robot"] = robot
        try:
            await self._ws.send_json(payload)
            async with asyncio.timeout(COMMAND_TIMEOUT):
                return await future
        except TimeoutError as err:
            raise VectorError(f"{command}: no answer within {COMMAND_TIMEOUT}s") from err
        finally:
            self._pending.pop(request_id, None)

    def url(self, path: str) -> str:
        """URL of a bridge HTTP resource (MJPEG, photos)."""
        return f"{self._base}{path}"

    @property
    def headers(self) -> dict[str, str]:
        """Headers with the token for HTTP requests to the bridge."""
        return self._headers

    async def _get_image(self, path: str, params: dict[str, str] | None = None) -> bytes | None:
        """JPEG from the bridge; None when there is none (404)."""
        try:
            async with asyncio.timeout(COMMAND_TIMEOUT):
                resp = await self._session.get(
                    self.url(path), params=params or {}, headers=self._headers
                )
                if resp.status == 404:
                    return None
                if resp.status != 200:
                    raise VectorError(f"{path}: HTTP {resp.status} {await resp.text()}")
                return await resp.read()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise VectorError(f"{path} failed: {err}") from err

    async def snapshot(self, esn: str, cached: bool = True) -> bytes | None:
        """Camera frame: cached by the bridge (does not start the camera) or fresh."""
        return await self._get_image(f"/snapshot/{esn}", {"cached": "true"} if cached else None)

    async def photo(self, esn: str, photo_id: int, thumb: bool = False) -> bytes | None:
        """Photo stored on the robot (or its thumbnail)."""
        return await self._get_image(
            f"/photo/{esn}/{photo_id}", {"thumb": "true"} if thumb else None
        )

    async def play_audio(
        self, esn: str, data: bytes, volume: int | None = None, interrupt: bool = False
    ) -> None:
        """Send audio (any format) to the robot speaker; it is queued."""
        params = {"interrupt": "true"} if interrupt else {}
        if volume is not None:
            params["volume"] = str(volume)
        try:
            async with asyncio.timeout(60):
                resp = await self._session.post(
                    self.url(f"/audio/{esn}"), data=data, params=params, headers=self._headers
                )
                if resp.status != 202:
                    raise VectorError(f"audio: HTTP {resp.status} {await resp.text()}")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise VectorError(f"audio failed: {err}") from err

    async def close(self) -> None:
        """Close the connection and stop reconnecting."""
        self._stopping = True
        if self._ws is not None:
            await self._ws.close()
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        self._fail_pending(VectorError("client closed"))
