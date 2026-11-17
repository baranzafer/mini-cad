"""BlendCAD şeridi (ribbon): yerleşim, durum, olaylar ve çizim.

Bu modül bpy / gpu kullanmaz. Çizim bir "ressam" (painter) nesnesi üzerinden yapılır:
Blender'da ribbon_gpu.GPUPainter, testte / önizlemede PIL ressamı kullanılır. Böylece aynı
çizim kodu Blender dışında da görüntüye dökülüp denetlenebilir.

Koordinatlar Blender bölge pikselleridir: sol alt (0, 0), y yukarı.

v0.27.0: yalnızca arayüz. Düğmeler seçilir / açılır listeler açılır / açıklama kartı görünür;
işlevler sonraki adımda bağlanacak (on_action geri çağrısı).
"""

import math

from . import ribbon_data as data
from .ribbon_icons import icon_lines

# ---------------------------------------------------------------- renkler

COL_SHADOW = (0.0, 0.0, 0.0, 0.28)
COL_BG = (0.135, 0.135, 0.145, 0.95)
COL_TABBAR = (0.095, 0.095, 0.105, 0.97)
COL_BORDER = (0.27, 0.27, 0.30, 1.0)
COL_HOVER = (0.27, 0.27, 0.30, 1.0)
COL_PRESS = (0.33, 0.33, 0.37, 1.0)
COL_ACTIVE = (0.20, 0.42, 0.75, 1.0)
COL_TOGGLE = (0.16, 0.30, 0.48, 1.0)
COL_ACCENT = (0.33, 0.60, 0.98, 1.0)
COL_ICON = (0.90, 0.90, 0.92, 1.0)
COL_ICON_DIM = (0.62, 0.62, 0.66, 1.0)
COL_TEXT = (0.92, 0.92, 0.94, 1.0)
COL_TEXT_DIM = (0.60, 0.60, 0.64, 1.0)
COL_SEP = (0.24, 0.24, 0.27, 1.0)
COL_PLANNED = (0.96, 0.66, 0.22, 1.0)
COL_READY = (0.35, 0.78, 0.48, 1.0)
COL_CARD = (0.085, 0.085, 0.095, 0.98)
COL_CARD_ICON = (0.16, 0.16, 0.18, 1.0)
COL_KEY = (0.22, 0.22, 0.25, 1.0)
COL_LOGO = (0.36, 0.64, 1.0, 1.0)

# ---------------------------------------------------------------- zamanlama (sn)

TIP_DELAY = 0.45        # kısa kart
TIP_EXPAND = 1.4        # uzun kart (kullanım adımları)
TIP_WARM = 0.6          # kart kapandıktan sonra bu süre içinde yeni düğmede hemen aç
TIP_FADE = 0.12
TOAST_TIME = 2.6

DEFAULT_TOGGLES = ("CONS_SHOW", "CONS_AUTO")


def _mix(c, a):
    return (c[0], c[1], c[2], c[3] * a)


