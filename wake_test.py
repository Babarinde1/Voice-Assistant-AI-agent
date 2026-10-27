"""Find out why "Hey Jarvis" is slow or unreliable, and get recommended settings.

Run:  python wake_test.py
Then, for about 25 seconds, say "Hey Jarvis" 5 times at your normal distance,
with a short pause between each. Nothing is saved or sent anywhere.
"""
from __future__ import annotations

import statistics
import time

import numpy as np

from audio.listener import BLOCK_SAMPLES, SAMPLE_RATE, apply_gain
from config import config

TEST_SECONDS = 25


def summarize(attempt_scores: list[float], speech_peak: float, threshold: float, gain: float) -> list[str]:
    """Turn measurements into plain advice. Pure function, so it is unit-tested."""
    tips: list[str] = []
    if speech_peak < 0.02:
        return ["I heard almost nothing. Check the microphone: Windows Settings > System > Sound > Input "
                "(right device selected, not muted, input volume 100), and Settings > Privacy > Microphone "
                "(allow desktop apps). Then run audio_check.py."]
    if speech_peak < 0.15:
        wanted = min(8.0, round(0.5 / max(speech_peak / max(gain, 0.1), 0.01), 1))
        tips.append(f"Your voice is very quiet (peak {speech_peak:.2f}). Raise Windows input volume to 100 "
                    f"and set MIC_GAIN={max(wanted, 2.0)} in .env.")
    elif speech_peak > 0.95:
        tips.append("Your voice is clipping (too loud). Lower the Windows input volume or MIC_GAIN.")

    good = [s for s in attempt_scores if s >= 0.1]
    if not good:
        tips.append("The wake model barely reacted. Say it clearly as 'HEY JAR-VIS', closer to the mic "
                    "(30 to 50 cm), and turn off Windows microphone enhancements "
                    "(Sound > Input > your mic > Properties > Audio enhancements off).")
        return tips

    median = statistics.median(good)
    fired = sum(1 for s in good if s >= threshold)
    tips.append(f"You said it about {len(good)} times; it would have woken Jarvis {fired} times at "
                f"threshold {threshold}. Typical score {median:.2f}.")
    if fired < len(good):
        suggested = round(max(0.2, min(0.45, min(good) * 0.8)), 2)
        if suggested < threshold:
            tips.append(f"Set WAKE_WORD_THRESHOLD={suggested} in .env. Lower values wake more easily but can "
                        "trigger by mistake, so raise it a little if Jarvis wakes by itself.")
    else:
        tips.append("Wake-up looks healthy. If it still feels slow, the delay is after waking "
                    "(speech recognition); check the '(transcribed in X s)' line in the console.")
    return tips


def main() -> None:
    try:
        import sounddevice as sd
        from openwakeword.model import Model
    except ImportError as error:
        raise SystemExit(f"Missing package: {error}. Run: python -m pip install -r requirements.txt")

    model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
    device = int(config.audio_input_device) if str(config.audio_input_device or "").isdigit() \
        else config.audio_input_device
    print(f"Say 'Hey Jarvis' 5 times over the next {TEST_SECONDS} seconds. "
          f"(threshold {config.wake_word_threshold}, MIC_GAIN {config.mic_gain})\n")

    attempts: list[float] = []
    current = 0.0
    quiet_blocks = 0
    speech_peak = 0.0
    started = time.monotonic()
    last_print = 0.0

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                        blocksize=BLOCK_SAMPLES, device=device) as stream:
        model.reset()
        while time.monotonic() - started < TEST_SECONDS:
            block, _ = stream.read(BLOCK_SAMPLES)
            block = apply_gain(np.asarray(block).reshape(-1))
            level = float(np.abs(block).max()) / 32768.0
            score = max((float(v) for v in model.predict(block).values()), default=0.0)

            if level > 0.03:
                speech_peak = max(speech_peak, level)
            if score >= 0.05:
                current = max(current, score)
                quiet_blocks = 0
            else:
                quiet_blocks += 1
                if quiet_blocks >= 8 and current > 0:   # ~0.6 s of calm ends one attempt
                    attempts.append(current)
                    current = 0.0

            now = time.monotonic()
            if now - last_print > 0.15:
                last_print = now
                bar = "#" * int(min(level, 1.0) * 40)
                flag = "  <-- WAKE" if score >= config.wake_word_threshold else ""
                print(f"\rvolume {bar:<40} score {score:4.2f}{flag}      ", end="", flush=True)
    if current > 0:
        attempts.append(current)

    print("\n\nResults")
    for tip in summarize(attempts, speech_peak, config.wake_word_threshold, config.mic_gain):
        print("- " + tip)


if __name__ == "__main__":
    main()
