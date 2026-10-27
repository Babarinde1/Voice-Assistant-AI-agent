"""Decide automatically when you START and STOP speaking.

Pure logic with no microphone code, so it can be tested with fake frames.
Frames are 30 ms of 16 kHz mono int16 audio (480 samples).
"""
from __future__ import annotations

from collections import deque

import numpy as np

FRAME_MS = 30


class Rechunker:
    """Turn microphone blocks of any size into exact 480-sample frames."""

    def __init__(self, frame_samples: int = 480):
        self.frame_samples = frame_samples
        self._buffer = np.zeros(0, dtype=np.int16)

    def feed(self, block: np.ndarray):
        self._buffer = np.concatenate([self._buffer, block.reshape(-1)])
        while self._buffer.size >= self.frame_samples:
            frame = self._buffer[: self.frame_samples]
            self._buffer = self._buffer[self.frame_samples:]
            yield frame


class Endpointer:
    """Feed it frames; it tells you when the utterance is complete.

    reason after finishing:
      "done"       you spoke and then stopped
      "no_speech"  nobody spoke within no_speech_timeout_s
      "too_short"  a click or cough, not a real utterance
      "max_length" you kept talking until the time limit
    """

    def __init__(
        self,
        is_speech,
        end_silence_ms: int = 900,
        no_speech_timeout_s: float = 6.0,
        max_seconds: float = 20.0,
        pre_roll_ms: int = 300,
        min_speech_ms: int = 250,
        start_hits: int = 3,
        start_window: int = 5,
        keep_trailing_ms: int = 300,
    ):
        self.is_speech = is_speech
        self.end_frames = max(1, end_silence_ms // FRAME_MS)
        self.no_speech_frames = int(no_speech_timeout_s * 1000 // FRAME_MS)
        self.max_frames = int(max_seconds * 1000 // FRAME_MS)
        self.min_speech_frames = max(1, min_speech_ms // FRAME_MS)
        self.keep_trailing = keep_trailing_ms // FRAME_MS
        self.start_hits = start_hits

        self._pre_roll = deque(maxlen=max(1, pre_roll_ms // FRAME_MS))
        self._recent = deque(maxlen=start_window)
        self._frames: list[np.ndarray] = []
        self._waiting_frames = 0
        self._silence_run = 0
        self._voiced = 0

        self.speaking = False
        self.finished = False
        self.reason = ""

    def feed(self, frame: np.ndarray) -> bool:
        """Returns True once the utterance is finished."""
        if self.finished:
            return True

        voiced = bool(self.is_speech(frame))

        if not self.speaking:
            self._pre_roll.append(frame)
            self._recent.append(voiced)
            self._waiting_frames += 1

            if sum(self._recent) >= self.start_hits:
                self.speaking = True
                self._frames = list(self._pre_roll)  # keeps the first syllable
                self._voiced = sum(self._recent)
            elif self._waiting_frames >= self.no_speech_frames:
                self._finish("no_speech")
            return self.finished

        self._frames.append(frame)
        if voiced:
            self._voiced += 1
            self._silence_run = 0
        else:
            self._silence_run += 1

        if self._silence_run >= self.end_frames:
            self._finish("done")
        elif len(self._frames) >= self.max_frames:
            self._finish("max_length")
        return self.finished

    def _finish(self, reason: str) -> None:
        self.finished = True
        self.reason = reason
        if reason in {"done", "max_length"} and self._voiced < self.min_speech_frames:
            self.reason = "too_short"

    @property
    def audio(self) -> np.ndarray:
        """float32 audio, as Whisper expects. Empty unless speech was captured."""
        if self.reason not in {"done", "max_length"} or not self._frames:
            return np.zeros(0, dtype=np.float32)

        frames = self._frames
        extra_silence = self._silence_run - self.keep_trailing
        if extra_silence > 0:
            frames = frames[:-extra_silence]
        return (np.concatenate(frames).astype(np.float32)) / 32768.0
