"""Approved PC-control functions used by the Stage 9 agent.

Every function here is ordinary, reviewed Python. The AI can choose WHICH one to
call and with what (validated) arguments, but it cannot add new abilities.
"""
from __future__ import annotations

import ast
import ctypes
import logging
import operator
import re
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# ======================================================================
# Keyboard shortcuts (allowlisted)
# ======================================================================

_MODIFIERS = {"ctrl", "alt", "shift", "win"}
_PLAIN_KEYS = (
    set("abcdefghijklmnopqrstuvwxyz0123456789")
    | {f"f{i}" for i in range(1, 13)}
    | {"enter", "esc", "tab", "space", "backspace", "delete", "home", "end",
       "pageup", "pagedown", "up", "down", "left", "right"}
)
# The Windows key is limited to harmless shortcuts (no Run dialog, no admin menu).
_WIN_ALLOWED = {"d", "e", "tab", "up", "down", "left", "right", "i", "v", "shift+s"}
_BLOCKED_COMBOS = {"ctrl+alt+delete", "ctrl+shift+delete", "alt+ctrl+delete"}
_CONFIRM_COMBOS = {"alt+f4", "delete", "ctrl+w"}
MAX_KEY_COMBOS = 8


def parse_combo(combo: str) -> list[str]:
    """'Ctrl + T' -> ['ctrl', 't'].  Raises ValueError if not allowed."""
    aliases = {"control": "ctrl", "escape": "esc", "return": "enter", "windows": "win",
               "page up": "pageup", "page down": "pagedown", "del": "delete", "arrowup": "up",
               "arrowdown": "down", "arrowleft": "left", "arrowright": "right"}
    parts = [aliases.get(p.strip().lower(), p.strip().lower()) for p in combo.split("+")]
    parts = [p for p in parts if p]
    if not parts or len(parts) > 3:
        raise ValueError("That isn't a valid key combination.")
    *mods, key = parts
    if any(m not in _MODIFIERS for m in mods) or key not in _PLAIN_KEYS:
        raise ValueError(f"I don't allow the key combination {combo}.")
    if len(set(parts)) != len(parts):
        raise ValueError("That isn't a valid key combination.")
    joined = "+".join(parts)
    if joined in _BLOCKED_COMBOS:
        raise ValueError(f"I don't allow {combo}.")
    if "win" in mods and "+".join(parts[1:]) not in _WIN_ALLOWED:
        raise ValueError("I only allow a few Windows-key shortcuts.")
    return parts


def split_combos(keys: str) -> list[list[str]]:
    """'ctrl+t, enter' -> [['ctrl','t'], ['enter']]"""
    items = [k for k in re.split(r"[,;]| then ", keys) if k.strip()]
    if not items or len(items) > MAX_KEY_COMBOS:
        raise ValueError(f"Give me between 1 and {MAX_KEY_COMBOS} key presses.")
    return [parse_combo(k) for k in items]


def confirm_keys(args: dict) -> str | None:
    try:
        combos = ["+".join(c) for c in split_combos(args["keys"])]
    except ValueError:
        return None  # handler reports the problem
    risky = [c for c in combos if c in _CONFIRM_COMBOS]
    if risky:
        return f"Press {risky[0].replace('+', ' plus ')}? This can close things or delete."
    return None


def press_keys(args: dict) -> str:
    combos = split_combos(args["keys"])
    import pyautogui

    for parts in combos:
        pyautogui.hotkey(*parts) if len(parts) > 1 else pyautogui.press(parts[0])
        time.sleep(0.15)
    return "Pressed " + ", ".join("+".join(c) for c in combos) + "."


# ======================================================================
# Media, volume, brightness
# ======================================================================

_MEDIA_KEYS = {
    "play_pause": "playpause", "next": "nexttrack", "previous": "prevtrack",
    "stop": "stop", "mute": "volumemute", "volume_up": "volumeup", "volume_down": "volumedown",
}


def media_control(args: dict) -> str:
    import pyautogui

    action = args["action"]
    presses = 5 if action in {"volume_up", "volume_down"} else 1
    pyautogui.press(_MEDIA_KEYS[action], presses=presses, interval=0.02)
    return {"play_pause": "Toggled play and pause.", "next": "Next track.",
            "previous": "Previous track.", "stop": "Stopped.", "mute": "Toggled mute.",
            "volume_up": "Volume up.", "volume_down": "Volume down."}[action]


def set_volume(args: dict) -> str:
    """Set an approximate volume 0-100 using keys (each key press is about 2 percent)."""
    import pyautogui

    level = args["level"]
    pyautogui.press("volumedown", presses=50, interval=0.005)
    if level > 0:
        pyautogui.press("volumeup", presses=round(level / 2), interval=0.005)
    return f"Volume set to about {level} percent."


