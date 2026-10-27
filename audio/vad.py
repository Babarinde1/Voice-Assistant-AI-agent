"""Voice activity detection: "is someone speaking in this 30 ms frame?"

Two detectors with the same interface, is_speech(frame) -> bool:

* SileroVAD  - a small neural model (bundled with openWakeWord). Best in
               noisy rooms; this is the default when openWakeWord is installed.
* EnergyVAD  - volume-based with an adaptive noise floor. Needs only numpy.
               Works in quiet rooms, can be fooled by constant loud noise.
"""
from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
FRAME_SAMPLES = 480  # 30 ms at 16 kHz


class EnergyVAD:
    def __init__(self, margin: float = 3.0, min_rms: float = 0.006):
        self.margin = margin
        self.min_rms = min_rms
        self._floor: float | None = None
        self._seen = 0

    def reset(self) -> None:
        self._seen = 0  # keep the learned noise floor, it is still valid

    def is_speech(self, frame: np.ndarray) -> bool:
        rms = float(np.sqrt(np.mean((frame.astype(np.float32) / 32768.0) ** 2)))

        if self._floor is None:
            self._floor = rms
        self._seen += 1

        threshold = max(self.min_rms, self._floor * self.margin)
        speech = rms > threshold and self._seen > 3

        if not speech:
            # Follow the room's background noise: fall quickly, rise slowly.
            weight = 0.2 if rms < self._floor else 0.005
            self._floor = (1 - weight) * self._floor + weight * rms
        return speech


class SileroVAD:
    def __init__(self, threshold: float = 0.5, vad=None):
        self.threshold = threshold
        if vad is not None:  # tests can inject a fake
            self._vad = vad
            return
        from openwakeword.vad import VAD  # needs silero_vad.onnx (setup_wake_word.py)

        self._vad = VAD()

    def reset(self) -> None:
        self._vad.reset_states()

    def is_speech(self, frame: np.ndarray) -> bool:
        return float(self._vad.predict(frame, frame_size=FRAME_SAMPLES)) >= self.threshold


def create_vad(engine: str = "auto", threshold: float = 0.5):
    """Return (detector, human-readable name). Never raises."""
    engine = (engine or "auto").lower()

    if engine in {"auto", "silero"}:
        try:
            return SileroVAD(threshold), "Silero neural VAD"
        except Exception as error:
            logger.info("Silero VAD unavailable (%s); using energy VAD", type(error).__name__)

    return EnergyVAD(), "volume-based VAD"
