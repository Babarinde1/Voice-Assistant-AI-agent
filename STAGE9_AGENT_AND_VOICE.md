# Stage 9: spoken time, and a "do what I ask" agent

## Install

```powershell
python -m pip install -r requirements.txt
python -m unittest test_stage9.py
```

## 1. Hear the time out loud

```powershell
python main.py --say-time
```

That speaks the current time once and prints which voice it used. If you hear it, saying
"Hey Jarvis, what time is it" will speak too.

What changed: pyttsx3 can speak once and then go silent on Windows, and it fails when a
timer speaks from another thread. The voice is now a small background Windows speech
helper (offline, built into Windows). pyttsx3 is still used as a backup.
Change the speed with `TTS_RATE` in `.env`.

## 2. The agent: ask for things in your own words

Order of handling is unchanged: your fixed commands first (instant, offline), then the
agent for everything else. The agent needs `AI_API_KEY` and `AI_MODEL` in `.env`.

| Try saying | Tool used |
|---|---|
| "set a timer for 10 minutes for the rice" | set_timer (speaks when done) |
| "what's 15 percent of 8400" | calculate |
| "find my CV and open it" | search_files, then open_path |
| "make a folder called Physics on my desktop" | create_folder |
| "save a note called ideas that says buy data" | write_text_file |
| "what's in my downloads folder" | list_folder |
| "switch to Chrome" / "minimize Notepad" / "close Notepad" | window_action (close asks first) |
| "open a new tab and go to wikipedia.org" | press_keys, open_website |
| "pause the music" / "next song" / "set volume to 30" | media_control, set_volume |
| "lower the brightness to 40" | set_brightness |
| "how much battery / memory / disk space" | system_info |
| "copy this sentence to the clipboard: ..." | set_clipboard |
| "lock the computer" | power_action |

## 3. Safety (matches section 8 of your blueprint)

- **No shell.** There is no tool that runs commands, scripts, PowerShell or Python. The AI picks
  from the tool list in `assistant/agent.py`; to add an ability you add a reviewed Tool.
- Every tool name and argument is validated (`assistant/tools.py`) before anything runs.
- **Asks "yes or no" out loud** before: closing a window, moving or replacing a file, deleting,
  restart/shutdown/sleep/sign-out, and Alt+F4/Delete key presses. Silence or unclear = no.
  The question is written by the program, not the AI.
- Files: only Desktop, Documents, Downloads, Pictures, Music, Videos (plus `ALLOWED_FOLDERS`).
  `..` tricks and shortcuts that point elsewhere are blocked. Programs and scripts
  (.exe .bat .ps1 .py ...) can never be created or opened. Nothing is overwritten silently.
- Deleting is **off** until `ALLOW_FILE_DELETION=true`; it goes to the Recycle Bin.
  Restart/shutdown/sleep is **off** until `ALLOW_POWER_ACTIONS=true`; shutdown waits 30 s
  and "cancel shutdown" stops it.
- What Jarvis says after an action is the real result from the tool, not the AI's claim.
- Logs record tool names only, never what you said, typed, or the file names.

## Limits (honest)

- Written and unit-tested (121 tests) without a Windows PC or a microphone, so the
  Windows-only parts (speech helper, window control, brightness, power) need your first run.
  If something fails, send me the line from `logs/jarvis.log`.
- It cannot see the screen, so "click the blue button" is not possible yet.
- Quality depends on your `AI_MODEL`. Small local models may answer in plain text or break
  the JSON format; the agent tolerates that but may do less.
- Each agent request costs one AI call (two if it has to look something up first), so expect
  roughly 1 to 3 seconds extra with a cloud model.
- Timers speak even if you are mid-sentence, and can be picked up by the microphone.
