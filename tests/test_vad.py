import unittest
from array import array

from claude_audio_connector.audio_utils import VadConfig, VoiceActivityDetector


def make_frame(amp: int, samples: int = 320) -> bytes:
    data = array("h", [amp] * samples)
    return data.tobytes()


class TestVad(unittest.TestCase):
    def test_adaptive_threshold(self) -> None:
        cfg = VadConfig(
            sample_rate=16000,
            blocksize=320,
            use_local_vad=False,
            vad_mode=2,
            energy_threshold=0.001,
            noise_ms=60,
            noise_multiplier=3.0,
        )
        vad = VoiceActivityDetector(cfg)

        # Build noise floor
        for _ in range(3):
            self.assertFalse(vad.is_speech(make_frame(200)))

        # Below adaptive threshold
        self.assertFalse(vad.is_speech(make_frame(400)))
        # Above adaptive threshold
        self.assertTrue(vad.is_speech(make_frame(800)))
