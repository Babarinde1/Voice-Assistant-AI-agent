"""Stage 4: local wake-word detection using openWakeWord.

Audio is processed locally at 16 kHz, mono, signed 16-bit PCM. This module
only detects the wake phrase; it does not send audio to the AI provider.
"""
from __future__ import annotations

import numpy as np

SAMPLE_RATE = 16_000
FRAME_SAMPLES = 1_280  # 80 ms at 16 kHz; a recommended openWakeWord frame size


class WakeWordError(RuntimeError):
    """Raised when wake-word detection cannot start or keep running."""


def _parse_device(device: str | None):
    if device is None:
        return None
    return int(device) if str(device).isdigit() else device


class WakeWordDetector:
    """Wait for the local English phrase 'Hey Jarvis'.

    The model is loaded once and reused between activations. Press Ctrl+C in
    the terminal to stop the listener.
    """

    def __init__(self, device: str | None = None, threshold: float = 0.5):
        if not 0.0 < threshold <= 1.0:
            raise ValueError("wake-word threshold must be greater than 0 and at most 1")

        try:
            import sounddevice as sd
            from openwakeword.model import Model
        except ImportError as error:
            raise WakeWordError(
                "Wake-word dependencies are missing. Run: "
                "pip install openwakeword sounddevice"
            ) from error

        self._sd = sd
        self._device = _parse_device(device)
        self._threshold = threshold

        try:
            self._model = Model(
                wakeword_models=["hey_jarvis"],
                inference_framework="onnx",
            )
        except Exception as error:
            raise WakeWordError(
                "Could not load the 'Hey Jarvis' wake-word model. "
                "Run setup_wake_word.py once, then try again. "
                f"Details: {error}"
            ) from error

    @property
    def model(self):
        """The loaded openWakeWord model (shared with the hands-free listener)."""
        return self._model

    def wait(self) -> None:
        """Block until 'Hey Jarvis' is detected or an error/interrupt occurs."""
        # The model remembers ~1 second of audio. Clear it so the previous
        # "Hey Jarvis" cannot trigger again immediately.
        self._model.reset()
        print("Waiting for wake phrase: 'Hey Jarvis' (Ctrl+C to stop)...")
        try:
            with self._sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=FRAME_SAMPLES,
                device=self._device,
            ) as stream:
                while True:
                    frame, overflowed = stream.read(FRAME_SAMPLES)
                    if overflowed:
                        # A dropped frame is not fatal; continue with the next one.
                        continue

                    scores = self._model.predict(np.asarray(frame).reshape(-1))
                    score = max((float(value) for value in scores.values()), default=0.0)
                    if score >= self._threshold:
                        print(f"Wake phrase detected (score {score:.2f}).")
                        return
        except KeyboardInterrupt:
            raise
        except Exception as error:
            raise WakeWordError(f"Wake-word microphone error: {error}") from error
