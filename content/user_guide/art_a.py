"""Storybook (direction A) support: image slots with stand-in vector fallbacks."""
import os, math
from reportlab.lib import colors
from reportlab.platypus import Flowable
import art

HEX = colors.HexColor
ART_DIR = os.environ.get("SWEETYAAR_ART_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "art"))
PAPER = HEX("#fbf3e4")


def find_art(name):
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = os.path.join(ART_DIR, f"{name}.{ext}")
        if os.path.exists(p):
            return p
    return None


def _size(path):
    from PIL import Image
    with Image.open(path) as im:
        return im.size


def draw_cover_fit(c, path, x, y, w, h, fy=0.5):
    """Fill the w x h box (crop to fit). fy: 0 keeps the image top, 1 the bottom, 0.5 centres."""
    iw, ih = _size(path)
    s = max(w / iw, h / ih)
    dw, dh = iw * s, ih * s
    c.saveState()
    p = c.beginPath(); p.rect(x, y, w, h); c.clipPath(p, stroke=0, fill=0)
    c.drawImage(path, x + (w - dw) / 2, y + (h - dh) * (1 - fy), dw, dh, mask="auto")
    c.restoreState()


def draw_contain(c, path, x, y, w, h):
    iw, ih = _size(path)
    s = min(w / iw, h / ih)
    dw, dh = iw * s, ih * s
    c.drawImage(path, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh, mask="auto")


def wave(c, y, amp, wl, fill, w, x0=0, below=True):
    p = c.beginPath(); p.moveTo(x0, y)
    x = x0
    while x <= x0 + w:
        p.lineTo(x, y + amp * math.sin((x - x0) / wl * 2 * math.pi)); x += 4
    p.lineTo(x0 + w, y - 300 if below else y + 300); p.lineTo(x0, y - 300 if below else y + 300); p.close()
    c.setFillColor(fill); c.drawPath(p, fill=1, stroke=0)


class ArtImg(Flowable):
    """Generated image if present in ART_DIR, otherwise a vector stand-in."""
    def __init__(self, name, width, height, fallback):
        super().__init__(); self.name = name; self.width = width; self.height = height; self.fallback = fallback
    def draw(self):
        p = find_art(self.name)
        if p: draw_contain(self.canv, p, 0, 0, self.width, self.height)
        else:
            self.canv.saveState(); self.fallback(self.canv, self.width, self.height); self.canv.restoreState()


# ------------------------------------------------------------------ chapter band stand-ins
TINT = {"A": "#dfe9cf", 1: "#cfe5df", 2: "#f6e3c4", 3: "#d6e6f5", 4: "#e3ddf3", 5: "#f8dfc9", 6: "#d8d5ee", 7: "#f9dccf", 8: "#dfe9cf"}


def _phone(c, x, y, w, h, screen="#fff"):
    c.setFillColor(HEX("#3d4f50")); c.roundRect(x, y, w, h, w * 0.14, fill=1, stroke=0)
    c.setFillColor(HEX(screen)); c.roundRect(x + w * 0.07, y + h * 0.05, w * 0.86, h * 0.9, w * 0.1, fill=1, stroke=0)


def _arcs(c, cx, cy, r, col):
    c.setStrokeColor(col); c.setLineWidth(2.4); c.setLineCap(1)
    for k, rr in enumerate((r, r * 1.6, r * 2.2)):
        c.arc(cx - rr, cy - rr, cx + rr, cy + rr, -35, 70)


def band_scene(c, w, h, n):
    """Stand-in header art for chapter n; drawn into (0,0,w,h)."""
    c.setFillColor(HEX(TINT[n])); c.rect(0, 0, w, h, fill=1, stroke=0)
    for (x, y, s) in [(0.12, 0.74, 0.12), (0.86, 0.68, 0.14)]:
        art.cloud(c, w * x, h * y, w * s, colors.Color(1, 1, 1, alpha=0.8))
    wave(c, h * 0.22, 5, 90, HEX("#b9d99b"), w)
    wave(c, h * 0.12, 6, 130, HEX("#9bc885"), w)
    cx, cy = w / 2, h * 0.36
    if n == 1:
        art.cube(c, cx - 18 * 2.835, cy - 4, 30 * 2.835)
        c.setStrokeColor(HEX("#3d4f50")); c.setLineWidth(3); c.setLineCap(1)
        p = c.beginPath(); p.moveTo(cx + 30 * 2.835, cy + 14); p.curveTo(cx + 55 * 2.835, cy + 40, cx + 45 * 2.835, cy - 10, cx + 70 * 2.835, cy + 10)
        c.drawPath(p, fill=0, stroke=1)
        c.setFillColor(HEX("#3d4f50")); c.roundRect(cx + 70 * 2.835, cy + 2, 16 * 2.835, 16, 4, fill=1, stroke=0)
        art.star(c, cx + 50 * 2.835, cy + 52, 9, art.YELLOW)
    elif n == 2:
        c.saveState(); c.translate(cx - 70 * 2.835, cy - 6); art.icon_note(c, 32 * 2.835, 32 * 2.835); c.restoreState()
        c.saveState(); c.translate(cx + 38 * 2.835, cy - 6); art.icon_teddy(c, 32 * 2.835, 32 * 2.835); c.restoreState()
        art.teddy_head(c, cx, cy + 22, 22 * 2.835 * 0.7)
    elif n == 3:
        _phone(c, cx - 70 * 2.835, cy - 10, 26 * 2.835, 44 * 2.835, "#cfe7f7")
        art.cube(c, cx + 28 * 2.835, cy - 6, 24 * 2.835)
        _arcs(c, cx - 28 * 2.835, cy + 36, 10, art.BLUE)
    elif n == 4:
        _phone(c, cx - 22 * 2.835, cy - 14, 40 * 2.835, 56 * 2.835, "#f8f4ef")
        for i, col in enumerate([art.TEAL_L, HEX("#f7c49a"), HEX("#d9d2c8")]):
            c.setFillColor(col); c.roundRect(cx - 14 * 2.835, cy + 62 - i * 22 - 6, 24 * 2.835, 16, 5, fill=1, stroke=0)
        art.teddy_head(c, cx + 52 * 2.835, cy + 26, 16 * 2.835 * 0.7)
    elif n == 5:
        _phone(c, cx - 78 * 2.835, cy - 10, 24 * 2.835, 42 * 2.835, "#fff3d6")
        art.cube(c, cx + 36 * 2.835, cy - 6, 24 * 2.835)
        c.setStrokeColor(art.YELLOW); c.setLineWidth(5)
        c.arc(cx - 26 * 2.835, cy + 6, cx + 26 * 2.835 - 4 * 2.835, cy + 60, 30, 260)
        c.setFillColor(HEX("#3d4f50")); c.setFont("Round", 16); c.drawCentredString(cx - 1 * 2.835, cy + 29, "75%")
    elif n == 6:
        c.saveState(); c.translate(w * 0.15, h * 0.05); art.scene_moon(c, w * 0.7, h * 0.95); c.restoreState()
    elif n == 7:
        c.setFillColor(HEX("#f3dfc0")); c.roundRect(cx - 24 * 2.835, cy - 8, 48 * 2.835, 26 * 2.835, 10, fill=1, stroke=0)
        c.setFillColor(HEX("#c98f52")); c.roundRect(cx + 24 * 2.835, cy + 24, 6, 20, 3, fill=1, stroke=0)
        art.heart(c, cx, cy + 44, 12, art.PINK)
        art.star(c, cx - 62 * 2.835, cy + 40, 9, art.YELLOW)
    elif n == 8 or n == "A":
        art.teddy_head(c, cx - 16 * 2.835, cy + 20, 22 * 2.835 * 0.7)
        c.setFillColor(HEX("#d9825b")); c.setFont("Georgia-BI" if False else "Round", 60); c.drawCentredString(cx + 40 * 2.835, cy + 10, "?")


def cover_scene(c, x, y, w, h):
    """Stand-in cover scene inside an arch window (x, y, w, h)."""
    c.saveState()
    r = w / 2
    p = c.beginPath(); p.moveTo(x, y); p.lineTo(x, y + h - r); p.arcTo(x, y + h - 2 * r, x + w, y + h, 180, -180); p.lineTo(x + w, y); p.close()
    c.clipPath(p, stroke=0, fill=0)
    c.setFillColor(HEX("#cfe5df")); c.rect(x, y, w, h, fill=1, stroke=0)
    c.setFillColor(HEX("#f6d9b8")); c.rect(x, y, w, h * 0.38, fill=1, stroke=0)
    wave(c, y + h * 0.58, 6, 90, HEX("#a9d3b8"), w, x0=x)
    wave(c, y + h * 0.47, 8, 120, HEX("#86bf9f"), w, x0=x)
    for (fx, fy) in [(0.2, 0.8), (0.78, 0.86)]:
        art.cloud(c, x + w * fx, y + h * fy, w * 0.28, colors.white)
    art.crescent(c, x + w * 0.75, y + h * 0.60, 28 * 2.835, HEX("#f3d58a"))
    for (fx, fy, rr) in [(0.22, 0.60, 6), (0.40, 0.72, 4.5), (0.58, 0.52, 5), (0.86, 0.78, 4)]:
        art.star(c, x + w * fx, y + h * fy, rr * 2.835, HEX("#f5c94e"))
    art.cube(c, x + w / 2 - 24 * 2.835, y + h * 0.1, 48 * 2.835)
    art.note(c, x + w * 0.3, y + h * 0.34, 3.6 * 2.835, art.PINK, False)
    art.note(c, x + w * 0.68, y + h * 0.40, 3.6 * 2.835, art.TEAL, True)
    c.restoreState()
