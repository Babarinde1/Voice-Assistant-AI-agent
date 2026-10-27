# Stage 8: hands-free speech, desktop actions, and the transparent orb

## Install (once)

```powershell
python -m pip install -r requirements.txt
python setup_wake_word.py
```

`PySide6-Essentials` (about 80 MB) gives the transparent colorful orb. If you skip it,
Jarvis uses the simple orb automatically.

## 1. It knows when you start and stop speaking

```powershell
python main.py --wake
```

Say **"Hey Jarvis"** (you hear a short beep), then say your request. Jarvis stops
listening when you pause (default 0.9 s), so you never press Enter. Pressing Enter on an
empty line in normal mode (`python main.py`) works the same way.

Wake word and request use ONE microphone stream, so nothing is lost between them.
The speech detector is the small Silero neural model that ships with openWakeWord (runs
locally, uses very little CPU). If it is missing, a volume-based detector is used.

Tuning (all in `.env`):

| Setting | Meaning | If you have this problem |
|---|---|---|
| `END_SILENCE_MS=900` | pause that ends a request | cuts you off mid-sentence: raise to 1200-1500; feels slow: lower to 700 |
| `NO_SPEECH_TIMEOUT_S=6` | give up if you say nothing after the wake phrase | |
| `WAKE_GRACE_MS=200` | ignore the tail of "...Jarvis" | first word of your request is cut: lower to 100; "jarvis" leaks into requests: raise to 350 |
| `VAD_ENGINE=auto` | `silero` or `energy` | constant fan/generator noise: use `silero` |
| `AUTO_ENDPOINT=false` | go back to press-Enter-to-stop | |

## 2. Things you can ask for

| Say | What happens |
|---|---|
| "search for best jollof rice recipe" / "google weather in Ibadan" | opens a web search in your default browser |
| "search YouTube for afrobeats" / "play burna boy on YouTube" | opens YouTube results (does not auto-play) |
| "open YouTube" / "go to wikipedia.org" / "open example dot com" | opens that website |
| "take a screenshot" | saves a PNG in Pictures\Jarvis Screenshots (the orb hides for it) |
| "open Notepad and type hello world" | starts Notepad if needed, then types |
| "type in Notepad: dear sir" / "type hello in Notepad" | types into Notepad |
| "type good morning everyone" | types into the window you are using |
| "volume up" / "volume down" / "mute" | changes system volume |
| "show desktop" | minimizes all windows |
| "open Paint" / "open Microsoft Word" | opens installed apps (Start Menu search) |

Safety rules:
- Only these approved actions can touch the computer. The AI never controls it.
- Typing needs the word "type" or "dictate" (or a colon). Ordinary sentences such as
  "write a poem about my school" are NOT typed anywhere.
- Typing uses paste and puts your previous clipboard text back afterwards.
- Logs record the kind of action only, never what you typed or searched.

## 3. The orb

Transparent, anti-aliased, colorful, and reacts to your voice (bars follow loudness).
Colors: cyan-violet = waiting, orange-rainbow = listening, violet with orbiting arcs =
thinking, green-blue = speaking.

- Drag it with the left mouse button. Transparent areas let clicks pass through.
- Double-click: shrink / enlarge.   Right-click: Close orb.
- `ORB_STYLE=auto|qt|tk|off` in `.env`, or `--no-overlay`.

## Limits

- Not tested on a real microphone by the author: tune the settings above on your laptop.
- Typing and window focus use Windows automation. Some windows (for example apps running
  as administrator) can block them.
- The orb cannot appear over the Windows lock screen or UAC prompts.
