"""Vector illustrations (flat, soft, friendly) drawn with reportlab."""
import math
from reportlab.lib import colors
from reportlab.platypus import Flowable

HEX = colors.HexColor
WOOD_F, WOOD_S, WOOD_T = HEX("#e3ad70"), HEX("#c98f52"), HEX("#f0c88f")
WOOD_DK = HEX("#7b4b23")
TEAL, TEAL_L, TEAL_D = HEX("#34b8a9"), HEX("#a9ddd4"), HEX("#08736c")
PINK, YELLOW, BLUE, LILAC = HEX("#f2a7b8"), HEX("#f5c94e"), HEX("#74b9e6"), HEX("#c7bde5")
GREEN_L, GREEN_D = HEX("#b9d99b"), HEX("#7fb26a")
BEAR, BEAR_D, BEAR_L = HEX("#e6b06f"), HEX("#c98a4a"), HEX("#f6dcae")


def star(c, cx, cy, r, fill, rot=0):
    p = c.beginPath()
    for i in range(10):
        a = math.pi / 2 + rot + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.48
        x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
        (p.moveTo if i == 0 else p.lineTo)(x, y)
    p.close()
    c.setFillColor(fill); c.setStrokeColor(fill); c.setLineJoin(1); c.setLineWidth(r * 0.22)
    c.drawPath(p, fill=1, stroke=1)


def note(c, x, y, s, fill, double=False):
    """Eighth note (or beamed pair); (x, y) is the head centre."""
    c.setFillColor(fill); c.setStrokeColor(fill); c.setLineCap(1)
    def head(hx, hy):
        c.saveState(); c.translate(hx, hy); c.rotate(-20)
        c.ellipse(-0.55 * s, -0.40 * s, 0.55 * s, 0.40 * s, fill=1, stroke=0); c.restoreState()
    c.setLineWidth(0.17 * s)
    head(x, y)
    c.line(x + 0.5 * s, y + 0.1 * s, x + 0.5 * s, y + 2.2 * s)
    if double:
        x2 = x + 1.5 * s
        head(x2, y - 0.3 * s)
        c.line(x2 + 0.5 * s, y - 0.2 * s, x2 + 0.5 * s, y + 1.9 * s)
        c.setLineWidth(0.4 * s); c.line(x + 0.5 * s, y + 2.15 * s, x2 + 0.5 * s, y + 1.85 * s)
    else:
        p = c.beginPath(); p.moveTo(x + 0.5 * s, y + 2.2 * s)
        p.curveTo(x + 0.6 * s, y + 1.6 * s, x + 1.5 * s, y + 1.7 * s, x + 1.3 * s, y + 0.9 * s)
        p.curveTo(x + 1.3 * s, y + 1.5 * s, x + 0.9 * s, y + 1.5 * s, x + 0.5 * s, y + 1.5 * s)
        p.close(); c.drawPath(p, fill=1, stroke=0)


def cloud(c, cx, cy, w, fill, edge=None):
    c.setFillColor(fill)
    for dx, dy, r in [(-0.28, 0.00, 0.22), (0.0, 0.10, 0.30), (0.28, 0.02, 0.23), (-0.05, -0.05, 0.25), (0.10, -0.03, 0.25)]:
        c.circle(cx + dx * w, cy + dy * w, r * w * 0.8, fill=1, stroke=0)
    c.rect(cx - 0.34 * w, cy - 0.17 * w, 0.68 * w, 0.14 * w, fill=1, stroke=0)


def heart(c, cx, cy, s, fill):
    p = c.beginPath()
    p.moveTo(cx, cy - s * 0.9)
    p.curveTo(cx - s * 1.5, cy - s * 0.1, cx - s * 0.9, cy + s * 1.0, cx, cy + s * 0.35)
    p.curveTo(cx + s * 0.9, cy + s * 1.0, cx + s * 1.5, cy - s * 0.1, cx, cy - s * 0.9)
    c.setFillColor(fill); c.drawPath(p, fill=1, stroke=0)


