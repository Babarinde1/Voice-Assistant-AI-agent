# Stage 4: Local wake-word detection

This stage adds local detection of **“Hey Jarvis”** using openWakeWord. The wake-word model processes microphone frames on this PC; it does not send them to Groq. The existing typed Stage 3 workflow remains the default.

## 1. Install the dependency

Run these commands from the project folder, using the same Python environment you use for `main.py`:

```powershell
python -m pip install openwakeword
```

`sounddevice` is already required by Stage 3. If it is missing, run `python -m pip install sounddevice`.

## 2. Download the model files once

While connected to the internet, run:

```powershell
python setup_wake_word.py
```

The model files are cached locally. After setup, wake-word inference is local.

## 3. Start Stage 4

```powershell
python main.py --wake
```

Say **“Hey Jarvis”**, pause briefly while the microphone stream switches to command capture, speak your request, then press **Enter** to finish recording. For example, say “Hey Jarvis”, pause, say “open Chrome”, then press Enter. Jarvis sends the transcript through the same local command router used in Stage 3. General questions can use the configured Groq fallback.

Stop the listener with **Ctrl+C**. Use `python main.py` without `--wake` to return to Stage 3 typed/push-to-talk mode.

## Important limitation in this incremental stage

Wake-word detection is hands-free, but command recording still uses Stage 3's Enter-to-stop behavior. Automatic silence-based end-of-utterance detection can be added in a later iteration after the wake-word model and microphone device have been verified. Pause after saying “Hey Jarvis”; speech spoken immediately after the wake phrase may be missed during the switch to command capture.

## Troubleshooting

- Run `python audio_check.py` to check microphone device names and input level.
- If the wake phrase is missed, try speaking clearly and start with `WAKE_WORD_THRESHOLD=0.4` in `.env`; lower thresholds can also cause false activations. Start with the default `0.5`.
- If the model fails to load, rerun `python setup_wake_word.py` while online and check the full error message.
- Keep `.env` private. Never share the Groq API key.
