"""Çizim aracının 3D görünüm içindeki kayan araç penceresi ve vektör simgeleri.

Pencere tamamen GPU ile çizilir ve çizim modunun kendi olaylarıyla tıklanır; böylece
çizim sürerken açık kalır (Blender açılır pencereleri fare çıkınca kapanır). Başlıktan
sürüklenerek taşınır, konumu oturum boyunca hatırlanır.
"""

import math

import blf
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

DRAW_TOOLS = [
    ("SELECT", "Seç / duraklat: tıklamalar ve kısayollar Blender'a gider", "W · Esc"),
    ("LINE", "Doğru", "L"),
    ("TARC", "Teğet yay: çizgi ucundan teğet devam eder", "A"),
    ("ARC3", "3 noktalı yay: başlangıç, bitiş, eğrilik", "E"),
    ("CARC", "Merkezli yay: merkez, başlangıç, bitiş (D: yön)", "M"),
    ("CIRCLE", "Daire: merkez, yarıçap", "O"),
    ("RECT", "Dikdörtgen: iki köşe", "R"),
    ("CV", "Spline: kontrol noktalı (CV)", "S"),
    ("FIT", "Spline: noktalardan geçen", "K"),
    ("PEN", "Kalem: tıkla-sürükle ile bezier tutamacı", "P"),
]
MODIFY_TOOLS = [
    ("TRIM", "Kırp: parçayı en yakın kesişimler arasında sil (sürükle: çoklu, Shift: Uzat)", "B"),
    ("EXTEND", "Uzat: ucu en yakın sınıra uzat (Shift: Kırp)", ""),
    ("SPLIT", "Böl: nesneyi kesişimde ikiye ayır", ""),
    ("OFFSET", "Ötele: çizgiye tıkla, mesafe ver (Shift+tık: tek nesne)", ""),
    ("FILLET2D", "Köşe yuvarla: yarıçap yaz, köşeye tıkla", ""),
    ("CHAMFER2D", "Pah: mesafe yaz (Tab: 2. mesafe), köşeye tıkla", ""),
]
XFORM_TOOLS = [
    ("MOVE", "Taşı: seç → temel nokta → hedef (uzunluk / açı yazılabilir)", ""),
    ("COPY", "Kopyala: seç → temel nokta → hedef", ""),
    ("ROTATE", "Döndür: seç → merkez → açı (Shift: 15°, C: kopya)", ""),
    ("SCALE", "Ölçekle: seç → temel nokta → ölçek (C: kopya)", ""),
    ("STRETCH", "Esnet: noktaları kutuyla seç → temel → hedef", ""),
]
PATTERN_TOOLS = [
    ("RPAT", "Dikdörtgen desen: seç → başlangıç → 1. yön (adet, aralık) → 2. yön", ""),
    ("CPAT", "Dairesel desen: seç → merkez → adet, açı", ""),
    ("MIRROR", "Ayna: seç → ayna çizgisinin iki noktası (kopya eklenir)", ""),
]
PLANES = [("PICK", "Seç", "Çizim düzlemini görünümde seç: eksen düzlemi ya da gövde yüzü "
                          "(Shift+Q)"),
          ("AUTO", "Oto", "Görüşe göre eksen düzlemi; gövde yüzüne tıklarsan yüz düzlemi"),
          ("XY", "XY", "Üst düzlem (Z)"), ("XZ", "XZ", "Ön düzlem (Y)"),
          ("YZ", "YZ", "Yan düzlem (X)"), ("VIEW", "Görüş", "Ekrana paralel düzlem (V)")]
