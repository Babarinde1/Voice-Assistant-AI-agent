# Stage 6 — Security, logging, diagnostics, and reliability

This is the final stage in the initial six-stage roadmap. It hardens the existing local-first assistant without granting the AI control of Windows.

## What changed

- Rotating operational log at `logs/jarvis.log` (up to 1 MB per file, three backups).
- Logs command names, state changes, and failure categories. It does **not** log recognized transcripts, AI prompts/replies, or API keys.
- Refused computer actions remain blocked from the AI fallback. Approved programs are still launched using argument lists with `shell=False`.
- TTS errors and command failures are recorded without printing exception contents that might expose sensitive data.
- A diagnostics mode reports setup status without starting the microphone or contacting the AI service.

## Install / update

1. Back up your current `windows_voice_assistant` folder.
2. Extract this ZIP to a temporary folder. Copy the extracted project files into your existing project, but **keep your existing `.env` file**.
3. In PowerShell, from the project folder, run:

```powershell
python -m pip install -r requirements.txt
python -m unittest test_stage1.py test_stage2.py test_stage3.py test_stage5.py test_stage6.py
```

4. Run diagnostics first:

```powershell
python main.py --diagnostics
```

5. Start normal mode or wake-word mode:

```powershell
python main.py
python main.py --wake
```

## Log settings

Optional `.env` setting:

```dotenv
LOG_LEVEL=INFO
```

Use `DEBUG`, `INFO`, `WARNING`, or `ERROR`. `INFO` is recommended for normal use. Logs can include operational metadata and command names, so review them before sharing. Never share `.env` or API keys.

## Performance checklist

- Run `python benchmark_stt.py` to compare transcription speed on this PC.
- Keep the assistant on `base.en` initially; choose another model only after comparing speed and accuracy.
- Keep local commands for frequent actions; AI fallback is for questions and flexible requests, not computer control.
- If the assistant is slow, check the timestamps in `logs/jarvis.log` and the transcription timings printed in the console.

## Limits

- Stage 6 does not make wake-word detection or transcription perfect. Whisper may still mishear words; approved aliases can help.
- This is a local desktop project, not a Windows service. It still requires the user to start it.
- Logging and diagnostics are best-effort; they do not replace Windows security, backups, or safe handling of API credentials.
