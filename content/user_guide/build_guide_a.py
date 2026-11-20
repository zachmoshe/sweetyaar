import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, PageBreak,
                                Table, TableStyle, Flowable, NextPageTemplate, Preformatted)
import art, art_a
from art_a import ArtImg, find_art, draw_cover_fit, draw_contain, band_scene, cover_scene, wave

FD = "/System/Library/Fonts/Supplemental/"
pdfmetrics.registerFont(TTFont("Body", FD + "Trebuchet MS.ttf"))
pdfmetrics.registerFont(TTFont("Body-B", FD + "Trebuchet MS Bold.ttf"))
pdfmetrics.registerFont(TTFont("Body-I", FD + "Trebuchet MS Italic.ttf"))
pdfmetrics.registerFont(TTFont("Body-BI", FD + "Trebuchet MS Bold Italic.ttf"))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-B", italic="Body-I", boldItalic="Body-BI")
pdfmetrics.registerFont(TTFont("Round", FD + "Arial Rounded Bold.ttf"))
pdfmetrics.registerFont(TTFont("Mono", FD + "Courier New.ttf"))
for _n, _f in [("Geo", "Georgia.ttf"), ("Geo-B", "Georgia Bold.ttf"), ("Geo-I", "Georgia Italic.ttf"), ("Geo-BI", "Georgia Bold Italic.ttf")]:
    pdfmetrics.registerFont(TTFont(_n, FD + _f))
pdfmetrics.registerFontFamily("Geo", normal="Geo", bold="Geo-B", italic="Geo-I", boldItalic="Geo-BI")

PAGE = colors.HexColor("#fbf3e4")
CARD = colors.HexColor("#fff9ee")
INK = colors.HexColor("#3d4f50")
MUTED = colors.HexColor("#7a7466")
LINE = colors.HexColor("#ead9b8")
TEAL = colors.HexColor("#2f6f73")
TEAL_D = colors.HexColor("#2f6f73")
TEAL_L = colors.HexColor("#f4e6c8")
TERRA = colors.HexColor("#d9825b")
PINK = colors.HexColor("#d9825b")
PURPLE = colors.HexColor("#6243aa")
LED_RED = colors.HexColor("#d63a4a")
BLUE = colors.HexColor("#0875ee")
GREEN = colors.HexColor("#15925f")
AMBER = colors.HexColor("#e9b949")
AMBER_L = colors.HexColor("#fdf0c9")

W, H = A4
M = 20 * mm
FW = W - 2 * M

body = ParagraphStyle("body", fontName="Geo", fontSize=10.3, leading=15.5, textColor=INK, spaceAfter=6)
small = ParagraphStyle("small", parent=body, fontSize=9, leading=12.5, textColor=MUTED, spaceAfter=0)
h1 = ParagraphStyle("h1", fontName="Geo-BI", fontSize=28, leading=32, textColor=TEAL_D, spaceAfter=4)
lead = ParagraphStyle("lead", parent=body, fontName="Geo-I", fontSize=12.5, leading=18, textColor=MUTED, spaceAfter=10)
h2 = ParagraphStyle("h2", fontName="Geo-BI", fontSize=15.5, leading=19, textColor=TERRA, spaceBefore=12, spaceAfter=5)
cell = ParagraphStyle("cell", parent=body, fontName="Body", fontSize=9.6, leading=13.4, spaceAfter=0)
cellb = ParagraphStyle("cellb", parent=cell, fontName="Body-B")
bul = ParagraphStyle("bul", parent=body, leftIndent=14, bulletIndent=2, spaceAfter=3)
code = ParagraphStyle("code", fontName="Mono", fontSize=8.8, leading=11.5, textColor=colors.HexColor("#2f3f41"))


def P(t, s=body): return Paragraph(t, s)
def bullets(items): return [Paragraph(t, bul, bulletText="•") for t in items]


def card(flows, bg=CARD, border=LINE, pad=12):
    t = Table([[flows]], colWidths=[FW])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("BOX", (0, 0), (-1, -1), 0.8, border),
                           ("ROUNDEDCORNERS", [10, 10, 10, 10]),
                           ("LEFTPADDING", (0, 0), (-1, -1), pad), ("RIGHTPADDING", (0, 0), (-1, -1), pad),
                           ("TOPPADDING", (0, 0), (-1, -1), pad - 2), ("BOTTOMPADDING", (0, 0), (-1, -1), pad - 2)]))
    return t


class Mascot(Flowable):
    def __init__(self, size=15 * mm):
        super().__init__(); self.width = size; self.height = size; self.size = size
    def draw(self):
        c = self.canv; d = self.size
        c.setFillColor(colors.HexColor("#f3dfc0")); c.circle(d / 2, d / 2, d / 2, fill=1, stroke=0)
        p = find_art("teddy_wave")
        if p: draw_contain(c, p, d * 0.06, d * 0.06, d * 0.88, d * 0.88)
        else: art.teddy_head(c, d / 2, d * 0.46, d * 0.30)


def tip(title, text, kind="tip"):
    bg, bd, col = {"tip": (AMBER_L, AMBER, TERRA), "note": (colors.HexColor("#f3e9d4"), LINE, colors.HexColor("#8a6f3a"))}[kind]
    ts = ParagraphStyle("t", parent=body, fontName="Geo-BI", textColor=col, spaceAfter=2, fontSize=11.5)
    inner = [Paragraph(title, ts), Paragraph(text, ParagraphStyle("tt", parent=cell, fontName="Geo", textColor=INK, fontSize=9.8))]
    t = Table([[Mascot(), inner]], colWidths=[20 * mm, FW - 20 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (1, 0), (1, 0), bg), ("ROUNDEDCORNERS", [12, 12, 12, 12]),
                           ("VALIGN", (0, 0), (0, 0), "TOP"), ("VALIGN", (1, 0), (1, 0), "TOP"),
                           ("LEFTPADDING", (0, 0), (0, 0), 0), ("LEFTPADDING", (1, 0), (1, 0), 12), ("RIGHTPADDING", (1, 0), (1, 0), 12),
                           ("TOPPADDING", (1, 0), (1, 0), 9), ("BOTTOMPADDING", (1, 0), (1, 0), 9), ("TOPPADDING", (0, 0), (0, 0), 6)]))
    return t


