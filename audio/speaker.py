"""Offline text-to-speech for Windows.

Why this was rewritten (Stage 9)
--------------------------------
pyttsx3's runAndWait() has well-known problems on Windows: it can speak the
first sentence and then go silent, and it breaks when called from a different
thread (which timers and reminders need). So the PRIMARY voice is now a small
long-lived Windows PowerShell helper that uses the built-in
System.Speech engine (the same offline voices Windows already has).

- Text is sent to the helper as base64, so it is only ever treated as words to
  say, never as PowerShell code.
- One helper process stays running, so replies start speaking quickly.
- A lock makes speak() safe to call from the main loop AND from timers.
- If the helper cannot start (or you are not on Windows), pyttsx3 is used.
"""
from __future__ import annotations

import atexit
import base64
import logging
import queue
import re
import subprocess
import sys
import threading

logger = logging.getLogger(__name__)

MAX_SPOKEN_CHARS = 1200

_PS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.Rate = {rate}
$s.Volume = {volume}
[Console]::Out.WriteLine('READY'); [Console]::Out.Flush()
while ($true) {
    $line = [Console]::In.ReadLine()
    if ($line -eq $null) { break }
    try {
        $text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($line))
        $s.Speak($text)
    } catch { }
    [Console]::Out.WriteLine('DONE'); [Console]::Out.Flush()
}
"""


def clean_for_speech(text: str) -> str:
    """Remove characters that sound odd when read aloud."""
    text = re.sub(r"[*_`#>]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_SPOKEN_CHARS]


class Speaker:
    def __init__(self, enabled: bool = True, rate: int = 175, volume: float = 1.0):
        self.enabled = enabled
        self.engine = None          # pyttsx3 engine (fallback backend)
        self.status = "Local TTS is off."
        self.backend: str | None = None
        self._rate = rate
        self._volume = max(0.0, min(1.0, volume))
        self._lock = threading.RLock()
        self._proc: subprocess.Popen | None = None
        self._lines: queue.Queue[str] = queue.Queue()
        if not enabled:
            return

        if sys.platform == "win32" and self._start_helper():
            self.backend = "windows-speech"
            self.status = "Local TTS is on (Windows speech helper)."
            atexit.register(self.close)
            return
        self._init_pyttsx3()

    # ---- backends -----------------------------------------------------

    def _helper_command(self) -> list[str]:
        """Command that starts the speech helper. Tests replace this."""
        # SAPI rate is -10..10 (0 is normal). 175 words/min is about normal.
        sapi_rate = max(-10, min(10, round((self._rate - 175) / 25)))
        script = _PS_SCRIPT.replace("{rate}", str(sapi_rate)).replace(
            "{volume}", str(int(self._volume * 100)))
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        return ["powershell.exe", "-NoProfile", "-NonInteractive",
                "-EncodedCommand", encoded]

    def _start_helper(self) -> bool:
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self._proc = subprocess.Popen(
                self._helper_command(),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, creationflags=flags,
                text=True, encoding="ascii", bufsize=1,
            )
        except (OSError, ValueError) as error:
            logger.warning("Speech helper could not start (%s)", type(error).__name__)
            self._proc = None
            return False

        self._lines = queue.Queue()
        proc = self._proc
        lines = self._lines

        def reader():
            try:
                for line in proc.stdout:
                    lines.put(line.strip())
            except Exception:
                pass
            lines.put("EXIT")

        threading.Thread(target=reader, daemon=True).start()
        try:
            if lines.get(timeout=15) == "READY":
                return True
        except queue.Empty:
            pass
        logger.warning("Speech helper did not become ready")
        self._kill_helper()
        return False

    def _kill_helper(self) -> None:
        proc, self._proc = self._proc, None
        if proc is not None:
            for stream in (proc.stdin, proc.stdout):
                try:
                    stream.close()
                except Exception:
                    pass
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass

    def _init_pyttsx3(self) -> None:
        try:
            import pyttsx3

            self.engine = pyttsx3.init("sapi5") if sys.platform == "win32" else pyttsx3.init()
            self.engine.setProperty("rate", self._rate)
            self.engine.setProperty("volume", self._volume)
            self.backend = "pyttsx3"
            self.status = "Local TTS is on (Windows SAPI)."
        except Exception as error:
            self.enabled = False
            self.engine = None
            self.status = f"Local TTS is off (initialization failed: {type(error).__name__})."
            logger.warning("TTS initialization failed (%s)", type(error).__name__)

    # ---- public -------------------------------------------------------

    def speak(self, text: str) -> bool:
        """Speak text and wait until finished. Never raises."""
        if not self.enabled:
            return False
        text = clean_for_speech(text or "")
        if not text:
            return False
        with self._lock:
            if self.backend == "windows-speech":
                if self._speak_helper(text):
                    return True
                # One restart, then give up on the helper for this session.
                logger.warning("Speech helper failed; restarting once")
                self._kill_helper()
                if self._start_helper() and self._speak_helper(text):
                    return True
                self._kill_helper()
                print("[TTS] Windows speech helper failed; switching to the backup voice.")
                self.backend = None
                self._init_pyttsx3()
                if self.engine is None:
                    return False
            return self._speak_pyttsx3(text)

    def _speak_helper(self, text: str) -> bool:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            return False
        try:
            payload = base64.b64encode(text.encode("utf-8")).decode("ascii")
            proc.stdin.write(payload + "\n")
            proc.stdin.flush()
            timeout = 20 + len(text) / 6
            while True:
                line = self._lines.get(timeout=timeout)
                if line == "DONE":
                    return True
                if line == "EXIT":
                    return False
        except (queue.Empty, OSError, ValueError):
            return False

    def _speak_pyttsx3(self, text: str) -> bool:
        if self.engine is None:
            return False
        try:
            self.engine.say(text)
            self.engine.runAndWait()
            return True
        except Exception as error:
            print(f"[TTS] Speech output failed ({type(error).__name__}).")
            logger.warning("TTS speech output failed (%s)", type(error).__name__)
            try:
                self.engine.stop()
            except Exception:
                pass
            return False

    def close(self) -> None:
        with self._lock:
            proc = self._proc
            if proc is not None:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
            self._kill_helper()
