"""BlendCAD sağ tık menüsü (v0.30.0): üzerine gelinen öğeye göre değişen mini menü.

İmlecin sağına açılır (sığmazsa soluna). Öğeler: simge, ad, kısayol, açık / seçili işareti,
ayraç ve başlık. Şeritle aynı ressam ve renkler; bpy / gpu kullanmaz.

Öğe: {"id", "text", "icon", "key", "fn", "enabled", "check"} ya da {"sep": True} /
{"head": "metin"}. fn() menü kapandıktan sonra çağrılır.
"""

from .ribbon import (COL_ACCENT, COL_BORDER, COL_CARD, COL_HOVER, COL_ICON, COL_ICON_DIM,
                     COL_SEP, COL_SHADOW, COL_TEXT, COL_TEXT_DIM, _clip, _icon)


class ContextMenu:
    def __init__(self, scale=1.0):
        self.s = scale
        self.items = []
        self.title = ""
        self.icon = None
        self.rows = []             # (rect, öğe)
        self.box = None
        self.hover = None
        self.at = None             # (x, y) açıldığı nokta (bölge pikseli)

    def is_open(self):
        return self.box is not None or self.at is not None

    def open(self, title, items, x, y, icon=None):
        self.title, self.items, self.icon = title, list(items), icon
        self.at = (x, y)
        self.box, self.rows, self.hover = None, [], None

    def close(self):
        self.at = self.box = None
        self.rows, self.items, self.hover = [], [], None

    def layout(self, p, region_w, region_h):
        if self.at is None:
            return
        s = self.s
        W = 210 * s
        for it in self.items:
            if it.get("text"):
                W = max(W, p.measure(it["text"], int(10 * s))[0] +
                        (p.measure(it.get("key") or "", int(8 * s))[0] if it.get("key") else 0)
                        + 70 * s)
        W = min(W, 320 * s)
        RH, SH, HH = 22 * s, 7 * s, 24 * s
        h = HH + sum(SH if it.get("sep") else (18 * s if it.get("head") else RH)
                     for it in self.items) + 6 * s
        x, y = self.at
        x0 = x + 10 * s
        if x0 + W > region_w - 4 * s:
            x0 = max(4 * s, x - 10 * s - W)          # sığmıyorsa imlecin soluna
        y1 = min(y + HH * 0.5, region_h - 4 * s)
        if y1 - h < 4 * s:
            y1 = min(region_h - 4 * s, h + 4 * s)
        self.box = (x0, y1 - h, x0 + W, y1)
        rows = []
        yy = y1 - HH
        for it in self.items:
            hh = SH if it.get("sep") else (18 * s if it.get("head") else RH)
            rows.append(((x0 + 4 * s, yy - hh, x0 + W - 4 * s, yy), it))
            yy -= hh
        self.rows = rows

    def contains(self, mx, my):
        b = self.box
        return b is not None and b[0] <= mx <= b[2] and b[1] <= my <= b[3]

    def _hit(self, mx, my):
        for r, it in self.rows:
            if r[0] <= mx <= r[2] and r[1] <= my <= r[3] and it.get("fn") and \
                    it.get("enabled", True):
                return it
        return None

    def move(self, mx, my):
        if self.box is None:
            return False
        it = self._hit(mx, my)
        h = it["id"] if it else None
        ch = h != self.hover
        self.hover = h
        return ch

    def press(self, mx, my):
        """Sol / sağ tık. Öğe seçildiyse fn çalışır. Dışarı tık menüyü kapatır. True: tüketildi."""
        if not self.is_open():
            return False
        it = self._hit(mx, my) if self.box is not None else None
        inside = self.contains(mx, my)
        self.close()
        if it is not None:
            it["fn"]()
            return True
        return inside or True                       # dışarı tık yalnız menüyü kapatır

    def draw(self, p, region_w, region_h):
        if self.at is None:
            return
        self.layout(p, region_w, region_h)
        s = self.s
        x0, y0, x1, y1 = self.box
        p.rect(x0 + 2 * s, y0 - 3 * s, x1 + 2 * s, y1 - 3 * s, COL_SHADOW, 6 * s)
        p.rect(x0, y0, x1, y1, COL_CARD, 6 * s)
        p.outline(x0, y0, x1, y1, COL_BORDER, 6 * s, 1.0)
        ty = y1 - 16 * s
        tx = x0 + 10 * s
        if self.icon:
            _icon(p, self.icon, tx + 6 * s, ty + 4 * s, 12 * s, COL_ACCENT, 1.4)
            tx += 18 * s
        p.text(tx, ty, _clip(p, self.title, int(10 * s), x1 - tx - 8 * s), COL_ACCENT,
               int(10 * s), bold=True)
        for r, it in self.rows:
            rx0, ry0, rx1, ry1 = r
            if it.get("sep"):
                p.rect(rx0 + 4 * s, (ry0 + ry1) / 2, rx1 - 4 * s, (ry0 + ry1) / 2 + 1, COL_SEP, 0)
                continue
            if it.get("head"):
                p.text(rx0 + 6 * s, ry0 + 5 * s, it["head"].upper(), COL_TEXT_DIM, int(8 * s),
                       bold=True)
                continue
            en = it.get("enabled", True)
            if self.hover == it["id"] and en:
                p.rect(rx0, ry0, rx1, ry1, COL_HOVER, 4 * s)
            cy = (ry0 + ry1) / 2
            if it.get("check"):
                p.lines([(rx0 + 7 * s, cy), (rx0 + 10 * s, cy - 4 * s),
                         (rx0 + 10 * s, cy - 4 * s), (rx0 + 15 * s, cy + 4 * s)], COL_ACCENT, 1.6)
            elif it.get("icon"):
                _icon(p, it["icon"], rx0 + 11 * s, cy, 13 * s, COL_ICON if en else COL_ICON_DIM,
                      1.3)
            col = COL_TEXT if en else COL_TEXT_DIM
            p.text(rx0 + 24 * s, cy - 4 * s, _clip(p, it["text"], int(10 * s),
                                                    rx1 - rx0 - 70 * s), col, int(10 * s))
            if it.get("key"):
                kw = p.measure(it["key"], int(8 * s))[0]
                p.text(rx1 - kw - 8 * s, cy - 3 * s, it["key"], COL_TEXT_DIM, int(8 * s))
