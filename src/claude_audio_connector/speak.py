import asyncio
import sys

from .config import load_env_from_args
from .ipc import speak_via_daemon
from .runtime import socket_path


def _play_direct(text: str) -> None:
    import warnings
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    import sounddevice as sd
    from cartesia import Cartesia

    from .config import load_config

    cfg = load_config()
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


def main() -> None:
    load_env_from_args(sys.argv[1:])
    text = " ".join(sys.argv[1:]).strip()
    if not text:
        text = sys.stdin.read().strip()
    if not text:
        return

    sent = asyncio.run(speak_via_daemon(text, socket_path()))
    if not sent:
        _play_direct(text)


if __name__ == "__main__":
    main()
