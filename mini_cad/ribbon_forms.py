"""BlendCAD araç pencereleri (Inventor'daki gibi şeridin altına açılan ayar kartları).

Eski N paneli parçalarının yerini alır: sayı alanı (sürükle / tıkla-yaz / oklarla adım), aç /
kapa, bölmeli seçim, açılır liste (enum / obje), düğme, satır listesi, bölüm başlığı, bilgi
yazısı. Hepsi şeritle aynı ressamla (painter) ve aynı renklerle çizilir.

"Anlık" (immediate-mode) yapı: pencerenin içeriği her çizimde ve her olaydan önce spec(ui, ctx)
çağrılarak yeniden kurulur; böylece Blender'daki veri (geri alma sonrası bile) her zaman taze
okunur, eski referans tutulmaz.

bpy / gpu kullanmaz. Özellik bilgisi (tür, aralık, enum öğeleri) meta_fn ile, değer yazımı
ve okunması fmt_fn / parse_fn ile dışarıdan verilir (Blender'da RNA + birim sistemi).
"""

import math

from .ribbon import (COL_ACCENT, COL_ACTIVE, COL_BORDER, COL_CARD, COL_CARD_ICON, COL_HOVER,
                     COL_ICON, COL_ICON_DIM, COL_KEY, COL_PLANNED, COL_READY, COL_SEP, COL_SHADOW,
                     COL_TEXT, COL_TEXT_DIM, COL_TOGGLE, _clip, _icon, wrap)

COL_FIELD = (0.20, 0.20, 0.22, 1.0)
COL_FIELD_HOV = (0.25, 0.25, 0.28, 1.0)
COL_LIST = (0.11, 0.11, 0.12, 1.0)
COL_ERR = (0.95, 0.40, 0.36, 1.0)
COL_INFO = (0.55, 0.70, 0.95, 1.0)
TONES = {"": COL_TEXT, "dim": COL_TEXT_DIM, "ok": COL_READY, "err": COL_ERR,
         "warn": COL_PLANNED, "info": COL_INFO}


class Meta:
    """Bir değerin türü ve sınırları (Blender'da RNA'dan okunur)."""

    def __init__(self, type="FLOAT", name="", desc="", items=(), min=-1e12, max=1e12,
                 soft_min=None, soft_max=None, step=1.0, precision=3, unit="NONE"):
        self.type, self.name, self.desc = type, name, desc
        self.items = list(items)                    # [(kimlik, ad, açıklama)]
        self.min, self.max = min, max
        self.soft_min = min if soft_min is None else soft_min
        self.soft_max = max if soft_max is None else soft_max
        self.step, self.precision, self.unit = step, precision, unit

    @classmethod
    def int(cls, lo, hi, name=""):
        return cls("INT", name, min=lo, max=hi)

    @classmethod
    def bool(cls, name="", desc=""):
        return cls("BOOLEAN", name, desc)

    @classmethod
    def enum(cls, items, name=""):
        return cls("ENUM", name, items=items)


def default_fmt(meta, v):
    if meta.type == "INT":
        return str(int(v))
    if meta.unit == "ROTATION":
        return f"{math.degrees(v):.1f}°"
    p = max(0, min(6, int(meta.precision if meta.precision is not None else 3)))
    t = f"{v:.{p}f}"
    if "." in t:
        t = t.rstrip("0").rstrip(".")
    return t if t not in ("-0", "") else "0"


def default_parse(meta, text):
    t = text.strip().replace(",", ".").replace("°", "")
    v = float(eval(t, {"__builtins__": {}}, {})) if any(c in t for c in "+-*/") and \
        not t.lstrip("-").replace(".", "").isdigit() else float(t)
    if meta.type == "INT":
        return int(round(v))
    if meta.unit == "ROTATION":
        return math.radians(v)
    return v


def _nice(x):
    if x <= 0:
        return 0.01
    e = math.floor(math.log10(x))
    f = x / 10 ** e
    return (1 if f < 1.5 else 2 if f < 3.5 else 5 if f < 7.5 else 10) * 10 ** e


# ---------------------------------------------------------------- kurucu (spec'lerin gördüğü)

class _Row:
    def __init__(self, ui, weights):
        self.ui, self.weights, self.items = ui, weights, []

    def __enter__(self):
        self.ui._rows.append(self)
        return self

    def __exit__(self, *a):
        self.ui._rows.pop()
        self.ui._flush_row(self)
        return False


