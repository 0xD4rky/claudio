import os
import sys
import time

MSG_PATH = "/tmp/claude-audio.msg"
READY_PATH = "/tmp/claude-audio.ready"
PID_PATH = "/tmp/claude-audio.pid"
STATUS_PATH = "/tmp/claude-audio.status"
WAITING_PATH = "/tmp/claude-audio.waiting"

STATES = {
    "idle": "Listening...",
}


def main() -> None:
    if not os.path.exists(PID_PATH):
        sys.stderr.write("(voice daemon not running)\n")
        sys.exit(1)

    # Signal to the daemon that wait_cmd is active (fast path)
    try:
        with open(WAITING_PATH, "w") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass

    last_shown = ""

    try:
        while True:
            if os.path.exists(READY_PATH):
                try:
                    os.remove(READY_PATH)
                    with open(MSG_PATH, "r") as f:
                        text = f.read().strip()
                    os.remove(MSG_PATH)
                    if text:
                        sys.stdout.write(text + "\n")
                    return
                except OSError:
                    pass

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
        # Clear waiting flag so daemon knows to interrupt next time
        try:
            os.remove(WAITING_PATH)
        except OSError:
            pass


if __name__ == "__main__":
    main()
