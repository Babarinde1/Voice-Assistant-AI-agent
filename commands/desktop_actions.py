"""Local Windows app discovery, launching, and voice typing helpers."""
from __future__ import annotations
import logging
import os
import re
import json
import shutil
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


def _normalize(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r'\.(lnk|url|exe|appref-ms)$', '', value)
    value = re.sub(r'[^a-z0-9]+', ' ', value)
    return re.sub(r'\s+', ' ', value).strip()


def _start_menu_roots() -> list[Path]:
    roots = []
    appdata = os.environ.get('APPDATA')
    programdata = os.environ.get('PROGRAMDATA', r'C:\ProgramData')
    if appdata:
        roots.append(Path(appdata) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs')
    roots.append(Path(programdata) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs')
    return [root for root in roots if root.exists()]


def find_app_shortcut(app_name: str) -> Path | None:
    """Find a Start Menu shortcut for an installed app, preferring exact matches."""
    wanted = _normalize(app_name)
    if not wanted:
        return None
    candidates: list[tuple[str, Path]] = []
    for root in _start_menu_roots():
        try:
            for path in root.rglob('*'):
                if path.is_file() and path.suffix.lower() in {'.lnk', '.url', '.appref-ms'}:
                    candidates.append((_normalize(path.stem), path))
        except (OSError, PermissionError):
            continue
    for stem, path in candidates:
        if stem == wanted:
            return path
    # Use conservative partial matching only when the app name is distinctive.
    matches = [(stem, path) for stem, path in candidates if wanted in stem or stem in wanted]
    matches = [(stem, path) for stem, path in matches if len(stem) >= 3 and len(wanted) >= 3]
    if len(matches) == 1:
        return matches[0][1]
    return None


# ---- Microsoft Store / packaged apps (WhatsApp, Spotify, Netflix...) ---------
# These have no .lnk shortcut. Windows lists them through Get-StartApps, and they
# start with "shell:AppsFolder\\<AppID>". The PowerShell script below is fixed text
# (your words are never put into it); matching is done here in Python.

_APPID_OK = re.compile(r"^[\w .\-!{}\\:()]+$")
_start_apps_cache: list[tuple[str, str]] | None = None


def list_start_apps(refresh: bool = False) -> list[tuple[str, str]]:
    """[(name, app_id), ...] for every app Windows shows in the Start Menu."""
    global _start_apps_cache
    if _start_apps_cache is not None and not refresh:
        return _start_apps_cache
    apps: list[tuple[str, str]] = []
    if sys.platform == "win32":
        script = ("[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
                  "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress")
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, timeout=25,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            data = json.loads(result.stdout.decode("utf-8", errors="replace") or "[]")
            if isinstance(data, dict):
                data = [data]
            for item in data:
                name, app_id = str(item.get("Name") or ""), str(item.get("AppID") or "")
                if name and app_id and _APPID_OK.match(app_id):
                    apps.append((name, app_id))
        except Exception as error:
            logger.warning("Could not list Start apps (%s)", type(error).__name__)
    _start_apps_cache = apps
    return apps


def find_start_app(app_name: str) -> tuple[str, str] | None:
    wanted = _normalize(app_name)
    if len(wanted) < 2:
        return None
    apps = [(_normalize(name), name, app_id) for name, app_id in list_start_apps()]
    for norm, name, app_id in apps:
        if norm == wanted:
            return name, app_id
    for test in (lambda n: n.startswith(wanted), lambda n: wanted in n):
        matches = [(name, app_id) for norm, name, app_id in apps if test(norm)]
        if len(matches) == 1:
            return matches[0]
    return None


def open_application(app_name: str) -> str:
    """Launch an app by Start Menu shortcut or a known Windows executable alias."""
    app_name = re.sub(r'^(the|my|windows)\s+', '', app_name.strip(), flags=re.I).strip()
    app_name = re.sub(r'\s+(app|application|program|please|for me)$', '', app_name, flags=re.I).strip()
    if not app_name:
        return 'Tell me which application to open.'

    aliases = {
        'notepad': 'notepad.exe', 'calculator': 'calc.exe', 'calc': 'calc.exe',
        'paint': 'mspaint.exe', 'command prompt': 'cmd.exe', 'cmd': 'cmd.exe',
        'powershell': 'powershell.exe', 'file explorer': 'explorer.exe',
        'explorer': 'explorer.exe', 'task manager': 'taskmgr.exe',
        'control panel': 'control.exe', 'settings': 'ms-settings:',
        'wordpad': 'write.exe',
    }
    key = _normalize(app_name)
    try:
        if key in aliases:
            target = aliases[key]
            if target.endswith(':'):
                os.startfile(target)  # Windows URI handler, no shell command string.
            else:
                os.startfile(target)
            return f'Opening {app_name}.'
        shortcut = find_app_shortcut(app_name)
        if shortcut is not None:
            os.startfile(str(shortcut))
            return f'Opening {app_name}.'
        executable = shutil.which(app_name)
        if executable:
            os.startfile(executable)
            return f'Opening {app_name}.'
        store_app = find_start_app(app_name)
        if store_app is not None:
            os.startfile("shell:AppsFolder\\" + store_app[1])
            return f'Opening {store_app[0]}.'
    except (OSError, AttributeError) as error:
        return f'I could not open {app_name}. Windows reported {type(error).__name__}.'
    return (f'I could not find an app called {app_name}. '
            'Check that it is installed and appears in the Windows Start Menu.')


# Apps Jarvis may start by itself when you ask it to type into them.
AUTO_LAUNCH = {"notepad", "wordpad"}


def _find_window(wanted: str):
    import pygetwindow

    for window in pygetwindow.getAllWindows():
        title = (window.title or "").strip()
        if title and wanted in _normalize(title):
            return window
    return None


def _wait_for_window(wanted: str, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        window = _find_window(wanted)
        if window is not None:
            return window
        time.sleep(0.25)
    return None


def _focus(window, wanted: str) -> bool:
    """Bring a window to the front. Windows sometimes raises a harmless error."""
    import pygetwindow

    try:
        window.activate()
    except Exception:
        try:
            window.minimize()
            window.restore()
        except Exception:
            pass
    time.sleep(0.3)
    try:
        active = pygetwindow.getActiveWindow()
        return bool(active and wanted in _normalize(active.title or ""))
    except Exception:
        return True  # cannot verify; try anyway


def type_text(text: str, target_app: str | None = None) -> str:
    """Paste text into the active window, optionally bringing a named app forward.

    Notepad and WordPad are started automatically if they are not open.
    """
    text = text.strip()
    if not text:
        return "Tell me what text to type."
    try:
        import pyautogui
        import pyperclip
    except ImportError:
        return ("Voice typing needs pyautogui and pyperclip. "
                "Run: python -m pip install pyautogui pyperclip")

    if target_app:
        wanted = _normalize(target_app)
        try:
            window = _find_window(wanted)
            launched = False
            if window is None and wanted in AUTO_LAUNCH:
                open_application(wanted)
                window = _wait_for_window(wanted)
                launched = window is not None
            if window is None:
                return f"I could not find an open window for {target_app}. Open it first."
            if not _focus(window, wanted):
                return f"I could not bring {target_app} to the front. Click its window and try again."
            if launched:
                time.sleep(0.6)  # let a freshly opened editor finish loading
        except ImportError:
            return "Window targeting needs pygetwindow. Run: python -m pip install pygetwindow"
        except Exception:
            return f"I could not focus {target_app}. Click its window and try again."

    try:
        try:
            previous = pyperclip.paste()
        except Exception:
            previous = None
        pyperclip.copy(text)
        time.sleep(0.15)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.3)
        if previous is not None:
            pyperclip.copy(previous)  # give you your clipboard back
        return "Typed your text." if not target_app else f"Typed your text in {target_app}."
    except Exception as error:
        return f"I could not type the text ({type(error).__name__}). Make sure the target window is open and focused."


# ---- web --------------------------------------------------------------

def web_search(query: str, engine: str = "google") -> str:
    query = query.strip()
    if not query:
        return "Tell me what to search for."
    if engine == "youtube":
        url = "https://www.youtube.com/results?search_query=" + quote_plus(query)
        where = "YouTube"
    else:
        url = "https://www.google.com/search?q=" + quote_plus(query)
        where = "the web"
    try:
        opened = webbrowser.open(url)
    except Exception:
        opened = False
    if not opened:
        return "I could not open your web browser."
    return f"Searching {where} for {query}."


def open_website(domain: str) -> str:
    try:
        opened = webbrowser.open("https://" + domain)
    except Exception:
        opened = False
    return f"Opening {domain}." if opened else "I could not open your web browser."


# ---- screenshot -------------------------------------------------------

_screenshot_hooks = {"before": None, "after": None}


def set_screenshot_hooks(before=None, after=None) -> None:
    """main.py uses this to hide the floating orb while a screenshot is taken."""
    _screenshot_hooks["before"] = before
    _screenshot_hooks["after"] = after


def screenshot_folder() -> Path:
    return Path.home() / "Pictures" / "Jarvis Screenshots"


def take_screenshot() -> str:
    try:
        from PIL import ImageGrab
    except ImportError:
        return "Screenshots need Pillow. Run: python -m pip install pillow"

    before, after = _screenshot_hooks["before"], _screenshot_hooks["after"]
    try:
        if before:
            before()
            time.sleep(0.4)
        image = ImageGrab.grab(all_screens=True)
    except Exception as error:
        logger.warning("Screenshot failed (%s)", type(error).__name__)
        return f"I could not take the screenshot ({type(error).__name__})."
    finally:
        if after:
            after()

    try:
        folder = screenshot_folder()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"screenshot_{datetime.now():%Y%m%d_%H%M%S}.png"
        image.save(path)
    except Exception as error:
        return f"I took the screenshot but could not save it ({type(error).__name__})."
    logger.info("Screenshot saved")
    print(f"[screenshot] {path}")
    return "Screenshot saved in Pictures, in the Jarvis Screenshots folder."


# ---- keys -------------------------------------------------------------

def _press(key: str, presses: int = 1) -> bool:
    try:
        import pyautogui

        pyautogui.press(key, presses=presses, interval=0.02)
        return True
    except Exception:
        return False


def change_volume(direction: str) -> str:
    key = "volumeup" if direction == "up" else "volumedown"
    if not _press(key, presses=5):
        return "I could not change the volume. Voice control needs pyautogui."
    return "Volume up." if direction == "up" else "Volume down."


def toggle_mute() -> str:
    return "Toggled mute." if _press("volumemute") else "I could not change the volume."


def show_desktop() -> str:
    try:
        import pyautogui

        pyautogui.hotkey("win", "d")
        return "Showing the desktop."
    except Exception:
        return "I could not show the desktop. Voice control needs pyautogui."
