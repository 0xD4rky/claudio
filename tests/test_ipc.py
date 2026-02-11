import asyncio
import tempfile
import unittest
from pathlib import Path

from claude_audio_connector.ipc import IpcServer, wait_for_message


class TestIpc(unittest.IsolatedAsyncioTestCase):
    async def test_send_wait(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sock = str(Path(tmp) / "ipc.sock")
            server = IpcServer(sock)
            try:
                await server.start()
            except PermissionError as exc:
                self.skipTest(f"unix socket not permitted in sandbox: {exc}")

            waiter = asyncio.create_task(wait_for_message(sock))
            await asyncio.sleep(0.05)

            sent = await server.send("hello")
            self.assertTrue(sent)
            msg = await waiter
            self.assertEqual(msg, "hello")

            await server.close()

    async def test_send_without_waiter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            sock = str(Path(tmp) / "ipc.sock")
            server = IpcServer(sock)
            try:
                await server.start()
            except PermissionError as exc:
                self.skipTest(f"unix socket not permitted in sandbox: {exc}")
            sent = await server.send("noop")
            self.assertFalse(sent)
            await server.close()