def codebox(text):
    t = Table([[Preformatted(text, code)]], colWidths=[FW])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f2ece3")), ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                           ("ROUNDEDCORNERS", [6, 6, 6, 6]), ("LEFTPADDING", (0, 0), (-1, -1), 10),
                           ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7)]))
    return t


def table(rows, widths, head=True, pad=6):
    data = [[Paragraph(c, (cellb if (head and i == 0) else cell)) if isinstance(c, str) else c for c in r]
            for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if head else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BACKGROUND", (0, 0), (-1, -1), CARD),
          ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE), ("BOX", (0, 0), (-1, -1), 0.8, LINE),
          ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
          ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8)]
    if head:
        st += [("BACKGROUND", (0, 0), (-1, 0), TEAL_L), ("LINEBELOW", (0, 0), (-1, 0), 1, TEAL)]
    t.setStyle(TableStyle(st))
    return t


class NumBadge(Flowable):
    """Terracotta circle with a lining numeral, centred on the glyph height (Georgia's own digits are old-style)."""
    def __init__(self, text, diameter=7.6 * mm, size=12.5):
        super().__init__(); self.text = str(text); self.d = diameter; self.size = size
        self.width = self.height = diameter
    def draw(self):
        c = self.canv; r = self.d / 2
        c.setFillColor(TERRA); c.circle(r, r, r, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont("Round", self.size)
        c.drawCentredString(r, r - 0.358 * self.size, self.text)


def step_list(steps, width=None):
    rows = []
    for i, s in enumerate(steps, 1):
        rows.append([NumBadge(i), Paragraph(s, cell)])
    t = Table(rows, colWidths=[11 * mm, (width or FW) - 11 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 4),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    return t


def centered(flowable):
    t = Table([[flowable]], colWidths=[FW])
    t.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


A = os.path.join(HERE, "..", "..", "app", "public", "assets") + os.sep


class TabBar(Flowable):
    """Shows the app's bottom tabs using the app's own toy artwork."""
    def __init__(self, width=FW, height=36 * mm):
        super().__init__(); self.width = width; self.height = height
    def draw(self):
        c = self.canv; w, h = self.width, self.height
        c.setFillColor(colors.HexColor("#fff8ee")); c.setStrokeColor(LINE); c.roundRect(0, 0, w, h, 10, fill=1, stroke=1)
        c.setFillColor(colors.HexColor("#b9dcc5")); c.rect(1, 1, w - 2, 9 * mm, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#a9d3b8")); c.rect(1, 1, w - 2, 4 * mm, fill=1, stroke=0)
        for i, (f, label, ih) in enumerate([("tab-doll.png", "Doll", 22 * mm), ("tab-remote.png", "Remote", 22 * mm), ("tab-settings.png", "Settings", 22 * mm)]):
            cx = w * (0.2 + i * 0.3)
            from PIL import Image as PI
            iw, ihh = PI.open(A + f).size
            iw_mm = ih * iw / ihh
            c.drawImage(A + f, cx - iw_mm / 2, 7 * mm + (3 * mm if i == 1 else 0), iw_mm, ih, mask="auto")
            c.setFillColor(INK); c.setFont("Body-B", 9); c.drawCentredString(cx, 2.2 * mm, label)
        # bead on the doll's ear
        bx, by = w * 0.2 + 7 * mm, 7 * mm + 20.5 * mm
        c.setFillColor(colors.white); c.circle(bx, by, 2.3 * mm, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#ec5d86")); c.circle(bx, by, 1.5 * mm, fill=1, stroke=0)
        c.setFillColor(MUTED); c.setFont("Body-I", 8)
        c.drawString(w * 0.2 + 11 * mm, 7 * mm + 20 * mm, "pink bead: take a look")


class FeatureGrid(Flowable):
    """Three-across grid of illustrated cards: (image name, title, text)."""
    def __init__(self, items, cols=3, card_h=56 * mm, gap=2 * mm):
        super().__init__(); self.items = items; self.cols = cols; self.gap = gap; self.ch = card_h
        self.rows = (len(items) + cols - 1) // cols
        self.width = FW; self.height = self.rows * card_h + (self.rows - 1) * gap
        self.cw = (FW - (cols - 1) * gap) / cols
    def draw(self):
        c = self.canv
        for k, (name, title, text) in enumerate(self.items):
            col, row = k % self.cols, k // self.cols
            x = col * (self.cw + self.gap); y = self.height - (row + 1) * self.ch - row * self.gap
            pth = find_art("feat_" + name)
            ih = 36 * mm
            if pth: draw_contain(c, pth, x, y + self.ch - 1 * mm - ih, self.cw, ih)
            c.setFillColor(TEAL_D); c.setFont("Geo-BI", 11.5)
            c.drawCentredString(x + self.cw / 2, y + self.ch - 1 * mm - ih - 5.5 * mm, title)
            st = ParagraphStyle("fg", fontName="Geo", fontSize=8.8, leading=11.2, textColor=INK, alignment=TA_CENTER)
            p = Paragraph(text, st); _, ph = p.wrap(self.cw - 8 * mm, 100 * mm)
            p.drawOn(c, x + 4 * mm, y + self.ch - 1 * mm - ih - 8 * mm - ph)


class ChapterHeader(Flowable):
    """Full-bleed illustrated band at the very top of a chapter's first page."""
    TOP = 18 * mm  # the frame's top margin
    def __init__(self, n, art=None):
        super().__init__(); self.n = n; self.art = art or n; self.width = FW; self.height = 38 * mm
    def draw(self):
        c = self.canv; bh = self.height + self.TOP
        c.saveState(); c.translate(-M, 0)
        pth = find_art(f"ch{self.art}")
        if pth: draw_cover_fit(c, pth, 0, 0, W, bh, fy={1: 0.15}.get(self.n, 0.5))
        else:
            c.saveState(); p = c.beginPath(); p.rect(0, 0, W, bh); c.clipPath(p, stroke=0, fill=0)
            band_scene(c, W, bh, self.n); c.restoreState()
        wave(c, 0, 3.2, 70, PAGE, W)
        c.restoreState()


class ChapterTitle(Flowable):
    def __init__(self, n, title):
        super().__init__(); self.n = n; self.title = title; self.width = FW; self.height = 17 * mm
    def draw(self):
        c = self.canv
        c.setFillColor(TERRA); c.circle(8.5 * mm, 8.5 * mm, 8.5 * mm, fill=1, stroke=0)
        c.setFillColor(colors.white); c.setFont("Round", 25); c.drawCentredString(8.5 * mm, 8.5 * mm - 0.358 * 25, str(self.n))
        c.setFillColor(TEAL_D); c.setFont("Geo-BI", 27); c.drawString(22 * mm, 5 * mm, self.title)


def chapter(n, title, art=None):
    return [ChapterHeader(n, art), Spacer(1, 2 * mm), ChapterTitle(n, title)]


class ButtonDiagram(Flowable):
    """The two big buttons are the focus; a small chip between them shows that pressing both stops the sound."""
    def __init__(self, width=FW, height=62 * mm):
        super().__init__(); self.width = width; self.height = height
    def draw(self):
        c = self.canv; w, h = self.width, self.height
        c.setFillColor(CARD); c.setStrokeColor(LINE); c.roundRect(0, 0, w, h, 14, fill=1, stroke=1)
        d = 30 * mm; cy = h * 0.36
        xs = (w * 0.24, w * 0.76)
        for cx, fn, name, label, sub in [(xs[0], art.icon_note, "btn_song", "Song button", "music and lullabies"),
                                         (xs[1], art.icon_teddy, "btn_animal", "Animal button", "animal sounds")]:
            pth = find_art(name)
            if pth: draw_contain(c, pth, cx - d / 2, cy, d, d)
            else:
                c.saveState(); c.translate(cx - d / 2, cy); fn(c, d, d); c.restoreState()
            c.setFillColor(INK); c.setFont("Geo-BI", 13); c.drawCentredString(cx, cy - 7 * mm, label)
            c.setFillColor(MUTED); c.setFont("Geo-I", 9.5); c.drawCentredString(cx, cy - 12 * mm, sub)
        # small "press both = stop" chip between the buttons
        mx, my = w / 2, cy + d / 2
        c.setStrokeColor(colors.HexColor("#d9b99a")); c.setLineWidth(1.2); c.setDash(2, 3); c.setLineCap(1)
        c.line(xs[0] + d / 2 + 2 * mm, my, mx - 6.5 * mm, my)
        c.line(mx + 6.5 * mm, my, xs[1] - d / 2 - 2 * mm, my)
        c.setDash()
        c.setFillColor(colors.HexColor("#e9a58a")); c.circle(mx, my, 5.5 * mm, fill=1, stroke=0)
        c.setFillColor(colors.HexColor("#fff1e4")); c.circle(mx, my, 3.6 * mm, fill=1, stroke=0)
        c.setFillColor(TERRA); c.roundRect(mx - 1.9 * mm, my - 1.9 * mm, 3.8 * mm, 3.8 * mm, 0.8 * mm, fill=1, stroke=0)
        c.setFillColor(MUTED); c.setFont("Geo-I", 9.5)
        c.drawCentredString(mx, my - 10 * mm, "both together = stop")


def on_page(c, doc):
    c.saveState()
    c.setFillColor(PAGE); c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFont("Geo-I", 8.5); c.setFillColor(MUTED)
    c.drawString(M, 11 * mm, "SweetYaar  ·  A little guide for big grown-ups")
    c.drawRightString(W - M, 11 * mm, str(doc.page))
    c.setStrokeColor(LINE); c.line(M, 16 * mm, W - M, 16 * mm)
    c.restoreState()


def on_cover(c, doc):
    c.saveState()
    c.setFillColor(PAGE); c.rect(0, 0, W, H, fill=1, stroke=0)
    full = find_art("cover_page")
    if full:   # the whole cover is one painting, with the title painted on its sign
        draw_cover_fit(c, full, 0, 0, W, H)
        c.restoreState()
        return
    ax, ay, aw, ah = 22 * mm, 62 * mm, W - 44 * mm, 205 * mm
    pth = find_art("cover")
    if pth:
        c.saveState(); r = aw / 2
        p = c.beginPath(); p.moveTo(ax, ay); p.lineTo(ax, ay + ah - r); p.arcTo(ax, ay + ah - 2 * r, ax + aw, ay + ah, 180, -180); p.lineTo(ax + aw, ay); p.close()
        c.clipPath(p, stroke=0, fill=0); draw_cover_fit(c, pth, ax, ay, aw, ah); c.restoreState()
    else:
        cover_scene(c, ax, ay, aw, ah)
    c.setFillColor(colors.HexColor("#fbf3e4")); c.circle(W - 44 * mm, 78 * mm, 20 * mm, fill=1, stroke=0)
    c.setFillColor(colors.HexColor("#f3dfc0")); c.circle(W - 44 * mm, 78 * mm, 18 * mm, fill=1, stroke=0)
    mp = find_art("teddy_wave")
    if mp: draw_contain(c, mp, W - 44 * mm - 16 * mm, 78 * mm - 16 * mm, 32 * mm, 32 * mm)
    else: art.teddy_head(c, W - 44 * mm, 76 * mm, 11 * mm)
    c.setFillColor(TEAL_D); c.setFont("Geo-BI", 42); c.drawCentredString(W / 2, 40 * mm, "SweetYaar")
    c.setFillColor(INK); c.setFont("Geo-I", 14.5); c.drawCentredString(W / 2, 28 * mm, "A parent’s guide to the singing doll")
    c.restoreState()


OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "SweetYaar_Parents_Guide_A.pdf")
doc = BaseDocTemplate(OUT, pagesize=A4, leftMargin=M, rightMargin=M, topMargin=18 * mm, bottomMargin=22 * mm,
                      title="SweetYaar: a little guide for big grown-ups", author="SweetYaar")
frame = Frame(M, 22 * mm, FW, H - 40 * mm, id="f", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
doc.addPageTemplates([PageTemplate(id="cover", frames=[Frame(M, 20 * mm, FW, H - 40 * mm, id="c", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)], onPage=on_cover),
                      PageTemplate(id="main", frames=[frame], onPage=on_page)])

MONO = '<font name="Mono" size="8.8">'
S = []
# ---------------- Cover ----------------
S += [Spacer(1, 1), NextPageTemplate("main"), PageBreak()]

# ---------------- Welcome ----------------
S += [P("Welcome", h1),
      P("SweetYaar is a little music-box heart that lives inside a doll. Your child gets two big, friendly buttons. "
        "You get the grown-up controls on your phone.", lead),
      Spacer(1, 1 * mm)]
S += [P("What SweetYaar does", h2),
      FeatureGrid([
          ("songs", "Songs and lullabies", "Press a button and the doll plays music from its memory card."),
          ("animals", "Animal sounds", "Press the other button for a moo, a quack or a baa."),
          ("speaker", "A Bluetooth speaker", "Play music or a story from your phone, tablet or computer."),
          ("remote", "In your hands", "Choose music, volume and bedtime, or pause the buttons, from the app."),
          ("sleep", "Peace and quiet", "Need a breather? Quiet time pauses the doll’s buttons for ten minutes, so you get some peace."),
          ("update", "Always up to date", "New firmware, the doll’s built-in software, arrives from the app. No cables."),
      ]),
      Spacer(1, 3 * mm)]
S += [P("In this guide", h2)]
toc = [["1", "Getting started", "Charge, switch on, first play"],
       ["2", "Playing with the doll", "The two buttons and the little light"],
       ["3", "Using it as a Bluetooth speaker", "Pairing your phone"],
       ["4", "The SweetYaar app", "Your remote control and settings"],
       ["5", "SweetYaar Studio", "Your own songs and animal sounds"],
       ["6", "Keeping the doll up to date", "Installing new firmware from the app"],
       ["7", "Bedtime, Quiet time and sleep", "Making it fit your routine"],
       ["8", "Care, charging and safety", "The battery and how to treat it"],
       ["9", "Troubleshooting", "Quick answers"]]
S += [table(toc, [10 * mm, 70 * mm, FW - 80 * mm], head=False), PageBreak()]

# ---------------- 1 Getting started ----------------
S += [*chapter(1, "Getting started"),
      P("Four quick steps and the doll is ready to play.", lead)]
S += [step_list([
    "<b>Charge it.</b> Plug a USB-C cable into the charging port and use a 5 V USB charger that can supply at least 1.5 A.",
    "<b>Switch it on.</b> The doll has a small on/off switch. It is meant for storage and travel: normally you leave it on, "
    "because the doll sleeps by itself.",
    "<b>Wait for the chime and the green light.</b> A short “ready” sound plays and the little light blinks green. "
    "SweetYaar is ready.",
    "<b>Press the song button.</b> Music! Press it again for the next song.",
]), Spacer(1, 4 * mm)]
S += [tip("The memory card is already inside",
          "SweetYaar ships with a microSD card inside the doll, with songs and animal sounds on it. "
          "You can add your own later with SweetYaar Studio (see section 5).")]
S += [Spacer(1, 4 * mm), P("What is where", h2),
      table([["Part", "What it does"],
             ["Song button", "Plays songs from the current theme (for example lullabies)."],
             ["Animal button", "Plays one animal sound."],
             ["Little light", "Shows what the doll is doing. See the guide in the next section."],
             ["Charging port (USB-C)", "For charging. Power only; it is not used to load music or firmware."],
             ["On/off switch", "Complete power-off for storage and travel."],
             ["Memory card slot", "Inside the doll."]],
            [48 * mm, FW - 48 * mm]),
      PageBreak()]

# ---------------- 2 Playing ----------------
S += [*chapter(2, "Playing with the doll"),
      P("The buttons are deliberately simple, so little hands can’t get lost.", lead),
      ButtonDiagram(), Spacer(1, 5 * mm)]
S += [table([["Do this", "And the doll…"],
             ["Press the <b>song</b> button", "plays a song. Press it again to hear the next song."],
             ["Press the <b>animal</b> button", "plays one animal sound. Press it again for another animal."],
             ["Press <b>both</b> buttons together", "stops the sound."],
             ["Hold both for <b>3 seconds</b>", "opens Bluetooth pairing for 60 seconds (see section 3)."],
             ["Keep holding both to <b>10 seconds</b>", "forgets every paired phone (see section 3)."]],
            [62 * mm, FW - 62 * mm]),
      Spacer(1, 3 * mm),
      P("A song stops when it ends. Turn on <b>Loop songs</b> in the app and the next song starts by itself. "
        "Fancy some surprises? Each theme also has a <b>shuffle</b> switch in the app’s Settings, which plays its songs in random order.", body),
      Spacer(1, 3 * mm),
      tip("Sleeping and waking",
          "After about 10 minutes with nothing happening, the doll falls asleep to protect the battery. "
          "Pick it up or move it and it wakes with its ready chime. Music that was playing does not resume, and any "
          "Bluetooth connection has to be made again. You can change these times in the app."),
      PageBreak()]

S += [P("What the little light means", h1),
      P("A single light shows the doll’s state at a glance. In the pictures below, a dot with rays is one blink, "
        "and the closer together the blinks are, the faster the light is flashing.", lead)]
LEG = [
    (art.Blink(colors.HexColor("#f5c94e"), "solid"), "Solid yellow", "Starting up."),
    (art.Blink(GREEN, "slow"), "Green, slow blink", "Ready. Press a button."),
    (art.Blink(GREEN, "quick"), "Green, quick blink", "Playing a song or animal sound."),
    (art.Blink(BLUE, "slow"), "Blue, slow blink", "A phone is connected as a speaker, nothing playing."),
    (art.Blink(BLUE, "quick"), "Blue, quick blink", "Music is streaming from your phone."),
    (art.Blink(BLUE, "rapid"), "Blue, rapid blink", "Pairing is open for 60 seconds."),
    (art.Blink(PURPLE, "mostly"), "Purple", "Quiet time is on: the buttons are paused. (Lit most of the time, with a brief flicker.)"),
    (art.Blink(LED_RED, "once"), "Red, one flash", "All paired phones were forgotten."),
    (art.Blink(LED_RED, "rapid"), "Red, rapid blink", "Something needs attention (for example the memory card is missing or can’t be read)."),
    (art.Blink(colors.HexColor("#f5c94e"), "quick"), "Yellow, quick blink", "Installing an update. Keep the app open."),
    (art.Blink(colors.HexColor("#b9b9b9"), "off"), "Off", "Sleeping."),
]
t = Table([[a, Paragraph(f"<b>{b}</b>", cell), Paragraph(c, cell)] for a, b, c in LEG],
          colWidths=[40 * mm, 38 * mm, FW - 78 * mm], rowHeights=[11 * mm] * len(LEG))
t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BACKGROUND", (0, 0), (-1, -1), CARD),
                       ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE), ("BOX", (0, 0), (-1, -1), 0.8, LINE),
                       ("LEFTPADDING", (0, 0), (-1, -1), 10)]))
