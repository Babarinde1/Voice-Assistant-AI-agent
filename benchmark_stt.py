"""Compare Whisper model sizes on THIS computer.

Run: python benchmark_stt.py
It records one clip, then transcribes it with each model size and prints
load time, transcription time, and what each model heard. The first run of
each size downloads that model (internet needed once).
"""
import sys
import time

import numpy as np

from audio.microphone import (
    SAMPLE_RATE,
    MicrophoneError,
    is_silent,
    record_until_enter,
)
from audio.speech_recognition import SpeechRecognizer
from config import config

SIZES = sys.argv[1:] or ["tiny.en", "base.en", "small.en"]


def main():
    print("Press Enter once to stop. Start speaking right away, e.g. 'can you please open Chrome',")
    print("then press Enter as soon as you finish (the clip is cut off at 10 seconds).")
    try:
        audio = record_until_enter(config.audio_input_device, 10)
    except MicrophoneError as error:
        print(error)
        return

    seconds = audio.size / SAMPLE_RATE
    if is_silent(audio):
        print("Recorded silence. Run audio_check.py first.")
        return

    peak = float(np.max(np.abs(audio)))
    print(f"\nYour voice peaked at {peak:.2f} (healthy is 0.30 to 0.90).")
    if peak < 0.3:
        boost = min(8.0, round(0.7 / max(peak, 0.01), 1))
        print(f"That is quiet. Boosting this clip x{boost} for a fair test. "
              f"Use MIC_GAIN={boost} in .env for real use.")
        audio = np.clip(audio * boost, -1.0, 1.0).astype(np.float32)

    print(f"\nClip length: {seconds:.1f}s\n")
    print(f"{'model':<10} {'load':>7} {'transcribe':>11}  heard")

    for size in SIZES:
        try:
            t0 = time.monotonic()
            recognizer = SpeechRecognizer(
                size, config.stt_language, config.stt_cpu_threads
            )
            load = time.monotonic() - t0

            recognizer.transcribe(audio)            # warm-up run (first run is always slower)
            t1 = time.monotonic()
            heard = recognizer.transcribe(audio)
            took = time.monotonic() - t1
        except Exception as error:
            print(f"{size:<10} failed: {error}")
            continue

        print(f"{size:<10} {load:>6.1f}s {took:>10.1f}s  {heard!r}")

    print("\n'load' happens once when Jarvis starts. 'transcribe' is the wait after each request")
    print("(second run, so it excludes the one-time warm-up). If every model hears '', your clip")
    print("was too quiet or empty: run it again, speak louder and closer, and press Enter right after.")


if __name__ == "__main__":
    main()
