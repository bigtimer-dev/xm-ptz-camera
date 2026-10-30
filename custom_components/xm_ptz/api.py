"""Async client for Xiongmai ("XMEye" / Sofia firmware) cameras over DVRIP, TCP port 34567.

Standard library only, so the CLI (xmcam.py) can use it without Home Assistant installed.
Every frame is a 20-byte little-endian header followed by a JSON body ending in b"\\n\\0" (or raw bytes
for snapshots). A reply carries message id = request id + 1; alarms arrive unsolicited as id 1504.
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import struct
from collections.abc import Callable
from datetime import datetime
from urllib.parse import quote

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 34567
RTSP_PORT = 554

# head 0xff, version, 2 reserved, session id, sequence, total/current packet, message id, body length
HEADER = struct.Struct("<BB2xII2xHI")

LOGIN = 1000
KEEPALIVE = 1006
SYSINFO = 1020
CONFIG_SET = 1040
CONFIG_GET = 1042
ABILITY_GET = 1360
PTZ = 1400
OPERATION = 1450  # OPMachine (reboot), OPTimeSetting
TIME_QUERY = 1452
GUARD = 1500  # subscribe to alarms
ALARM = 1504
SNAPSHOT = 1560

RET_OK = (100, 515)
RET_AUTH = {203: "wrong password", 205: "unknown user", 206: "account locked", 207: "user blacklisted"}

PTZ_COMMANDS = {
    "up": "DirectionUp", "down": "DirectionDown", "left": "DirectionLeft", "right": "DirectionRight",
    "left_up": "DirectionLeftUp", "left_down": "DirectionLeftDown",
    "right_up": "DirectionRightUp", "right_down": "DirectionRightDown",
    "zoom_in": "ZoomTile", "zoom_out": "ZoomWide", "focus_near": "FocusNear", "focus_far": "FocusFar",
    "iris_open": "IrisLarge", "iris_close": "IrisSmall",
}
PTZ_START = 65535  # "Preset" value that starts a continuous move; -1 stops it
PTZ_STOP = -1


class XMError(Exception):
    """Camera unreachable or returned an error code."""


class XMAuthError(XMError):
    """Login rejected."""


def sofia_hash(password: str) -> str:
    """Xiongmai's 8-character password digest: MD5 bytes summed pairwise mod 62 into [0-9A-Za-z]."""
    digest = hashlib.md5(password.encode()).digest()
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    return "".join(chars[(digest[2 * i] + digest[2 * i + 1]) % 62] for i in range(8))