S += [t, Spacer(1, 6 * mm)]
S += [P("Sounds the doll makes", h2),
      P("Besides music, the doll plays a few short chimes of its own. They work even without a memory card, and they use the doll’s "
        "current volume, so they are softer at bedtime.", body),
      table([["Chime", "When you hear it"],
             ["<b>Ready</b>", "Once when the doll has started and is ready to play."],
             ["<b>Pairing</b>", "Once when you open pairing (hold both buttons for 3 seconds)."],
             ["<b>Charger plugged in</b>", "A rising three-note “sunrise”, once, when you plug in the charger and charging really starts."],
             ["<b>Low battery</b>", "Three soft notes when the battery drops to “charge soon” or “charge now” while the doll is not charging."],
             ["<b>Error</b>", "Something needs attention, for example the memory card is missing."]],
            [42 * mm, FW - 42 * mm]),
      PageBreak()]

# ---------------- 3 Bluetooth speaker ----------------
S += [*chapter(3, "Using it as a Bluetooth speaker"),
      P("SweetYaar can play anything from your phone, tablet or computer, like a story, a podcast or your own playlist.", lead)]
S += [P("Connect your phone for the first time", h2),
      step_list([
          "Hold <b>both buttons for 3 seconds</b>. A chime plays once and the light blinks blue rapidly. You now have <b>60 seconds</b>.",
          "On your phone, open <b>Bluetooth settings</b> and choose <b>SweetYaar Speaker</b> from the list (your doll’s name followed by “Speaker”).",
          "If your phone asks, tap <b>Pair</b>. There is no code to type.",
          "Play something on your phone. The sound comes out of the doll.",
      ]), Spacer(1, 3 * mm)]
