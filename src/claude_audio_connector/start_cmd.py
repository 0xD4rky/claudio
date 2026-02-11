import os
import signal
import subprocess
import sys
import time

from .config import load_env_from_args

PID_PATH = "/tmp/claude-audio.pid"


def main() -> None:
    load_env_from_args(sys.argv[1:])

    if os.path.exists(PID_PATH):
        try:
            old_pid = int(open(PID_PATH).read().strip())
            os.kill(old_pid, signal.SIGTERM)
            time.sleep(0.3)
        except (OSError, ValueError):
            pass

    for f in ("/tmp/claude-audio.msg", "/tmp/claude-audio.ready", "/tmp/claude-audio.status", PID_PATH):
        try:
            os.remove(f)
        except OSError:
            pass

    subprocess.Popen(
        [sys.executable, "-m", "claude_audio_connector.daemon"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    time.sleep(1)

    if os.path.exists(PID_PATH):
        print("Voice mode on.")
    else:
        print("Failed to start daemon.")
        sys.exit(1)


if __name__ == "__main__":
    main()
