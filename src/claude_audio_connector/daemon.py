import asyncio
import os
import re
import signal
import sys
import time


from sarvamai import SarvamAI

from .audio_utils import chunks_to_wav, mic_stream, rms, trim_silence
from .config import load_config, load_env_from_args

ENERGY_THRESHOLD = 0.005
SILENCE_AFTER_SPEECH = 1.0

MSG_PATH = "/tmp/claude-audio.msg"
PID_PATH = "/tmp/claude-audio.pid"
READY_PATH = "/tmp/claude-audio.ready"
STATUS_PATH = "/tmp/claude-audio.status"
WAITING_PATH = "/tmp/claude-audio.waiting"


def post_message(text: str) -> None:
    with open(MSG_PATH, "w") as f:
        f.write(text)
    with open(READY_PATH, "w") as f:
        f.write("1")


def set_status(status: str) -> None:
    try:
        with open(STATUS_PATH, "w") as f:
            f.write(status)
    except OSError:
        pass


WAKE_RE = re.compile(
    r"^(?:hey|a|ok|okay)\s+(?:claude|cloud|claud|klaud|lord|clod|klaude|clade)[,.:!?\s]*",
    re.IGNORECASE,
)
STOP_PHRASES = {"stop listening", "no audio", "stop audio", "exit audio"}


def run_daemon(cfg) -> None:
    client = SarvamAI(api_subscription_key=cfg.api_key)
    loop = asyncio.new_event_loop()

    def transcribe(wav_buf) -> str:
        resp = client.speech_to_text.transcribe(
            file=wav_buf,
            language_code=cfg.stt_language,
            model=cfg.stt_model,
        )
        text = (resp.transcript or "").strip()
        return "" if text == "<nospeech>" else text

    async def listen_loop():
        audio_q: asyncio.Queue = asyncio.Queue()

        with mic_stream(audio_q, cfg.stt_sample_rate, device=cfg.stt_input_device):
            set_status("idle")

            while True:
                chunks: list[bytes] = []
                last_voice = 0.0
                heard_speech = False

                while True:
                    audio = await audio_q.get()
                    now = time.monotonic()
                    energy = rms(audio)
                    chunks.append(audio)

                    if energy >= ENERGY_THRESHOLD:
                        last_voice = now
                        if not heard_speech:
                            heard_speech = True
                            set_status("recording")

                    if not heard_speech:
                        if len(chunks) > 100:
                            chunks = chunks[-50:]
                        continue

                    if now - last_voice > SILENCE_AFTER_SPEECH:
                        break

                trimmed = trim_silence(chunks)
                if not trimmed:
                    set_status("idle")
                    continue

                set_status("transcribing")
                wav = chunks_to_wav(trimmed, cfg.stt_sample_rate)
                text = transcribe(wav)

                if not text:
                    set_status("idle")
                    continue

                if text.lower().strip() in STOP_PHRASES:
                    post_message("STOP_LISTENING")
                    return

                # Only process commands when wait_cmd is active (no queuing)
                if not os.path.exists(WAITING_PATH):
                    set_status("idle")
                    continue

                match = WAKE_RE.match(text)
                if match:
                    prompt = text[match.end():].strip()
                    if prompt:
                        set_status(f"heard:{prompt}")
                        post_message(prompt)

                set_status("idle")

    loop.run_until_complete(listen_loop())
    loop.close()


def cleanup(*_):
    for path in (MSG_PATH, PID_PATH, READY_PATH, STATUS_PATH, WAITING_PATH):
        try:
            os.remove(path)
        except OSError:
            pass
    os._exit(0)


def main() -> None:
    load_env_from_args(sys.argv[1:])
    cfg = load_config()

    for path in (MSG_PATH, READY_PATH, STATUS_PATH, WAITING_PATH):
        try:
            os.remove(path)
        except OSError:
            pass

    with open(PID_PATH, "w") as f:
        f.write(str(os.getpid()))

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    try:
        run_daemon(cfg)
    finally:
        cleanup()


if __name__ == "__main__":
    main()
