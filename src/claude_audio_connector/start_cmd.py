import os
import signal
import subprocess
import sys
import time

from .config import load_env_from_args
from .runtime import runtime_path, socket_path

PID_PATH = runtime_path("pid")
STATUS_PATH = runtime_path("status")


def _kill_all_daemons() -> None:
    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude_audio_connector.daemon"],
            capture_output=True, text=True, check=False,
        )
    except Exception:
        return
    for line in result.stdout.strip().splitlines():
        pid = int(line.strip())
        if pid == os.getpid():
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def main() -> None:
    load_env_from_args(sys.argv[1:])
    _kill_all_daemons()
    time.sleep(0.3)

    for f in (PID_PATH, STATUS_PATH, socket_path()):
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

    for _ in range(30):
        if os.path.exists(PID_PATH):
            print("Voice mode on.")
            return
        time.sleep(0.2)

    print("Failed to start daemon.")
    sys.exit(1)


if __name__ == "__main__":
    main()