CONSTRAINTS = [
    ("AXIS", "Eksene hizala (yatay / dikey): 1 kenar"),
    ("PARALLEL", "Paralel: 2 kenar"),
    ("PERP", "Dik: 2 kenar"),
    ("COLLINEAR", "Doğrusal: 2 kenar"),
    ("EQUAL", "Eşit boy: 2 kenar"),
    ("COINCIDENT", "Çakışık: 2 nokta"),
    ("FIX", "Sabitle: 1 nokta"),
    ("TANGENT", "Teğet: aynı noktada birleşen 2 kenar"),
    ("SYMMETRIC", "Simetrik: 2 nokta (dünya eksen düzlemine göre)"),
    ("DISTANCE", "Uzunluk ölçüsü: 1 kenar (değer panelden)"),
    ("ANGLE", "Açı ölçüsü: 2 kenar"),
]
SKETCH = [("FINISH", "Bitir", "Taslağı eğri objesine kaydet (Ctrl+Enter)"),
          ("UNDO", "Geri al", "Taslaktaki son çizgiyi / noktayı geri al (Backspace)")]
TARGETS = [("ACTIVE", "Mevcut eğri", "Bitir: aktif / son eğri objesine ekler"),
           ("NEW", "Yeni eğri", "Bitir: yeni bir eğri objesi oluşturur")]
OPTIONS = [("auto", "Oto kısıt", "Çizerken yakalanan yatay/dikey, paralel, dik, uç çakışması ve "
                                "yazılan uzunluk kısıt olarak kaydedilsin"),
           ("show", "Göster", "Kısıt simgelerini görünümde göster"),
           ("snap", "Yakalama", "Uç / orta / kesişim yakalama ve kılavuzlar"),
           ("grid", "Izgara", "Izgaraya hafif yakalama; ızgara aralığı yakınlaştırmaya göre "
                              "değişir (I)"),
           ("look", "Bak", "Düzlem seçince görünümü düzleme çevir"),
           ("first", "Önce düzlem", "Çizim açılınca önce düzlem seçtir (Inventor gibi)")]

COLS = 6
COL_BG = (0.11, 0.11, 0.12, 0.92)
COL_TITLE = (0.17, 0.17, 0.19, 0.98)
COL_BTN = (0.22, 0.22, 0.24, 1.0)
COL_HOVER = (0.32, 0.32, 0.36, 1.0)
COL_ON = (0.25, 0.45, 0.75, 1.0)
COL_ICON = (0.92, 0.92, 0.92, 1.0)
COL_DIM = (0.65, 0.65, 0.68, 1.0)
COL_SECTION = (0.6, 0.75, 0.95, 1.0)

_POS = {"x": None, "y": None}       # oturum boyunca pencere konumu (sol üst)


# ---------------------------------------------------------------- çizim temel taşları

def _lines(seg, color, width, region):
    if not seg:
        return
    sh = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    batch = batch_for_shader(sh, "LINES", {"pos": [(p[0], p[1], 0.0) for p in seg]})
    sh.bind()
    sh.uniform_float("viewportSize", (region.width, region.height))
    sh.uniform_float("lineWidth", width)
    sh.uniform_float("color", color)
    batch.draw(sh)


def rect(x0, y0, x1, y1, color):
    sh = gpu.shader.from_builtin("UNIFORM_COLOR")
    batch = batch_for_shader(sh, "TRIS", {"pos": [(x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0),
                                                 (x0, y1, 0.0)]},
                             indices=[(0, 1, 2), (0, 2, 3)])
    sh.bind()
    sh.uniform_float("color", color)
    batch.draw(sh)


def text(x, y, txt, color=COL_ICON, size=11, center=False):
    font = 0
    try:
        blf.size(font, size)
    except TypeError:
        blf.size(font, size, 72)
    w, h = blf.dimensions(font, txt)
    if center:
        x -= w / 2
    blf.color(font, *color)
    blf.position(font, x, y, 0)
    blf.draw(font, txt)
    return w, h


def _poly(pts, closed=False):
    out = []
    for i in range(len(pts) - 1):
        out += [pts[i], pts[i + 1]]
    if closed:
        out += [pts[-1], pts[0]]
    return out


def _arc(cx, cy, r, a0, a1, n=12):
    return [(cx + r * math.cos(a0 + (a1 - a0) * k / n), cy + r * math.sin(a0 + (a1 - a0) * k / n))
            for k in range(n + 1)]


def _dot(x, y, s=0.09):
    return _poly([(x - s, y - s), (x + s, y - s), (x + s, y + s), (x - s, y + s)], True)