S += bullets([
    "<b>You only pair once.</b> Next time, you don’t need to open pairing again: with the doll awake and nearby and your phone’s "
    "Bluetooth on, the phone connects by itself.",
    "While the phone is connected, the doll’s buttons pause and the app shows “Used as a speaker”. <b>Use the phone’s own volume control.</b>",
    "Only one phone can stream at a time. Disconnect the first phone before connecting a second.",
    "<b>To pair the app, disconnect the speaker first.</b> While any phone is connected to the doll as a speaker, even with nothing "
    "playing, the doll refuses to pair a new app, even in the 60-second window. Disconnect the phone’s speaker connection, then connect the app (see section 4).",
    "When the phone disconnects, the doll goes back to its songs and animal sounds.",
    "<b>The speaker and the SweetYaar app are paired separately:</b> pair each one while pairing is open. Phones stream best; a computer can have small gaps.",
])
S += [P("Forgetting all paired phones", h2),
      P("Hold both buttons for <b>10 seconds</b>. The light flashes red once and every paired phone and app is removed. "
        "Use this if you give the doll away or want a fresh start. Afterwards, also choose “Forget this device” "
        "in your phone’s Bluetooth settings, then pair again.", body),
      PageBreak()]

# ---------------- 4 The app ----------------
S += [*chapter(4, "The SweetYaar app"),
      P("Your remote control: pick the music, set the volume, set bedtime.", lead)]