def cube(c, x, y, s):
    """Wooden speaker cube. (x, y) is the bottom-left of the front face."""
    dx, dy = 0.26 * s, 0.20 * s
    c.setLineJoin(1)
    c.setFillColor(colors.Color(0, 0, 0, alpha=0.08))
    c.ellipse(x - 0.05 * s, y - 0.10 * s, x + s + dx + 0.05 * s, y + 0.07 * s, fill=1, stroke=0)
    p = c.beginPath(); p.moveTo(x + s, y); p.lineTo(x + s + dx, y + dy); p.lineTo(x + s + dx, y + s + dy); p.lineTo(x + s, y + s); p.close()
    c.setFillColor(WOOD_S); c.setStrokeColor(WOOD_S); c.setLineWidth(s * 0.04); c.drawPath(p, fill=1, stroke=1)
    p = c.beginPath(); p.moveTo(x, y + s); p.lineTo(x + s, y + s); p.lineTo(x + s + dx, y + s + dy); p.lineTo(x + dx, y + s + dy); p.close()
    c.setFillColor(WOOD_T); c.setStrokeColor(WOOD_T); c.drawPath(p, fill=1, stroke=1)
    c.setFillColor(WOOD_F); c.setStrokeColor(WOOD_F); c.setLineWidth(s * 0.04)
    c.roundRect(x, y, s, s, s * 0.07, fill=1, stroke=1)
    gx, gy, gr = x + 0.40 * s, y + 0.50 * s, 0.28 * s
    c.setFillColor(WOOD_DK); c.circle(gx, gy, gr, fill=1, stroke=0)
    c.setStrokeColor(WOOD_F); c.setLineWidth(s * 0.035); c.setLineCap(1)
    for k in (-0.55, -0.18, 0.18, 0.55):
        hw = math.sqrt(max(gr * gr - (k * gr) ** 2, 0)) * 0.80
        c.line(gx - hw, gy + k * gr, gx + hw, gy + k * gr)
    c.setFillColor(WOOD_S); c.circle(x + 0.84 * s, y + 0.17 * s, 0.045 * s, fill=1, stroke=0)
    heart(c, x + s + dx * 0.5, y + 0.58 * s + dy * 0.5, 0.075 * s, WOOD_DK)
    kx, ky = x + 0.52 * s + dx * 0.45, y + s + dy * 0.45
    c.setFillColor(HEX("#1f9a8c")); c.ellipse(kx - 0.12 * s, ky - 0.05 * s, kx + 0.12 * s, ky + 0.05 * s, fill=1, stroke=0)
    c.rect(kx - 0.12 * s, ky, 0.24 * s, 0.09 * s, fill=1, stroke=0)
    c.setFillColor(TEAL); c.ellipse(kx - 0.12 * s, ky + 0.04 * s, kx + 0.12 * s, ky + 0.14 * s, fill=1, stroke=0)


def crescent(c, cx, cy, r, fill, off=0.42):
    """Crescent: outer circle clipped, with an offset circle cut out (even-odd)."""
    r2 = r * 0.84
    ox, oy = cx + off * r, cy + off * r * 0.55
    c.saveState()
    clip = c.beginPath(); clip.circle(cx, cy, r); c.clipPath(clip, stroke=0, fill=0)
    p = c.beginPath(); p.rect(cx - 2 * r, cy - 2 * r, 4 * r, 4 * r); p.circle(ox, oy, r2)
    c.setFillColor(fill); c.drawPath(p, fill=1, stroke=0, fillMode=0)
    c.restoreState()


