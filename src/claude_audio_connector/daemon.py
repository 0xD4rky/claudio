import asyncio
import base64
import io
import os
import re
import signal
import sys
import wave
import warnings

import sounddevice as sd
from sarvamai import AsyncSarvamAI

warnings.filterwarnings("ignore", category=DeprecationWarning)

from .audio_utils import resolve_device
from .config import load_config, load_env_from_args
from .ipc import IpcServer
from .runtime import runtime_path

WAKE_RE = re.compile(
    r"^(?:hey|a|ok|okay)\s+(?:claude|cloud|claud|klaud|lord|clod|klaude|clade)[,.:!?\s]*",
    re.IGNORECASE,
)
STOP_PHRASES = {"stop listening", "no audio", "stop audio", "exit audio"}

PID_PATH = runtime_path("pid")
STATUS_PATH = runtime_path("status")

BATCH_INTERVAL = 0.15


def set_status(status: str) -> None:
    try:
        with open(STATUS_PATH, "w") as f:
            f.write(status)
    except OSError:
        pass


def _pcm_to_wav_b64(pcm: bytes, sample_rate: int) -> str:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return base64.b64encode(buf.getvalue()).decode()


def _play_tts_sync(text: str, cfg) -> None:
    from cartesia import Cartesia

    if not cfg.cartesia_api_key:
        return

    speed_map = {"slowest": -1.0, "slow": -0.5, "normal": 0.0, "fast": 0.25, "fastest": 0.5}
    client = Cartesia(api_key=cfg.cartesia_api_key)

    with sd.RawOutputStream(samplerate=cfg.tts_sample_rate, channels=1, dtype="int16") as stream:
        for chunk in client.tts.bytes(
            model_id="sonic-2",
            transcript=text,
            voice={"mode": "id", "id": cfg.cartesia_voice_id},
            output_format={"container": "raw", "encoding": "pcm_s16le", "sample_rate": cfg.tts_sample_rate},
            speed=speed_map.get(cfg.tts_speed, 0.25),
            language="en",
        ):
            stream.write(chunk)


async def _send_audio_loop(ws, buf: list, sr: int, stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        await asyncio.sleep(BATCH_INTERVAL)
        if not buf:
            continue
        frames = buf[:]
        buf.clear()
        try:
            await ws.transcribe(
                audio=_pcm_to_wav_b64(b"".join(frames), sr),
                encoding="audio/wav",
                sample_rate=sr,
            )
        except Exception:
            return


async def _streaming_loop(client: AsyncSarvamAI, cfg, ipc: IpcServer, stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    buf: list[bytes] = []
    sr = cfg.stt_sample_rate
    dev_id = resolve_device(cfg.stt_input_device)

    def mic_cb(indata, frames, time_info, status):
        loop.call_soon_threadsafe(buf.append, bytes(indata))

    async with client.speech_to_text_streaming.connect(
        model=cfg.stt_model,
        mode="transcribe",
        language_code=cfg.stt_language,
        high_vad_sensitivity="false",
        vad_signals="true",
    ) as ws:
        with sd.RawInputStream(
            samplerate=sr, channels=1, dtype="int16",
            blocksize=cfg.audio_blocksize, callback=mic_cb, device=dev_id,
        ):
            sender = asyncio.create_task(_send_audio_loop(ws, buf, sr, stop_event))
            pending_wake = False

            try:
                async for msg in ws:
                    if stop_event.is_set():
                        return

                    msg_type = str(getattr(msg, "type", ""))
                    data = getattr(msg, "data", None)

                    if msg_type == "events":
                        sig = getattr(data, "signal_type", "") if data else ""
                        if sig == "START_SPEECH":
                            set_status("recording")
                        elif sig == "END_SPEECH":
                            set_status("processing")

                    elif msg_type == "data":
                        text = (getattr(data, "transcript", "") or "").strip()
                        if not text or text == "<nospeech>":
                            set_status("idle")
                            continue

                        if not ipc.has_waiter:
                            pending_wake = False
                            set_status("idle")
                            continue

                        if text.lower().strip() in STOP_PHRASES:
                            await ipc.send("STOP_LISTENING")
                            return

                        if pending_wake:
                            set_status(f"heard:{text}")
                            await ipc.send(text)
                            pending_wake = False
                            set_status("idle")
                            continue

                        match = WAKE_RE.match(text)
                        if match:
                            prompt = text[match.end():].strip()
                            if prompt:
                                set_status(f"heard:{prompt}")
                                await ipc.send(prompt)
                            else:
                                pending_wake = True
                                set_status("idle")
                                continue

                        set_status("idle")
            finally:
                sender.cancel()
                try:
                    await sender
                except asyncio.CancelledError:
                    pass


async def run_daemon(cfg) -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())

    async def tts_fn(text: str) -> None:
        await loop.run_in_executor(None, _play_tts_sync, text, cfg)

    ipc = IpcServer(cfg.socket_path, tts_fn=tts_fn)
    await ipc.start()

    with open(PID_PATH, "w") as f:
        f.write(str(os.getpid()))

    client = AsyncSarvamAI(api_subscription_key=cfg.api_key)
    backoff = 0.5

    try:
        while not stop_event.is_set():
            set_status("idle")
            try:
                await _streaming_loop(client, cfg, ipc, stop_event)
                backoff = 0.5
            except Exception:
                set_status("error")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15)
    finally:
        await ipc.close()
        for path in (PID_PATH, STATUS_PATH):
            try:
                os.remove(path)
            except OSError:
                pass


def main() -> None:
    load_env_from_args(sys.argv[1:])
    cfg = load_config()

    try:
        asyncio.run(run_daemon(cfg))
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
