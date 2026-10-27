"""Regenerates assets/orb-states.png, the picture used in README.md.

The shapes and colours mirror ui/qt_orb.py: a glassy core, a ring of 84 bars and a
soft two-colour glow. Needs: pillow, numpy.   Run:  python assets/make_orb_states.py
"""
import colorsys
import math
from pathlib import Path

W, H = 960, 380
R = 41.0
STATES = [
    # title, in-app label, hue, span, audio level, wobble time, breathing seconds
    ("Sleeping", 'Say "Hey Jarvis"', 0.52, 0.22, 0.04, 1.0, 4.0, "Waiting for the wake word"),
    ("Listening", "Listening", 0.07, 0.55, 0.78, 2.3, 1.2, "Recording your request"),
    ("Speaking", "Speaking", 0.40, 0.45, 0.52, 3.7, 0.9, "Reading the answer aloud"),
]


def hsl(h, s, l):
    r, g, b = colorsys.hls_to_rgb(h % 1.0, l, s)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def render_png(path: Path, scale: int = 2) -> bool:
    """Same artwork drawn with Pillow (no SVG renderer needed). Returns False if Pillow/numpy are missing."""
    try:
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False

    S = scale
    w, h = W * S, H * S

    def rgb(hexcol):
        return tuple(int(hexcol[i:i + 2], 16) for i in (1, 3, 5))

    def radial(layer, cx, cy, r, stops):
        """Composite a radial gradient; stops = [(offset, '#rrggbb', alpha 0..1)]."""
        x0, y0 = int(max(0, cx - r)), int(max(0, cy - r))
        x1, y1 = int(min(w, cx + r)), int(min(h, cy + r))
        if x1 <= x0 or y1 <= y0:
            return layer
        yy, xx = np.mgrid[y0:y1, x0:x1]
        d = np.clip(np.hypot(xx - cx, yy - cy) / r, 0, 1)
        offs = [o for o, _, _ in stops]
        patch = np.zeros((y1 - y0, x1 - x0, 4), dtype=np.float32)
        for ch in range(3):
            patch[..., ch] = np.interp(d, offs, [rgb(c)[ch] for _, c, _ in stops])
        patch[..., 3] = np.interp(d, offs, [a * 255 for _, _, a in stops])
        tile = Image.fromarray(patch.astype(np.uint8), "RGBA")
        layer.alpha_composite(tile, (x0, y0))
        return layer

    def font(size, bold=False):
        for name in ("segoeuib.ttf" if bold else "segoeui.ttf", "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
                     "arialbd.ttf" if bold else "arial.ttf"):
            try:
                return ImageFont.truetype(name, size * S)
            except OSError:
                continue
        return ImageFont.load_default()

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    bg = np.zeros((h, w, 4), dtype=np.uint8)
    grad = (np.linspace(0, 1, w)[None, :] + np.linspace(0, 1, h)[:, None]) / 2
    for ch, (a, b) in enumerate(((0x12, 0x0a), (0x16, 0x0c), (0x2b, 0x18))):
        bg[..., ch] = (a + (b - a) * grad).astype(np.uint8)
    bg[..., 3] = 255
    panel = Image.fromarray(bg, "RGBA")
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=22 * S, fill=255)
    img.paste(panel, (0, 0), mask)

    xs = [W * 0.17, W * 0.5, W * 0.83]
    for i, (title, label, hue, span, lvl, t, breathe, caption) in enumerate(STATES):
        cx, cy = round(xs[i]) * S, 150 * S
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        for dx, dy, off, strength in ((-12, -8, 0.0, 1.0), (14, 10, span * 0.8 + 0.08, 0.8)):
            c = hsl(hue + off, 0.95, 0.58)
            a0 = min(1.0, 0.37 * strength * (0.55 + lvl))
            radial(layer, cx + dx * S, cy + dy * S, 118 * S,
                   [(0, c, a0), (0.5, c, a0 * 0.36), (1, c, 0)])
        # bars on a supersampled layer for smooth round caps
        bars = Image.new("RGBA", (w * 2, h * 2), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bars)
        n, r0 = 84, R + 10
        for k in range(n):
            frac = k / n
            ang = 2 * math.pi * frac + t * 0.08
            wob = 0.5 + 0.5 * math.sin(t * 2.4 + k * 0.47) * math.sin(t * 1.3 - k * 0.19)
            length = 2.0 + lvl * 38.0 * (0.30 + 0.70 * wob)
            a = int(min(1.0, (150 + 90 * min(1.0, lvl * 1.4)) / 255) * 255)
            col = rgb(hsl(hue + span * frac + t * 0.03, 0.88, 0.62)) + (a,)
            c_, s_ = math.cos(ang), math.sin(ang)
            p1 = ((cx / S + c_ * r0) * S * 2, (cy / S + s_ * r0) * S * 2)
            p2 = ((cx / S + c_ * (r0 + length)) * S * 2, (cy / S + s_ * (r0 + length)) * S * 2)
            bd.line([p1, p2], fill=col, width=int(2.1 * S * 2))
            for px, py in (p1, p2):
                rr = 2.1 * S
                bd.ellipse((px - rr, py - rr, px + rr, py + rr), fill=col)
        bars = bars.resize((w, h), Image.LANCZOS)
        layer.alpha_composite(bars)
        # glassy core
        rad = R * (1 + 0.075 * lvl) * S
        core = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        radial(core, cx - rad * 0.32, cy - rad * 0.38, rad * 1.5, [
            (0, "#ffffff", 0.84), (0.3, hsl(hue + span * 0.2, 0.9, 0.68), 0.73),
            (0.75, hsl(hue + span * 0.7, 0.85, 0.52), 0.65), (1, hsl(hue + span, 0.8, 0.4), 0.59)])
        disc = Image.new("L", (w * 2, h * 2), 0)
        ImageDraw.Draw(disc).ellipse(((cx - rad) * 2, (cy - rad) * 2, (cx + rad) * 2, (cy + rad) * 2), fill=255)
        disc = disc.resize((w, h), Image.LANCZOS)
        core.putalpha(Image.fromarray((np.array(core)[..., 3].astype(np.float32)
                                       * np.array(disc).astype(np.float32) / 255).astype(np.uint8)))
        layer.alpha_composite(core)
        ImageDraw.Draw(layer).ellipse((cx - rad, cy - rad, cx + rad, cy + rad),
                                      outline=(255, 255, 255, 110), width=max(1, S))
        img.alpha_composite(Image.composite(layer, Image.new("RGBA", (w, h), (0, 0, 0, 0)), mask))

        d = ImageDraw.Draw(img)
        d.text((cx, (cy / S + R + 82 - 14) * S), label, font=font(15, True), fill=(255, 255, 255, 240), anchor="mm")
        d.text((cx, (H - 52 - 8) * S), title, font=font(22, True),
               fill=rgb(hsl(hue + span * 0.3, 0.9, 0.72)) + (255,), anchor="mm")
        d.text((cx, (H - 28 - 4) * S), caption, font=font(13), fill=(154, 163, 196, 255), anchor="mm")
    img.save(path)
    return True


if __name__ == "__main__":
    here = Path(__file__).parent
    print("wrote", here / "orb-states.png" if render_png(here / "orb-states.png") else "PNG skipped (needs pillow, numpy)")