def teddy_head(c, cx, cy, r, mood="happy"):
    for sx in (-1, 1):
        c.setFillColor(BEAR); c.circle(cx + sx * r * 0.72, cy + r * 0.78, r * 0.36, fill=1, stroke=0)
        c.setFillColor(BEAR_L); c.circle(cx + sx * r * 0.72, cy + r * 0.78, r * 0.2, fill=1, stroke=0)
    c.setFillColor(BEAR); c.circle(cx, cy, r, fill=1, stroke=0)
    c.setFillColor(BEAR_L); c.ellipse(cx - r * 0.38, cy - r * 0.55, cx + r * 0.38, cy - r * 0.02, fill=1, stroke=0)
    c.setFillColor(HEX("#7a4a2a")); c.ellipse(cx - r * 0.13, cy - r * 0.16, cx + r * 0.13, cy - r * 0.02, fill=1, stroke=0)
    c.setStrokeColor(HEX("#7a4a2a")); c.setLineWidth(r * 0.06); c.setLineCap(1)
    c.line(cx, cy - r * 0.16, cx, cy - r * 0.26)
    if mood == "happy":
        c.setFillColor(HEX("#5b3a22"))
        for sx in (-1, 1): c.circle(cx + sx * r * 0.36, cy + r * 0.18, r * 0.085, fill=1, stroke=0)
        p = c.beginPath(); p.moveTo(cx - r * 0.16, cy - r * 0.30)
        p.curveTo(cx - r * 0.08, cy - r * 0.42, cx + r * 0.08, cy - r * 0.42, cx + r * 0.16, cy - r * 0.30)
        c.drawPath(p, fill=0, stroke=1)
    else:  # tired: closed, drooping eyes
        for sx in (-1, 1):
            p = c.beginPath(); p.moveTo(cx + sx * r * 0.52, cy + r * 0.18)
            p.curveTo(cx + sx * r * 0.44, cy + r * 0.05, cx + sx * r * 0.26, cy + r * 0.05, cx + sx * r * 0.2, cy + r * 0.18)
            c.drawPath(p, fill=0, stroke=1)
        c.setFillColor(PINK); c.ellipse(cx - r * 0.12, cy - r * 0.44, cx + r * 0.12, cy - r * 0.26, fill=1, stroke=0)
    c.setFillColor(colors.Color(0.95, 0.55, 0.6, alpha=0.45))
    for sx in (-1, 1): c.circle(cx + sx * r * 0.62, cy - r * 0.12, r * 0.14, fill=1, stroke=0)


class Art(Flowable):
    def __init__(self, width, height, fn):
        super().__init__(); self.width = width; self.height = height; self.fn = fn
    def draw(self):
        self.canv.saveState(); self.fn(self.canv, self.width, self.height); self.canv.restoreState()


def scene_cover(c, w, h):
    c.setFillColor(TEAL_L); c.ellipse(w * 0.06, h * 0.03, w * 0.94, h * 0.30, fill=1, stroke=0)
    c.setFillColor(HEX("#c3e8e1")); c.ellipse(w * 0.14, h * 0.07, w * 0.86, h * 0.26, fill=1, stroke=0)
    for (x, y, k) in [(0.10, 0.76, 0.2), (0.80, 0.82, 0.2), (0.03, 0.50, 0.14), (0.88, 0.56, 0.16)]:
        cloud(c, w * x + w * 0.07, h * y, w * k, colors.white)
    cube(c, w * 0.34, h * 0.14, w * 0.27)
    for (x, y, s, col, d) in [(0.18, 0.60, 0.028, PINK, False), (0.30, 0.74, 0.026, TEAL, True), (0.62, 0.78, 0.026, LILAC, True),
                              (0.76, 0.62, 0.028, YELLOW, False)]:
        note(c, w * x, h * y, w * s, col, d)
    for (x, y, r, col) in [(0.10, 0.20, 0.03, GREEN_L), (0.24, 0.50, 0.012, YELLOW), (0.70, 0.45, 0.012, PINK), (0.82, 0.30, 0.014, BLUE)]:
        c.setFillColor(col); c.circle(w * x, h * y, w * r, fill=1, stroke=0)
    star(c, w * 0.14, h * 0.46, w * 0.025, YELLOW)
    c.setFillColor(GREEN_D)
    for ang, ln in [(-25, 0.12), (10, 0.16), (35, 0.11)]:
        c.saveState(); c.translate(w * 0.20, h * 0.12); c.rotate(ang); c.ellipse(-w * 0.015, 0, w * 0.015, h * ln * 1.4, fill=1, stroke=0); c.restoreState()