S += [P("Before you start", h2)]
S += bullets([
    "The app is a website, so there is nothing to download from an app store. Open <b>sweetyaar.zachmoshe.com</b> "
    "in <b>Chrome</b> on an Android phone, or in Chrome or Edge on a computer. (Safari and other iPhone browsers don’t support "
    "the Bluetooth feature the app needs.)",
    "You can add it to your home screen to use it like a normal app. It also opens without internet. "
    "Talking to the doll uses Bluetooth only: no accounts, no cloud.",
])
S += [P("Connect for the first time", h2),
      step_list([
          "Make sure the doll is awake and nearby (with no phone connected to it as a speaker), then hold <b>both buttons for 3 seconds</b> to open pairing.",
          "In the app, tap <b>Connect to SweetYaar</b> and choose the doll from the list your browser shows.",
          "Accept the Bluetooth pairing request on your phone.",
      ]),
      Spacer(1, 3 * mm),
      P("Afterwards, just open the app: it finds the doll by itself, with no list to choose from (wake the doll first if it sleeps). "
        "In Chrome or Edge the app may show a short tip about one browser setting to switch on so that this works; follow the tip once, "
        "then restart the browser. If the app can’t reach the doll, tap <b>Connect to SweetYaar</b>. A phone the doll "
        "doesn’t know yet, or one you forgot with the 10-second hold, gets <b>“Device not approved”</b>: hold both buttons for "
        "3 seconds and tap Connect again.", body)]
