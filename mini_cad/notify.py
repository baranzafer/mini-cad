"""BlendCAD bildirim merkezi (v0.30.0): bütün hata / uyarı / bilgi / öneri iletileri tek yerde.

Görünümün SOL ALT köşesinde (araç çubuğunun sağında, alttaki bölgelerin üstünde), önem
derecesine göre gruplanmış renkli yazılar. Her ileti 45 sn kalır; köşedeki çarpı hepsini
kapatır. Başka yerde (sol üst kırmızı liste, şerit altı bildirim) ileti balonu çıkmaz.

İki tür ileti:
  push(level, text)           anlık ileti (araç sonucu, geçersiz değer, planlanan özellik ...)
  sync(source, [(level, text)]) süren durum (gövdede başarısız yüzey / işlem): kaynak başına
                              liste; durum düzelince ileti hemen kalkar, değişince yenilenir.

bpy / gpu kullanmaz; çizim şeritle aynı ressamla (painter) yapılır.
"""

from .ribbon import (COL_BORDER, COL_CARD, COL_HOVER, COL_PLANNED, COL_READY, COL_SHADOW,
                     COL_TEXT, COL_TEXT_DIM, _icon, wrap)

LIFETIME = 45.0
COL_ERR = (1.0, 0.42, 0.38, 1.0)
COL_INFO = (0.55, 0.72, 1.0, 1.0)
LEVELS = (("error", "Hatalar", COL_ERR), ("warn", "Uyarılar", COL_PLANNED),
          ("info", "Bilgi", COL_INFO), ("hint", "Öneriler", COL_READY))
MAX_PER_GROUP = 4


def level_of(text):
    """Serbest metinden önem derecesi (araç iletileri için)."""
    t = (text or "").lower()
    if t.startswith(("hata", "error")) or "başarısız" in t or "yapılamadı" in t or \
            "oluşturulamadı" in t or "uygulanamadı" in t or "hesaplanamadı" in t:
        return "error"
    if t.startswith(("geçersiz", "uyarı", "önce ")) or "yazılamadı" in t or \
            "açık değil" in t or "kapalı:" in t:
        return "warn"
    if "planlandı" in t or "yakında" in t or t.startswith(("ipucu", "öneri")):
        return "hint"
    return "info"


class Center:
    def __init__(self):
        self.items = []            # {"level", "text", "t0", "src"}
        self.state = {}            # kaynak -> [(level, text)]
        self.dismissed = {}        # kaynak -> kapatıldığındaki liste (değişmedikçe gizli)
        self.box = None
        self.close_rect = None
        self.hover_close = False

    # -------------------------------------------------- iletiler
    def push(self, level, text, now):
        if not text:
            return
        if level not in dict((k, 1) for k, _n, _c in LEVELS):
            level = level_of(text)
        for it in self.items:
            if it["src"] is None and it["text"] == text:
                it["t0"] = now                # aynı ileti: süre yenilenir, çoğalmaz
                it["level"] = level
                return
        self.items.append({"level": level, "text": text, "t0": now, "src": None})

    def sync(self, src, entries, now):
        """Süren durum iletileri: değişmedikçe zamanı ilerlemez, kalkınca silinir."""
        entries = [(lv, tx) for lv, tx in entries if tx]
        if self.dismissed.get(src) is not None and self.dismissed[src] != entries:
            self.dismissed.pop(src, None)     # durum değişti: yeniden göster
        old = self.state.get(src, [])
        if entries == old:
            return
        self.state[src] = entries
        keep = {(it["level"], it["text"]): it for it in self.items if it["src"] == src}
        self.items = [it for it in self.items if it["src"] != src]
        for lv, tx in entries:
            it = keep.get((lv, tx)) or {"level": lv, "text": tx, "t0": now, "src": src}
            self.items.append(it)

    def expire(self, now):
        n = len(self.items)
        self.items = [it for it in self.items if now - it["t0"] < LIFETIME]
        return len(self.items) != n

    def close(self):
        """Çarpı: hepsini kapat. Süren durumlar değişene kadar yeniden çıkmaz."""
        for src, entries in self.state.items():
            self.dismissed[src] = entries
        self.items = []
        self.box = self.close_rect = None

    def visible(self):
        return [it for it in self.items
                if it["src"] is None or self.dismissed.get(it["src"]) != self.state.get(it["src"])]

    # -------------------------------------------------- isabet
    def contains(self, mx, my):
        b = self.box
        return b is not None and b[0] <= mx <= b[2] and b[1] <= my <= b[3]

    def hit_close(self, mx, my):
        r = self.close_rect
        return r is not None and r[0] <= mx <= r[2] and r[1] <= my <= r[3]

    def move(self, mx, my):
        h = self.hit_close(mx, my)
        ch = h != self.hover_close
        self.hover_close = h
        return ch

    def press(self, mx, my):
        if self.hit_close(mx, my):
            self.close()
            return True
        return self.contains(mx, my)

    # -------------------------------------------------- çizim
    def draw(self, p, s, left, bottom, max_w=420, now=0.0):
        vis = self.visible()
        if not vis:
            self.box = self.close_rect = None
            return
        W = max_w * s
        PAD = 10 * s
        LH = 15 * s
        tsz = int(10 * s)
        rows = []                              # (tür, metin, renk)
        for lv, name, col in LEVELS:
            its = [it for it in vis if it["level"] == lv]
            if not its:
                continue
            rows.append(("head", f"{name} ({len(its)})", col))
            its.sort(key=lambda it: -it["t0"])
            for it in its[:MAX_PER_GROUP]:
                lines = wrap(it["text"], tsz, W - 2 * PAD - 14 * s, p.measure) or [""]
                for k, ln in enumerate(lines[:3]):
                    rows.append(("line" if k == 0 else "cont", ln, col))
            if len(its) > MAX_PER_GROUP:
                rows.append(("more", f"… {len(its) - MAX_PER_GROUP} ileti daha", COL_TEXT_DIM))
        h = PAD * 2 + sum(18 * s if r[0] == "head" else LH for r in rows) + 4 * s
        x0, y0 = left, bottom
        x1, y1 = x0 + W, y0 + h
        self.box = (x0, y0, x1, y1)
        p.rect(x0 + 2 * s, y0 - 3 * s, x1 + 2 * s, y1 - 3 * s, COL_SHADOW, 7 * s)
        p.rect(x0, y0, x1, y1, COL_CARD, 7 * s)
        p.outline(x0, y0, x1, y1, COL_BORDER, 7 * s, 1.0)
        cr = (x1 - 24 * s, y1 - 22 * s, x1 - 6 * s, y1 - 4 * s)
        self.close_rect = cr
        if self.hover_close:
            p.rect(*cr, COL_HOVER, 4 * s)
        _icon(p, "CLOSE", (cr[0] + cr[2]) / 2, (cr[1] + cr[3]) / 2, 9 * s,
              COL_TEXT if self.hover_close else COL_TEXT_DIM, 1.4)
        y = y1 - PAD
        for kind, txt, col in rows:
            if kind == "head":
                y -= 18 * s
                p.circle(x0 + PAD + 4 * s, y + 4 * s, 4 * s, col)
                p.text(x0 + PAD + 14 * s, y, txt.upper(), col, int(9 * s), bold=True)
            else:
                y -= LH
                tc = col if kind != "more" else COL_TEXT_DIM
                p.text(x0 + PAD + 14 * s, y + 2 * s, txt,
                       tc if kind == "line" else (tc[0], tc[1], tc[2], 0.8), tsz)


CENTER = Center()