def scene_welcome(c, w, h):
    c.setFillColor(HEX("#cfe7d3")); c.circle(w * 0.84, h * 0.42, h * 0.40, fill=1, stroke=0)
    c.setFillColor(HEX("#b9dcc5")); c.circle(w * 0.72, h * 0.30, h * 0.26, fill=1, stroke=0)
    cube(c, w * 0.34, h * 0.10, h * 0.62)
    c.setStrokeColor(GREEN_D); c.setLineWidth(2.2); c.line(w * 0.14, h * 0.08, w * 0.14, h * 0.50)
    for k in range(5):
        a = k * 2 * math.pi / 5 + 0.3
        c.setFillColor(PINK); c.circle(w * 0.14 + h * 0.10 * math.cos(a), h * 0.58 + h * 0.10 * math.sin(a), h * 0.075, fill=1, stroke=0)
    c.setFillColor(YELLOW); c.circle(w * 0.14, h * 0.58, h * 0.06, fill=1, stroke=0)
    c.setFillColor(BLUE); c.roundRect(w * 0.20, h * 0.08, h * 0.22, h * 0.22, 5, fill=1, stroke=0)
    c.setFillColor(HEX("#5aa6d6")); c.roundRect(w * 0.20, h * 0.08, h * 0.22, h * 0.06, 3, fill=1, stroke=0)
    star(c, w * 0.86, h * 0.22, h * 0.13, YELLOW, rot=0.2)
    c.setFillColor(PINK); c.circle(w * 0.64, h * 0.08, h * 0.06, fill=1, stroke=0)
    note(c, w * 0.80, h * 0.62, h * 0.07, BLUE, True)


def scene_moon(c, w, h):
    for (x, y, r, col) in [(0.06, 0.34, 0.03, BLUE), (0.20, 0.30, 0.022, PINK), (0.79, 0.30, 0.018, LILAC), (0.92, 0.70, 0.03, PINK), (0.72, 0.62, 0.02, YELLOW)]:
        c.setFillColor(col); c.circle(w * x, h * y, h * r * 1.6, fill=1, stroke=0)
    for (x, y, r, rot) in [(0.14, 0.52, 0.09, 0.1), (0.30, 0.55, 0.07, -0.2), (0.62, 0.70, 0.08, 0.2), (0.82, 0.38, 0.10, -0.1)]:
        star(c, w * x, h * y, h * r * 1.1, YELLOW, rot)
    for (x, y, r, col) in [(0.24, 0.22, 0.09, TEAL_L), (0.94, 0.45, 0.08, LILAC)]:
        star(c, w * x, h * y, h * r, col)
    crescent(c, w * 0.47, h * 0.56, h * 0.42, HEX("#f3d58a"))
    cloud(c, w * 0.59, h * 0.28, w * 0.20, LILAC)
    c.setStrokeColor(HEX("#5a4a80")); c.setLineWidth(1.4); c.setLineCap(1)
    for sx in (-1, 1):
        cx = w * 0.59 + sx * w * 0.036
        p = c.beginPath(); p.moveTo(cx - w * 0.012, h * 0.30)
        p.curveTo(cx - w * 0.008, h * 0.27, cx + w * 0.008, h * 0.27, cx + w * 0.012, h * 0.30); c.drawPath(p, fill=0, stroke=1)
    p = c.beginPath(); p.moveTo(w * 0.575, h * 0.23); p.curveTo(w * 0.585, h * 0.20, w * 0.595, h * 0.20, w * 0.605, h * 0.23)
    c.drawPath(p, fill=0, stroke=1)
    c.setFillColor(colors.Color(0.95, 0.55, 0.7, alpha=0.4))
    for sx in (-1, 1): c.circle(w * 0.59 + sx * w * 0.062, h * 0.255, h * 0.035, fill=1, stroke=0)


