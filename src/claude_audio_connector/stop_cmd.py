import os
import signal
import sys

PID_PATH = "/tmp/claude-audio.pid"
FILES = (
    "/tmp/claude-audio.pid",
    "/tmp/claude-audio.msg",
    "/tmp/claude-audio.ready",
    "/tmp/claude-audio.status",
)


def main() -> None:
    if os.path.exists(PID_PATH):
        try:
            pid = int(open(PID_PATH).read().strip())
            os.kill(pid, signal.SIGTERM)
        except (OSError, ValueError):
            pass

    for f in FILES:
        try:
            os.remove(f)
        except OSError:
            pass

    print("Voice mode off.")


if __name__ == "__main__":
    main()
