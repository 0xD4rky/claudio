import asyncio
import re
import sys
import time

from sarvamai import SarvamAI

from .audio_utils import chunks_to_wav, mic_stream, rms, trim_silence
from .config import load_config, load_env_from_args

ENERGY_THRESHOLD = 0.005
SILENCE_AFTER_SPEECH = 2.0

WAKE_RE = re.compile(
    r"^(?:hey|a|ok|okay)\s+(?:claude|cloud|claud|klaud|lord|clod|klaude|clade)[,.:!?\s]*",
    re.IGNORECASE,
)
STOP_PHRASES = {"stop listening", "no audio", "stop audio", "exit audio"}


def transcribe(client: SarvamAI, wav_buf, cfg) -> str:
    resp = client.speech_to_text.transcribe(
        file=wav_buf,
        language_code=cfg.stt_language,
        model=cfg.stt_model,
    )
    text = (resp.transcript or "").strip()
    if text == "<nospeech>":
        return ""
    return text


def listen_once(cfg) -> str | None:
    """Listen for 'hey claude ...' and return the part after the wake word.
    Returns None if killed externally, empty string on stop command."""
    client = SarvamAI(api_subscription_key=cfg.api_key)
    loop = asyncio.new_event_loop()
    result: str | None = None

    async def run():
        nonlocal result
        audio_q: asyncio.Queue = asyncio.Queue()

        with mic_stream(audio_q, cfg.stt_sample_rate, device=cfg.stt_input_device):
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
                        heard_speech = True

                    if not heard_speech:
                        if len(chunks) > 100:
                            chunks = chunks[-50:]
                        continue

                    if now - last_voice > SILENCE_AFTER_SPEECH:
                        break

                trimmed = trim_silence(chunks)
                if not trimmed:
                    continue

                wav = chunks_to_wav(trimmed, cfg.stt_sample_rate)
                text = transcribe(client, wav, cfg)

                if not text:
                    sys.stderr.write("  (noise, ignoring)\n")
                    sys.stderr.flush()
                    continue

                sys.stderr.write(f"  heard: \"{text}\"\n")
                sys.stderr.flush()

                if text.lower().strip() in STOP_PHRASES:
                    result = ""
                    return

                match = WAKE_RE.match(text)
                if match:
                    prompt = text[match.end():].strip()
                    if prompt:
                        result = prompt
                        return
                    sys.stderr.write("  (wake word only, waiting for more)\n")
                    sys.stderr.flush()

    loop.run_until_complete(run())
    loop.close()
    return result


def main() -> None:
    load_env_from_args(sys.argv[1:])
    cfg = load_config()

    sys.stderr.write("👂 Listening for 'hey claude'...\n")
    sys.stderr.flush()

    text = listen_once(cfg)

    if text:
        sys.stderr.write(f"📝 {text}\n")
        sys.stderr.flush()
        sys.stdout.write(text + "\n")
    elif text == "":
        sys.stdout.write("STOP_LISTENING\n")


if __name__ == "__main__":
    main()