def _bspline_pts(cv, n=24):
    cv = np.asarray(cv, dtype=float)
    out = []
    for t in np.linspace(0, len(cv) - 3, n):
        i = min(int(t), len(cv) - 4)
        u = t - i
        b = [(1 - u) ** 3 / 6, (3 * u ** 3 - 6 * u * u + 4) / 6,
             (-3 * u ** 3 + 3 * u * u + 3 * u + 1) / 6, u ** 3 / 6]
        out.append(tuple(sum(b[k] * cv[i + k] for k in range(4))))
    return out


def icon_lines(name):
    """[-1,1]² içinde simge çizgileri (nokta çiftleri)."""
    P = _poly
    if name == "TRASH":
        return P([(-0.6, 0.55), (0.6, 0.55)]) + P([(-0.2, 0.55), (-0.2, 0.8), (0.2, 0.8),
                                                   (0.2, 0.55)]) + \
            P([(-0.45, 0.55), (-0.35, -0.8), (0.35, -0.8), (0.45, 0.55)]) + \
            P([(-0.12, 0.3), (-0.12, -0.55)]) + P([(0.12, 0.3), (0.12, -0.55)])
    if name == "FREEZE":
        out = []
        for k in range(3):
            a = k * math.pi / 3
            c, s_ = math.cos(a) * 0.85, math.sin(a) * 0.85
            out += P([(-c, -s_), (c, s_)])
            for sgn in (1, -1):
                ex, ey = c * sgn, s_ * sgn
                bx, by = ex * 0.6, ey * 0.6
                px, py = -ey * 0.25, ex * 0.25
                out += P([(bx + px, by + py), (ex * 0.8, ey * 0.8), (bx - px, by - py)])
        return out
    if name == "SELECT":
        return P([(-0.5, 0.85), (-0.5, -0.55), (-0.15, -0.2), (0.12, -0.8), (0.35, -0.7),
                  (0.1, -0.1), (0.55, -0.1)], True)
    if name == "LINE":
        return P([(-0.7, -0.7), (0.7, 0.7)]) + _dot(-0.7, -0.7) + _dot(0.7, 0.7)
    if name == "TARC":
        return P([(-0.85, -0.6), (0.0, -0.6)]) + P(_arc(0.0, 0.0, 0.6, -math.pi / 2, math.pi / 2)) \
            + _dot(0.0, -0.6)
    if name == "ARC3":
        return P(_arc(0.0, -0.4, 0.75, 0.0, math.pi)) + _dot(0.75, -0.4) + _dot(-0.75, -0.4) + \
            _dot(0.0, 0.35)
    if name == "CARC":
        return P(_arc(-0.5, -0.5, 1.1, 0.0, math.pi / 2)) + P([(-0.5, -0.5), (0.6, -0.5)]) + \
            _dot(-0.5, -0.5)
    if name == "CIRCLE":
        return P(_arc(0, 0, 0.75, 0, 2 * math.pi, 20)) + _dot(0, 0, 0.06)
    if name == "RECT":
        return P([(-0.75, -0.55), (0.75, -0.55), (0.75, 0.55), (-0.75, 0.55)], True)
    if name == "CV":
        cv = [(-0.85, -0.6), (-0.4, 0.75), (0.35, -0.75), (0.85, 0.6)]
        dash = []
        for i in range(3):
            a, b = np.array(cv[i]), np.array(cv[i + 1])
            for k in range(0, 6, 2):
                dash += [tuple(a + (b - a) * k / 6), tuple(a + (b - a) * (k + 1) / 6)]
        ext = [cv[0]] + cv + [cv[-1]]
        return dash + P(_bspline_pts(ext)) + sum((_dot(x, y, 0.07) for x, y in cv), [])
    if name == "FIT":
        pts = [(-0.85, -0.5), (-0.3, 0.45), (0.3, -0.45), (0.85, 0.5)]
        t = np.linspace(-0.85, 0.85, 24)
        curve = [(float(x), float(0.5 * math.sin((x + 0.85) / 1.7 * 3 * math.pi - math.pi / 2)))
                 for x in t]
        return P(curve) + sum((_dot(x, y, 0.08) for x, y in pts), [])
    if name == "PEN":
        return P([(0.0, -0.85), (-0.4, 0.05), (0.0, 0.3), (0.4, 0.05)], True) + \
            P([(0.0, -0.85), (0.0, -0.15)]) + P([(-0.85, 0.65), (0.85, 0.65)]) + \
            _dot(-0.85, 0.65) + _dot(0.85, 0.65)
    if name == "TRIM":
        dash = []
        for k in range(3):
            x = -0.85 + k * 0.22
            dash += [(x, 0.0), (x + 0.12, 0.0)]
        return P([(-0.15, 0.0), (0.85, 0.0)]) + P([(0.1, -0.8), (0.1, 0.8)]) + dash + \
            P([(-0.55, 0.25), (-0.35, 0.45)]) + P([(-0.55, 0.45), (-0.35, 0.25)])
    if name == "EXTEND":
        dash = []
        for k in range(3):
            x = -0.05 + k * 0.25
            dash += [(x, -0.2), (x + 0.14, -0.2)]
        return P([(-0.85, -0.2), (-0.15, -0.2)]) + dash + P([(0.75, -0.8), (0.75, 0.8)]) + \
            P([(0.5, 0.05), (0.7, -0.2), (0.5, -0.45)])
    if name == "SPLIT":
        return P([(-0.85, -0.3), (-0.12, -0.3)]) + P([(0.12, -0.3), (0.85, -0.3)]) + \
            P([(0.0, -0.85), (0.0, 0.25)]) + _dot(-0.12, -0.3) + _dot(0.12, -0.3)
    if name == "OFFSET":
        return P(_arc(0.15, -0.15, 0.55, math.pi / 2, math.pi)) + \
            P([(-0.4, -0.15), (-0.4, -0.85)]) + P([(0.15, 0.4), (0.85, 0.4)]) + \
            P(_arc(0.15, -0.15, 0.9, math.pi / 2, math.pi)) + \
            P([(-0.75, -0.15), (-0.75, -0.85)]) + P([(0.15, 0.75), (0.85, 0.75)])
    if name == "FILLET2D":
        return P([(-0.75, 0.8), (-0.75, -0.1)]) + P(_arc(-0.05, -0.1, 0.7, math.pi,
                                                         1.5 * math.pi)) + \
            P([(-0.05, -0.8), (0.85, -0.8)])
    if name == "CHAMFER2D":
        return P([(-0.75, 0.8), (-0.75, -0.2), (-0.15, -0.8), (0.85, -0.8)])
    if name == "MOVE":
        out = P([(-0.8, 0.0), (0.8, 0.0)]) + P([(0.0, -0.8), (0.0, 0.8)])
        for x, y, dx, dy in ((0.8, 0, 1, 0), (-0.8, 0, -1, 0), (0, 0.8, 0, 1), (0, -0.8, 0, -1)):
            out += P([(x - dx * 0.25 + dy * 0.2, y - dy * 0.25 + dx * 0.2), (x, y),
                      (x - dx * 0.25 - dy * 0.2, y - dy * 0.25 - dx * 0.2)])
        return out
    if name == "COPY":
        return P([(-0.8, -0.2), (0.2, -0.2), (0.2, 0.8), (-0.8, 0.8)], True) + \
            P([(-0.2, -0.8), (0.8, -0.8), (0.8, 0.2), (0.4, 0.2)]) + P([(-0.2, -0.8), (-0.2, -0.4)])
    if name == "ROTATE":
        return P(_arc(0.0, 0.0, 0.7, 0.3, 2 * math.pi - 0.3, 18)) + \
            P([(0.45, 0.45), (0.67, 0.2), (0.9, 0.42)]) + _dot(0, 0, 0.08)
    if name == "SCALE":
        return P([(-0.85, -0.85), (0.1, -0.85), (0.1, 0.1), (-0.85, 0.1)], True) + \
            P([(-0.85, -0.85), (0.85, -0.85), (0.85, 0.85), (-0.85, 0.85)], True) + \
            P([(0.1, 0.1), (0.7, 0.7)]) + P([(0.45, 0.7), (0.7, 0.7), (0.7, 0.45)])
    if name == "STRETCH":
        return P([(-0.85, -0.6), (0.0, -0.6), (0.0, 0.6), (-0.85, 0.6)]) + \
            P([(0.0, -0.6), (0.85, -0.6)]) + P([(0.0, 0.6), (0.85, 0.6)]) + \
            P([(0.45, -0.2), (0.85, 0.0), (0.45, 0.2)]) + P([(0.2, 0.0), (0.85, 0.0)])
    if name == "RPAT":
        out = []
        for x in (-0.6, 0.0, 0.6):
            for y in (-0.5, 0.3):
                out += P([(x - 0.2, y - 0.2), (x + 0.2, y - 0.2), (x + 0.2, y + 0.2),
                          (x - 0.2, y + 0.2)], True)
        return out
    if name == "CPAT":
        out = _dot(0, 0, 0.07)
        for k in range(6):
            a = k * math.pi / 3
            x, y = 0.65 * math.cos(a), 0.65 * math.sin(a)
            out += P(_arc(x, y, 0.17, 0, 2 * math.pi, 8))
        return out
    if name == "MIRROR":
        dash = []
        for k in range(-4, 4, 2):
            dash += [(0.0, k * 0.22), (0.0, (k + 1) * 0.22)]
        return P([(-0.15, -0.7), (-0.85, 0.7), (-0.15, 0.7)], True) + \
            P([(0.15, -0.7), (0.85, 0.7), (0.15, 0.7)], True) + dash
    if name == "AXIS":
        return P([(-0.8, 0.0), (0.8, 0.0)]) + P([(-0.8, -0.3), (-0.8, 0.3)]) + \
            P([(0.8, -0.3), (0.8, 0.3)]) + P([(0.0, -0.75), (0.0, -0.45)])
    if name == "PARALLEL":
        return P([(-0.6, -0.75), (-0.1, 0.75)]) + P([(0.1, -0.75), (0.6, 0.75)])
    if name == "PERP":
        return P([(-0.75, -0.6), (0.75, -0.6)]) + P([(0.0, -0.6), (0.0, 0.75)])
    if name == "COLLINEAR":
        return P([(-0.8, -0.8), (-0.2, -0.2)]) + P([(0.2, 0.2), (0.8, 0.8)]) + \
            _dot(-0.8, -0.8) + _dot(0.8, 0.8)
    if name == "EQUAL":
        return P([(-0.65, 0.25), (0.65, 0.25)]) + P([(-0.65, -0.25), (0.65, -0.25)])
    if name == "COINCIDENT":
        return P([(-0.75, -0.6), (0.0, 0.2)]) + P([(0.75, -0.6), (0.0, 0.2)]) + _dot(0.0, 0.2, 0.15)
    if name == "FIX":
        return P([(-0.5, -0.75), (0.5, -0.75), (0.5, 0.05), (-0.5, 0.05)], True) + \
            P(_arc(0.0, 0.05, 0.32, 0.0, math.pi)) + P([(0.32, 0.05), (0.32, 0.05)])
    if name == "TANGENT":
        return P(_arc(0.0, -0.25, 0.5, 0, 2 * math.pi, 20)) + P([(-0.85, 0.25), (0.85, 0.25)])
    if name == "SYMMETRIC":
        dash = []
        for k in range(-4, 4, 2):
            dash += [(0.0, k * 0.2), (0.0, (k + 1) * 0.2)]
        return P([(-0.35, -0.7), (-0.75, -0.7), (-0.75, 0.7), (-0.35, 0.7)]) + \
            P([(0.35, -0.7), (0.75, -0.7), (0.75, 0.7), (0.35, 0.7)]) + dash
    if name == "DISTANCE":
        return P([(-0.8, 0.0), (0.8, 0.0)]) + P([(-0.8, -0.45), (-0.8, 0.45)]) + \
            P([(0.8, -0.45), (0.8, 0.45)]) + P([(-0.8, 0.0), (-0.5, 0.2)]) + \
            P([(-0.8, 0.0), (-0.5, -0.2)]) + P([(0.8, 0.0), (0.5, 0.2)]) + \
            P([(0.8, 0.0), (0.5, -0.2)])
    if name == "ANGLE":
        return P([(-0.75, -0.6), (0.8, -0.6)]) + P([(-0.75, -0.6), (0.45, 0.7)]) + \
            P(_arc(-0.75, -0.6, 0.8, 0.0, math.atan2(1.3, 1.2)))
    return P([(-0.5, -0.5), (0.5, 0.5)]) + P([(-0.5, 0.5), (0.5, -0.5)])


