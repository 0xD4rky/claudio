import asyncio

import sys
import time

from sarvamai import SarvamAI

from .audio_utils import chunks_to_wav, mic_stream, rms, trim_silence
from .config import load_config, load_env_from_args

NO_SPEECH_TIMEOUT = 10
SILENCE_AFTER_SPEECH = 1.0
ENERGY_THRESHOLD = 0.005


def capture_audio(cfg) -> list[bytes]:
    loop = asyncio.new_event_loop()
    chunks: list[bytes] = []
    started = time.monotonic()
    last_voice = 0.0
    heard_speech = False

    async def record():
        nonlocal last_voice, heard_speech
        audio_q: asyncio.Queue = asyncio.Queue()
        with mic_stream(audio_q, cfg.stt_sample_rate, device=cfg.stt_input_device):
            while True:
                audio = await audio_q.get()
                chunks.append(audio)
                now = time.monotonic()
                energy = rms(audio)

                if energy >= ENERGY_THRESHOLD:
                    last_voice = now
                    if not heard_speech:
                        heard_speech = True
                        sys.stderr.write("🗣️  Speech detected...\n")
                        sys.stderr.flush()

                if not heard_speech and now - started > NO_SPEECH_TIMEOUT:
                    break
                if heard_speech and now - last_voice > SILENCE_AFTER_SPEECH:
                    break

    loop.run_until_complete(record())
    loop.close()
    return chunks


def main() -> None:
    load_env_from_args(sys.argv[1:])
    cfg = load_config()
    client = SarvamAI(api_subscription_key=cfg.api_key)

    sys.stderr.write("🎤 Listening... (speak now)\n")
    sys.stderr.flush()

    chunks = capture_audio(cfg)
    trimmed = trim_silence(chunks)

    if not trimmed:
        sys.stderr.write("(no speech detected)\n")
        sys.stderr.flush()
        return

    sys.stderr.write("⏳ Transcribing...\n")
    sys.stderr.flush()

    wav = chunks_to_wav(trimmed, cfg.stt_sample_rate)
    resp = client.speech_to_text.transcribe(
        file=wav,
        language_code=cfg.stt_language,
        model=cfg.stt_model,
    )
    text = (resp.transcript or "").strip()
    if text and text != "<nospeech>":
        sys.stderr.write(f"📝 {text}\n")
        sys.stderr.flush()
        sys.stdout.write(text + "\n")
    else:
        sys.stderr.write("(no speech detected)\n")
        sys.stderr.flush()


if __name__ == "__main__":
    main()
