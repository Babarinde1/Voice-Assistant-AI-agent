"""Chooses and controls the on-screen orb.

ORB_STYLE=auto  -> the transparent Qt orb if PySide6 works, else the simple Tk orb
ORB_STYLE=qt    -> Qt orb only      ORB_STYLE=tk -> Tk orb only      ORB_STYLE=off -> none

Every orb object offers the same methods, so main.py does not care which one runs:
set_state(state), set_level(0..1), set_visible(bool), close(), status
"""
from __future__ import annotations

import importlib.util
import logging
import multiprocessing
import queue
import time

logger = logging.getLogger(__name__)


class NullOrb:
    def __init__(self, reason: str = "Desktop orb is off."):
        self.status = reason

    def set_state(self, state) -> None: ...
    def set_level(self, level: float) -> None: ...
    def set_visible(self, visible: bool) -> None: ...
    def close(self) -> None: ...


def _qt_child(in_queue, status_queue) -> None:
    from ui.qt_orb import run  # imported here so the main process stays light

    run(in_queue, status_queue)


class QtOrb:
    """Runs the Qt orb in a separate process and sends it messages."""

    def __init__(self, startup_timeout: float = 12.0):
        ctx = multiprocessing.get_context("spawn")
        self._queue = ctx.Queue(maxsize=256)
        self._status = ctx.Queue()
        self._process = ctx.Process(
            target=_qt_child, args=(self._queue, self._status),
            name="jarvis-orb", daemon=True,
        )
        self._process.start()
        self._last_level = 0.0
        self.available = False
        self.failure = ""

        try:
            message = self._status.get(timeout=startup_timeout)
        except queue.Empty:
            message = "failed: the orb did not start in time"

        if message == "ready":
            self.available = True
            self.status = "Desktop orb is running (transparent Qt)."
        else:
            self.failure = str(message)
            self.status = f"Transparent orb unavailable ({self.failure})."
            self._terminate()

    def _send(self, kind: str, value=None) -> None:
        if not self.available:
            return
        try:
            self._queue.put_nowait((kind, value))
        except queue.Full:
            pass  # dropping a frame of animation is harmless

    def set_state(self, state) -> None:
        self._send("state", getattr(state, "value", str(state)))

    def set_level(self, level: float) -> None:
        now = time.monotonic()
        if now - self._last_level >= 0.03:  # at most ~30 updates per second
            self._last_level = now
            self._send("level", float(level))

    def set_visible(self, visible: bool) -> None:
        self._send("visible", bool(visible))

    def _terminate(self) -> None:
        try:
            if self._process.is_alive():
                self._process.terminate()
        except Exception:
            pass

    def close(self) -> None:
        if self.available:
            self._send("close")
            self._process.join(timeout=2.0)
        self._terminate()
        self.available = False


def create_orb(style: str = "auto"):
    style = (style or "auto").lower()

    if style == "off":
        return NullOrb("Desktop orb is off.")

    notes = []
    if style in {"auto", "qt"}:
        if importlib.util.find_spec("PySide6") is None:
            notes.append("PySide6 is not installed (pip install PySide6-Essentials)")
        else:
            try:
                orb = QtOrb()
                if orb.available:
                    return orb
                notes.append(orb.failure)
            except Exception as error:
                notes.append(f"{type(error).__name__}: {error}")
        if style == "qt":
            return NullOrb("Transparent orb unavailable: " + "; ".join(notes))

    try:
        from ui.desktop_orb import DesktopOrb

        orb = DesktopOrb(enabled=True)
        if notes:
            logger.info("Using the simple orb (%s)", "; ".join(notes))
        return orb
    except Exception as error:
        return NullOrb(f"Desktop orb is unavailable ({type(error).__name__}).")
