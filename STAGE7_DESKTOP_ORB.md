# Stage 7: Floating Desktop Orb

Jarvis now has an optional small floating desktop orb implemented with Python's
built-in Tkinter. It stays visible above ordinary desktop windows while Jarvis
is running and reflects its current state:

- **JARVIS** — idle
- **LISTENING** — waiting for the wake phrase
- **HEARING YOU** — recording a request
- **THINKING** — processing a request
- **SPEAKING** — local text-to-speech is running

The orb pulses during recording, processing, and speaking. Drag it to move it
somewhere convenient. It does not require a downloaded icon image or cloud service.

## Run it

From the project folder in PowerShell:

```powershell
python main.py --wake
```

To run without the desktop orb:

```powershell
python main.py --wake --no-overlay
```

Diagnostics still runs without starting the orb:

```powershell
python main.py --diagnostics
```

## Important limitations

- The orb is shown on the normal Windows desktop and above ordinary application
  windows while Jarvis is running. It cannot display over the secure Windows
  lock screen, UAC secure desktop, or before the user signs in.
- If Tkinter cannot initialize, Jarvis continues in console mode.
- Keep the `.env` file from your existing project; this archive does not include
  your private API key.


See `STAGE7_DESKTOP_CONTROL.md` for additional app launching and voice-typing commands. Install the new dependencies with `python -m pip install -r requirements.txt`.
