from dataclasses import dataclass
import os
from pathlib import Path


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def load_env_file(path: str, override: bool = False) -> None:
    file_path = Path(path).expanduser()
    if not file_path.exists():
        return
    for raw in file_path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"").strip("'")
        if key and (override or key not in os.environ):
            os.environ[key] = value


def load_env_from_args(argv: list[str]) -> None:
    path = None
    override = False
    if "--config" in argv:
        idx = argv.index("--config")
        if idx + 1 >= len(argv):
            raise SystemExit("--config requires a path")
        path = argv[idx + 1]
        override = True
    if not path:
        path = os.getenv("CLAUDE_AUDIO_ENV") or ".env"
    load_env_file(path, override=override)


@dataclass(frozen=True)
class Config:
    api_key: str
    stt_model: str
    stt_language: str
    stt_sample_rate: int
    stt_codec: str
    stt_input_device: str | None
    stt_high_vad: bool
    audio_blocksize: int
    socket_path: str
    cartesia_api_key: str
    cartesia_voice_id: str
    tts_speed: str
    tts_sample_rate: int


def load_config() -> Config:
    api_key = os.getenv("SARVAM_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("SARVAM_API_KEY is required")

    from .runtime import socket_path

    return Config(
        api_key=api_key,
        stt_model=_env_str("SARVAM_STT_MODEL", "saaras:v3"),
        stt_language=_env_str("SARVAM_STT_LANGUAGE", "en-IN"),
        stt_sample_rate=_env_int("SARVAM_STT_SAMPLE_RATE", 16000),
        stt_codec=_env_str("SARVAM_STT_CODEC", "pcm_s16le").lower(),
        stt_input_device=os.getenv("SARVAM_INPUT_DEVICE") or None,
        stt_high_vad=_env_bool("SARVAM_STT_HIGH_VAD", True),
        audio_blocksize=_env_int("AUDIO_BLOCKSIZE", 320),
        socket_path=socket_path(),
        cartesia_api_key=_env_str("CARTESIA_API_KEY", ""),
        cartesia_voice_id=_env_str("CARTESIA_VOICE_ID", "e07c00bc-4134-4eae-9ea4-1a55fb45746b"),
        tts_speed=_env_str("TTS_SPEED", "fast"),
        tts_sample_rate=_env_int("TTS_SAMPLE_RATE", 24000),
    )
