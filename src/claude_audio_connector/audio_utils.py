import asyncio
import io
import wave
from array import array
from collections import deque

import sounddevice as sd

MIC_GAIN = 15
PREROLL_CHUNKS = 25  # ~0.5s at 320 samples / 16kHz


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


def amplify(data: bytes, gain: int = MIC_GAIN) -> bytes:
    samples = array("h")
    samples.frombytes(data)
    for i in range(len(samples)):
        samples[i] = max(-32768, min(32767, samples[i] * gain))
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


def chunks_to_wav(chunks: list[bytes], sample_rate: int) -> io.BytesIO:
    amplified = b"".join(amplify(c) for c in chunks)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(amplified)
    buf.seek(0)
    return buf


def mic_stream(audio_q: asyncio.Queue, sample_rate: int, device: str | None = None) -> sd.RawInputStream:
    loop = asyncio.get_running_loop()

    def callback(indata, frames, time, status) -> None:
        loop.call_soon_threadsafe(audio_q.put_nowait, bytes(indata))

    dev_id = resolve_device(device)
    return sd.RawInputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        blocksize=320,
        callback=callback,
        device=dev_id,
    )