class UI:
    """spec(ui, ctx) içinde kullanılan yerleşim kurucusu."""

    def __init__(self, host, x0, x1, ytop, s):
        self.host, self.s = host, s
        self.x0, self.x1, self.y = x0, x1, ytop
        self.els = []
        self._rows = []
        self._enabled = [True]
        self._ids = {}

    # -------------------------------------------------- iç işler
    def _uid(self, base):
        n = self._ids.get(base, 0)
        self._ids[base] = n + 1
        return f"{base}#{n}" if n else base

    def _add(self, el, h, weight=1.0):
        el.setdefault("enabled", True)
        el["enabled"] = el["enabled"] and all(self._enabled)
        if self._rows:
            self._rows[-1].items.append((el, h, weight))
            return el
        s = self.s
        el["rect"] = (self.x0, self.y - h, self.x1, self.y)
        self.y -= h + 4 * s
        self.els.append(el)
        return el

    def _flush_row(self, row):
        if not row.items:
            return
        s = self.s
        gap = 3 * s
        ws = row.weights or [w for _e, _h, w in row.items]
        if len(ws) < len(row.items):
            ws = list(ws) + [1.0] * (len(row.items) - len(ws))
        tot = sum(ws[:len(row.items)]) or 1.0
        h = max(hh for _e, hh, _w in row.items)
        avail = (self.x1 - self.x0) - gap * (len(row.items) - 1)
        x = self.x0
        outer = self._rows[-1] if self._rows else None
        built = []
        for (el, hh, _w), w in zip(row.items, ws):
            ww = avail * w / tot
            el["rect"] = (x, self.y - h, x + ww, self.y)
            x += ww + gap
            built.append(el)
        if outer is not None:                     # iç içe satır: dış satıra tek parça
            grp = {"kind": "group", "children": built, "rect": None}
            outer.items.append((grp, h, sum(ws)))
            return
        self.els.extend(built)
        self.y -= h + 4 * s

    # -------------------------------------------------- öğeler
    def row(self, *weights):
        return _Row(self, list(weights))

    class _Enabled:
        def __init__(self, ui, on):
            self.ui, self.on = ui, on

        def __enter__(self):
            self.ui._enabled.append(bool(self.on))

        def __exit__(self, *a):
            self.ui._enabled.pop()
            return False

    def enabled(self, on):
        return UI._Enabled(self, on)

    def section(self, text):
        s = self.s
        self.y -= 4 * s
        self._add({"kind": "section", "text": text, "id": self._uid("sec:" + text)}, 16 * s)

    def label(self, text, tone="", icon=None, wrap_lines=True, weight=1.0):
        s = self.s
        lines = wrap(text, int(10 * s), self.x1 - self.x0 - (16 * s if icon or tone else 0),
                     self.host.measure) if (wrap_lines and not self._rows) else [text]
        for i, ln in enumerate(lines or [""]):
            self._add({"kind": "label", "text": ln, "tone": tone, "icon": icon if i == 0 else None,
                       "dot": bool(tone) and tone != "dim" and i == 0 and not icon and
                       not self._rows, "id": None}, 15 * s if not self._rows else 20 * s, weight)

    def sep(self):
        s = self.s
        self._add({"kind": "sep", "id": None}, 3 * s)

    def button(self, text, fn, icon=None, primary=False, enabled=True, depress=False, tip="",
               weight=1.0, key=""):
        s = self.s
        return self._add({"kind": "button", "text": text, "fn": fn, "icon": icon,
                          "primary": primary, "enabled": enabled, "depress": depress,
                          "tip": tip, "key": key, "id": self._uid("btn:" + text + (icon or ""))},
                         24 * s, weight)

    def prop(self, owner, name, text=None, meta=None, style=None, enabled=True, choices=None,
             icon=None, weight=1.0, on_change=None):
        """Özellik alanı. style: field / check / toggle / seg / drop / object (boşsa türden)."""
        s = self.s
        if meta is None:
            meta = self.host.meta(owner, name)
        if meta is None:
            return self.label(f"({name}?)", "err")
        lbl = meta.name if text is None else text
        st = style
        if st is None:
            st = {"BOOLEAN": "check", "ENUM": "drop", "POINTER": "object"}.get(meta.type, "field")
        base = f"prop:{name}:{lbl}"
        el = {"kind": "prop", "owner": owner, "name": name, "meta": meta, "text": lbl,
              "style": st, "enabled": enabled, "choices": choices, "icon": icon,
              "on_change": on_change, "id": self._uid(base)}
        if st == "seg":
            el["kind"] = "segrow"
            with self.row():
                for k, (ident, nm, _d) in enumerate(meta.items):
                    self._add({"kind": "seg", "owner": owner, "name": name, "meta": meta,
                               "value": ident, "text": nm, "enabled": enabled,
                               "first": k == 0, "last": k == len(meta.items) - 1,
                               "on_change": on_change,
                               "id": self._uid(f"{base}:{ident}")}, 22 * s)
            return el
        return self._add(el, 22 * s, weight)

    def list(self, lid, items, active, on_select, cells, rows=5, empty="Liste boş"):
        """Satır listesi. cells(ui, öğe, i) satırın hücrelerini kurar (aynı satırda)."""
        s = self.s
        RH = 22 * s
        n = len(items)
        off = self.host.list_scroll.get(lid, 0)
        off = max(0, min(off, max(0, n - rows)))
        self.host.list_scroll[lid] = off
        shown = items[off:off + rows]
        h = max(1, len(shown)) * RH + 6 * s
        top = self.y
        box = {"kind": "listbox", "id": "list:" + lid, "lid": lid, "n": n, "rows": rows,
               "rect": (self.x0, top - h, self.x1, top), "enabled": True}
        self.els.append(box)
        y = top - 3 * s
        if not items:
            self.els.append({"kind": "label", "text": empty, "tone": "dim", "icon": None,
                             "dot": False, "id": None, "enabled": True,
                             "rect": (self.x0 + 8 * s, y - RH, self.x1, y)})
        for j, it in enumerate(shown):
            i = off + j
            self.els.append({"kind": "listrow", "index": i, "active": i == active,
                             "fn": (lambda i=i: on_select(i)), "id": f"row:{lid}:{i}",
                             "enabled": True,
                             "rect": (self.x0 + 3 * s, y - RH, self.x1 - 3 * s, y)})
            sub = UI(self.host, self.x0 + 6 * s, self.x1 - 6 * s, y - 1 * s, s)
            sub._ids = self._ids
            with sub.row():
                cells(sub, it, i)
            for e in sub.els:
                e["rect"] = (e["rect"][0], y - RH + 1 * s, e["rect"][2], y - 1 * s)
                e["inrow"] = True
                self.els.append(e)
            y -= RH
        if n > rows:
            self.els.append({"kind": "label", "text": f"{off + 1}–{off + len(shown)} / {n}  "
                             "(tekerlek: kaydır)", "tone": "dim", "icon": None, "dot": False,
                             "id": None, "enabled": True,
                             "rect": (self.x0, top - h - 14 * s, self.x1, top - h)})
            h += 14 * s
        self.y = top - h - 4 * s