S += [P("Finding your way around", h2),
      P("Once connected, three little toys standing on the grass at the bottom of the screen are the app’s menu. Tap one to switch page.", body),
      TabBar(), Spacer(1, 3 * mm),
      table([["Page", "What it is for"],
             ["<b>Doll</b> (teddy)", "How the doll is doing: battery and charging, its firmware version, and updates. "
                                     "A <b>pink bead</b> on the teddy’s ear means it is worth a look: an update you haven’t seen, a low battery, or a charger problem."],
             ["<b>Remote</b>", "The remote control: play, stop, volume, theme, Quiet time. While a phone streams music it says “Used as a speaker”."],
             ["<b>Settings</b> (gears)", "Everything permanent: name, defaults, bedtime, sleep, themes and songs."]],
            [38 * mm, FW - 38 * mm]),
      Spacer(1, 3 * mm)]
S += [KeepTogether([P("The remote screen", h2),
      table([["Control", "What it does"],
             ["<b>Play song</b>", "Plays a song from the current theme. Tap again for the next one."],
             ["<b>Animal</b>", "Plays an animal sound. Tap again for another."],
             ["<b>Stop</b>", "Stops whatever is playing."],
             ["<b>Loop songs</b>", "Keeps playing one song after another. It switches itself off after Stop, an animal sound, Quiet time, phone streaming or a restart."],
             ["<b>Volume</b>", "Sets the doll’s volume for its own songs and sounds. (It does not change the volume of phone streaming.)"],
             ["<b>Theme</b>", "Chooses which group of songs the song button plays. Lasts until the doll sleeps; set a permanent default in Settings."],
             ["<b>Quiet time</b>", "Stops the sound and makes the doll ignore its buttons for 10 minutes, so you get some quiet (for example during a phone call). "
                                   "The app shows the time left. Switch it off any time. You can still change the volume; it applies when Quiet time ends."],
             ["<b>Daytime / Bedtime</b>", "Shows the current mode and lets you switch it for now."],
             ["Battery", "Shows the battery status, and when the doll is charging. Tap it to open the Doll page."]],
            [40 * mm, FW - 40 * mm])]),
      Spacer(1, 4 * mm)]

S += [P("Settings and your own sounds", h1)]
S += [P("Settings", h2),
      P("Change as many things as you like, then tap <b>Save</b> once.", body),
      table([["Section", "What you can set"],
             ["General", "The doll’s Bluetooth name, the volume it starts at, and the theme it starts with."],
             ["Bedtime mode", "Turn it on or off, choose the bedtime theme, the start and end time, and a volume limit."],
             ["Sleep", "Turn automatic sleep on or off and how long the doll waits before it sleeps."],
             ["Themes", "A <b>theme</b> is a group of songs, such as lullabies or nature sounds. Switch a whole theme off and the doll "
                        "skips it. Shuffle plays a theme’s songs in random order."],
             ["Songs and animals", "See every song and animal sound, and switch individual ones off by tapping a row. Anything switched off is skipped, "
                                   "while the rest of its theme keeps playing. A file the doll can’t play is skipped and shown with the reason."]],
            [38 * mm, FW - 38 * mm]),
      Spacer(1, 3 * mm),
      tip("Volume and theme: “now” versus “at start”",
          "The volume and theme on the Remote page are for right now. The ones in Settings are what the doll uses "
          "<b>each time it wakes up</b>. Saving Settings does not change what is playing right now.")]
S += [P("The Doll page", h2),
      P("The Doll page shows how the doll is doing. At the top is the charge status (for example charging, finished, or no external power). "
        "Below it, charger notes appear only when something needs a look. <i>About this doll</i> shows the firmware version and "
        "whether a newer one is available (see section 6). When the battery is getting low, "
        "a sleepy teddy appears as a reminder.", body),
      Spacer(1, 2 * mm), centered(ArtImg('doll_page', 32 * mm, 28 * mm, art.scene_tired_teddy)), Spacer(1, 2 * mm)]
S += [P("Adding your own songs and sounds", h2),
      P("The doll’s songs and animal sounds live on the microSD card inside it. You edit them with <b>SweetYaar Studio</b>, "
        "a free editor that opens from a card on the app’s opening screen and on the Remote page. It has its own chapter next.", body),
      PageBreak()]

# ---------------- 5 Studio ----------------
from reportlab.platypus import Image as RLImage
from PIL import Image as PILImage
SCREENS = os.path.join(HERE, "screens")


def screen(name, width, center=True):
    iw, ih = PILImage.open(os.path.join(SCREENS, name)).size
    im = RLImage(os.path.join(SCREENS, name), width=width, height=width * ih / iw)
    t = Table([[im]], colWidths=[width + 4])
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, LINE), ("ROUNDEDCORNERS", [6, 6, 6, 6]), ("BACKGROUND", (0, 0), (-1, -1), CARD),
                           ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
                           ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return centered(t) if center else t


def caption(text): return Paragraph(text, ParagraphStyle("cap", parent=small, alignment=TA_CENTER, spaceBefore=3, spaceAfter=6))


S += [*chapter(5, "SweetYaar Studio", art="A"),
      P("A free editor, in your browser, for the doll’s memory card.", lead),
      P("Studio needs no installation and no account. Open it from the <b>SweetYaar Studio</b> card on the app’s opening screen or on the "
        "Remote page. It works best on a tablet or a laptop, in Chrome or Edge. What you make stays in your browser until you "
        "<b>export</b> it to the memory card.", body),
      screen("studio_1_overview.jpg", 100 * mm),
      caption("<b>1</b> My themes: your own songs.  <b>2</b> The SweetYaar library: ready-made themes to download.  "
              "<b>3</b> Export to SD card: when you are done.  Scroll down for the <b>Animals</b> shelf."),
      P("Songs and themes", h2),
      P("A <b>theme</b> is a group of songs, for example lullabies. The song button plays the songs of the current theme.", body),
      step_list([
          "Tap <b>+ New theme</b> and give it a name.",
          "Add songs with <b>+ Upload songs</b>, or drag audio files onto the theme. Drag songs up and down to set their order.",
          "To tidy a song, tap its waveform icon: you can trim it, fade it in and out, or even-out its volume. "
          "<b>Record</b> lets you record your own voice, for example a bedtime story."]),
      PageBreak(),
      screen("studio_2_newtheme.jpg", 138 * mm),
      caption("<b>1</b> New theme.  <b>2</b> Upload songs, or record.  <b>3</b> Drop audio files here."),
      P("Download from the library", h2),
      P("The SweetYaar library holds ready-made themes. Tap <b>+ Add</b> and the theme is downloaded into <b>My themes</b>, where you can "
        "change it like one of your own. Its tag then reads <i>Added</i>, and <b>Update</b> fetches the library’s newest version.", body),
      KeepTogether([screen("studio_3_library.jpg", 138 * mm),
          caption("<b>1</b> The library theme, now tagged Added.  <b>2</b> Its copy in My themes, ready to edit.")]),
      PageBreak()]

