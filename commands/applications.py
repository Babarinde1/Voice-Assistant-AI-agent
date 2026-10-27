import os
import subprocess


def _launch(executable: str, friendly_name: str) -> str:
    """Start one approved program. Never uses a shell."""
    try:
        subprocess.Popen([executable], shell=False)
        return f"Opening {friendly_name}."
    except FileNotFoundError:
        return f"I couldn't find {friendly_name} on this computer."
    except OSError:
        return f"I couldn't start {friendly_name}."


def open_chrome() -> str:
    candidates = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(
            r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"
        ),
    ]

    for path in candidates:
        if os.path.exists(path):
            return _launch(path, "Google Chrome")

    return "Chrome was not found in its usual installation folders."


def open_notepad() -> str:
    return _launch("notepad.exe", "Notepad")


def open_calculator() -> str:
    return _launch("calc.exe", "Calculator")
