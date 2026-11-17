"""BlendCAD şeridini Blender'sız PNG olarak çizer (aynı ribbon.py çizim kodu, PIL ressamı).

Kullanım:  python3 ribbon_preview.py <eklenti klasörü> <çıktı klasörü>

Blender'daki görüntüye yakın bir önizleme verir (yazı tipi farklıdır: burada DejaVu,
Blender'da Inter). GPU çizimi gerçek Blender'da ayrıca kontrol edilmelidir.
"""

import importlib
import os
import sys
import types

from PIL import Image, ImageDraw, ImageFont

SRC, OUT = sys.argv[1], sys.argv[2]
SS = 2                                   # süper örnekleme
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# palette.py gpu / blf ister: boş taklitler (yalnızca icon_lines kullanılır)
for name in ("gpu", "blf", "gpu_extras", "gpu_extras.batch"):
    m = types.ModuleType(name)
    sys.modules[name] = m
sys.modules["gpu_extras.batch"].batch_for_shader = None
pkg = types.ModuleType("mini_cad")
pkg.__path__ = [SRC]
sys.modules["mini_cad"] = pkg
ribbon = importlib.import_module("mini_cad.ribbon")
data = importlib.import_module("mini_cad.ribbon_data")


class PILPainter:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.img = Image.new("RGB", (w * SS, h * SS), (57, 57, 57))
        self.d = ImageDraw.Draw(self.img, "RGBA")
        self._fonts = {}

    def _c(self, c):
        return tuple(int(max(0, min(1, v)) * 255) for v in c)

    def _x(self, x):
        return x * SS

    def _y(self, y):
        return (self.h - y) * SS

    def font(self, size, bold=False):
        k = (size, bold)
        if k not in self._fonts:
            self._fonts[k] = ImageFont.truetype(FONT_B if bold else FONT, int(size * SS * 0.92))
        return self._fonts[k]

    def rect(self, x0, y0, x1, y1, col, r=0):
        box = [self._x(x0), self._y(y1), self._x(x1), self._y(y0)]
        if box[2] <= box[0] or box[3] <= box[1]:
            return
        if r:
            self.d.rounded_rectangle(box, radius=r * SS, fill=self._c(col))
        else:
            self.d.rectangle(box, fill=self._c(col))

    def outline(self, x0, y0, x1, y1, col, r=0, width=1.0):
        box = [self._x(x0), self._y(y1), self._x(x1), self._y(y0)]
        self.d.rounded_rectangle(box, radius=r * SS, outline=self._c(col), width=int(width * SS))

    def lines(self, seg, col, width):
        c = self._c(col)
        for i in range(0, len(seg) - 1, 2):
            a, b = seg[i], seg[i + 1]
            self.d.line([(self._x(a[0]), self._y(a[1])), (self._x(b[0]), self._y(b[1]))], fill=c,
                        width=max(1, int(width * SS)))

    def tri(self, pts, col):
        self.d.polygon([(self._x(x), self._y(y)) for x, y in pts], fill=self._c(col))

    def circle(self, cx, cy, r, col):
        self.d.ellipse([self._x(cx - r), self._y(cy + r), self._x(cx + r), self._y(cy - r)],
                       fill=self._c(col))

    def text(self, x, y, txt, col, size, bold=False):
        self.d.text((self._x(x), self._y(y)), txt, font=self.font(size, bold), fill=self._c(col),
                    anchor="ls")

    def measure(self, txt, size, bold=False):
        f = self.font(size, bold)
        l, t, r, b = f.getbbox(txt)
        return ((r - l) / SS, (b - t) / SS)

    def viewport(self):
        """Blender görünümüne benzer zemin: ızgara, eksenler, başlık şeridi."""
        d = self.d
        w, h = self.w, self.h
        for gx in range(0, w, 40):
            d.line([(gx * SS, 0), (gx * SS, h * SS)], fill=(66, 66, 66), width=1)
        for gy in range(0, h, 40):
            d.line([(0, gy * SS), (w * SS, gy * SS)], fill=(66, 66, 66), width=1)
        d.line([(0, h * 0.62 * SS), (w * SS, h * 0.62 * SS)], fill=(150, 60, 60), width=2)
        d.line([(w * 0.45 * SS, 0), (w * 0.45 * SS, h * SS)], fill=(90, 140, 40), width=2)
        # gezinme gizmosu
        cx, cy, r = (w - 52), 52, 38
        d.ellipse([(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS],
                  fill=(255, 255, 255, 18))
        for ang, col in ((0, (230, 70, 80)), (240, (110, 170, 30)), (90, (60, 130, 230))):
            import math
            ex = cx + 28 * math.cos(math.radians(ang))
            ey = cy - 28 * math.sin(math.radians(ang))
            d.line([(cx * SS, cy * SS), (ex * SS, ey * SS)], fill=col, width=3)
            d.ellipse([(ex - 8) * SS, (ey - 8) * SS, (ex + 8) * SS, (ey + 8) * SS], fill=col)

    def headers(self, top):
        """Saydam başlık + araç başlığı (Blender 4.x / 5.x bölge örtüşmesi) ve araç çubuğu."""
        d, w, h = self.d, self.w, self.h
        d.rectangle([0, 0, w * SS, top * SS], fill=(48, 48, 48, 235))
        d.line([(0, 26 * SS), (w * SS, 26 * SS)], fill=(40, 40, 40), width=SS)
        f = self.font(11)
        x = 12
        for t in ("Object Mode", "View", "Select", "Add", "Object"):
            d.text((x * SS, 18 * SS), t, font=f, fill=(210, 210, 210), anchor="ls")
            x += self.measure(t, 11)[0] + 18
        x = 12
        for t in ("Global", "Snap", "Options"):
            d.text((x * SS, 44 * SS), t, font=f, fill=(190, 190, 190), anchor="ls")
            x += self.measure(t, 11)[0] + 26
        d.rectangle([4 * SS, (top + 6) * SS, 40 * SS, (top + 150) * SS], fill=(45, 45, 45, 230))
        for k in range(4):
            y = top + 12 + k * 34
            d.rectangle([9 * SS, y * SS, 35 * SS, (y + 26) * SS], fill=(70, 70, 70))

    def save(self, path):
        self.img.resize((self.w * SS // 2 * 2 // SS * 1, self.h), Image.LANCZOS) if False else None
        self.img.save(path)


TOP, LEFT = 52, 44            # saydam başlıklar (2 × 26 px) ve araç çubuğu


def frame(name, setup, w=1500, h=560, scale=1.0, collapsed=False):
    p = PILPainter(w, h)
    p.viewport()
    p.headers(TOP)
    r = ribbon.Ribbon(scale)
    r.collapsed = collapsed
    lw = 34 * scale + p.measure("BlendCAD", int(12 * scale))[0]
    right = 104 * scale + lw + 10 * scale
    r.layout(p, w, h, LEFT, right, TOP)
    now = setup(r, p, w, h) or 0.0
    ribbon.draw_launcher(p, w, h, scale, 0, hover=False, active=True, top_reserve=TOP)
    r.draw(p, w, h, LEFT, right, now=now, top_reserve=TOP)
    p.save(os.path.join(OUT, name))
    return r


def hover_btn(bid, t):
    def f(r, p, w, h):
        rc = r._rect("btn", bid)
        mx, my = (rc[0] + rc[2]) / 2, (rc[1] + rc[3]) / 2
        r.move(mx, my, 0.0)
        return t
    return f


os.makedirs(OUT, exist_ok=True)
frame("01_eskiz.png", lambda r, p, w, h: 0.0)
frame("02_kart_kisa.png", hover_btn("LINE", 0.6))
frame("03_kart_uzun.png", hover_btn("RECT", 2.0))


def fly(r, p, w, h):
    rc = r._rect("btn", "CIRCLE")
    r.press(rc[2] - 3, rc[1] + 3, 0.0)
    r.layout(p, w, h)
    it = r.fly_items[2]
    r.move((it[0] + it[2]) / 2, (it[1] + it[3]) / 2, 0.0)
    return 0.1


frame("04_acilir_liste.png", fly)


def tab(t, bid=None, at=2.0):
    def f(r, p, w, h):
        r.tab = t
        if bid:
            r.layout(p, w, h)
            return hover_btn(bid, at)(r, p, w, h)
        return 0.0
    return f


frame("05_kisit.png", tab("CONSTRAIN"))
frame("06_yuzey.png", tab("SURFACE", "THICKEN"))
frame("07_kati.png", tab("SOLID", "EXTRUDE"))
frame("08_delik_vida.png", tab("HOLE", "HOLE"))
frame("09_araclar.png", tab("TOOLS"))
frame("10_daraltilmis.png", lambda r, p, w, h: 0.0, collapsed=True)


def toast(r, p, w, h):
    rc = r._rect("btn", "TRIM")
    r.press((rc[0] + rc[2]) / 2, (rc[1] + rc[3]) / 2, 0.0)
    return 0.3


frame("11_secim_bildirim.png", toast)
frame("12_dar_gorunum_kaydirma.png", lambda r, p, w, h: 0.0, w=820)
frame("13_eskiz_genis.png", lambda r, p, w, h: 0.0, w=1920)
frame("14_secenek_karti.png", hover_btn("OPT_NEW", 2.0), w=1920)

# simge sayfası: bütün simgeler büyük
items = []
for b in data.all_buttons():
    items.append(b)
    items += b["variants"]
seen, uniq = set(), []
for b in items:
    if b["icon"] not in seen:
        seen.add(b["icon"])
        uniq.append(b)
cols = 10
cw, ch = 120, 96
rows = (len(uniq) + cols - 1) // cols
p = PILPainter(cols * cw, rows * ch)
p.rect(0, 0, cols * cw, rows * ch, ribbon.COL_BG)
for i, b in enumerate(uniq):
    r_, c = divmod(i, cols)
    cx = c * cw + cw / 2
    cy = rows * ch - r_ * ch - 40
    p.rect(cx - 30, cy - 30, cx + 30, cy + 30, ribbon.COL_CARD_ICON, 6)
    ribbon._icon(p, b["icon"], cx, cy, 38, ribbon.COL_ICON, 1.8)
    tw = p.measure(b["icon"], 9)[0]
    p.text(cx - tw / 2, cy - 46, b["icon"], ribbon.COL_TEXT_DIM, 9)
p.save(os.path.join(OUT, "00_simgeler.png"))
print("tamam:", sorted(os.listdir(OUT)))