def set_brightness(args: dict) -> str:
    """Laptop screen brightness through Windows' built-in WMI. Level is an int 0-100."""
    level = int(args["level"])
    script = ("(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
              f".WmiSetBrightness(1,{level})")
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, timeout=15, creationflags=_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "I couldn't change the brightness."
    if result.returncode != 0:
        return "This screen doesn't allow brightness changes from here."
    return f"Brightness set to {level} percent."


# ======================================================================
# Windows
# ======================================================================

def _titled_windows():
    import pygetwindow

    return [w for w in pygetwindow.getAllWindows() if (w.title or "").strip()]


def list_windows(args: dict) -> str:
    titles = []
    for window in _titled_windows():
        title = window.title.strip()
        if title not in titles:
            titles.append(title)
    return "Open windows: " + "; ".join(titles[:20]) if titles else "I see no open windows."


# What people say  ->  what actually appears in that app's title bar.
_WINDOW_ALIASES = {
    "vs code": "visual studio code", "vscode": "visual studio code", "code": "visual studio code",
    "visual studio code": "visual studio code",
    "chrome": "google chrome", "google chrome": "google chrome", "browser": "google chrome",
    "edge": "microsoft edge", "firefox": "firefox",
    "word": "word", "microsoft word": "word", "excel": "excel", "microsoft excel": "excel",
    "powerpoint": "powerpoint", "power point": "powerpoint",
    "file explorer": "file explorer", "explorer": "file explorer", "files": "file explorer",
    "terminal": "terminal", "command prompt": "command prompt", "powershell": "powershell",
    "whatsapp": "whatsapp", "spotify": "spotify", "teams": "teams", "zoom": "zoom",
    "notepad": "notepad", "note pad": "notepad", "calculator": "calculator",
    "settings": "settings", "task manager": "task manager",
}


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _match_window(title: str):
    wanted = title.lower().strip()
    candidates = [wanted]
    alias = _WINDOW_ALIASES.get(re.sub(r"\s+", " ", wanted))
    if alias and alias not in candidates:
        candidates.append(alias)
    windows = _titled_windows()
    for cand in candidates:
        for w in windows:
            if w.title.strip().lower() == cand:
                return w
    for cand in candidates:
        for w in windows:
            if cand in w.title.lower():
                return w
    # Last try ignoring spaces and punctuation: "vscode" ~ "VS Code".
    for cand in candidates:
        squashed = _squash(cand)
        if len(squashed) >= 3:
            for w in windows:
                if squashed in _squash(w.title):
                    return w
    return None


def confirm_window(args: dict) -> str | None:
    if args["action"] != "close":
        return None
    try:
        window = _match_window(args["title"])
    except Exception:
        window = None
    name = window.title.strip()[:60] if window else args["title"]
    return f"Close the window {name}? Unsaved work may be lost."


def window_action(args: dict) -> str:
    action, title = args["action"], args["title"]
    window = _match_window(title)
    if window is None:
        return f"I couldn't find a window matching {title}."
    name = window.title.strip()[:60]
    if action == "focus":
        try:
            window.activate()
        except Exception:
            window.minimize()
            window.restore()
        return f"Switched to {name}."
    if action == "minimize":
        window.minimize()
        return f"Minimized {name}."
    if action == "maximize":
        window.maximize()
        return f"Maximized {name}."
    if action == "restore":
        window.restore()
        return f"Restored {name}."
    if action == "close":
        window.close()
        return f"Closed {name}."
    return "I don't know that window action."


# ======================================================================
# Clipboard
# ======================================================================

def get_clipboard(args: dict) -> str:
    import pyperclip

    text = pyperclip.paste() or ""
    return ("The clipboard says: " + text[:1500]) if text.strip() else "The clipboard is empty."


def set_clipboard(args: dict) -> str:
    import pyperclip

    pyperclip.copy(args["text"])
    return "Copied to the clipboard."


# ======================================================================
# Calculator (arithmetic only, never eval)
# ======================================================================

_BINOPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
           ast.Mod: operator.mod, ast.Pow: operator.pow}
_UNOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) \
            and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > 100 or abs(left) > 1e6):
            raise ValueError("That power is too large.")
        return _BINOPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNOPS:
        return _UNOPS[type(node.op)](_eval(node.operand))
    raise ValueError("I can only do plain arithmetic.")


