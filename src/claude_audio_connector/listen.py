import asyncio
import re
import sys

from .audio_utils import CaptureConfig, VadConfig, record_utterance
from .config import load_config, load_env_from_args
from .stt import StreamingTranscriber, streaming_supported, transcribe_chunks

WAKE_RE = re.compile(
    r"^(?:hey|a|ok|okay)\s+(?:claude|cloud|claud|klaud|lord|clod|klaude|clade)[,.:!?\s]*",
    re.IGNORECASE,
)
STOP_PHRASES = {"stop listening", "no audio", "stop audio", "exit audio"}


async def listen_once(cfg) -> str | None:
    """Listen for 'hey claude ...' and return the part after the wake word.
    Returns None if killed externally, empty string on stop command."""
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

    streaming_ok = streaming_supported(cfg)

    while True:
        if streaming_ok:
            with StreamingTranscriber(cfg) as stt:
                chunks = await record_utterance(
                    cap_cfg,
                    device=cfg.stt_input_device,
                    on_chunk=stt.send_pcm,
                    status_cb=None,
                )
                result = stt.finalize(cfg.stt_streaming_max_wait_ms / 1000)
                text = result.transcript.strip() or transcribe_chunks(chunks, cfg)
        else:
            chunks = await record_utterance(
                cap_cfg,
                device=cfg.stt_input_device,
                on_chunk=None,
                status_cb=None,
            )
            text = transcribe_chunks(chunks, cfg)

        if not text:
            sys.stderr.write("  (noise, ignoring)\n")
            sys.stderr.flush()
            continue

        sys.stderr.write(f"  heard: \"{text}\"\n")
        sys.stderr.flush()

        if text.lower().strip() in STOP_PHRASES:
            return ""

        match = WAKE_RE.match(text)
        if match:
            prompt = text[match.end() :].strip()
            if prompt:
                return prompt
            sys.stderr.write("  (wake word only, waiting for more)\n")
            sys.stderr.flush()


def main() -> None:
    load_env_from_args(sys.argv[1:])
    cfg = load_config()

    sys.stderr.write("👂 Listening for 'hey claude'...\n")
    sys.stderr.flush()

    try:
        text = asyncio.run(listen_once(cfg))
    except KeyboardInterrupt:
        return

    if text:
        sys.stderr.write(f"📝 {text}\n")
        sys.stderr.flush()
        sys.stdout.write(text + "\n")
    elif text == "":
        sys.stdout.write("STOP_LISTENING\n")


if __name__ == "__main__":
    main()
