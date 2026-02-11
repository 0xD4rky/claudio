from __future__ import annotations

import asyncio
import os
from typing import Optional

from .runtime import socket_path


class IpcServer:
    def __init__(self, path: str | None = None) -> None:
        self._path = path or socket_path()
        self._server: asyncio.AbstractServer | None = None
        self._waiter: Optional[asyncio.StreamWriter] = None
        self._lock = asyncio.Lock()

    @property
    def path(self) -> str:
        return self._path

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
            line = await reader.readline()
        except OSError:
            writer.close()
            return

        if line.strip() != b"WAIT":
            writer.close()
            return

        async with self._lock:
            if self._waiter:
                self._waiter.close()
            self._waiter = writer

    @property
    def has_waiter(self) -> bool:
        return self._waiter is not None

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
    if not data:
        return None
    return data.decode("utf-8").strip()