S += [P("Animal sounds", h2),
      P("Each animal file is a little scene: a spoken <b>question</b> (“How does a cow sound?”), a pause, and then the <b>animal</b>. "
        "On the <b>Animals</b> shelf, questions are on the left and animal sounds on the right.", body),
      step_list([
          "The library has ready-made questions in several languages. Choose the language you want (<b>1</b>).",
          "A question and a sound with the same name match by themselves: the rows turn green and a dashed line joins them. "
          "Tap <b>Play both</b> (<b>2</b>) to hear the whole scene.",
          "To match differently, drag a question onto a sound. Tap <b>×</b> to unmatch. Only matched animals are put on the card.",
          "Want your own voice or your own animal sounds? Use <b>+ Add prompts</b>, <b>Record prompts</b> or <b>+ Add animal sounds</b>."]),
      Spacer(1, 2 * mm), screen("studio_4_animals.jpg", 150 * mm),
      caption("Questions (left) and animal sounds (right), matched."),
      P("Putting it on the doll", h2)]
exp_steps = step_list([
    "Switch the doll off and take out its memory card. Put the card in a card reader on your computer.",
    "In Studio, tap <b>Export to SD card…</b>, then <b>Choose folder…</b> (1) and pick the card. Any folder works too, to copy to the card later.",
    "Tap <b>Export</b> (2) and wait until it says it is done. Anything already on the card is kept unless you untick the box.",
    "Put the card back in the doll and switch it on. The doll reads the card when it starts, so your new songs and sounds are there."], width=FW - 68 * mm)
t = Table([[[exp_steps, Spacer(1, 2 * mm), P("Exporting needs Chrome or Edge on a computer.", small)], screen("studio_5_export.jpg", 62 * mm, center=False)]],
          colWidths=[FW - 66 * mm, 66 * mm])
t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]))
S += [t,
      PageBreak()]

# ---------------- 5 Updates ----------------
S += [*chapter(6, "Keeping the doll up to date", art=5),
      P("New firmware, the doll’s built-in software, is installed from the app over Bluetooth. No cable, no computer, no Wi-Fi.", lead)]
S += [P("How you find out", h2),
      P("When you connect, the app checks whether a newer version has been published. If there is one, a <b>pink bead</b> appears on the "
        "Doll page. The bead goes away once you have opened that page on that phone. A very old doll that the app can no longer control "
        "shows an <b>Update needed</b> card instead, and its remote stays locked until it is updated.", body)]
S += [P("Updating", h2),
      step_list([
          "Open the <b>Doll</b> page. <i>About this doll</i> shows the doll’s version and the new one, with what’s new. Tap <b>Update to …</b>.",
          "Read <b>Before you start</b>: keep the screen open, keep the doll near you, and expect no songs for about a minute. "
          "The doll needs enough battery for the update, or to be charging. If the battery is too low, the update won’t start until you connect the charger.",
          "Tap <b>Start update</b>. The app downloads the update and checks it, restarts the doll into update mode (the light blinks yellow), "
          "reconnects by itself with no pairing, and sends the update with a progress ring and the time left.",
          "The doll installs it and restarts. The app confirms <b>SweetYaar is up to date</b> and shows what’s new, then returns to the remote."]),
      Spacer(1, 3 * mm)]
S += [tip("Good to know",
          "<b>If the connection drops</b> (for example the phone locks): the app shows “Update paused” and keeps reconnecting, then carries on where it "
          "stopped. The doll waits 2 minutes and then goes back to normal on its current version.<br/>"
          "<b>If you switch the doll off mid-update:</b> it comes back on its current version, and the app says “Update didn’t finish”. Tap <b>Try again</b>; "
          "nothing is damaged.<br/>"
          "<b>To stop:</b> tap <b>Cancel update</b> and confirm. The doll discards the partial update and restarts as before.<br/>"
          "You can also <b>Reinstall</b> the current version from the Doll page to repair a doll.")]
S += [Spacer(1, 3 * mm),
      P("If a new version turns out to have a problem while starting, the doll automatically goes back to the previous version.", body),
      PageBreak()]

# ---------------- 5 Bedtime / quiet / sleep ----------------
S += [*chapter(7, "Bedtime, Quiet time and sleep", art=6),
      P("Three gentle helpers that make SweetYaar fit your routine.", lead)]
S += [centered(ArtImg('bedtime', 120 * mm, 20 * mm, art.scene_moon))]
S += [P("Bedtime mode", h2),
      P("Every day between a start and an end time you choose (the factory setting is 18:30 to 06:30), the doll "
        "automatically switches to a calmer mode:", body)]
S += bullets(["It plays songs from your <b>bedtime theme</b> (for example lullabies).",
              "It limits the volume to the <b>bedtime volume limit</b> you set (factory setting 65%). This applies to songs and animal sounds. "
              "Your normal volume setting is kept for daytime.",
              "It does not affect music streamed from a phone, which is controlled by the phone."])
S += [P("The doll does not know the time by itself. Every time you connect the app, it tells the doll the correct time. "
        "Until then the app shows “clock not set” and Bedtime mode stays off. You can switch between Daytime and Bedtime for now "
        "from the Remote page; the schedule takes over again at the next boundary.", body)]