class XMCamera:
    """One persistent, logged-in DVRIP connection. Requests are serialized; reconnects on demand."""

    def __init__(self, host: str, username: str, password: str, port: int = DEFAULT_PORT,
                 timeout: float = 10, on_alarm: Callable[[dict], None] | None = None) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.on_alarm = on_alarm
        self.alive_interval = 20
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._session = 0
        self._sequence = 0
        self._lock = asyncio.Lock()
        self._pending: asyncio.Future | None = None
        self._tasks: list[asyncio.Task] = []
        self._closed = asyncio.Event()
        self._closed.set()

    @property
    def connected(self) -> bool:
        return not self._closed.is_set()

    @property
    def session_id(self) -> str:
        return f"0x{self._session:08X}"

    def rtsp_url(self, stream: int = 0) -> str:
        """stream 0 = main (4K), 1 = sub (D1)."""
        user, pw = quote(self.username, safe=""), quote(self.password, safe="")
        return f"rtsp://{self.host}:{RTSP_PORT}/user={user}&password={pw}&channel=1&stream={stream}.sdp"

    # --- connection -------------------------------------------------------------------------

    async def connect(self) -> None:
        async with self._lock:
            await self._connect()

    async def _connect(self) -> None:
        if self.connected:
            return
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), self.timeout)
        except (OSError, asyncio.TimeoutError) as err:
            raise XMError(f"cannot connect to {self.host}:{self.port}: {err}") from err
        self._session = 0
        self._sequence = 0
        self._closed.clear()
        self._tasks = [asyncio.create_task(self._read_loop(), name=f"xm read {self.host}")]
        try:
            reply = await self._send(LOGIN, {
                "EncryptType": "MD5", "LoginType": "DVRIP-Web",
                "UserName": self.username, "PassWord": sofia_hash(self.password),
            })
            ret = reply.get("Ret")
            if ret in RET_AUTH:
                raise XMAuthError(f"login failed: {RET_AUTH[ret]} (Ret {ret})")
            if ret not in RET_OK:
                raise XMError(f"login failed (Ret {ret})")
            self._session = int(reply["SessionID"], 16)
            self.alive_interval = int(reply.get("AliveInterval", 20))
            if self.on_alarm:
                await self._command(GUARD, "")
        except BaseException:
            await self._disconnect()
            raise
        self._tasks.append(asyncio.create_task(self._keepalive_loop(), name=f"xm keepalive {self.host}"))
        _LOGGER.debug("Logged in to %s, session %s", self.host, self.session_id)

    async def close(self) -> None:
        await self._disconnect()

    async def _disconnect(self) -> None:
        self._closed.set()
        current = asyncio.current_task()
        for task in self._tasks:
            if task is not current:
                task.cancel()
        self._tasks = []
        if self._pending and not self._pending.done():
            self._pending.set_exception(XMError("connection closed"))
        if self._writer:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()
        self._reader = self._writer = None

    async def run(self, retry_delay: float = 10) -> None:
        """Hold the connection (and alarm subscription) open forever, reconnecting after failures."""
        while True:
            try:
                await self.connect()
                await self._closed.wait()
                _LOGGER.debug("Connection to %s lost", self.host)
            except XMAuthError:
                raise
            except XMError as err:
                _LOGGER.debug("Reconnect to %s failed: %s", self.host, err)
            await asyncio.sleep(retry_delay)

    async def _keepalive_loop(self) -> None:
        while True:
            await asyncio.sleep(self.alive_interval)
            try:
                await self.request(KEEPALIVE, "KeepAlive")
            except XMError as err:
                _LOGGER.debug("Keepalive to %s failed: %s", self.host, err)
                await self._disconnect()
                return

    async def _read_loop(self) -> None:
        assert self._reader
        try:
            while True:
                header = await self._reader.readexactly(HEADER.size)
                _, _, _, _, msg_id, length = HEADER.unpack(header)
                body = await self._reader.readexactly(length)
                if msg_id == ALARM:
                    self._dispatch_alarm(body)
                elif self._pending and not self._pending.done():
                    self._pending.set_result((msg_id, body))
                else:
                    _LOGGER.debug("Unexpected message %s from %s", msg_id, self.host)
        except (asyncio.IncompleteReadError, OSError) as err:
            if self._pending and not self._pending.done():
                self._pending.set_exception(XMError(f"connection lost: {err}"))
            await self._disconnect()

    def _dispatch_alarm(self, body: bytes) -> None:
        try:
            info = _decode(body).get("AlarmInfo") or {}
        except ValueError:
            return
        _LOGGER.debug("Alarm from %s: %s", self.host, info)
        if self.on_alarm:
            try:
                self.on_alarm(info)
            except Exception:  # noqa: BLE001 - a listener bug must not kill the connection
                _LOGGER.exception("Alarm callback failed")

    # --- requests ---------------------------------------------------------------------------

    async def _send(self, msg_id: int, payload: dict, raw: bool = False) -> dict | bytes:
        if not self._writer:
            raise XMError("not connected")
        if self._session:
            payload = {**payload, "SessionID": self.session_id}
        body = json.dumps(payload).encode() + b"\n\0"
        self._pending = asyncio.get_running_loop().create_future()
        self._writer.write(HEADER.pack(0xFF, 0, self._session, self._sequence, msg_id, len(body)) + body)
        self._sequence += 1
        try:
            await self._writer.drain()
            reply_id, data = await asyncio.wait_for(self._pending, self.timeout)
        except asyncio.TimeoutError as err:
            await self._disconnect()
            raise XMError(f"no reply to message {msg_id}") from err
        except OSError as err:
            await self._disconnect()
            raise XMError(str(err)) from err
        finally:
            self._pending = None
        if raw and data[:2] == b"\xff\xd8":
            return data
        try:
            return _decode(data)
        except ValueError as err:
            raise XMError(f"unreadable reply to message {msg_id} (got {reply_id})") from err

    async def _command(self, msg_id: int, name: str, body: dict | None = None, raw: bool = False):
        payload: dict = {"Name": name}
        if body is not None:
            payload[name] = body
        reply = await self._send(msg_id, payload, raw)
        if isinstance(reply, dict) and reply.get("Ret") not in RET_OK:
            raise XMError(f"{name or msg_id} failed (Ret {reply.get('Ret')})")
        return reply

    async def request(self, msg_id: int, name: str, body=None, raw: bool = False):
        """Send one command, logging in first if needed. Returns the reply dict (or JPEG bytes)."""
        async with self._lock:
            await self._connect()
            return await self._command(msg_id, name, body, raw)

    # --- high level -------------------------------------------------------------------------

    async def system_info(self) -> dict:
        return (await self.request(SYSINFO, "SystemInfo"))["SystemInfo"]

    async def get_config(self, name: str):
        return (await self.request(CONFIG_GET, name))[name]

    async def set_config(self, name: str, value) -> None:
        await self.request(CONFIG_SET, name, value)

    async def ability(self, name: str):
        return (await self.request(ABILITY_GET, name))[name]

    async def snapshot(self) -> bytes:
        data = await self.request(SNAPSHOT, "OPSNAP", {"Channel": 0}, raw=True)
        if not isinstance(data, bytes):
            raise XMError("snapshot did not return a JPEG")
        return data

    async def get_time(self) -> datetime:
        reply = await self.request(TIME_QUERY, "OPTimeQuery")
        return datetime.strptime(reply["OPTimeQuery"], "%Y-%m-%d %H:%M:%S")

    async def set_time(self, local: datetime) -> None:
        """Set the camera clock (it keeps local time; System.TimeZone only affects ONVIF UTC)."""
        await self.request(OPERATION, "OPTimeSetting", local.strftime("%Y-%m-%d %H:%M:%S"))

    async def reboot(self) -> None:
        await self.request(OPERATION, "OPMachine", {"Action": "Reboot"})

    async def ptz(self, command: str, preset: int = PTZ_START, step: int = 5, tour: int = 0) -> None:
        """Raw OPPTZControl. command is a DVRIP name (DirectionLeft, GotoPreset, StartTour, ...)."""
        await self.request(PTZ, "OPPTZControl", {"Command": command, "Parameter": {
            "AUX": {"Number": 0, "Status": "On"}, "Channel": 0, "MenuOpts": "Enter",
            "POINT": {"bottom": 0, "left": 0, "right": 0, "top": 0}, "Pattern": "SetBegin",
            "Preset": preset, "Step": step, "Tour": tour,
        }})

    async def ptz_move(self, direction: str, speed: int = 5) -> None:
        """Start moving; keeps going until ptz_stop(direction)."""
        await self.ptz(PTZ_COMMANDS[direction], PTZ_START, speed)

    async def ptz_stop(self, direction: str = "left") -> None:
        await self.ptz(PTZ_COMMANDS[direction], PTZ_STOP)

    async def ptz_step(self, direction: str, speed: int = 5, duration: float = 0.5) -> None:
        await self.ptz_move(direction, speed)
        try:
            await asyncio.sleep(duration)
        finally:
            await self.ptz_stop(direction)

    async def preset(self, action: str, number: int) -> None:
        """action: GotoPreset, SetPreset or ClearPreset."""
        await self.ptz(action, number)

    async def tour(self, start: bool) -> None:
        await self.ptz("StartTour" if start else "StopTour", PTZ_STOP, tour=1)


def _decode(body: bytes) -> dict:
    return json.loads(body.rstrip(b"\0\n ").decode("utf-8", "replace"))