def draw_icon(name, cx, cy, size, color, region, width=1.6):
    s = size * 0.5
    seg = [(cx + x * s, cy + y * s) for x, y in icon_lines(name)]
    _lines(seg, color, width, region)


# ---------------------------------------------------------------- pencere

class Palette:
    def __init__(self, scale):
        self.s = scale
        self.items = []         # (x0, y0, x1, y1, tür, kimlik)
        self.hover = None
        self.drag = None
        self.box = (0, 0, 0, 0)

    def _layout(self, region):
        s = self.s
        B = 30 * s
        pad = 6 * s
        W = COLS * B + pad * 2
        if _POS["x"] is None:
            _POS["x"] = 70 * s
            _POS["y"] = region.height - 70 * s
        _POS["x"] = min(max(_POS["x"], 0), max(region.width - W, 0))
        _POS["y"] = min(max(_POS["y"], 120 * s), region.height)
        x, top = _POS["x"], _POS["y"]
        items = []
        y = top
        th = 20 * s
        items.append((x, y - th, x + W, y, "title", None))
        y -= th + 4 * s

        def section(label):
            nonlocal y
            items.append((x + pad, y - 14 * s, x + W - pad, y, "label", label))
            y -= 15 * s

        def grid(kind, entries):
            nonlocal y
            for i, e in enumerate(entries):
                r, c = divmod(i, COLS)
                bx = x + pad + c * B
                by = y - (r + 1) * B
                items.append((bx + 1, by + 1, bx + B - 1, by + B - 1, kind, e[0]))
            rows = (len(entries) + COLS - 1) // COLS
            y -= rows * B + 4 * s

        def strip(kind, entries):
            nonlocal y
            n = len(entries)
            w = (W - 2 * pad) / n
            h = 20 * s
            for i, e in enumerate(entries):
                bx = x + pad + i * w
                items.append((bx + 1, y - h, bx + w - 1, y, kind, e[0]))
            y -= h + 6 * s

        section("TASLAK")
        strip("sk", SKETCH)
        strip("tgt", TARGETS)
        section("ÇİZ")
        grid("tool", DRAW_TOOLS)
        section("DEĞİŞTİR")
        grid("tool", MODIFY_TOOLS)
        section("DÜZENLE · DESEN")
        grid("tool", XFORM_TOOLS + PATTERN_TOOLS)
        section("DÜZLEM")
        strip("plane", PLANES)
        section("KISIT")
        grid("cons", CONSTRAINTS)
        strip("opt", OPTIONS[:3])
        strip("opt", OPTIONS[3:])
        items.append((x, y - 18 * s, x + W, y, "tip", None))
        y -= 20 * s
        self.items = items
        self.box = (x, y, x + W, top)
        return items

    def contains(self, mx, my):
        x0, y0, x1, y1 = self.box
        return x0 <= mx <= x1 and y0 <= my <= y1

    def hit(self, mx, my):
        for it in self.items:
            x0, y0, x1, y1, kind, ident = it
            if x0 <= mx <= x1 and y0 <= my <= y1 and kind not in ("label", "tip"):
                return kind, ident
        return None

    def tooltip(self):
        if self.hover is None:
            return ""
        kind, ident = self.hover
        if kind == "tool":
            for k, name, key in DRAW_TOOLS + MODIFY_TOOLS + XFORM_TOOLS + PATTERN_TOOLS:
                if k == ident:
                    return name + (f"  [{key}]" if key else "")
        if kind == "plane":
            for k, name, tip in PLANES:
                if k == ident:
                    return tip
        if kind == "cons":
            for k, name in CONSTRAINTS:
                if k == ident:
                    return name
        if kind == "opt":
            for k, name, tip in OPTIONS:
                if k == ident:
                    return tip
        if kind in ("sk", "tgt"):
            for k, name, tip in (SKETCH if kind == "sk" else TARGETS):
                if k == ident:
                    return tip
        if kind == "title":
            return "Sürükleyerek taşı · X: bitir ve kapat"
        return ""

    # -------------------------------------------------------- olaylar

    def press(self, mx, my):
        h = self.hit(mx, my)
        if h is not None and h[0] == "title":
            x0, y0, x1, y1 = self.box
            if mx >= x1 - 20 * self.s:
                return ("close", None)
            self.drag = (mx - _POS["x"], my - _POS["y"])
            return ("drag", None)
        return h

    def move(self, mx, my):
        if self.drag is not None:
            _POS["x"] = mx - self.drag[0]
            _POS["y"] = my - self.drag[1]
            return True
        h = self.hit(mx, my) if self.contains(mx, my) else None
        changed = h != self.hover
        self.hover = h
        return changed

    def release(self):
        was = self.drag is not None
        self.drag = None
        return was

    # -------------------------------------------------------- çizim

    def draw(self, region, state):
        """state: {"tool", "plane", "opts": {...}, "status": str}"""
        self._layout(region)
        s = self.s
        x0, y0, x1, y1 = self.box
        rect(x0, y0, x1, y1, COL_BG)
        for bx0, by0, bx1, by1, kind, ident in self.items:
            hov = self.hover == (kind, ident)
            if kind == "title":
                rect(bx0, by0, bx1, by1, COL_TITLE)
                text(bx0 + 7 * s, by0 + 6 * s, "Mini CAD · Çizim", COL_ICON, int(11 * s))
                text(bx1 - 14 * s, by0 + 6 * s, "X", COL_DIM, int(11 * s))
            elif kind == "label":
                text(bx0, by0 + 3 * s, ident, COL_SECTION, int(9 * s))
            elif kind == "tip":
                tip = self.tooltip() or state.get("status", "")
                if len(tip) > 46:
                    tip = tip[:45] + "…"
                text(bx0 + 7 * s, by0 + 5 * s, tip, COL_DIM, int(9 * s))
            elif kind in ("tool", "cons"):
                on = (state.get("tool") == ident) if kind == "tool" else \
                    (state.get("tool") == "C_" + ident)
                rect(bx0, by0, bx1, by1, COL_ON if on else (COL_HOVER if hov else COL_BTN))
                cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
                draw_icon(ident, cx, cy, (bx1 - bx0) * 0.62, COL_ICON, region)
            elif kind in ("sk", "tgt"):
                if kind == "sk":
                    n = state.get("sketch", 0)
                    on = ident == "FINISH" and n > 0
                    label = next(nm for k, nm, _ in SKETCH if k == ident)
                    if ident == "FINISH" and n:
                        label += f" ({n})"
                else:
                    on = state.get("target") == ident
                    label = next(nm for k, nm, _ in TARGETS if k == ident)
                col = (0.2, 0.55, 0.3, 1.0) if (kind == "sk" and on) else \
                    (COL_ON if on else (COL_HOVER if hov else COL_BTN))
                rect(bx0, by0, bx1, by1, col)
                text((bx0 + bx1) / 2, by0 + 6 * s, label, COL_ICON, int(10 * s), center=True)
            elif kind in ("plane", "opt"):
                if kind == "plane":
                    on = state.get("plane") == ident or (ident == "PICK" and
                                                          state.get("picking"))
                    label = next(n for k, n, _ in PLANES if k == ident)
                else:
                    on = bool(state.get("opts", {}).get(ident))
                    label = next(n for k, n, _ in OPTIONS if k == ident)
                rect(bx0, by0, bx1, by1, COL_ON if on else (COL_HOVER if hov else COL_BTN))
                text((bx0 + bx1) / 2, by0 + 6 * s, label, COL_ICON, int(10 * s), center=True)