def wrap(text, size, maxw, measure):
    """Sözcük sınırından satırlara böl."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if cur and measure(t, size)[0] > maxw:
            lines.append(cur)
            cur = w
        else:
            cur = t
    if cur:
        lines.append(cur)
    return lines


# ---------------------------------------------------------------- başlatıcı (BlendCAD düğmesi)

def launcher_rect(region_w, region_h, s, right_reserve=0.0, text_w=None, top_reserve=0.0):
    """Sağ üstte, gezinme gizmosunun solunda duran 'BlendCAD' düğmesi."""
    tw = text_w if text_w is not None else 58 * s
    w = 34 * s + tw
    h = 26 * s
    x1 = region_w - right_reserve - 104 * s
    y1 = region_h - top_reserve - 10 * s
    return (x1 - w, y1 - h, x1, y1)


def draw_launcher(p, region_w, region_h, s, right_reserve=0.0, hover=False, active=False,
                  top_reserve=0.0):
    tsz = int(12 * s)
    tw = p.measure("BlendCAD", tsz)[0]
    x0, y0, x1, y1 = launcher_rect(region_w, region_h, s, right_reserve, tw, top_reserve)
    r = (y1 - y0) / 2
    p.rect(x0 + 1 * s, y0 - 2 * s, x1 + 1 * s, y1 - 2 * s, COL_SHADOW, r)
    bg = COL_ACTIVE if active else (COL_HOVER if hover else (0.16, 0.16, 0.18, 0.96))
    p.rect(x0, y0, x1, y1, bg, r)
    p.outline(x0, y0, x1, y1, COL_ACCENT if (hover or active) else COL_BORDER, r, 1.0)
    cy = (y0 + y1) / 2
    _icon(p, "LOGO", x0 + 16 * s, cy, 16 * s, COL_TEXT if active else COL_LOGO, 1.4)
    p.text(x0 + 28 * s, cy - 4 * s, "BlendCAD", COL_TEXT, tsz, bold=True)
    return (x0, y0, x1, y1)


def _icon(p, name, cx, cy, size, color, width=1.5):
    s = size * 0.5
    seg = [(cx + x * s, cy + y * s) for x, y in icon_lines(name)]
    p.lines(seg, color, width)


# ---------------------------------------------------------------- şerit

class Ribbon:
    def __init__(self, scale=1.0, on_action=None):
        self.s = scale
        self.tab = data.TABS[0][0]
        self.collapsed = False
        self.active = None                  # seçili araç (tür kimliği)
        self.variant = {}                   # düğme id -> seçili tür id
        self.toggles = set(DEFAULT_TOGGLES)
        self.items = []                     # (x0, y0, x1, y1, tür, kimlik)
        self.box = (0, 0, 0, 0)             # panel kutusu
        self.fly = None                     # açık açılır liste: düğme id
        self.fly_items = []
        self.fly_box = None
        self.hover = None
        self.hover_t0 = 0.0
        self.tip_last = -10.0               # kartın son göründüğü an
        self.pressed = None
        self.scroll = 0.0
        self.scroll_max = 0.0
        self.toast = None                   # (metin, t0)
        self.on_action = on_action
        self.notify = None                  # (metin) -> bildirim merkezine
        self.state_fn = None                # (düğme) -> açık mı (None: şeridin kendi durumu)
        self.active_fn = None               # () -> etkin araç kimliği (Blender'dan)
        self.now = 0.0
        self._anchor_x = 0.0                # son tıklanan düğmenin sol kenarı (pencere yeri)
        from .ribbon_forms import FormHost
        from .ribbon_menu import ContextMenu
        self.forms = FormHost(scale)        # araç pencereleri (şeridin altına açılır)
        self.menu = ContextMenu(scale)      # sağ tık menüsü (v0.30.0)

    def open_form(self, fid, title, icon, spec, width=300):
        """Son tıklanan düğmenin altında araç penceresi aç (aynısı açıksa kapatır)."""
        self.forms.s = self.s
        return self.forms.open(fid, title, icon, spec, self._anchor_x, width)

    # ------------------------------------------------------------ veri yardımcıları

    def groups(self):
        for tid, _lbl, groups in data.TABS:
            if tid == self.tab:
                return groups
        return []

    def current(self, btn):
        """Düğmenin şu anki türü (tür yoksa düğmenin kendisi)."""
        if not btn["variants"]:
            return btn
        vid = self.variant.get(btn["id"], btn["variants"][0]["id"])
        for v in btn["variants"]:
            if v["id"] == vid:
                return v
        return btn["variants"][0]

    def _btn(self, bid):
        for _g, btns in self.groups():
            for b in btns:
                if b["id"] == bid:
                    return b
        return None

    def is_on(self, btn):
        if self.state_fn is not None:
            try:
                v = self.state_fn(btn)
            except Exception:
                v = None
            if v is not None:
                return bool(v)
        if btn["toggle"]:
            return btn["id"] in self.toggles
        cur = self.current(btn)
        return self.active is not None and (self.active == cur["id"] or self.active == btn["id"])

    def sync(self):
        """Etkin aracı Blender'dan al; tür düğmesi o türü göstersin (O'ya iki kez basınca
        Teğet daire gibi)."""
        if self.active_fn is None:
            return
        try:
            self.active = self.active_fn()
        except Exception:
            self.active = None
        if self.active is None:
            return
        for b in data.all_buttons():
            for v in b["variants"]:
                if v["id"] == self.active and not v.get("keep"):
                    self.variant[b["id"]] = v["id"]

    @staticmethod
    def _small(b):
        return bool(b.get("small"))

    def _gwidth(self, p, btns):
        """Grup genişliği: büyük düğmeler yan yana, küçükler iki satırlık sütunlar."""
        s = self.s
        BS, GAP = 34 * s, 2 * s
        w = 0.0
        big = [b for b in btns if not self._small(b)]
        w += len(big) * (BS + GAP)
        small = [b for b in btns if self._small(b)]
        for c in range(0, len(small), 2):
            w += self._scol(p, small[c:c + 2]) + GAP
        return w - GAP if btns else 0.0

    def _scol(self, p, col):
        s = self.s
        return max(p.measure(b["short"], int(9 * s))[0] for b in col) + 24 * s

    # ------------------------------------------------------------ yerleşim

    def layout(self, p, region_w, region_h, left=0.0, right=0.0, top_reserve=0.0):
        self.sync()
        s = self.s
        M = 6 * s
        TH = 24 * s           # sekme şeridi
        BS = 34 * s           # düğme
        GAP = 2 * s
        GG = 9 * s            # grup arası
        LH = 15 * s           # grup adı
        PAD = 8 * s
        x0 = left + M
        top = region_h - top_reserve - M
        avail = max(region_w - right - x0 - M, 200 * s)
        items = []

        # ---- sekme şeridi
        tsz = int(11 * s)
        x = x0 + PAD
        logo_w = 22 * s + p.measure("BlendCAD", int(12 * s))[0]
        items.append((x, top - TH, x + logo_w, top, "logo", None))
        x += logo_w + 10 * s
        for tid, lbl, _g in data.TABS:
            w = p.measure(lbl, tsz)[0] + 18 * s
            items.append((x, top - TH, x + w, top, "tab", tid))
            x += w + 2 * s
        tabs_w = x - x0 + 2 * 22 * s + PAD

        # ---- düğmeler
        bw = 0.0
        groups = self.groups()
        for gi, (_g, btns) in enumerate(groups):
            bw += self._gwidth(p, btns) + (GG * 2 if gi else 0)
        width = min(max(tabs_w, bw + 2 * PAD), avail)
        rows_h = 0 if self.collapsed else BS + 2 * 4 * s + LH
        bottom = top - TH - rows_h
        self.box = (x0, bottom, x0 + width, top)

        # sağdaki denetimler (daralt / kapat)
        cx = x0 + width - PAD
        for kind in ("close", "collapse"):
            items.append((cx - 20 * s, top - TH + 2 * s, cx, top - 2 * s, kind, None))
            cx -= 22 * s

        if not self.collapsed:
            inner0, inner1 = x0 + PAD, x0 + width - PAD
            self.scroll_max = max(0.0, bw - (inner1 - inner0))
            self.scroll = min(max(self.scroll, 0.0), self.scroll_max)
            by1 = top - TH - 4 * s
            by0 = by1 - BS
            x = inner0 - self.scroll
            for gi, (gname, btns) in enumerate(groups):
                if gi:
                    items.append((x + GG - 0.5, by0 - LH + 2 * s, x + GG + 0.5, by1, "sep", None))
                    x += GG * 2
                g0 = x
                for b in btns:
                    if self._small(b):
                        continue
                    if x >= inner0 - 0.5 and x + BS <= inner1 + 0.5:
                        items.append((x, by0, x + BS, by1, "btn", b["id"]))
                    x += BS + GAP
                small = [b for b in btns if self._small(b)]
                SH = (BS - GAP) / 2
                for c in range(0, len(small), 2):
                    col = small[c:c + 2]
                    cw = self._scol(p, col)
                    for k, b in enumerate(col):
                        yy1 = by1 - k * (SH + GAP)
                        if x >= inner0 - 0.5 and x + cw <= inner1 + 0.5:
                            items.append((x, yy1 - SH, x + cw, yy1, "btn", b["id"]))
                    x += cw + GAP
                g1 = x - GAP
                x = g1
                gc = (g0 + g1) / 2
                gw = p.measure(gname, int(9 * s))[0] / 2
                if inner0 <= gc - gw and gc + gw <= inner1 - 14 * s:
                    items.append((g0, by0 - LH, g1, by0 - 1 * s, "glabel", gname))
            if self.scroll_max > 0:
                if self.scroll > 0:
                    items.append((x0, by0, x0 + PAD + 4 * s, by1, "scroll", -1))
                if self.scroll < self.scroll_max:
                    items.append((x0 + width - PAD - 4 * s, by0, x0 + width, by1, "scroll", 1))
        self.items = items
        self._layout_fly(p)
        return items

    def _layout_fly(self, p):
        self.fly_items, self.fly_box = [], None
        if self.fly is None or self.collapsed:
            return
        btn = self._btn(self.fly)
        rect = self._rect("btn", self.fly)
        if btn is None or rect is None:
            self.fly = None
            return
        s = self.s
        RH = 34 * s
        W = 250 * s
        x0 = rect[0]
        y = rect[1] - 3 * s
        for v in btn["variants"]:
            self.fly_items.append((x0, y - RH, x0 + W, y, "fly", v["id"]))
            y -= RH
        self.fly_box = (x0 - 4 * s, y - 4 * s, x0 + W + 4 * s, rect[1] - 1 * s)

    def _rect(self, kind, ident):
        for it in self.items:
            if it[4] == kind and it[5] == ident:
                return it[:4]
        return None

    # ------------------------------------------------------------ isabet

    def contains(self, mx, my):
        x0, y0, x1, y1 = self.box
        if x0 <= mx <= x1 and y0 <= my <= y1:
            return True
        if self.forms.contains(mx, my):
            return True
        if self.menu.is_open():
            return True                     # açık menü: bütün tıklar menünün
        if self.fly_box:
            fx0, fy0, fx1, fy1 = self.fly_box
            if fx0 <= mx <= fx1 and fy0 <= my <= fy1:
                return True
        return False

    def hit(self, mx, my):
        for x0, y0, x1, y1, kind, ident in self.fly_items:
            if x0 <= mx <= x1 and y0 <= my <= y1:
                return (kind, ident)
        if self.fly_box and self.fly_box[0] <= mx <= self.fly_box[2] and \
                self.fly_box[1] <= my <= self.fly_box[3]:
            return ("flybg", None)
        for x0, y0, x1, y1, kind, ident in self.items:
            if kind in ("sep", "glabel"):
                continue
            if x0 <= mx <= x1 and y0 <= my <= y1:
                if kind == "btn":
                    b = self._btn(ident)
                    if b and b["variants"] and mx >= x1 - 12 * self.s and my <= y0 + 12 * self.s:
                        return ("arrow", ident)
                return (kind, ident)
        if self.contains(mx, my):
            return ("panel", None)
        return None

    # ------------------------------------------------------------ olaylar

    def move(self, mx, my, now, shift=False):
        self.now = now
        if self.menu.is_open():
            return self.menu.move(mx, my)
        fch = self.forms.move(mx, my, shift)
        if self.forms.drag is not None or (self.forms.contains(mx, my) and
                                           not self._in_box(mx, my)):
            if self.hover is not None:
                self.hover = None
                return True
            return fch
        h = self.hit(mx, my)
        if h and h[0] == "arrow":
            h = ("btn", h[1])
        if h != self.hover:
            if self._tip_visible(now):
                self.tip_last = now
            self.hover = h
            self.hover_t0 = now
            return True
        return False

    def _in_box(self, mx, my):
        x0, y0, x1, y1 = self.box
        return x0 <= mx <= x1 and y0 <= my <= y1

    def release(self, mx, my):
        return self.forms.release(mx, my)

    def key(self, etype, unicode="", ctrl=False, shift=False):
        return self.forms.key(etype, unicode, ctrl, shift)

    def capturing(self):
        return self.forms.capturing()

    def leave(self, now):
        if self.hover is not None:
            if self._tip_visible(now):
                self.tip_last = now
            self.hover = None
            return True
        return False

    def press(self, mx, my, now):
        """Sol tık. Dönüş: True = olay şeritte tüketildi."""
        self.now = now
        if self.menu.is_open():
            return self.menu.press(mx, my)
        if self.fly is None and not self._in_box(mx, my) and (
                self.forms.contains(mx, my) or self.forms.edit is not None or
                self.forms.drop is not None):
            used = self.forms.press(mx, my)
            if used or self.forms.contains(mx, my):
                return True
        elif self.forms.edit is not None:
            self.forms._commit_edit()
        h = self.hit(mx, my)
        if h is None:
            if self.fly is not None:
                self.fly = None
                return True          # açık listeyi kapatan tık görünüme gitmesin
            return False
        kind, ident = h
        self.hover_t0 = now + 10.0   # tıklayınca kart kapanır, fare kıpırdayınca yeniden
        if kind == "tab":
            if self.tab == ident and not self.collapsed:
                pass
            self.tab = ident
            self.collapsed = False
            self.fly = None
            self.scroll = 0.0
        elif kind == "collapse":
            self.collapsed = not self.collapsed
            self.fly = None
        elif kind == "close":
            self._emit("CLOSE", None)
        elif kind == "scroll":
            self.scroll += ident * 120 * self.s
        elif kind == "arrow":
            self.fly = None if self.fly == ident else ident
        elif kind == "btn":
            b = self._btn(ident)
            self.fly = None
            r = self._rect("btn", ident)
            if r is not None:
                self._anchor_x = r[0]
            if b is not None:
                if b["toggle"]:
                    if ident in self.toggles:
                        self.toggles.discard(ident)
                    else:
                        self.toggles.add(ident)
                    self._emit("TOGGLE", b)
                else:
                    cur = self.current(b)
                    self.active = None if self.active == cur["id"] else cur["id"]
                    self._emit("TOOL", cur)
        elif kind == "fly":
            r = self._rect("btn", self.fly)
            if r is not None:
                self._anchor_x = r[0]
            b = self._btn(self.fly)
            if b is not None:
                self.variant[b["id"]] = ident
                cur = self.current(b)
                self.active = cur["id"]
                self._emit("TOOL", cur)
            self.fly = None
        elif kind == "logo":
            self.collapsed = not self.collapsed
        return True

    def wheel(self, mx, my, direction):
        if not self._in_box(mx, my) and self.forms.wheel(mx, my, direction):
            return True
        if not self.contains(mx, my):
            return False
        if self.scroll_max > 0:
            self.scroll += direction * 60 * self.s
        else:
            # sekmeler arasında gez
            ids = [t[0] for t in data.TABS]
            i = ids.index(self.tab)
            self.tab = ids[(i + direction) % len(ids)]
            self.fly = None
        return True

    def escape(self):
        if self.menu.is_open():
            self.menu.close()
            return True
        if self.forms.key("ESC"):
            return True
        if self.fly is not None:
            self.fly = None
            return True
        return False

    def tick(self, now):
        """Zamanlayıcı: kart görünmeye / genişlemeye başlarken yeniden çiz."""
        self.now = now
        if self.toast and now - self.toast[1] > TOAST_TIME:
            self.toast = None
            return True
        if self.hover and self.hover[0] in ("btn", "fly"):
            age = now - self.hover_t0
            d = self._delay(now)
            if d - 0.06 <= age <= TIP_EXPAND + TIP_FADE + 0.1:
                return True
        return self.toast is not None

    def _emit(self, kind, btn):
        msg = None
        if self.on_action:
            try:
                msg = self.on_action(kind, btn)
            except Exception as e:          # arayüz çökmesin; hatayı bildir
                msg = f"Hata: {e}"
        if kind in ("TOOL", "TOGGLE"):
            if btn["status"] == data.PLANNED:
                msg = f"“{btn['title']}” yeni özellik olarak planlandı (yakında)"
            elif msg is None and self.on_action is None:
                msg = f"“{btn['title']}” seçildi"
        if msg:
            self.toast = (msg, self.now)
            if self.notify is not None:       # v0.30.0: bildirim merkezi (sol alt)
                self.notify(msg)

    # ------------------------------------------------------------ kart

    def _tip_visible(self, now):
        if not self.hover or self.hover[0] not in ("btn", "fly"):
            return False
        return now - self.hover_t0 >= self._delay(now)

    def _delay(self, now):
        return 0.0 if (self.hover_t0 - self.tip_last) < TIP_WARM else TIP_DELAY

    def tip_target(self):
        if not self.hover:
            return None, None
        kind, ident = self.hover
        if kind == "btn":
            b = self._btn(ident)
            if b is None:
                return None, None
            return self.current(b), b
        if kind == "fly":
            b = self._btn(self.fly) if self.fly else None
            return data.find(ident), b
        return None, None

    # ------------------------------------------------------------ çizim

    def draw(self, p, region_w, region_h, left=0.0, right=0.0, now=None, top_reserve=0.0):
        if now is not None:
            self.now = now
        now = self.now
        self.layout(p, region_w, region_h, left, right, top_reserve)
        s = self.s
        x0, y0, x1, y1 = self.box
        R = 6 * s
        TH = 24 * s
        p.rect(x0 + 2 * s, y0 - 3 * s, x1 + 2 * s, y1 - 3 * s, COL_SHADOW, R)
        p.rect(x0, y0, x1, y1, COL_BG, R)
        p.rect(x0, y1 - TH, x1, y1, COL_TABBAR, R)
        if not self.collapsed:
            p.rect(x0, y1 - TH - R, x1, y1 - TH, COL_BG, 0)   # sekme şeridinin alt köşeleri düz
        p.outline(x0, y0, x1, y1, COL_BORDER, R, 1.0)

        for bx0, by0, bx1, by1, kind, ident in self.items:
            hov = self.hover == (kind, ident)
            if kind == "logo":
                cy = (by0 + by1) / 2
                _icon(p, "LOGO", bx0 + 8 * s, cy, 15 * s, COL_LOGO, 1.4)
                p.text(bx0 + 20 * s, cy - 4 * s, "BlendCAD", COL_TEXT, int(12 * s), bold=True)
            elif kind == "tab":
                on = self.tab == ident
                lbl = next(t[1] for t in data.TABS if t[0] == ident)
                if hov and not on:
                    p.rect(bx0, by0 + 3 * s, bx1, by1 - 3 * s, COL_HOVER, 4 * s)
                col = COL_TEXT if on else (COL_TEXT if hov else COL_TEXT_DIM)
                tw = p.measure(lbl, int(11 * s))[0]
                p.text((bx0 + bx1) / 2 - tw / 2, by0 + 8 * s, lbl, col, int(11 * s), bold=on)
                if on and not self.collapsed:
                    p.rect(bx0 + 6 * s, by0 + 1 * s, bx1 - 6 * s, by0 + 3 * s, COL_ACCENT, 1 * s)
            elif kind in ("close", "collapse"):
                if hov:
                    p.rect(bx0, by0, bx1, by1, COL_HOVER, 4 * s)
                name = "CLOSE" if kind == "close" else ("EXPAND" if self.collapsed else "COLLAPSE")
                _icon(p, name, (bx0 + bx1) / 2, (by0 + by1) / 2, 11 * s,
                      COL_TEXT if hov else COL_TEXT_DIM, 1.4)
            elif kind == "sep":
                p.rect(bx0, by0, bx1, by1, COL_SEP, 0)
            elif kind == "glabel":
                tw = p.measure(ident, int(9 * s))[0]
                p.text((bx0 + bx1) / 2 - tw / 2, by0 + 3 * s, ident, COL_TEXT_DIM, int(9 * s))
            elif kind == "scroll":
                if hov:
                    p.rect(bx0, by0, bx1, by1, COL_HOVER, 3 * s)
                _icon(p, "CHEV_L" if ident < 0 else "CHEV_R", (bx0 + bx1) / 2, (by0 + by1) / 2,
                      12 * s, COL_TEXT, 1.6)
            elif kind == "btn":
                self._draw_btn(p, ident, bx0, by0, bx1, by1, hov)

        if self.forms.form is not None:
            self.forms.s = s
            self.forms.draw(p, y0 - 6 * s, region_w, region_h)
        if self.fly is not None:
            self._draw_fly(p)
        tip = self._draw_tip(p, now, region_w) if not self.menu.is_open() else False
        if not tip and self.fly is None and self.notify is None:
            self._draw_toast(p, now, region_w)
        if self.menu.is_open():
            self.menu.s = s
            self.menu.draw(p, region_w, region_h)

    def _draw_btn(self, p, ident, x0, y0, x1, y1, hov):
        s = self.s
        b = self._btn(ident)
        if b is None:
            return
        cur = self.current(b)
        on = self.is_on(b)
        R = 5 * s
        if self._small(b):
            if on:
                p.rect(x0, y0, x1, y1, COL_TOGGLE, 3 * s)
                p.outline(x0, y0, x1, y1, COL_ACCENT, 3 * s, 1.0)
            elif hov:
                p.rect(x0, y0, x1, y1, COL_HOVER, 3 * s)
            cy = (y0 + y1) / 2
            _icon(p, cur["icon"], x0 + 9 * s, cy, 12 * s, COL_ICON if on else COL_ICON_DIM, 1.3)
            p.text(x0 + 19 * s, cy - 3 * s, b["short"], COL_TEXT if (on or hov) else COL_TEXT_DIM,
                   int(9 * s))
            return
        if on:
            p.rect(x0, y0, x1, y1, COL_TOGGLE if b["toggle"] else COL_ACTIVE, R)
            if b["toggle"]:
                p.outline(x0, y0, x1, y1, COL_ACCENT, R, 1.0)
        elif self.fly == ident:
            p.rect(x0, y0, x1, y1, COL_PRESS, R)
        elif hov:
            p.rect(x0, y0, x1, y1, COL_HOVER, R)
        planned = cur["status"] == data.PLANNED
        col = COL_ICON if (on or not planned) else COL_ICON_DIM
        _icon(p, cur["icon"], (x0 + x1) / 2, (y0 + y1) / 2 + (1 * s if b["variants"] else 0),
              (x1 - x0) * 0.58, col, 1.5)
        if b["variants"]:
            # sağ alt köşede açılır liste üçgeni
            ax, ay = x1 - 4 * s, y0 + 4 * s
            p.tri([(ax - 6 * s, ay), (ax, ay), (ax, ay + 6 * s)],
                  COL_TEXT if (hov or self.fly == ident) else COL_TEXT_DIM)
        if planned:
            p.circle(x1 - 5 * s, y1 - 5 * s, 2.6 * s, COL_PLANNED)

    def _draw_fly(self, p):
        s = self.s
        b = self._btn(self.fly)
        if b is None or not self.fly_box:
            return
        fx0, fy0, fx1, fy1 = self.fly_box
        p.rect(fx0 + 2 * s, fy0 - 3 * s, fx1 + 2 * s, fy1 - 3 * s, COL_SHADOW, 6 * s)
        p.rect(fx0, fy0, fx1, fy1, COL_CARD, 6 * s)
        p.outline(fx0, fy0, fx1, fy1, COL_BORDER, 6 * s, 1.0)
        cur = self.current(b)
        for x0, y0, x1, y1, _k, vid in self.fly_items:
            v = data.find(vid)
            hov = self.hover == ("fly", vid)
            if v["id"] == cur["id"]:
                p.rect(x0, y0 + 1 * s, x1, y1 - 1 * s, COL_TOGGLE, 4 * s)
            if hov:
                p.rect(x0, y0 + 1 * s, x1, y1 - 1 * s, COL_HOVER, 4 * s)
            cy = (y0 + y1) / 2
            _icon(p, v["icon"], x0 + 18 * s, cy, 20 * s, COL_ICON, 1.4)
            p.text(x0 + 36 * s, cy + 2 * s, v["title"], COL_TEXT, int(11 * s), bold=True)
            p.text(x0 + 36 * s, cy - 11 * s, _clip(p, v["desc"], int(9 * s), x1 - x0 - 44 * s),
                   COL_TEXT_DIM, int(9 * s))
            if v["key"]:
                kw = p.measure(v["key"], int(9 * s))[0]
                p.text(x1 - kw - 8 * s, cy + 2 * s, v["key"], COL_TEXT_DIM, int(9 * s))
            if v["status"] == data.PLANNED:
                p.circle(x1 - 8 * s, cy - 7 * s, 2.6 * s, COL_PLANNED)

    def _draw_tip(self, p, now, region_w):
        item, btn = self.tip_target()
        if item is None:
            return False
        delay = self._delay(now)
        age = now - self.hover_t0 - delay
        if age < 0:
            return False
        self.tip_last = now
        expanded = age >= (TIP_EXPAND - TIP_DELAY)
        fade = min(1.0, age / TIP_FADE) if TIP_FADE > 0 else 1.0
        s = self.s
        if self.hover[0] == "fly":
            r = next((it[:4] for it in self.fly_items if it[5] == self.hover[1]), None)
            if r is None:
                return False
            ax, ay = self.fly_box[2] + 6 * s, r[1]
            anchor_top = r[3]
        else:
            r = self._rect("btn", self.hover[1])
            if r is None:
                return False
            ax = r[0]
            anchor_top = self.box[1] - 6 * s
        W = 300 * s
        PAD = 10 * s
        IC = 46 * s
        tsz, dsz, ssz = int(13 * s), int(11 * s), int(10 * s)
        desc = wrap(item["desc"], dsz, W - 2 * PAD - IC - 10 * s, p.measure)
        steps = []
        if expanded:
            src = item["steps"] or (btn["steps"] if btn is not None else [])
            for i, st in enumerate(src):
                ln = wrap(st, ssz, W - 2 * PAD - 18 * s, p.measure)
                steps.append((i + 1, ln))
        var = btn["variants"] if (btn and btn["variants"] and self.hover[0] == "btn") else []

        h = PAD + max(IC, 18 * s + len(desc) * 15 * s + 4 * s) + PAD
        if expanded and steps:
            h += 22 * s + sum(len(ln) * 14 * s + 3 * s for _n, ln in steps) + 6 * s
        if expanded and var:
            h += 24 * s
        h += 22 * s                         # alt bilgi (durum)
        slide = (1.0 - fade) * 6 * s
        x0 = min(max(ax, 4 * s), region_w - W - 4 * s)
        y1 = anchor_top + slide
        y0 = y1 - h
        a = fade
        p.rect(x0 + 2 * s, y0 - 3 * s, x0 + W + 2 * s, y1 - 3 * s, _mix(COL_SHADOW, a), 7 * s)
        p.rect(x0, y0, x0 + W, y1, _mix(COL_CARD, a), 7 * s)
        p.outline(x0, y0, x0 + W, y1, _mix(COL_BORDER, a), 7 * s, 1.0)
        # üstte küçük ok (karta bağlantı)
        if self.hover[0] == "btn":
            cx = min(max((r[0] + r[2]) / 2, x0 + 12 * s), x0 + W - 12 * s)
            p.tri([(cx - 6 * s, y1), (cx + 6 * s, y1), (cx, y1 + 6 * s)], _mix(COL_CARD, a))

        # simge kutusu
        iy1 = y1 - PAD
        p.rect(x0 + PAD, iy1 - IC, x0 + PAD + IC, iy1, _mix(COL_CARD_ICON, a), 6 * s)
        _icon(p, item["icon"], x0 + PAD + IC / 2, iy1 - IC / 2, IC * 0.62, _mix(COL_ICON, a), 1.8)
        tx = x0 + PAD + IC + 10 * s
        title = item["title"]
        if btn is not None and item is not btn and btn["title"] != title:
            title = btn["title"] + " · " + title
        p.text(tx, iy1 - 13 * s, _clip(p, title, tsz, W - PAD - (tx - x0) - 40 * s), _mix(COL_TEXT, a), tsz, bold=True)
        if item["key"]:
            kw = p.measure(item["key"], int(9 * s))[0]
            kx1 = x0 + W - PAD
            p.rect(kx1 - kw - 10 * s, iy1 - 17 * s, kx1, iy1 - 1 * s, _mix(COL_KEY, a), 3 * s)
            p.text(kx1 - kw - 5 * s, iy1 - 12 * s, item["key"], _mix(COL_TEXT, a), int(9 * s))
        y = iy1 - 18 * s
        for ln in desc:
            y -= 15 * s
            p.text(tx, y + 3 * s, ln, _mix((0.80, 0.80, 0.84, 1.0), a), dsz)
        y = min(y - 4 * s, iy1 - IC) - PAD

        if expanded and steps:
            p.rect(x0 + PAD, y - 1, x0 + W - PAD, y, _mix(COL_SEP, a), 0)
            y -= 16 * s
            p.text(x0 + PAD, y, "NASIL KULLANILIR", _mix(COL_ACCENT, a), int(9 * s), bold=True)
            y -= 6 * s
            for n, ln in steps:
                for j, t in enumerate(ln):
                    y -= 14 * s
                    if j == 0:
                        p.circle(x0 + PAD + 6 * s, y + 4 * s, 6 * s, _mix(COL_KEY, a))
                        nw = p.measure(str(n), int(8 * s))[0]
                        p.text(x0 + PAD + 6 * s - nw / 2, y + 1 * s, str(n), _mix(COL_TEXT, a),
                               int(8 * s))
                    p.text(x0 + PAD + 18 * s, y, t, _mix((0.78, 0.78, 0.82, 1.0), a), ssz)
                y -= 3 * s
        if expanded and var:
            y -= 16 * s
            names = " · ".join(v["title"] for v in var)
            p.text(x0 + PAD, y, _clip(p, "Türler: " + names, int(9 * s), W - 2 * PAD),
                   _mix(COL_TEXT_DIM, a), int(9 * s))
            y -= 4 * s

        # alt bilgi
        fy = y0 + 8 * s
        p.rect(x0 + PAD, fy + 14 * s, x0 + W - PAD, fy + 14 * s + 1, _mix(COL_SEP, a), 0)
        planned = item["status"] == data.PLANNED
        p.circle(x0 + PAD + 4 * s, fy + 4 * s, 3.2 * s, _mix(COL_PLANNED if planned else COL_READY, a))
        st = "Yakında · yeni özellik" if planned else "Hazır"
        p.text(x0 + PAD + 12 * s, fy, st, _mix(COL_TEXT_DIM, a), int(9 * s))
        hint = "▾ türler" if var else ("" if expanded or not item["steps"] else "bekleyin: ayrıntı")
        if hint:
            hw = p.measure(hint, int(9 * s))[0]
            p.text(x0 + W - PAD - hw, fy, hint, _mix(COL_TEXT_DIM, a), int(9 * s))
        return True

    def _draw_toast(self, p, now, region_w):
        if not self.toast:
            return
        msg, t0 = self.toast
        age = now - t0
        if age > TOAST_TIME:
            return
        a = min(1.0, (TOAST_TIME - age) / 0.3)
        s = self.s
        sz = int(10 * s)
        tw = p.measure(msg, sz)[0]
        x0, y0, x1, y1 = self.box
        bx0 = x0
        by1 = y0 - 8 * s
        p.rect(bx0, by1 - 22 * s, bx0 + tw + 20 * s, by1, _mix(COL_CARD, a), 11 * s)
        p.outline(bx0, by1 - 22 * s, bx0 + tw + 20 * s, by1, _mix(COL_BORDER, a), 11 * s, 1.0)
        p.text(bx0 + 10 * s, by1 - 15 * s, msg, _mix(COL_TEXT, a), sz)


def _clip(p, text, size, maxw):
    if p.measure(text, size)[0] <= maxw:
        return text
    while text and p.measure(text + "…", size)[0] > maxw:
        text = text[:-1]
    return text + "…"