def scene_tired_teddy(c, w, h):
    cx = w * 0.5
    for sx in (-1, 1):
        c.setFillColor(BEAR); c.circle(cx + sx * w * 0.30, h * 0.16, w * 0.17, fill=1, stroke=0)
        c.setFillColor(BEAR_D); c.circle(cx + sx * w * 0.31, h * 0.15, w * 0.085, fill=1, stroke=0)
    c.setFillColor(BEAR); c.ellipse(cx - w * 0.30, h * 0.08, cx + w * 0.30, h * 0.58, fill=1, stroke=0)
    c.setFillColor(BEAR_L); c.ellipse(cx - w * 0.17, h * 0.12, cx + w * 0.17, h * 0.46, fill=1, stroke=0)
    c.setStrokeColor(BEAR); c.setLineWidth(w * 0.14); c.setLineCap(1)
    c.line(cx + w * 0.26, h * 0.42, cx + w * 0.30, h * 0.66)
    teddy_head(c, cx, h * 0.68, w * 0.30, mood="tired")
    c.setFillColor(BEAR); c.circle(cx + w * 0.20, h * 0.80, w * 0.085, fill=1, stroke=0)
    c.setFillColor(BEAR_D); c.circle(cx + w * 0.20, h * 0.80, w * 0.028, fill=1, stroke=0)
    c.setFillColor(HEX("#a9d2ee"))
    for (x, y) in [(0.28, 0.88), (0.22, 0.62), (0.76, 0.66)]:
        c.circle(w * x, h * y, w * 0.022, fill=1, stroke=0)


def icon_note(c, w, h):
    c.setFillColor(HEX("#8fd6cb")); c.circle(w / 2, h / 2, min(w, h) / 2, fill=1, stroke=0)
    c.setFillColor(HEX("#e9f8f5")); c.circle(w / 2, h / 2, min(w, h) * 0.43, fill=1, stroke=0)
    note(c, w * 0.40, h * 0.30, w * 0.13, TEAL_D, True)


def icon_teddy(c, w, h):
    c.setFillColor(HEX("#f7c49a")); c.circle(w / 2, h / 2, min(w, h) / 2, fill=1, stroke=0)
    c.setFillColor(HEX("#fff1e4")); c.circle(w / 2, h / 2, min(w, h) * 0.43, fill=1, stroke=0)
    teddy_head(c, w / 2, h * 0.46, w * 0.24)


class Blink(Flowable):
    """Little status-light graphic: solid dot, or dots on a timeline (spacing = speed)."""
    def __init__(self, color, kind, width=36 * 2.835, height=14):
        super().__init__(); self.color = color; self.kind = kind; self.width = width; self.height = height
    def _dot(self, c, x, y, r, rays=True):
        if rays:
            c.setStrokeColor(self.color); c.setLineWidth(0.9); c.setLineCap(1)
            for k in range(8):
                a = k * math.pi / 4
                c.line(x + (r + 1.6) * math.cos(a), y + (r + 1.6) * math.sin(a), x + (r + 3.4) * math.cos(a), y + (r + 3.4) * math.sin(a))
        c.setFillColor(self.color); c.circle(x, y, r, fill=1, stroke=0)
    def draw(self):
        c = self.canv; c.saveState(); c.scale(1.3, 1.3)
        self._body(c, self.height / 2 / 1.3 + 1, 3.2)
        c.restoreState()
    CX = 42                      # centre of the graphic column (single icons sit here)
    LEFT, RIGHT = 8, 76          # left-most and right-most dot positions, identical in every row

    def _body(self, c, y, r):
        cx = self.CX
        if self.kind == "off":
            c.setStrokeColor(HEX("#b9b9b9")); c.setLineWidth(1.2); c.setFillColor(colors.white); c.circle(cx, y, r + 1, fill=1, stroke=1); return
        if self.kind == "solid":
            c.setFillColor(self.color); c.circle(cx, y, r + 1.4, fill=1, stroke=0); return
        if self.kind == "once":
            self._dot(c, cx, y, r + 0.8); return
        if self.kind == "mostly":
            R = r + 1.4
            c.setFillColor(self.color); c.wedge(cx - R, y - R, cx + R, y + R, 70, 290, stroke=0, fill=1)
            return
        n = {"slow": 2, "quick": 3, "rapid": 5}[self.kind]
        step = (self.RIGHT - self.LEFT) / (n - 1)
        for k in range(n):
            self._dot(c, self.LEFT + k * step, y, r if self.kind != "rapid" else r - 0.7)
