"""Hands-free listening on ONE microphone stream.

The same stream waits for "Hey Jarvis", then keeps recording your request
and stops by itself when you stop talking. Using one stream means nothing
is lost between the wake phrase and the start of your request.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import numpy as np

from audio.endpointing import Endpointer, Rechunker

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
BLOCK_SAMPLES = 1280  # 80 ms, the block size openWakeWord prefers


_input_gain = 1.0


def set_input_gain(gain: float) -> None:
    """Boost (or reduce) every microphone block. 1.0 leaves the audio unchanged."""
    global _input_gain
    _input_gain = max(0.1, min(float(gain), 12.0))


def apply_gain(block: np.ndarray, gain: float | None = None) -> np.ndarray:
    gain = _input_gain if gain is None else gain
    if gain == 1.0:
        return block
    boosted = block.astype(np.float32) * gain
    return np.clip(boosted, -32768, 32767).astype(np.int16)


@dataclass
class Capture:
    audio: np.ndarray  # float32, 16 kHz, empty if nothing was captured
    reason: str        # "done" | "no_speech" | "too_short" | "max_length" | "error"
    detail: str = ""


class ListenerError(RuntimeError):
    pass


def block_level(block: np.ndarray) -> float:
    """0..1 loudness for the on-screen orb (log scale, so quiet speech shows)."""
    rms = float(np.sqrt(np.mean((block.astype(np.float32) / 32768.0) ** 2)))
    decibels = 20.0 * np.log10(rms + 1e-6)
    return float(min(1.0, max(0.0, (decibels + 62.0) / 42.0)))


def _parse_device(device):
    if device is None:
        return None
    return int(device) if str(device).isdigit() else device


def _chime() -> None:
    try:
        import winsound

        threading.Thread(target=winsound.Beep, args=(1100, 70), daemon=True).start()
    except Exception:
        pass


class HandsFreeListener:
    def __init__(
        self,
        wake_model,
        vad,
        sd,
        device=None,
        wake_threshold: float = 0.5,
        end_silence_ms: int = 900,
        no_speech_timeout_s: float = 6.0,
        max_seconds: float = 15.0,
        wake_grace_ms: int = 200,
        chime: bool = True,
        on_level=None,
        on_wake=None,
    ):
        self._wake_model = wake_model
        self._vad = vad
        self._sd = sd
        self._device = _parse_device(device)
        self._threshold = wake_threshold
        self._endpoint_args = dict(
            end_silence_ms=end_silence_ms,
            no_speech_timeout_s=no_speech_timeout_s,
            max_seconds=max_seconds,
        )
        self._grace_s = wake_grace_ms / 1000.0
        self._chime = chime
        self._on_level = on_level or (lambda level: None)
        self._on_wake = on_wake or (lambda: None)

    def _open(self):
        try:
            return self._sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=BLOCK_SAMPLES,
                device=self._device,
            )
        except Exception as error:
            raise ListenerError(f"Could not open the microphone: {error}") from error

    def listen(self) -> Capture:
        """Block until 'Hey Jarvis' is heard, then capture one request."""
        # The wake model remembers ~1 second of audio; clear it so the previous
        # "Hey Jarvis" cannot trigger again immediately.
        self._wake_model.reset()

        try:
            with self._open() as stream:
                self._wait_for_wake(stream)
                self._on_wake()
                return self._capture(stream)
        except ListenerError:
            raise
        except KeyboardInterrupt:
            raise
        except Exception as error:
            raise ListenerError(f"Microphone error: {error}") from error

    def _wait_for_wake(self, stream) -> None:
        while True:
            block, _overflowed = stream.read(BLOCK_SAMPLES)
            block = apply_gain(np.asarray(block).reshape(-1))
            self._on_level(block_level(block) * 0.35)  # calm idle shimmer

            scores = self._wake_model.predict(block)
            if max((float(v) for v in scores.values()), default=0.0) >= self._threshold:
                logger.info("Wake phrase detected")
                return

    def _capture(self, stream) -> Capture:
        if self._chime:
            _chime()

        # Ignore the tail of the wake phrase itself ("...jarvis") and the chime.
        deadline = time.monotonic() + self._grace_s
        while time.monotonic() < deadline:
            block, _ = stream.read(BLOCK_SAMPLES)

        if hasattr(self._vad, "reset"):
            self._vad.reset()

        endpointer = Endpointer(self._vad.is_speech, **self._endpoint_args)
        return capture_from_stream(stream, endpointer, self._on_level)


def capture_from_stream(stream, endpointer: Endpointer, on_level=None) -> Capture:
    """Read blocks until the endpointer decides the request is finished."""
    on_level = on_level or (lambda level: None)
    chunker = Rechunker()

    while True:
        block, _ = stream.read(BLOCK_SAMPLES)
        block = apply_gain(np.asarray(block).reshape(-1))
        on_level(block_level(block))

        for frame in chunker.feed(block):
            if endpointer.feed(frame):
                return Capture(endpointer.audio, endpointer.reason)


def record_utterance(
    sd,
    vad,
    device=None,
    end_silence_ms: int = 900,
    no_speech_timeout_s: float = 6.0,
    max_seconds: float = 15.0,
    on_level=None,
) -> Capture:
    """Record one request (no wake word) and stop automatically."""
    try:
        stream_cm = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            blocksize=BLOCK_SAMPLES,
            device=_parse_device(device),
        )
    except Exception as error:
        raise ListenerError(f"Could not open the microphone: {error}") from error

    if hasattr(vad, "reset"):
        vad.reset()

    endpointer = Endpointer(
        vad.is_speech,
        end_silence_ms=end_silence_ms,
        no_speech_timeout_s=no_speech_timeout_s,
        max_seconds=max_seconds,
    )
    with stream_cm as stream:
        return capture_from_stream(stream, endpointer, on_level)
