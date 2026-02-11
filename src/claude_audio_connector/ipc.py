from __future__ import annotations

import asyncio
import os
from typing import Callable, Awaitable, Optional

from .runtime import socket_path


class IpcServer:
    def __init__(self, path: str | None = None, tts_fn: Callable[[str], Awaitable[None]] | None = None) -> None:
        self._path = path or socket_path()
        self._tts_fn = tts_fn
        self._server: asyncio.AbstractServer | None = None
        self._waiter: Optional[asyncio.StreamWriter] = None
        self._waiter_ready = asyncio.Event()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        try:
            if os.path.exists(self._path):
                os.remove(self._path)
        except OSError:
            pass
        self._server = await asyncio.start_unix_server(self._handle, path=self._path)

    async def close(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        async with self._lock:
            if self._waiter:
                self._waiter.close()
                self._waiter = None
        try:
            if os.path.exists(self._path):
                os.remove(self._path)
        except OSError:
            pass

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            line = await asyncio.wait_for(reader.readline(), timeout=5)
        except (OSError, asyncio.TimeoutError):
            writer.close()
            return

        cmd = line.decode("utf-8", errors="replace").strip()

        if cmd == "WAIT":
            async with self._lock:
                if self._waiter:
                    self._waiter.close()
                self._waiter = writer
                self._waiter_ready.set()

        elif cmd.startswith("SPEAK:"):
            text = cmd[6:]
            if self._tts_fn and text:
                try:
                    await self._tts_fn(text)
                except Exception:
                    pass
            try:
                writer.write(b"OK\n")
                await writer.drain()
            except OSError:
                pass
            writer.close()

        else:
            writer.close()

    @property
    def has_waiter(self) -> bool:
        return self._waiter is not None

    async def wait_for_waiter(self, stop_event: asyncio.Event) -> None:
        while not self.has_waiter and not stop_event.is_set():
            self._waiter_ready.clear()
            try:
                await asyncio.wait_for(self._waiter_ready.wait(), timeout=0.5)
            except asyncio.TimeoutError:
                pass

    async def send(self, text: str) -> bool:
        async with self._lock:
            if not self._waiter:
                return False
            writer = self._waiter
            self._waiter = None

        try:
            writer.write(text.encode("utf-8") + b"\n")
            await writer.drain()
        finally:
            writer.close()
        return True


async def wait_for_message(path: str | None = None) -> str | None:
    sock_path = path or socket_path()
    try:
        reader, writer = await asyncio.open_unix_connection(sock_path)
    except OSError:
        return None

    writer.write(b"WAIT\n")
    await writer.drain()

    try:
        data = await reader.readline()
    except OSError:
        data = b""

    writer.close()
    return data.decode("utf-8").strip() if data else None


async def speak_via_daemon(text: str, path: str | None = None) -> bool:
    sock_path = path or socket_path()
    try:
        reader, writer = await asyncio.open_unix_connection(sock_path)
    except OSError:
        return False

    writer.write(f"SPEAK:{text}\n".encode("utf-8"))
    await writer.drain()

    try:
        await asyncio.wait_for(reader.readline(), timeout=60)
    except (OSError, asyncio.TimeoutError):
        pass

    writer.close()
    return True
