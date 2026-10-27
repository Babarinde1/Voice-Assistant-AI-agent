"""Transparent, colorful, audio-reactive Jarvis orb (PySide6 / Qt).

Runs in its OWN process so a graphics problem can never crash the assistant.
Everything is anti-aliased and the window has a real alpha channel: only the
glow, the bars and the orb are visible, the rest of the window is invisible.
You can drag it anywhere. Double-click to shrink or enlarge it. Right-click
for a menu. Fully transparent areas let mouse clicks pass through.
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QAction, QColor, QFont, QGuiApplication, QPainter, QPen, QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QMenu, QWidget

BASE_W, BASE_H = 260, 300

# hue 0..1 (0 red, .08 orange, .17 yellow, .33 green, .5 cyan, .66 blue, .8 violet, .9 pink)
STYLES = {
    "IDLE":                  dict(label="Jarvis",           hue=0.52, span=0.22),
    "WAITING_FOR_WAKE_WORD": dict(label='Say "Hey Jarvis"', hue=0.52, span=0.22),
    "RECORDING":             dict(label="Listening",        hue=0.07, span=0.55),
    "PROCESSING":            dict(label="Thinking",         hue=0.78, span=0.35),
    "SPEAKING":              dict(label="Speaking",         hue=0.40, span=0.45),
    "STOPPED":               dict(label="Stopped",          hue=0.60, span=0.00),
}


def hsl(h: float, s: float, l: float, a: int = 255) -> QColor:
    return QColor.fromHslF(h % 1.0, max(0, min(1, s)), max(0, min(1, l)), a / 255.0)


class OrbWidget(QWidget):
    def __init__(self, in_queue=None):
        super().__init__()
        self._queue = in_queue
        self.state = "WAITING_FOR_WAKE_WORD"
        self.level = 0.0          # newest loudness from the microphone (0..1)
        self._smooth = 0.0        # smoothed copy that the drawing uses
        self._hue_shift = 0.0     # eased hue, so state changes blend smoothly
        self._hue_target = STYLES[self.state]["hue"]
        self._t0 = time.monotonic()
        self._t = 0.0
        self._scale = 1.0
        self._drag = None

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
            | Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowTitle("Jarvis")
        self._apply_size()
        self._move_to_corner()

        self._anim = QTimer(self)
        self._anim.timeout.connect(self._tick)
        self._anim.start(33)  # ~30 frames per second

    # ---- window -------------------------------------------------------
    def _apply_size(self):
        self.setFixedSize(int(BASE_W * self._scale), int(BASE_H * self._scale))

    def _move_to_corner(self):
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.move(area.right() - self.width() - 16, area.bottom() - self.height() - 16)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, event):
        self._drag = None

    def mouseDoubleClickEvent(self, event):
        self._scale = 0.6 if self._scale > 0.8 else 1.0
        self._apply_size()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        close = QAction("Close orb", self)
        close.triggered.connect(QApplication.instance().quit)
        menu.addAction(close)
        menu.exec(event.globalPos())

    # ---- messages from the assistant -----------------------------------
    def set_state(self, state: str):
        if state in STYLES:
            self.state = state
            self._hue_target = STYLES[state]["hue"]

    def _drain_queue(self):
        if self._queue is None:
            return
        for _ in range(64):
            try:
                kind, value = self._queue.get_nowait()
            except Exception:
                return
            if kind == "state":
                self.set_state(value)
            elif kind == "level":
                self.level = float(value)
            elif kind == "visible":
                self.setVisible(bool(value))
            elif kind == "close":
                QApplication.instance().quit()
                return

    # ---- animation ------------------------------------------------------
    def _tick(self):
        self._drain_queue()
        self._t = time.monotonic() - self._t0
        t = self._t

        if self.state == "SPEAKING":      # no microphone signal: synthesize a voice-like pulse
            target = 0.42 + 0.30 * abs(math.sin(t * 7.3) * math.sin(t * 2.9 + 1.0))
        elif self.state == "PROCESSING":
            target = 0.14 + 0.05 * math.sin(t * 3.0)
        elif self.state == "RECORDING":
            target = self.level
        else:
            target = 0.05 + 0.04 * math.sin(t * 1.3) + self.level * 0.5

        rate = 0.45 if target > self._smooth else 0.10   # quick attack, gentle release
        self._smooth += (target - self._smooth) * rate
        self.level *= 0.85                                # fades if updates stop

        diff = ((self._hue_target - self._hue_shift + 0.5) % 1.0) - 0.5
        self._hue_shift = (self._hue_shift + diff * 0.12) % 1.0
        self.update()

    # ---- drawing --------------------------------------------------------
    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing
                         | QPainter.SmoothPixmapTransform)
        p.scale(self._scale, self._scale)
        self._paint_orb(p)
        p.end()

    def _paint_orb(self, p: QPainter):
        style = STYLES.get(self.state, STYLES["IDLE"])
        t, lvl, hue = self._t, self._smooth, self._hue_shift
        span = style["span"]
        cx, cy, R = BASE_W / 2, 122.0, 41.0
        centre = QPointF(cx, cy)

        # Nearly invisible disc so the orb can be grabbed and dragged.
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 4))
        p.drawEllipse(centre, 100, 100)

        # Soft outer glow in two blended colours.
        for dx, dy, h_off, strength in ((-12, -8, 0.0, 1.0), (14, 10, span * 0.8 + 0.08, 0.8)):
            glow = QRadialGradient(QPointF(cx + dx, cy + dy), 118)
            glow.setColorAt(0.0, hsl(hue + h_off, 0.95, 0.58, int(95 * strength * (0.55 + lvl))))
            glow.setColorAt(0.5, hsl(hue + h_off, 0.95, 0.55, int(34 * strength * (0.55 + lvl))))
            glow.setColorAt(1.0, hsl(hue + h_off, 0.95, 0.55, 0))
            p.setBrush(glow)
            p.drawEllipse(QPointF(cx + dx, cy + dy), 118, 118)

        # Ring of fine bars: the audio-reactive part.
        n = 84
        thinking = self.state == "PROCESSING"
        spin = t * (0.35 if thinking else 0.08)
        r0 = R + 10
        for i in range(n):
            frac = i / n
            ang = 2 * math.pi * frac + spin
            wobble = 0.5 + 0.5 * math.sin(t * 2.4 + i * 0.47) * math.sin(t * 1.3 - i * 0.19)
            length = 2.0 + lvl * 38.0 * (0.30 + 0.70 * wobble)
            alpha = 150 + int(90 * min(1.0, lvl * 1.4))
            if thinking:
                length = 2.0 + 5.0 * wobble
                alpha = 110
            color = hsl(hue + span * frac + t * 0.03, 0.88, 0.62, alpha)
            pen = QPen(color, 2.1)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            c, s = math.cos(ang), math.sin(ang)
            p.drawLine(QPointF(cx + c * r0, cy + s * r0),
                       QPointF(cx + c * (r0 + length), cy + s * (r0 + length)))

        # Thinking: three bright arcs orbiting the core.
        if thinking:
            rect = QRectF(cx - (R + 20), cy - (R + 20), 2 * (R + 20), 2 * (R + 20))
            for k in range(3):
                pen = QPen(hsl(hue + 0.12 * k, 0.9, 0.66, 235), 3.2)
                pen.setCapStyle(Qt.RoundCap)
                p.setPen(pen)
                start = int(((t * 160 + k * 120) % 360) * 16)
                p.drawArc(rect, start, 70 * 16)

        # Core orb with a glassy highlight.
        radius = R * (1 + 0.075 * lvl + 0.02 * math.sin(t * 2.0))
        core = QRadialGradient(QPointF(cx - radius * 0.32, cy - radius * 0.38), radius * 1.5)
        core.setColorAt(0.00, QColor(255, 255, 255, 215))
        core.setColorAt(0.30, hsl(hue + span * 0.2, 0.90, 0.68, 185))
        core.setColorAt(0.75, hsl(hue + span * 0.7, 0.85, 0.52, 165))
        core.setColorAt(1.00, hsl(hue + span, 0.80, 0.40, 150))   # glassy, see-through
        p.setPen(QPen(QColor(255, 255, 255, 110), 1.2))
        p.setBrush(core)
        p.drawEllipse(centre, radius, radius)

        # Label with a soft shadow so it reads on any background.
        font = QFont("Segoe UI", 11)
        font.setWeight(QFont.DemiBold)
        p.setFont(font)
        box = QRectF(0, cy + R + 52, BASE_W, 28)
        p.setPen(QColor(0, 0, 0, 95))
        for ox, oy in ((1.4, 1.6), (-1.0, 1.4), (1.4, -0.8), (-1.0, -0.8)):
            p.drawText(box.translated(ox, oy), Qt.AlignCenter, style["label"])
        p.setPen(QColor(255, 255, 255, 240))
        p.drawText(box, Qt.AlignCenter, style["label"])


def run(in_queue, status_queue) -> None:
    """Entry point of the orb process."""
    try:
        app = QApplication([])
        app.setQuitOnLastWindowClosed(True)
        widget = OrbWidget(in_queue)
        widget.show()
        status_queue.put("ready")
        app.exec()
    except Exception as error:  # report instead of dying silently
        try:
            status_queue.put(f"failed: {type(error).__name__}: {error}")
        except Exception:
            pass
