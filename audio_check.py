"""Microphone diagnostic. Run: python audio_check.py"""
from audio.microphone import (
    SAMPLE_RATE,
    MicrophoneError,
    list_input_devices,
    peak_level,
    record_until_enter,
)
from config import config


def main():
    try:
        print("Input devices (number: name):")
        for line in list_input_devices():
            print("  " + line)
    except MicrophoneError as error:
        print(error)
        return

    print()
    print("Using:", config.audio_input_device or "Windows default input device")
    print("Say something for a few seconds, then press Enter.")

    try:
        audio = record_until_enter(config.audio_input_device, 10)
    except MicrophoneError as error:
        print(error)
        return

    seconds = audio.size / SAMPLE_RATE
    peak = peak_level(audio)
    print(f"Recorded {seconds:.1f}s, peak volume {peak:.3f} (0 = silence, 1 = maximum).")

    if peak < 0.005:
        print("Almost silent. Wrong device, muted mic, or Windows microphone privacy setting.")
    elif peak > 0.95:
        print("Very loud, may be distorted. Lower the input volume.")
    else:
        print("Level looks fine.")


if __name__ == "__main__":
    main()
