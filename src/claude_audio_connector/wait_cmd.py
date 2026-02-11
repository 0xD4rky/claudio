import asyncio
import os
import sys
import time

from .ipc import wait_for_message
from .runtime import runtime_path, socket_path

PID_PATH = runtime_path("pid")
STATUS_PATH = runtime_path("status")

STATES = {
    "idle": "Listening...",
    "error": "Error",
}


def main() -> None:
    if not os.path.exists(PID_PATH):
        sys.stderr.write("(voice daemon not running)\n")
        sys.exit(1)

    last_shown = ""

    try:
        # Kick off wait in background while we still show status
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        wait_task = loop.create_task(wait_for_message(socket_path()))

        while True:
            loop.run_until_complete(asyncio.sleep(0))
            if wait_task.done():
                text = wait_task.result()
                if text is None:
                    wait_task = loop.create_task(wait_for_message(socket_path()))
                else:
                    if text:
                        sys.stdout.write(text + "\n")
                    return

            if not os.path.exists(PID_PATH):
                return

            status = ""
            try:
                with open(STATUS_PATH, "r") as f:
                    status = f.read().strip()
            except OSError:
                pass

            if status.startswith("heard:"):
                display = f"heard: \"{status[6:]}\""
            else:
                display = STATES.get(status, STATES["idle"])

            if display != last_shown:
                sys.stderr.write(f"\r\033[K\033[2m{display}\033[0m")
                sys.stderr.flush()
                last_shown = display

            time.sleep(0.08)
    finally:
        try:
            if not wait_task.done():
                wait_task.cancel()
                try:
                    loop.run_until_complete(wait_task)
                except (asyncio.CancelledError, Exception):
                    pass
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
