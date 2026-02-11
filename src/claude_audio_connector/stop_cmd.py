import os
import signal
import subprocess
import time

from .runtime import runtime_path, socket_path

FILES = (
    runtime_path("pid"),
    runtime_path("status"),
    socket_path(),
)


def _kill_all(sig: int = signal.SIGTERM) -> list[int]:
    pids = []
    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude_audio_connector.daemon"],
            capture_output=True, text=True, check=False,
        )
        for line in result.stdout.strip().splitlines():
            pid = int(line.strip())
            if pid == os.getpid():
                continue
            try:
                os.kill(pid, sig)
                pids.append(pid)
            except (OSError, ValueError):
                pass
    except Exception:
        pass
    return pids


def main() -> None:
    pids = _kill_all(signal.SIGTERM)
    if pids:
        time.sleep(0.5)
        _kill_all(signal.SIGKILL)

    for f in FILES:
        try:
            os.remove(f)
        except OSError:
            pass

    print("Voice mode off.")


if __name__ == "__main__":
    main()
