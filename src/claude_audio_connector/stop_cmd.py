import os
import signal
import subprocess

from .runtime import runtime_path, socket_path

FILES = (
    runtime_path("pid"),
    runtime_path("status"),
    socket_path(),
)


def main() -> None:
    try:
        result = subprocess.run(
            ["pgrep", "-f", "claude_audio_connector.daemon"],
            capture_output=True, text=True, check=False,
        )
        for line in result.stdout.strip().splitlines():
            try:
                os.kill(int(line.strip()), signal.SIGTERM)
            except (OSError, ValueError):
                pass
    except Exception:
        pass

    for f in FILES:
        try:
            os.remove(f)
        except OSError:
            pass

    print("Voice mode off.")


if __name__ == "__main__":
    main()