S += [P("Quiet time", h2),
      P("Want the doll to stop, and stay quiet, for a while, say during a phone call or when you need five minutes of peace? "
        "Switch on <b>Quiet time</b> in the app. The sound stops and the doll ignores its buttons for <b>10 minutes</b>, "
        "or until you switch it off. The light turns purple. A phone that is already streaming is not stopped.", body)]
S += [P("Automatic sleep", h2),
      table([["After this much idle time…", "…the doll sleeps (factory setting)"],
             ["Nothing has been touched", "10 minutes"],
             ["It was woken by movement, but nobody pressed a button", "2 minutes"],
             ["The app is connected but you are not doing anything", "2 minutes"]],
            [90 * mm, FW - 90 * mm]),
      Spacer(1, 2 * mm),
      P("Sleep never starts while music plays. The doll wakes when moved or plugged in, and starts fresh, so reconnect your phone or the app if you need them.", body),
      PageBreak()]

# ---------------- 6 Care & safety ----------------
S += [*chapter(8, "Care, charging and safety", art=7)]
S += [P("The battery", h2),
      table([
             ["<b>Type</b>", "Removable lithium-ion 18650 cell with built-in protection (button top), 3.6–3.7 V nominal and 4.2 V when full."],
             ["<b>Capacity</b>", "2400 mAh or 3400 mAh, depending on the model."],
             ["<b>Charging</b>", "Through the USB-C port, at up to 1 A. Use a 5 V charger that provides at least 1.5 A."],
             ["<b>Temperature</b>", "Charging only runs while the battery is between 0 °C and 45 °C, and the doll stops charging by itself outside "
                                    "that range. A six-hour safety timer also limits a charge."]],
            [30 * mm, FW - 30 * mm], head=False),
      Spacer(1, 3 * mm)]
S += [P("Charging", h2)]
S += bullets([
    "When charging really starts, the doll plays a short rising “sunrise” chime once. No chime usually means the charger isn’t giving power.",
    "The doll can play while charging, but it charges slower then.",
    "If it doesn’t charge, check the cable and the charger (a 5 V charger that can supply at least 1.5 A) and try again.",
    "Charge it where you can see it, on a hard surface, and unplug it once it is full if you are going away.",
    "Switch the doll off with its on/off switch if you will not use it for many weeks.",
])
S += [P("Safety", h2)]
S += bullets([
    "<b>Adults only inside.</b> The battery, electronics and memory card are inside the doll. Only an adult should open it, and never a child.",
    "Use only a protected 18650 cell of the same type. An unprotected or damaged cell can overheat.",
    "Stop using the doll and take the battery out if it is swollen, dented, leaking, smells odd or gets hot while charging.",
    "Never crush, puncture, heat, short-circuit or wet the battery, and don’t charge a damaged cell.",
    "Keep the doll away from heat, direct sun, a radiator or a hot car.",
    "Don’t throw used batteries in the bin. Take them to a battery collection point.",
    "Do not use a damaged cable. Do not wash or soak the doll’s electronics.",
    "Check the doll regularly for loose parts and wear, as with any toy.",
])
S += [PageBreak()]

# ---------------- 7 Troubleshooting ----------------
S += [*chapter(9, "Troubleshooting", art=8)]
S += [table([["What’s happening", "Try this"],
             ["The doll doesn’t react to the buttons.",
              "It may be asleep, so move it gently and wait for the chime. Check that the on/off switch is on and that it is charged. "
              "Is the light purple? Quiet time is on; switch it off in the app."],
             ["The light blinks red rapidly (and there was an error chime).",
              "Something is wrong, most often the memory card: it is missing, loose or can’t be read. Switch the doll off, check that the card is seated and holds the SweetYaar folders, then switch on again."],
             ["The light is green but no songs play.",
              "The current theme may have no songs, or its songs and the theme are switched off in Settings. Pick another theme in the app. Also check that Quiet time is off."],
             ["My phone can’t find SweetYaar.",
              "Hold both buttons for 3 seconds first (pairing only opens for 60 seconds), and keep the phone close."],
             ["The phone connected but there’s no sound.",
              "Check the phone’s volume and that SweetYaar Speaker is chosen as the audio output. Then try disconnecting and reconnecting."],
             ["The app says “Device not approved”.",
              "The doll doesn’t know this phone yet. Hold both buttons for 3 seconds and tap Connect again within the minute."],
             ["The app says it can’t pair while a phone is connected as a speaker.",
              "A new app can’t pair while any phone is connected to the doll as a speaker, even if nothing is playing. Disconnect the doll in the phone’s Bluetooth settings, hold both buttons for 3 seconds, and connect the app again."],
             ["The app says another remote is connected while SweetYaar plays music.",
              "Another approved phone is using the doll. Close the app there, or stop the music, then connect."],
             ["The app says SweetYaar is busy right now.",
              "Wait a moment and try again."],
             ["The app says “Update needed”.",
              "The doll’s firmware is too old for this app. Open the Doll page and update it (keep the doll near you and the screen open)."],
             ["The app says “Update didn’t finish”.",
              "Tap Try again. Make sure the battery isn’t low, keep the doll close and don’t switch it off during the update."],
             ["The app says “Someone else took control”.",
              "Another approved phone connected. Tap Connect to take control back."],
             ["The app can’t connect.",
              "Move the doll to wake it, use Chrome (or Edge on a computer), and make sure Bluetooth is on. If it still fails, forget SweetYaar in your phone’s Bluetooth list and pair again."],
             ["The sound crackles.",
              "Make sure the battery isn’t low and try a lower volume. If it persists after charging, contact support."],
             ["Bedtime doesn’t start.",
              "Open the app once so the doll learns the time (it shows “clock not set” until then). Check that Bedtime mode is on in Settings."],
             ["I want to start over.",
              "Hold both buttons for 10 seconds to forget every paired phone, then pair again."]],
            [58 * mm, FW - 58 * mm], pad=4)]

doc.build(S)
print("built", OUT)
