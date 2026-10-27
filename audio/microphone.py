"""Microphone capture (Stage 3: push-to-talk).

Records 16 kHz mono audio, which is what Whisper expects. Press Enter to
stop. sounddevice is imported lazily so the typed mode still works if the
package is not installed.
"""
import sys
import time

import numpy as np

try:  # Windows
    import msvcrt
except ImportError:  # Linux/macOS, only so the code can be tested elsewhere
    msvcrt = None
    import select

SAMPLE_RATE = 16000
MIN_SECONDS = 0.3       # shorter than this is treated as an accidental press
SILENCE_PEAK = 0.005    # peak volume below this almost certainly means a dead mic


class MicrophoneError(RuntimeError):
    pass


def _import_sounddevice():
    try:
        import sounddevice as sd
    except ImportError as error:
        raise MicrophoneError(
            "The 'sounddevice' package is not installed. "
            "Run: pip install sounddevice"
        ) from error
    return sd


def _parse_device(device: str | None):
    if device is None:
        return None
    return int(device) if device.isdigit() else device


def _enter_pressed() -> bool:
    if msvcrt is not None:
        while msvcrt.kbhit():
            if msvcrt.getwch() in ("\r", "\n"):
                return True
        return False

    ready, _, _ = select.select([sys.stdin], [], [], 0)
    if ready:
        sys.stdin.readline()
        return True
    return False


def peak_level(audio: np.ndarray) -> float:
    return float(np.max(np.abs(audio))) if audio.size else 0.0


def list_input_devices() -> list[str]:
    sd = _import_sounddevice()
    lines = []
    for index, device in enumerate(sd.query_devices()):
        if device["max_input_channels"] > 0:
            lines.append(f"{index}: {device['name']}")
    return lines


def record_until_enter(
    device: str | None = None,
    max_seconds: float = 15.0,
) -> np.ndarray:
    """Record from the microphone until Enter is pressed (or max_seconds)."""
    sd = _import_sounddevice()
    chunks: list[np.ndarray] = []

    def on_audio(indata, frame_count, time_info, status):
        chunks.append(indata.copy())

    try:
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            device=_parse_device(device),
            callback=on_audio,
        )
    except Exception as error:
        raise MicrophoneError(f"Could not open the microphone: {error}") from error

    started = time.monotonic()
    with stream:
        while not _enter_pressed():
            if time.monotonic() - started >= max_seconds:
                break
            time.sleep(0.05)

    if not chunks:
        return np.zeros(0, dtype=np.float32)

    return np.concatenate(chunks).reshape(-1)


def is_too_short(audio: np.ndarray) -> bool:
    return audio.size < int(MIN_SECONDS * SAMPLE_RATE)


def is_silent(audio: np.ndarray) -> bool:
    return peak_level(audio) < SILENCE_PEAK