# ---------------------------------------------------------------- pencere yöneticisi

class FormHost:
    def __init__(self, scale=1.0, meta_fn=None, fmt_fn=None, parse_fn=None, ctx_fn=None,
                 on_commit=None, on_message=None):
        self.s = scale
        self.meta_fn = meta_fn
        self.fmt_fn = fmt_fn or default_fmt
        self.parse_fn = parse_fn or default_parse
        self.ctx_fn = ctx_fn or (lambda: None)
        self.on_commit = on_commit           # (metin) -> geri alma adımı
        self.on_message = on_message         # (metin) -> bildirim
        self.measure = lambda t, sz: (len(t) * sz * 0.6, sz)
        self.form = None                     # {"id", "title", "icon", "spec", "x", "w"}
        self.els = []
        self.box = None
        self.hover = None
        self.drag = None
        self.edit = None                     # {"id", "text", "fresh"}
        self.drop = None                     # {"id", "rows": [(rect, değer, ad)]}
        self.list_scroll = {}
        self.scroll = 0.0
        self.scroll_max = 0.0
        self._geom = None

    # -------------------------------------------------- dış arayüz
    def is_open(self, fid=None):
        return self.form is not None and (fid is None or self.form["id"] == fid)

    def open(self, fid, title, icon, spec, anchor_x, width=300):
        if self.is_open(fid):
            self.close()
            return False
        self.form = {"id": fid, "title": title, "icon": icon, "spec": spec, "x": anchor_x,
                     "w": width}
        self.scroll = 0.0
        self.edit = self.drag = self.drop = None
        return True

    def close(self):
        self._commit_edit()
        self.form = None
        self.els, self.box = [], None
        self.edit = self.drag = self.drop = None

    def capturing(self):
        """Klavye / sürükleme bu pencerede (diğer araçlar olayı almasın)."""
        return self.drag is not None or self.edit is not None

    def meta(self, owner, name):
        if self.meta_fn is not None:
            try:
                return self.meta_fn(owner, name)
            except Exception:
                return None
        m = getattr(owner, "__meta__", {}).get(name)
        return m

    def fmt(self, meta, v):
        try:
            return self.fmt_fn(meta, v)
        except Exception:
            return default_fmt(meta, v)

    # -------------------------------------------------- kurulum
    def build(self, p=None, top=None, region_w=None, region_h=None):
        if self.form is None:
            return
        if p is not None:
            self.measure = p.measure
            self._geom = (top, region_w, region_h)
        if self._geom is None:
            return
        top, region_w, region_h = self._geom
        s = self.s
        W = self.form["w"] * s
        x0 = min(max(self.form["x"], 6 * s), max(6 * s, region_w - W - 6 * s))
        HEAD = 30 * s
        PAD = 10 * s
        ui = UI(self, x0 + PAD, x0 + W - PAD, top - HEAD - 4 * s + self.scroll, s)
        try:
            self.form["spec"](ui, self.ctx_fn())
        except Exception as e:                # spec hatası arayüzü düşürmesin
            ui.label(f"Hata: {e}", "err")
        content_h = (top - HEAD - 4 * s + self.scroll) - ui.y + PAD - 4 * s
        avail = max(top - 12 * s - HEAD, 80 * s)
        vis = min(content_h, avail)
        self.scroll_max = max(0.0, content_h - avail)
        if self.scroll > self.scroll_max:
            self.scroll = self.scroll_max
        y0 = top - HEAD - vis
        self.box = (x0, y0, x0 + W, top)
        self.view = (top - HEAD, y0)            # içerik görünür aralığı (üst, alt)
        els = [{"kind": "head", "id": "head", "rect": (x0, top - HEAD, x0 + W, top),
                "enabled": True},
               {"kind": "close", "id": "close", "enabled": True,
                "rect": (x0 + W - 26 * s, top - HEAD + 5 * s, x0 + W - 6 * s, top - 5 * s)}]
        for e in ui.els:
            if e["kind"] == "group":
                els.extend(e["children"])
            else:
                els.append(e)
        self.els = els

    def _visible(self, e):
        if e["kind"] in ("head", "close"):
            return True
        r = e.get("rect")
        if r is None:
            return False
        top, bot = self.view
        return r[1] >= bot - 0.5 and r[3] <= top + 0.5

    def contains(self, mx, my):
        if self.form is None or self.box is None:
            return False
        x0, y0, x1, y1 = self.box
        if x0 <= mx <= x1 and y0 <= my <= y1:
            return True
        return self._drop_hit(mx, my) is not None or (
            self.drop is not None and self._in(self.drop["box"], mx, my))

    @staticmethod
    def _in(r, mx, my):
        return r[0] <= mx <= r[2] and r[1] <= my <= r[3]

    def hit(self, mx, my):
        for e in reversed(self.els):
            if e.get("rect") and e["kind"] not in ("label", "section", "sep", "listbox") and \
                    self._visible(e) and self._in(e["rect"], mx, my):
                return e
        return None

    def _drop_hit(self, mx, my):
        if self.drop is None:
            return None
        for r, val, _nm in self.drop["rows"]:
            if self._in(r, mx, my):
                return val
        return None

    def _find(self, eid):
        for e in self.els:
            if e.get("id") == eid:
                return e
        return None

    # -------------------------------------------------- değer
    def _get(self, e):
        try:
            return getattr(e["owner"], e["name"])
        except Exception:
            return None

    def _set(self, e, v, commit=True):
        m = e["meta"]
        if m.type in ("FLOAT", "INT"):
            v = min(max(v, m.min), m.max)
            if m.type == "INT":
                v = int(round(v))
        try:
            setattr(e["owner"], e["name"], v)
        except Exception as ex:
            if self.on_message:
                self.on_message(f"Değer yazılamadı: {ex}")
            return
        if e.get("on_change"):
            try:
                e["on_change"](v)
            except Exception:
                pass
        if commit and self.on_commit:
            self.on_commit(f"{self.form['title']}: {e.get('text') or e['name']}")

    def _step(self, m, v):
        if m.type == "INT":
            return 1
        if m.unit == "ROTATION":
            return math.radians(5)
        st = (m.step or 1.0) / 100.0
        if v and st > abs(v) * 0.5:
            st = _nice(abs(v) * 0.1)
        return st

    # -------------------------------------------------- olaylar
    def press(self, mx, my, ctrl=False, shift=False):
        """Sol tık. True: tüketildi."""
        if self.form is None:
            return False
        self.build()
        if self.drop is not None:
            val = self._drop_hit(mx, my)
            d, self.drop = self.drop, None
            if val is not None:
                e = self._find(d["id"])
                if e is not None:
                    self._set(e, val)
                return True
            if not self.contains(mx, my):
                return True
        if self.edit is not None:
            e = self.hit(mx, my)
            if e is None or e.get("id") != self.edit["id"]:
                self._commit_edit()
                self.build()
        e = self.hit(mx, my)
        if e is None:
            return self.contains(mx, my)
        if not e.get("enabled", True):
            return True
        k = e["kind"]
        s = self.s
        if k == "close":
            self.close()
        elif k == "button" or k == "listrow":
            try:
                e["fn"]()
            except Exception as ex:
                if self.on_message:
                    self.on_message(f"Hata: {ex}")
        elif k == "seg":
            self._set(e, e["value"])
        elif k == "prop":
            st, m = e["style"], e["meta"]
            v = self._get(e)
            if st in ("check", "toggle"):
                self._set(e, not bool(v))
            elif st in ("drop", "object"):
                self._open_drop(e)
            else:
                x0, _y0, x1, _y1 = e["rect"]
                if mx <= x0 + 14 * s or mx >= x1 - 14 * s:
                    d = self._step(m, v or 0.0) * (-1 if mx <= x0 + 14 * s else 1)
                    self._set(e, (v or 0) + d)
                else:
                    self.drag = {"id": e["id"], "x": mx, "v": v or 0.0, "moved": False}
        return True

    def _open_drop(self, e):
        s = self.s
        x0, y0, x1, _y1 = e["rect"]
        if e["style"] == "object":
            opts = [(None, "— yok —")] + list((e.get("choices") or (lambda: []))())
        else:
            opts = [(i, n) for i, n, _d in e["meta"].items]
        RH = 20 * s
        rows = []
        # v0.36.0: uzun listeler (diş ölçüleri) sütunlara bölünür
        per = 16 if len(opts) > 16 else max(len(opts), 1)
        opts = opts[:per * 4]
        ncol = max(1, -(-len(opts) // per))
        cw = max(x1 - x0, 90 * s) if ncol > 1 else x1 - x0
        if ncol > 1 and self._geom is not None:
            x0 = max(6 * s, min(x0, self._geom[1] - ncol * cw - 6 * s))
        y = y0 - 2 * s
        ymin = y
        for k, (val, nm) in enumerate(opts):
            c, r = divmod(k, per)
            yy = y0 - 2 * s - r * RH
            xx = x0 + c * cw
            rows.append(((xx, yy - RH, xx + cw, yy), val, nm))
            ymin = min(ymin, yy - RH)
        x1 = x0 + ncol * cw if ncol > 1 else x1
        self.drop = {"id": e["id"], "rows": rows,
                     "box": (x0 - 2 * s, ymin - 2 * s, x1 + 2 * s, y0)}

    def move(self, mx, my, shift=False):
        if self.form is None:
            return False
        if self.drag is not None:
            e = self._find(self.drag["id"])
            if e is None:
                self.drag = None
                return True
            dx = mx - self.drag["x"]
            if abs(dx) > 3 * self.s:
                self.drag["moved"] = True
            if self.drag["moved"]:
                m = e["meta"]
                v0 = self.drag["v"]
                if m.type == "INT":
                    per = 1.0 / (8 * self.s)
                elif m.unit == "ROTATION":
                    per = math.radians(0.5) / self.s
                else:
                    rng = m.soft_max - m.soft_min
                    per = (rng / (300 * self.s)) if 0 < rng < 1e5 else \
                        max(abs(v0), 0.01) * 0.005 / self.s
                if shift:
                    per *= 0.1
                self._set(e, v0 + dx * per, commit=False)
            return True
        h = self._drop_hit(mx, my)
        if h is not None or self.drop is not None:
            nh = ("drop", h)
        else:
            e = self.hit(mx, my)
            nh = e.get("id") if e else None
        ch = nh != self.hover
        self.hover = nh
        return ch

    def release(self, mx, my):
        if self.drag is None:
            return False
        d, self.drag = self.drag, None
        e = self._find(d["id"])
        if e is None:
            return True
        if d["moved"]:
            if self.on_commit:
                self.on_commit(f"{self.form['title']}: {e.get('text') or e['name']}")
        else:
            self.edit = {"id": e["id"], "text": self.fmt(e["meta"], self._get(e) or 0),
                         "fresh": True}
        return True

    def key(self, etype, unicode="", ctrl=False, shift=False):
        """Klavye (yazarken). True: tüketildi."""
        if self.edit is None:
            if etype == "ESC" and self.drop is not None:
                self.drop = None
                return True
            return False
        ed = self.edit
        if etype in ("RET", "NUMPAD_ENTER"):
            self._commit_edit()
        elif etype == "ESC":
            self.edit = None
        elif etype == "TAB":
            nxt = self._next_field(ed["id"], -1 if shift else 1)
            self._commit_edit()
            if nxt is not None:
                self.build()
                e = self._find(nxt)
                if e is not None:
                    self.edit = {"id": nxt, "text": self.fmt(e["meta"], self._get(e) or 0),
                                 "fresh": True}
        elif etype == "BACK_SPACE":
            ed["text"] = "" if ed["fresh"] or ctrl else ed["text"][:-1]
            ed["fresh"] = False
        elif ctrl and etype == "A":
            ed["fresh"] = True
        elif unicode and unicode.isprintable():
            ed["text"] = unicode if ed["fresh"] else ed["text"] + unicode
            ed["fresh"] = False
        return True

    def _next_field(self, eid, d):
        ids = [e["id"] for e in self.els if e["kind"] == "prop" and e["style"] == "field" and
               e.get("enabled", True)]
        if eid not in ids or len(ids) < 2:
            return None
        return ids[(ids.index(eid) + d) % len(ids)]

    def _commit_edit(self):
        ed, self.edit = self.edit, None
        if ed is None:
            return
        e = self._find(ed["id"])
        if e is None:
            return
        try:
            v = self.parse_fn(e["meta"], ed["text"])
        except Exception:
            if self.on_message:
                self.on_message(f"Geçersiz değer: {ed['text']}")
            return
        self._set(e, v)

    def wheel(self, mx, my, d):
        if not self.contains(mx, my):
            return False
        for e in self.els:
            if e["kind"] == "listbox" and self._in(e["rect"], mx, my) and e["n"] > e["rows"]:
                lid = e["lid"]
                self.list_scroll[lid] = max(0, min(self.list_scroll.get(lid, 0) + d,
                                                   e["n"] - e["rows"]))
                return True
        if self.scroll_max > 0:
            self.scroll = max(0.0, min(self.scroll + d * 30 * self.s, self.scroll_max))
        return True

    # -------------------------------------------------- çizim
    def draw(self, p, top, region_w, region_h):
        if self.form is None:
            return
        self.build(p, top, region_w, region_h)
        s = self.s
        x0, y0, x1, y1 = self.box
        R = 7 * s
        p.rect(x0 + 2 * s, y0 - 3 * s, x1 + 2 * s, y1 - 3 * s, COL_SHADOW, R)
        p.rect(x0, y0, x1, y1, COL_CARD, R)
        p.outline(x0, y0, x1, y1, COL_BORDER, R, 1.0)
        for e in self.els:
            if self._visible(e):
                self._draw_el(p, e)
        if self.scroll_max > 0:
            top_, bot = self.view
            hh = top_ - bot
            frac = hh / (hh + self.scroll_max)
            th = max(16 * s, hh * frac)
            ty1 = top_ - (hh - th) * (self.scroll / self.scroll_max)
            p.rect(x1 - 4 * s, ty1 - th, x1 - 2 * s, ty1, COL_SEP, 1 * s)
        if self.drop is not None:
            self._draw_drop(p)

    def _draw_el(self, p, e):
        s = self.s
        k = e["kind"]
        x0, y0, x1, y1 = e["rect"]
        hov = self.hover == e.get("id")
        en = e.get("enabled", True)
        dimc = (lambda c: (c[0], c[1], c[2], c[3] * (1.0 if en else 0.4)))
        if k == "head":
            f = self.form
            _icon(p, f["icon"], x0 + 18 * s, (y0 + y1) / 2, 16 * s, COL_ACCENT, 1.5)
            p.text(x0 + 32 * s, (y0 + y1) / 2 - 4 * s, f["title"], COL_TEXT, int(12 * s),
                   bold=True)
            p.rect(x0 + 8 * s, y0, x1 - 8 * s, y0 + 1, COL_SEP, 0)
        elif k == "close":
            if hov:
                p.rect(x0, y0, x1, y1, COL_HOVER, 4 * s)
            _icon(p, "CLOSE", (x0 + x1) / 2, (y0 + y1) / 2, 10 * s,
                  COL_TEXT if hov else COL_TEXT_DIM, 1.4)
        elif k == "section":
            p.text(x0, y0 + 4 * s, e["text"].upper(), COL_ACCENT, int(9 * s), bold=True)
            tw = p.measure(e["text"].upper(), int(9 * s), True)[0]
            p.rect(x0 + tw + 8 * s, y0 + 7 * s, x1, y0 + 7 * s + 1, COL_SEP, 0)
        elif k == "label":
            col = TONES.get(e["tone"], COL_TEXT)
            tx = x0
            if e.get("icon"):
                _icon(p, e["icon"], x0 + 6 * s, (y0 + y1) / 2, 11 * s, col, 1.3)
                tx += 16 * s
            elif e.get("dot"):
                p.circle(x0 + 4 * s, (y0 + y1) / 2, 3 * s, col)
                tx += 12 * s
            tcol = col if e["tone"] in ("", "dim") else (0.85, 0.85, 0.88, 1.0)
            p.text(tx, y0 + 4 * s, _clip(p, e["text"], int(10 * s), x1 - tx), tcol, int(10 * s))
        elif k == "sep":
            p.rect(x0, (y0 + y1) / 2, x1, (y0 + y1) / 2 + 1, COL_SEP, 0)
        elif k == "button":
            on = e.get("depress")
            bg = COL_ACTIVE if (e["primary"] or on) else COL_KEY
            if hov and en:
                bg = tuple(min(1.0, c + 0.06) for c in bg[:3]) + (1.0,)
            p.rect(x0, y0, x1, y1, dimc(bg), 4 * s)
            sz, ksz = int(10 * s), int(8 * s)
            bold = bool(e["primary"])
            txt = e["text"]
            iw = 18 * s if e.get("icon") else 0
            tw = p.measure(txt, sz, bold)[0] if txt else 0
            kw = p.measure(e["key"], ksz)[0] + 8 * s if e.get("key") else 0
            gap = 7 * s if kw else 0
            maxw = x1 - x0 - 10 * s - iw - kw - gap
            if tw > maxw:
                txt = _clip(p, txt, sz, maxw)
                tw = p.measure(txt, sz, bold)[0]
            cx = (x0 + x1) / 2 - (iw + tw + gap + kw) / 2
            cy = (y0 + y1) / 2
            if e.get("icon"):
                _icon(p, e["icon"], cx + 7 * s, cy, 12 * s, dimc(COL_ICON), 1.3)
                cx += iw
            if txt:
                p.text(cx, cy - 4 * s, txt, dimc(COL_TEXT), sz, bold=bold)
            if kw:
                kx = cx + tw + gap
                p.rect(kx, cy - 7 * s, kx + kw, cy + 7 * s,
                       dimc((0.0, 0.0, 0.0, 0.25) if (e["primary"] or on) else COL_FIELD), 3 * s)
                p.text(kx + 4 * s, cy - 3 * s, e["key"], dimc((0.85, 0.88, 0.98, 1.0)), ksz)
        elif k == "listbox":
            p.rect(x0, y0, x1, y1, COL_LIST, 4 * s)
        elif k == "listrow":
            if e["active"]:
                p.rect(x0, y0, x1, y1, COL_TOGGLE, 3 * s)
            elif hov:
                p.rect(x0, y0, x1, y1, (0.18, 0.18, 0.20, 1.0), 3 * s)
        elif k == "seg":
            v = self._get(e)
            on = v == e["value"]
            bg = COL_ACTIVE if on else (COL_FIELD_HOV if hov else COL_FIELD)
            p.rect(x0, y0, x1, y1, dimc(bg), 3 * s)
            sz = int(10 * s)
            t = _clip(p, e["text"], sz, x1 - x0 - 6 * s)
            tw = p.measure(t, sz)[0]
            p.text((x0 + x1) / 2 - tw / 2, y0 + 7 * s, t, dimc(COL_TEXT if on else
                                                               (0.82, 0.82, 0.86, 1.0)), sz)
        elif k == "prop":
            self._draw_prop(p, e, hov, dimc)

    def _draw_prop(self, p, e, hov, dimc):
        s = self.s
        x0, y0, x1, y1 = e["rect"]
        st, m = e["style"], e["meta"]
        v = self._get(e)
        sz = int(10 * s)
        cy = (y0 + y1) / 2
        if st == "check":
            bx0 = x0
            p.rect(bx0, cy - 7 * s, bx0 + 14 * s, cy + 7 * s,
                   dimc(COL_ACTIVE if v else (COL_FIELD_HOV if hov else COL_FIELD)), 3 * s)
            if v:
                p.lines([(bx0 + 3 * s, cy), (bx0 + 6 * s, cy - 4 * s),
                         (bx0 + 6 * s, cy - 4 * s), (bx0 + 11 * s, cy + 4 * s)],
                        dimc(COL_TEXT), 1.6)
            if e["text"]:
                p.text(bx0 + 20 * s, cy - 4 * s, _clip(p, e["text"], sz, x1 - bx0 - 22 * s),
                       dimc(COL_TEXT if v else (0.80, 0.80, 0.84, 1.0)), sz)
            return
        if st == "toggle":
            bg = COL_TOGGLE if v else (COL_FIELD_HOV if hov else COL_FIELD)
            p.rect(x0, y0, x1, y1, dimc(bg), 4 * s)
            if v:
                p.outline(x0, y0, x1, y1, dimc(COL_ACCENT), 4 * s, 1.0)
            t = e["text"]
            tw = p.measure(t, sz)[0] + (16 * s if e.get("icon") else 0)
            cx = (x0 + x1) / 2 - tw / 2
            if e.get("icon"):
                _icon(p, e["icon"], cx + 6 * s, cy, 11 * s, dimc(COL_ICON if v else COL_ICON_DIM),
                      1.3)
                cx += 16 * s
            p.text(cx, cy - 4 * s, _clip(p, t, sz, x1 - x0 - 6 * s),
                   dimc(COL_TEXT if v else (0.80, 0.80, 0.84, 1.0)), sz)
            return
        editing = self.edit is not None and self.edit["id"] == e["id"]
        p.rect(x0, y0, x1, y1, dimc(COL_FIELD_HOV if (hov or editing) else COL_FIELD), 4 * s)
        if editing:
            p.outline(x0, y0, x1, y1, COL_ACCENT, 4 * s, 1.0)
        if st in ("drop", "object"):
            if st == "drop":
                cur = next((n for i, n, _d in m.items if i == v), str(v))
            else:
                cur = getattr(v, "name", None) or "— yok —"
            lbl = e["text"]
            lw = 0
            if lbl:
                p.text(x0 + 7 * s, cy - 4 * s, lbl, dimc(COL_TEXT_DIM), sz)
                lw = p.measure(lbl, sz)[0] + 12 * s
            p.text(x0 + 7 * s + lw, cy - 4 * s, _clip(p, cur, sz, x1 - x0 - lw - 26 * s),
                   dimc(COL_TEXT), sz)
            p.tri([(x1 - 14 * s, cy + 2 * s), (x1 - 6 * s, cy + 2 * s), (x1 - 10 * s, cy - 3 * s)],
                  dimc(COL_TEXT_DIM))
            return
        # sayı alanı
        if editing:
            t = self.edit["text"]
            if self.edit["fresh"]:
                tw = p.measure(t, sz)[0]
                p.rect(x0 + 6 * s, cy - 7 * s, x0 + 8 * s + tw, cy + 7 * s, COL_TOGGLE, 2 * s)
            p.text(x0 + 7 * s, cy - 4 * s, t, COL_TEXT, sz)
            if not self.edit["fresh"]:
                tw = p.measure(t, sz)[0]
                p.rect(x0 + 8 * s + tw, cy - 6 * s, x0 + 9 * s + tw, cy + 6 * s, COL_TEXT, 0)
            return
        val = self.fmt(m, v if v is not None else 0)
        lbl = e["text"]
        if hov:
            for ax, flip in ((x0 + 7 * s, -1), (x1 - 7 * s, 1)):
                p.tri([(ax - flip * 2 * s, cy + 4 * s), (ax - flip * 2 * s, cy - 4 * s),
                       (ax + flip * 2 * s, cy)], COL_TEXT_DIM)
        p.text(x0 + 14 * s, cy - 4 * s, _clip(p, lbl, sz, (x1 - x0) * 0.55), dimc(COL_TEXT_DIM), sz)
        vw = p.measure(val, sz)[0]
        p.text(x1 - 14 * s - vw, cy - 4 * s, val, dimc(COL_TEXT), sz)

    def _draw_drop(self, p):
        s = self.s
        d = self.drop
        bx0, by0, bx1, by1 = d["box"]
        p.rect(bx0 + 2 * s, by0 - 3 * s, bx1 + 2 * s, by1 - 3 * s, COL_SHADOW, 5 * s)
        p.rect(bx0, by0, bx1, by1, COL_CARD, 5 * s)
        p.outline(bx0, by0, bx1, by1, COL_BORDER, 5 * s, 1.0)
        e = self._find(d["id"])
        cur = self._get(e) if e is not None else None
        for r, val, nm in d["rows"]:
            hov = self.hover == ("drop", val)
            on = val == cur or (val is not None and getattr(cur, "name", None) is not None and
                                getattr(val, "name", 0) == getattr(cur, "name", 1))
            if on:
                p.rect(r[0], r[1], r[2], r[3], COL_TOGGLE, 3 * s)
            if hov:
                p.rect(r[0], r[1], r[2], r[3], COL_HOVER, 3 * s)
            p.text(r[0] + 8 * s, r[1] + 6 * s, _clip(p, nm, int(10 * s), r[2] - r[0] - 12 * s),
                   COL_TEXT, int(10 * s))


def _unused():   # pragma: no cover - simge sabitleri dışa aktarılır
    return COL_CARD_ICON
