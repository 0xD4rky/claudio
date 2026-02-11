import asyncio
import os
import sys
import time

from .ipc import wait_for_message
from .runtime import runtime_path, socket_path

PID_PATH = runtime_path("pid")
STATUS_PATH = runtime_path("status")

DISPLAY = {"idle": "Listening...", "error": "Error", "recording": "Recording...", "processing": "Processing..."}


def main() -> None:
    if not os.path.exists(PID_PATH):
        sys.stderr.write("(voice daemon not running)\n")
        sys.exit(1)

    sock = socket_path()
    loop = asyncio.new_event_loop()
    task = loop.create_task(wait_for_message(sock))
    last_shown = ""

    try:
        while True:
            loop.run_until_complete(asyncio.sleep(0))
            if task.done():
                text = task.result()
                if text is None:
                    task = loop.create_task(wait_for_message(sock))
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
                display = f'heard: "{status[6:]}"'
            else:
                display = DISPLAY.get(status, DISPLAY["idle"])

            if display != last_shown:
                sys.stderr.write(f"\r\033[K\033[2m{display}\033[0m")
                sys.stderr.flush()
                last_shown = display

            time.sleep(0.08)
    finally:
        if not task.done():
            task.cancel()
            try:
                loop.run_until_complete(task)
            except (asyncio.CancelledError, Exception):
                pass
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
