from __future__ import annotations

import base64
import threading
import time
from dataclasses import dataclass

from sarvamai import SarvamAI

from .audio_utils import chunks_to_wav


@dataclass
class StreamingResult:
    transcript: str
    error: Exception | None = None


class StreamingTranscriber:
    def __init__(self, cfg) -> None:
        self._cfg = cfg
        self._client = SarvamAI(api_subscription_key=cfg.api_key)
        self._ctx = None
        self._ws = None
        self._thread: threading.Thread | None = None
        self._last_transcript = ""
        self._updated = threading.Event()
        self._stop = threading.Event()
        self._error: Exception | None = None

    def __enter__(self) -> "StreamingTranscriber":
        params = {
            "language_code": self._cfg.stt_language,
            "model": self._cfg.stt_model,
            "sample_rate": str(self._cfg.stt_sample_rate),
            "input_audio_codec": self._cfg.stt_codec,
        }
        if self._cfg.stt_high_vad:
            params["high_vad_sensitivity"] = True
        if self._cfg.stt_vad:
            params["vad_signals"] = True
        self._ctx = self._client.speech_to_text_streaming.connect(**params)
        self._ws = self._ctx.__enter__()
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop.set()
        if self._ctx is not None:
            self._ctx.__exit__(exc_type, exc, tb)
        if self._thread:
            self._thread.join(timeout=0.5)

    def _listen(self) -> None:
        try:
            for message in self._ws:
                if self._stop.is_set():
                    return
                if getattr(message, "type", None) != "data":
                    continue
                data = getattr(message, "data", None)
                transcript = getattr(data, "transcript", "") if data else ""
                if transcript:
                    self._last_transcript = transcript
                    self._updated.set()
        except Exception as exc:  # keep streaming best-effort
            self._error = exc

    def send_pcm(self, chunk: bytes) -> None:
        if self._ws is None:
            return
        codec = (self._cfg.stt_codec or "").lower()
        codec_map = {
            "pcm_s16le": "audio/pcm_s16le",
            "pcm_l16": "audio/pcm_l16",
            "pcm_raw": "audio/pcm_raw",
        }
        encoding = codec_map.get(codec, "audio/pcm_s16le")
        payload = {
            "audio": {
                "data": base64.b64encode(chunk).decode("utf-8"),
                "sample_rate": self._cfg.stt_sample_rate,
                "encoding": encoding,
            }
        }
        try:
            self._ws._send(payload)  # type: ignore[attr-defined]
        except Exception as exc:
            self._error = exc

    def finalize(self, timeout_s: float) -> StreamingResult:
        if self._ws is None:
            return StreamingResult(transcript="")
        try:
            self._ws.flush()
        except Exception as exc:
            self._error = exc

        deadline = time.monotonic() + timeout_s
        last = ""
        while time.monotonic() < deadline:
            remaining = max(0.05, deadline - time.monotonic())
            if not self._updated.wait(timeout=min(0.3, remaining)):
                break
            self._updated.clear()
            last = self._last_transcript
        transcript = last or self._last_transcript
        return StreamingResult(transcript=transcript, error=self._error)


def _normalize_transcript(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned == "<nospeech>":
        return ""
    return cleaned


def transcribe_chunks(chunks: list[bytes], cfg) -> str:
    if not chunks:
        return ""
    wav = chunks_to_wav(chunks, cfg.stt_sample_rate, gain=cfg.mic_gain)
    client = SarvamAI(api_subscription_key=cfg.api_key)
    resp = client.speech_to_text.transcribe(
        file=wav,
        language_code=cfg.stt_language,
        model=cfg.stt_model,
    )
    return _normalize_transcript(resp.transcript or "")


def streaming_supported(cfg) -> bool:
    if not cfg.stt_streaming:
        return False
    if cfg.stt_sample_rate not in {16000, 8000}:
        return False
    return (cfg.stt_codec or "").lower() in {"pcm_s16le", "pcm_l16", "pcm_raw"}
