import asyncio
import io
import time
import wave
from array import array
from collections import deque
from dataclasses import dataclass

import sounddevice as sd

try:
    import webrtcvad
except ImportError:  # optional dependency
    webrtcvad = None


def resolve_device(name: str | None) -> int | None:
    if name is None:
        return None
    if name.isdigit():
        return int(name)
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and name.lower() in d["name"].lower():
            return i
    return None


def rms(data: bytes) -> float:
    samples = array("h")
    samples.frombytes(data)
    if not samples:
        return 0.0
    return (sum(s * s for s in samples) / len(samples)) ** 0.5 / 32768.0


def amplify(data: bytes, gain: float) -> bytes:
    samples = array("h")
    samples.frombytes(data)
    for i in range(len(samples)):
        samples[i] = max(-32768, min(32767, int(samples[i] * gain)))
    return samples.tobytes()


def trim_silence(chunks: list[bytes], threshold: float = 0.003) -> list[bytes]:
    start = 0
    for i, chunk in enumerate(chunks):
        if rms(chunk) >= threshold:
            start = max(0, i - PREROLL_CHUNKS)
            break
    end = len(chunks)
    for i in range(len(chunks) - 1, start - 1, -1):
        if rms(chunks[i]) >= threshold:
            end = i + 1
            break
    return chunks[start:end]


def chunks_to_wav(chunks: list[bytes], sample_rate: int, gain: float = 1.0) -> io.BytesIO:
    if gain != 1.0:
        payload = b"".join(amplify(c, gain=gain) for c in chunks)
    else:
        payload = b"".join(chunks)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(payload)
    buf.seek(0)
    return buf


class AsyncAudioQueue:
    def __init__(self, max_chunks: int) -> None:
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=max_chunks)
        self._dropped = 0
        self._loop = asyncio.get_running_loop()

    @property
    def dropped(self) -> int:
        return self._dropped

    def put_from_thread(self, data: bytes) -> None:
        def _push() -> None:
            if self._queue.full():
                try:
                    self._queue.get_nowait()
                    self._dropped += 1
                except asyncio.QueueEmpty:
                    pass
            try:
                self._queue.put_nowait(data)
            except asyncio.QueueFull:
                self._dropped += 1

        self._loop.call_soon_threadsafe(_push)

    async def get(self) -> bytes:
        return await self._queue.get()

    def clear(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break


def mic_stream(
    audio_q: AsyncAudioQueue,
    sample_rate: int,
    blocksize: int,
    device: str | None = None,
) -> sd.RawInputStream:
    def callback(indata, frames, time_info, status) -> None:
        audio_q.put_from_thread(bytes(indata))

    dev_id = resolve_device(device)
    return sd.RawInputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        blocksize=blocksize,
        callback=callback,
        device=dev_id,
    )


@dataclass(frozen=True)
class VadConfig:
    sample_rate: int
    blocksize: int
    use_local_vad: bool
    vad_mode: int
    energy_threshold: float
    noise_ms: int
    noise_multiplier: float


class VoiceActivityDetector:
    def __init__(self, cfg: VadConfig) -> None:
        self._cfg = cfg
        self._vad = None
        if cfg.use_local_vad and webrtcvad is not None:
            frame_ms = int((cfg.blocksize / cfg.sample_rate) * 1000)
            if frame_ms in {10, 20, 30} and cfg.sample_rate in {8000, 16000, 32000}:
                self._vad = webrtcvad.Vad(cfg.vad_mode)
        self._noise_floor = None
        self._noise_alpha = 0.1
        self._noise_frames_target = max(1, int((cfg.noise_ms / 1000) * cfg.sample_rate / cfg.blocksize))
        self._noise_frames = 0

    def is_speech(self, frame: bytes) -> bool:
        if self._vad is not None:
            return self._vad.is_speech(frame, self._cfg.sample_rate)

        energy = rms(frame)
        if self._noise_frames < self._noise_frames_target:
            self._noise_frames += 1
            if self._noise_floor is None:
                self._noise_floor = energy
            else:
                self._noise_floor = (1 - self._noise_alpha) * self._noise_floor + self._noise_alpha * energy
        if self._noise_floor is None:
            threshold = self._cfg.energy_threshold
        else:
            threshold = max(self._cfg.energy_threshold, self._noise_floor * self._cfg.noise_multiplier)
        return energy >= threshold


@dataclass(frozen=True)
class CaptureConfig:
    sample_rate: int
    blocksize: int
    queue_ms: int
    pre_roll_ms: int
    silence_hold_ms: int
    no_speech_timeout: float
    max_utterance_sec: float
    vad_config: VadConfig


async def record_utterance(
    cfg: CaptureConfig,
    *,
    device: str | None = None,
    on_chunk=None,
    status_cb=None,
    stop_event: asyncio.Event | None = None,
) -> list[bytes]:
    max_chunks = max(4, int((cfg.queue_ms / 1000) * cfg.sample_rate / cfg.blocksize))
    audio_q = AsyncAudioQueue(max_chunks=max_chunks)
    vad = VoiceActivityDetector(cfg.vad_config)
    pre_roll_chunks = max(0, int((cfg.pre_roll_ms / 1000) * cfg.sample_rate / cfg.blocksize))
    hold_chunks = max(1, int((cfg.silence_hold_ms / 1000) * cfg.sample_rate / cfg.blocksize))
    max_utterance_chunks = max(1, int(cfg.max_utterance_sec * cfg.sample_rate / cfg.blocksize))

    chunks: list[bytes] = []
    pre_roll: deque[bytes] = deque(maxlen=pre_roll_chunks)
    started = time.monotonic()
    last_voice_chunks = 0
    heard_speech = False

    with mic_stream(audio_q, cfg.sample_rate, cfg.blocksize, device=device):
        while True:
            if stop_event and stop_event.is_set():
                break
            frame = await audio_q.get()
            pre_roll.append(frame)
            speaking = vad.is_speech(frame)
            just_started = False

            if speaking:
                if not heard_speech:
                    heard_speech = True
                    if status_cb:
                        status_cb("recording")
                    if pre_roll:
                        chunks.extend(pre_roll)
                        just_started = True
                    if on_chunk:
                        for pre in pre_roll:
                            on_chunk(pre)
                last_voice_chunks = 0
            elif heard_speech:
                last_voice_chunks += 1

            if heard_speech:
                if not just_started:
                    chunks.append(frame)
                if on_chunk and (speaking or last_voice_chunks <= hold_chunks) and not just_started:
                    on_chunk(frame)
            if not heard_speech and (time.monotonic() - started) > cfg.no_speech_timeout:
                break
            if heard_speech and last_voice_chunks >= hold_chunks:
                break
            if heard_speech and len(chunks) >= max_utterance_chunks:
                break

    if status_cb:
        status_cb("idle")
    return chunks
