import sys
import warnings

import sounddevice as sd
from cartesia import Cartesia

warnings.filterwarnings("ignore", category=DeprecationWarning, module="cartesia")

from .config import load_config, load_env_from_args

SPEED_MAP = {
    "slowest": -1.0,
    "slow": -0.5,
    "normal": 0.0,
    "fast": 0.25,
    "fastest": 0.5,
}


def speak(text: str, cfg=None) -> None:
    if cfg is None:
        cfg = load_config()
    if not cfg.cartesia_api_key:
        return

    client = Cartesia(api_key=cfg.cartesia_api_key)
    sr = cfg.tts_sample_rate
    speed = SPEED_MAP.get(cfg.tts_speed, 0.5)

    with sd.RawOutputStream(samplerate=sr, channels=1, dtype="int16") as stream:
        for chunk in client.tts.bytes(
            model_id="sonic-2",
            transcript=text,
            voice={"mode": "id", "id": cfg.cartesia_voice_id},
            output_format={
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": sr,
            },
            speed=speed,
            language="en",
        ):
            stream.write(chunk)


def main() -> None:
    load_env_from_args(sys.argv[1:])
    cfg = load_config()
    text = " ".join(sys.argv[1:]).strip()
    if not text:
        text = sys.stdin.read().strip()
    if not text:
        return
    speak(text, cfg)


if __name__ == "__main__":
    main()
