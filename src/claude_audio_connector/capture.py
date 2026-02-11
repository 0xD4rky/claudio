import asyncio
import sys

from .audio_utils import CaptureConfig, VadConfig, record_utterance
from .config import load_config, load_env_from_args
from .stt import StreamingTranscriber, streaming_supported, transcribe_chunks


async def capture_once(cfg) -> str:
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

    sys.stderr.write("🎤 Listening... (speak now)\n")
    sys.stderr.flush()

    streaming_ok = streaming_supported(cfg)
    if streaming_ok:
        with StreamingTranscriber(cfg) as stt:
            chunks = await record_utterance(
                cap_cfg,
                device=cfg.stt_input_device,
                on_chunk=stt.send_pcm,
                status_cb=None,
            )
            result = stt.finalize(cfg.stt_streaming_max_wait_ms / 1000)
            if result.error:
                sys.stderr.write("(streaming error, falling back to batch)\n")
                sys.stderr.flush()
            text = result.transcript.strip()
            if text:
                return text
            return transcribe_chunks(chunks, cfg)

    chunks = await record_utterance(
        cap_cfg,
        device=cfg.stt_input_device,
        on_chunk=None,
        status_cb=None,
    )
    return transcribe_chunks(chunks, cfg)


def main() -> None:
    load_env_from_args(sys.argv[1:])
    cfg = load_config()

    try:
        text = asyncio.run(capture_once(cfg))
    except KeyboardInterrupt:
        return

    if text:
        sys.stderr.write(f"📝 {text}\n")
        sys.stderr.flush()
        sys.stdout.write(text + "\n")
    else:
        sys.stderr.write("(no speech detected)\n")
        sys.stderr.flush()


if __name__ == "__main__":
    main()
