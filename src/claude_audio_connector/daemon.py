import asyncio
import os
import re
import signal
import sys

from .audio_utils import CaptureConfig, VadConfig, record_utterance
from .config import load_config, load_env_from_args
from .ipc import IpcServer
from .runtime import runtime_path
from .stt import transcribe_chunks

WAKE_RE = re.compile(
    r"^(?:hey|a|ok|okay)\s+(?:claude|cloud|claud|klaud|lord|clod|klaude|clade)[,.:!?\s]*",
    re.IGNORECASE,
)
STOP_PHRASES = {"stop listening", "no audio", "stop audio", "exit audio"}

PID_PATH = runtime_path("pid")
STATUS_PATH = runtime_path("status")


def set_status(status: str) -> None:
    try:
        with open(STATUS_PATH, "w") as f:
            f.write(status)
    except OSError:
        pass


async def run_daemon(cfg) -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            signal.signal(sig, lambda *_: stop_event.set())

    ipc = IpcServer(cfg.socket_path)
    await ipc.start()

    with open(PID_PATH, "w") as f:
        f.write(str(os.getpid()))

    vad_cfg = VadConfig(
        sample_rate=cfg.stt_sample_rate,
        blocksize=cfg.audio_blocksize,
        use_local_vad=cfg.local_vad,
        vad_mode=cfg.local_vad_mode,
        energy_threshold=cfg.local_vad_threshold,
        noise_ms=cfg.local_vad_noise_ms,
        noise_multiplier=cfg.local_vad_multiplier,
    )
    cap_cfg = CaptureConfig(
        sample_rate=cfg.stt_sample_rate,
        blocksize=cfg.audio_blocksize,
        queue_ms=cfg.audio_queue_ms,
        pre_roll_ms=cfg.local_vad_preroll_ms,
        silence_hold_ms=cfg.local_vad_hold_ms,
        no_speech_timeout=cfg.no_speech_timeout,
        max_utterance_sec=cfg.max_utterance_sec,
        vad_config=vad_cfg,
    )

    min_chunks = max(1, int(0.5 * cfg.stt_sample_rate / cfg.audio_blocksize))
    backoff = 0.5

    try:
        while not stop_event.is_set():
            set_status("idle")
            try:
                chunks = await record_utterance(
                    cap_cfg,
                    device=cfg.stt_input_device,
                    on_chunk=None,
                    status_cb=set_status,
                    stop_event=stop_event,
                )
                if len(chunks) < min_chunks or not ipc.has_waiter:
                    continue
                set_status("transcribing")
                text = transcribe_chunks(chunks, cfg)
                backoff = 0.5
            except Exception:
                set_status("error")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 15)
                continue

            if stop_event.is_set():
                break
            if not text:
                continue

            if text.lower().strip() in STOP_PHRASES:
                await ipc.send("STOP_LISTENING")
                return

            match = WAKE_RE.match(text)
            if match:
                prompt = text[match.end() :].strip()
                if prompt:
                    set_status(f"heard:{prompt}")
                    await ipc.send(prompt)
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
