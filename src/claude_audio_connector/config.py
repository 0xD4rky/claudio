from dataclasses import dataclass
import os
from pathlib import Path


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


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
    stt_vad: bool
    stt_high_vad: bool
    stt_streaming: bool
    stt_streaming_max_wait_ms: int
    audio_blocksize: int
    audio_queue_ms: int
    local_vad: bool
    local_vad_mode: int
    local_vad_threshold: float
    local_vad_preroll_ms: int
    local_vad_hold_ms: int
    local_vad_noise_ms: int
    local_vad_multiplier: float
    no_speech_timeout: float
    max_utterance_sec: float
    mic_gain: float
    socket_path: str
    cartesia_api_key: str
    cartesia_voice_id: str
    tts_speed: str
    tts_sample_rate: int
    tts_barge_in: bool


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
        stt_vad=_env_bool("SARVAM_STT_VAD", True),
        stt_high_vad=_env_bool("SARVAM_STT_HIGH_VAD", True),
        stt_streaming=_env_bool("SARVAM_STT_STREAMING", True),
        stt_streaming_max_wait_ms=_env_int("SARVAM_STT_STREAMING_MAX_WAIT_MS", 1500),
        audio_blocksize=_env_int("AUDIO_BLOCKSIZE", 320),
        audio_queue_ms=_env_int("AUDIO_QUEUE_MS", 2000),
        local_vad=_env_bool("LOCAL_VAD", True),
        local_vad_mode=_env_int("LOCAL_VAD_MODE", 2),
        local_vad_threshold=_env_float("LOCAL_VAD_THRESHOLD", 0.003),
        local_vad_preroll_ms=_env_int("LOCAL_VAD_PREROLL_MS", 500),
        local_vad_hold_ms=_env_int("LOCAL_VAD_HOLD_MS", 250),
        local_vad_noise_ms=_env_int("LOCAL_VAD_NOISE_MS", 300),
        local_vad_multiplier=_env_float("LOCAL_VAD_MULTIPLIER", 3.0),
        no_speech_timeout=_env_float("NO_SPEECH_TIMEOUT", 10.0),
        max_utterance_sec=_env_float("MAX_UTTERANCE_SEC", 20.0),
        mic_gain=_env_float("MIC_GAIN", 1.0),
        socket_path=socket_path(),
        cartesia_api_key=_env_str("CARTESIA_API_KEY", ""),
        cartesia_voice_id=_env_str("CARTESIA_VOICE_ID", "e07c00bc-4134-4eae-9ea4-1a55fb45746b"),
        tts_speed=_env_str("TTS_SPEED", "fast"),
        tts_sample_rate=_env_int("TTS_SAMPLE_RATE", 24000),
        tts_barge_in=_env_bool("TTS_BARGE_IN", False),
    )
