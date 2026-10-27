# Stage 5: Local voice output and state management

Stage 5 adds offline text-to-speech using Windows SAPI5 through `pyttsx3`, plus explicit runtime states. It preserves the local command registry, local Whisper speech recognition, local `openWakeWord` detector, and optional Groq AI fallback.

## Install the new dependency

Run in the same PowerShell environment used for `main.py`:

```powershell
python -m pip install -r requirements.txt
```

If the other requirements are already installed, the minimal install is:

```powershell
python -m pip install pyttsx3
```

## Start Stage 5

Wake-word mode:

```powershell
python main.py --wake
```

Typed/push-to-talk mode:

```powershell
python main.py
```

After a response is printed, Jarvis should speak it using the PC's local Windows voice. In wake mode, the wake-word detector is not running while Jarvis speaks, which reduces the chance that its own voice will trigger it.

## State labels

- `IDLE`: ready for typed input or the next cycle.
- `WAITING_FOR_WAKE_WORD`: waiting for “Hey Jarvis”.
- `RECORDING`: capturing the spoken command.
- `PROCESSING`: routing the transcript to a local command or the AI fallback.
- `SPEAKING`: speaking the response.
- `STOPPED`: the listener has stopped.

## Optional settings in `.env`

```dotenv
TTS_ENABLED=true
TTS_RATE=175
TTS_VOLUME=1.0
```

Set `TTS_ENABLED=false` to disable voice output while keeping the assistant functional. `TTS_RATE` controls speaking speed; `TTS_VOLUME` ranges from `0.0` to `1.0`.

## Notes

- TTS is local and does not send the assistant's response to a cloud speech service.
- The first wake-word version still requires Enter to stop recording each command.
- If `pyttsx3` or Windows SAPI5 fails to initialize, Jarvis prints a status message and continues in text-only mode.
- Keep `.env` private; never paste your Groq API key into chat.