def calculate(args: dict) -> str:
    expression = args["expression"].lower()
    expression = expression.replace("x", "*").replace("×", "*").replace("÷", "/").replace("^", "**")
    expression = expression.replace(",", "")
    expression = re.sub(r"(\d+(?:\.\d+)?)\s*%\s*of\s*(\d+(?:\.\d+)?)", r"(\1/100*\2)", expression)
    if not re.fullmatch(r"[\d\s+\-*/().%]+", expression) or len(expression) > 120:
        return "I can only do plain arithmetic."
    try:
        value = _eval(ast.parse(expression.strip(), mode="eval"))
    except (SyntaxError, ValueError, ZeroDivisionError, OverflowError):
        return "I couldn't work that out."
    if isinstance(value, float):
        value = round(value, 6)
        if value == int(value):
            value = int(value)
    return f"The answer is {value}."


# ======================================================================
# System information
# ======================================================================

class _MemoryStatus(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]


def system_info(args: dict) -> str:
    from commands.system import get_battery, get_date, get_time

    kind = args["kind"]
    if kind == "time":
        return get_time()
    if kind == "date":
        return get_date()
    if kind == "battery":
        return get_battery()
    if kind == "disk":
        anchor = Path.home().anchor or "/"
        usage = shutil.disk_usage(anchor)
        gb = 1024 ** 3
        return f"Drive {anchor} has {usage.free / gb:.0f} gigabytes free of {usage.total / gb:.0f}."
    if kind == "memory":
        if sys.platform == "win32":
            status = _MemoryStatus()
            status.dwLength = ctypes.sizeof(_MemoryStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            gb = 1024 ** 3
            return (f"Memory is {status.dwMemoryLoad} percent used: "
                    f"{status.ullAvailPhys / gb:.1f} of {status.ullTotalPhys / gb:.1f} gigabytes free.")
        try:
            import psutil

            m = psutil.virtual_memory()
            return f"Memory is {m.percent:.0f} percent used."
        except ImportError:
            return "I couldn't read memory use."
    if kind == "cpu":
        try:
            import psutil

            return f"The processor is at {psutil.cpu_percent(interval=0.7):.0f} percent."
        except ImportError:
            return "CPU use needs psutil. Run: python -m pip install psutil"
    return "I don't know that kind of information."


# ======================================================================
# Timers and reminders
# ======================================================================

_timers: list[threading.Timer] = []


def make_timer_tool(notify: Callable[[str], None]) -> Callable[[dict], str]:
    """notify(text) is called on a background thread when time is up."""

    def set_timer(args: dict) -> str:
        seconds = args["seconds"]
        label = (args.get("label") or "").strip()

        def fire():
            notify(f"Time's up. {label}" if label else "Time's up.")

        timer = threading.Timer(seconds, fire)
        timer.daemon = True
        timer.start()
        _timers[:] = [t for t in _timers if t.is_alive()] + [timer]
        minutes, secs = divmod(seconds, 60)
        spoken = (f"{minutes} minute{'s' if minutes != 1 else ''}" if minutes else "") + \
                 (f" {secs} seconds" if secs and minutes else f"{secs} seconds" if secs else "")
        return f"Timer set for {spoken.strip()}" + (f" for {label}." if label else ".")

    return set_timer


def cancel_timers(args: dict) -> str:
    count = 0
    for timer in _timers:
        if timer.is_alive():
            timer.cancel()
            count += 1
    _timers.clear()
    return f"Cancelled {count} timer{'s' if count != 1 else ''}." if count else "No timers are running."


# ======================================================================
# Power (off by default; always asks first)
# ======================================================================

def confirm_power(args: dict) -> str | None:
    action = args["action"]
    if action == "lock":
        return None
    if action == "cancel_shutdown":
        return None
    questions = {
        "sleep": "Put the computer to sleep?",
        "restart": "Restart the computer? You'll have 30 seconds to cancel.",
        "shutdown": "Shut down the computer? You'll have 30 seconds to cancel.",
        "sign_out": "Sign out of Windows? Unsaved work may be lost.",
    }
    return questions.get(action)


def power_action(args: dict) -> str:
    action = args["action"]
    if sys.platform != "win32":
        return "Power actions only work on Windows."
    commands = {
        "lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
        "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
        "restart": ["shutdown.exe", "/r", "/t", "30"],
        "shutdown": ["shutdown.exe", "/s", "/t", "30"],
        "sign_out": ["shutdown.exe", "/l"],
        "cancel_shutdown": ["shutdown.exe", "/a"],
    }
    subprocess.Popen(commands[action], shell=False, creationflags=_NO_WINDOW)
    return {"lock": "Locking the computer.", "sleep": "Going to sleep.",
            "restart": "Restarting in 30 seconds. Say cancel shutdown to stop it.",
            "shutdown": "Shutting down in 30 seconds. Say cancel shutdown to stop it.",
            "sign_out": "Signing out.", "cancel_shutdown": "Shutdown cancelled."}[action]
