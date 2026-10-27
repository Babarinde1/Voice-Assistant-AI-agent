"""Small floating desktop orb that reflects Jarvis runtime state.

The UI is intentionally optional and fails gracefully if Tk cannot start.
Tk calls happen only on the UI thread; other threads send state via a Queue.
"""
from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk

logger = logging.getLogger(__name__)

class DesktopOrb:
    """A movable, always-on-top Jarvis status orb."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._queue: queue.Queue[str] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._available = False
        self._state = "IDLE"
        self._phase = 0
        if enabled:
            self._thread = threading.Thread(
                target=self._run, name="jarvis-desktop-orb", daemon=True
            )
            self._thread.start()
            # Do not block startup if the desktop UI takes time.
            self._ready.wait(timeout=2.0)

    @property
    def status(self) -> str:
        if not self.enabled:
            return "Desktop orb is disabled."
        if self._available:
            return "Desktop orb is running."
        return "Desktop orb is unavailable (Jarvis can continue in console mode)."

    def set_level(self, level: float) -> None:
        """The simple orb does not react to loudness."""

    def set_visible(self, visible: bool) -> None:
        if self.enabled:
            self._queue.put("__SHOW__" if visible else "__HIDE__")

    def set_state(self, state) -> None:
        """Thread-safe; can be called from the assistant's main thread."""
        if self.enabled:
            value = getattr(state, "value", str(state))
            self._queue.put(value)

    def close(self) -> None:
        if self.enabled:
            self._queue.put("__CLOSE__")

    def _run(self) -> None:
        try:
            self._root = tk.Tk()
            self._root.title("Jarvis")
            self._root.overrideredirect(True)
            self._root.attributes("-topmost", True)
            self._root.configure(bg="#101522")
            self._root.geometry("116x142+30+120")
            self._canvas = tk.Canvas(
                self._root, width=116, height=142, bg="#101522",
                highlightthickness=0, bd=0
            )
            self._canvas.pack(fill="both", expand=True)
            self._install_drag()
            self._draw()
            self._available = True
            self._ready.set()
            self._root.after(100, self._tick)
            self._root.mainloop()
        except Exception as error:
            self._available = False
            self._ready.set()
            logger.warning("Desktop orb could not start (%s)", type(error).__name__)

    def _draw(self) -> None:
        c = self._canvas
        c.delete("all")
        # Dark rounded-looking panel and a luminous orb built from circles.
        c.create_rectangle(4, 4, 112, 138, fill="#101522", outline="#28334a", width=1)
        active = self._state in {"RECORDING", "SPEAKING", "PROCESSING"}
        color = {
            "IDLE": "#46d9c8",
            "WAITING_FOR_WAKE_WORD": "#46d9c8",
            "RECORDING": "#ffbd59",
            "PROCESSING": "#a58bff",
            "SPEAKING": "#42d9ff",
            "STOPPED": "#778096",
        }.get(self._state, "#46d9c8")
        cx, cy = 58, 48
        if active:
            pulse = (self._phase % 4) * 3
            c.create_oval(cx-30-pulse, cy-30-pulse, cx+30+pulse, cy+30+pulse,
                          outline=color, width=2)
            c.create_oval(cx-24-pulse//2, cy-24-pulse//2,
                          cx+24+pulse//2, cy+24+pulse//2,
                          outline=color, width=1)
        c.create_oval(cx-20, cy-20, cx+20, cy+20,
                      fill="#18283b", outline=color, width=3)
        c.create_oval(cx-9, cy-9, cx+9, cy+9, fill=color, outline="")
        label = {
            "IDLE": "JARVIS",
            "WAITING_FOR_WAKE_WORD": "LISTENING",
            "RECORDING": "HEARING YOU",
            "PROCESSING": "THINKING",
            "SPEAKING": "SPEAKING",
            "STOPPED": "STOPPED",
        }.get(self._state, self._state)
        c.create_text(58, 91, text=label, fill="#e8f0ff",
                      font=("Segoe UI", 8, "bold"))
        c.create_text(58, 108, text="drag to move", fill="#7f8ba5",
                      font=("Segoe UI", 7))

    def _tick(self) -> None:
        try:
            while True:
                state = self._queue.get_nowait()
                if state == "__CLOSE__":
                    self._root.destroy()
                    return
                if state == "__HIDE__":
                    self._root.withdraw()
                    continue
                if state == "__SHOW__":
                    self._root.deiconify()
                    continue
                self._state = state
        except queue.Empty:
            pass
        self._phase += 1
        self._draw()
        self._root.after(180, self._tick)

    # Drag the orb with the left mouse button.
    def _install_drag(self) -> None:
        offset = {"x": 0, "y": 0}

        def press(event):
            offset["x"], offset["y"] = event.x_root - self._root.winfo_x(), event.y_root - self._root.winfo_y()

        def move(event):
            self._root.geometry(f"+{event.x_root - offset['x']}+{event.y_root - offset['y']}")

        self._canvas.bind("<ButtonPress-1>", press)
        self._canvas.bind("<B1-Motion>", move)
