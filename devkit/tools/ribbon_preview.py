"""BlendCAD şeridini Blender'sız PNG olarak çizer (aynı ribbon.py çizim kodu, PIL ressamı).

Kullanım:  python3 ribbon_preview.py <eklenti klasörü> <çıktı klasörü>

Blender'daki görüntüye yakın bir önizleme verir (yazı tipi farklıdır: burada DejaVu,
Blender'da Inter). GPU çizimi gerçek Blender'da ayrıca kontrol edilmelidir.
"""

import importlib
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pil_painter import PILPainter  # noqa: E402

SRC, OUT = sys.argv[1], sys.argv[2]

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
    r.tab = "MODIFY"; r.layout(p, w, h, LEFT, 300, TOP)
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
