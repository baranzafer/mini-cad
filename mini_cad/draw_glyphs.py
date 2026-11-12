"""Kısıt arayüzü: kısıt için kenar / nokta seçimi ve kısıt simgelerinin sağ tık menüsü
(dondur / sil).

MINICAD_OT_draw (draw.py) bu mixin'den miras alır; metotlar self üzerinden birbirini çağırır.
"""
import bpy
import numpy as np

from . import constraints
from . import core
from . import palette
from . import sketchmath as sm
from .draw_common import COL_TEXT, _bezier, _marker, _poly, _project, _rect, _seg_px_dist, _text


class ConstraintUIMixin:
    """Kısıt arayüzü: kısıt için kenar / nokta seçimi ve kısıt simgelerinin sağ tık menüsü
    (dondur / sil)."""

    def _pick_entity(self, mx, my, is_pt):
        M = np.array(self.rv3d.perspective_matrix, dtype=np.float64)
        m = np.array([mx, my])
        taken = {(r[1], r[2], r[3]) for r in self.c_refs}
        refs = self.refs
        if is_pt:
            if not refs.wpts:
                return None
            P = np.array([p for _, p in refs.wpts])
            px, ok, _ = _project(P, M, self.region)
            d = np.where(ok, np.linalg.norm(px - m, axis=1), np.inf)
            for i in np.argsort(d):
                if d[i] > self.radius * 1.3:
                    return None
                key = refs.wpts[int(i)][0]
                if key not in taken:
                    return ("pt",) + key + (P[int(i)],)
            return None
        if not len(refs.WA):
            return None
        pa, oka, za = _project(refs.WA, M, self.region)
        pb, okb, zb = _project(refs.WB, M, self.region)
        dd, t = _seg_px_dist(pa, pb, m)
        dd = np.where(oka & okb, dd, np.inf)
        for i in np.argsort(dd)[:40]:
            if dd[i] > self.radius:
                return None
            k = int(refs.Wown[int(i)])
            name, si, seg, S = refs.wsegs[k]
            if (name, si, seg) not in taken:
                return ("seg", name, si, seg, S)
        return None

    def _click_constraint(self, context):
        kind = self.tool[2:]
        n = self._c_needed()
        if self.c_hover is None:
            return
        self.c_refs.append(self.c_hover)
        self.c_hover = None
        if kind not in ("DIM", "AUTODIM") and len(self.c_refs) >= n and \
                any(r[1] == "@sk" for r in self.c_refs):
            self._c_sketch(context, kind)            # taslak çizgilerine kısıt
            return
        if kind == "AUTODIM" and self.c_refs and self.c_refs[0][1] == "@sk":
            self._c_sketch(context, kind)
            return
        if kind == "AUTODIM":
            refs = self._refs_of(self.c_refs)
            self.c_refs = []
            if refs:
                n_ = self._autodim(context, refs[0])
                try:
                    bpy.ops.ed.undo_push(message="Mini CAD: Otomatik ölçü")
                except Exception:
                    pass
                self.dirty = True
                self._status(context, f"Otomatik ölçü: {n_} ölçü eklendi" if n_ else
                                      "Otomatik ölçü: eklenecek ölçü yok (hepsi ölçülü)")
            return
        if kind == "DIM":
            if len(self.c_refs) >= 2:
                self._dim_create(context)
            else:
                self._status(context, self._c_status_text())
            return
        if len(self.c_refs) < n:
            self._status(context, self._c_status_text())
            return
        value = None
        if kind in ("HORIZ", "VERT"):
            ax = self._plane_axes()
            if ax is None:
                self.c_refs = []
                self._status(context, "Yatay / Dikey: çizim düzlemi bir eksen düzlemi olmalı "
                                      "(XY / XZ / YZ); diğerlerinde Eksen kısıtını kullan")
                return
            value = ax[0] if kind == "HORIZ" else ax[1]
        refs = []
        for r in self.c_refs:
            ob = bpy.data.objects.get(r[1])
            if ob is None:
                self.c_refs = []
                return
            refs.append((r[0], ob, r[2], r[3]))
        self.c_refs = []
        real = "AXIS" if kind in ("HORIZ", "VERT") else kind
        c = constraints.add(real, refs, value=value)
        self._c_done(context, c, real if kind not in ("HORIZ", "VERT") else kind)

    def _c_sketch(self, context, kind):
        """Seçimde taslak çizgisi var: kısıt taslağa eklenir (Bitir gerekmez)."""
        refs = self._refs_of(self.c_refs)
        self.c_refs = []
        if refs is None:
            return
        name = constraints.NAMES.get(kind, kind)
        if kind == "AUTODIM":
            r = refs[0]
            k = self._uid_map().get(r[2])
            made = 0
            if k is not None:
                have = {(e["refs"][0][2], e["refs"][0][3]) for e in self.skc
                        if e["kind"] in ("DISTANCE", "RADIUS") and e["refs"][0][0] == "seg"}
                st = self.sketch[k]
                done_ent = set()
                for i, sg in enumerate(st["segs"]):
                    ref = ("seg", "@sk", r[2], i)
                    if (r[2], i) in have:
                        continue
                    info = self._seg_info(ref)
                    if info[0] == "line":
                        made += self._skc_add(context, "DISTANCE", [ref]) is not None
                    elif info[0] == "arc":
                        ent = sm.entity_of(st, i)
                        if ent in done_ent:
                            continue
                        done_ent.add(ent)
                        made += self._skc_add(context, "RADIUS", [ref]) is not None
            self._status(context, f"Otomatik ölçü (taslak): {made} ölçü")
            return
        value = None
        real = kind
        if kind in ("HORIZ", "VERT"):
            ax = self._plane_axes()
            if ax is None:
                self._status(context, "Yatay / Dikey: çizim düzlemi bir eksen düzlemi olmalı")
                return
            real, value = "AXIS", (ax[0] if kind == "HORIZ" else ax[1])
        i = self._skc_add(context, real, refs, axis=value)
        if i is None:
            self._status(context, f"{name}: eklenemedi")
            return
        e = self.skc[i]
        note = " (Bitir'de uygulanır)" if "Bitir" in e.get("info", "") else ""
        self._status(context, f"{name} taslağa eklendi{note}" if e.get("ok", True) else
                     f"{name} eklendi ama sağlanamadı: {e.get('info')}")

    def _glyph_menu_open(self, mx, my):
        """Kısıt simgesine SAĞ tıklanınca: iki küçük simge (dondur / sil)."""
        g = constraints.glyph_at(mx, my)
        if g is None:
            return False
        ob = bpy.data.objects.get(g[0])
        if ob is None or g[1] >= len(ob.cad.constraints):
            return False
        box = next(b for b in constraints._glyph_boxes if (b[4], b[5]) == g)
        c = ob.cad.constraints[g[1]]
        s = self.ui_scale
        B = 22 * s
        x0, y0 = box[2] + 3 * s, box[1] - 3 * s
        b1 = (x0 + 2 * s, y0 + 2 * s, x0 + 2 * s + B, y0 + 2 * s + B)
        b2 = (b1[2] + 2 * s, b1[1], b1[2] + 2 * s + B, b1[3])
        polys = []
        for r in c.refs:
            pts = constraints.ref_points(r.obj, r.spline, r.index, r.point)
            if pts is None:
                continue
            if r.point:
                polys.append(("pt", constraints._world(*pts[0])))
            else:
                try:
                    sp = r.obj.data.splines[r.spline]
                    seg = core._spline_segment(r.obj, r.spline, sp, r.index, r.obj.matrix_world)
                    P = [np.array(tuple(v)) for v in seg["p"]]
                    S = np.array(P) if len(P) == 2 else \
                        np.array([_bezier(P, t) for t in np.linspace(0, 1, 16)])
                    polys.append(("seg", S))
                except Exception:
                    pass
        self.gmenu = {"obj": g[0], "index": g[1], "glyph": box[:4],
                      "box": (x0, y0, b2[2] + 2 * s, b2[3] + 2 * s), "hover": None,
                      "polys": polys, "enabled": c.enabled,
                      "name": constraints.NAMES.get(c.kind, c.kind),
                      "buttons": [(b1, "toggle"), (b2, "delete")]}
        return True

    def _glyph_menu_hover(self, mx, my):
        gm = self.gmenu
        if gm is None:
            return False
        x0, y0, x1, y1 = gm["box"]
        far = 60 * self.ui_scale
        if not (x0 - far <= mx <= x1 + far and y0 - far <= my <= y1 + far):
            self.gmenu = None                    # fare uzaklaştı: menüyü kapat
            return True
        hov = None
        for r, act in gm["buttons"]:
            if r[0] <= mx <= r[2] and r[1] <= my <= r[3]:
                hov = act
        changed = hov != gm.get("hover")
        gm["hover"] = hov
        return changed

    def _glyph_menu_click(self, context, mx, my):
        gm = self.gmenu
        if gm is None:
            return False
        x0, y0, x1, y1 = gm["box"]
        if not (x0 <= mx <= x1 and y0 <= my <= y1):
            return False
        ob = bpy.data.objects.get(gm["obj"])
        for r, act in gm["buttons"]:
            if r[0] <= mx <= r[2] and r[1] <= my <= r[3] and ob is not None and \
                    gm["index"] < len(ob.cad.constraints):
                c = ob.cad.constraints[gm["index"]]
                if act == "toggle":
                    c.enabled = not c.enabled
                    msg = f"Kısıt {'açıldı' if c.enabled else 'kapatıldı'}"
                else:
                    constraints.remove(ob, gm["index"])
                    msg = "Kısıt silindi"
                try:
                    bpy.ops.ed.undo_push(message="Mini CAD: Kısıt")
                except Exception:
                    pass
                self.gmenu = None
                self._status(context, msg)
                break
        self.area.tag_redraw()
        return True

    def _draw_gmenu(self, region):
        gm = self.gmenu
        if gm is None:
            return
        s = self.ui_scale
        for kind, data in gm["polys"]:          # kısıtın bağlı olduğu kenar / noktalar
            if kind == "seg":
                pts = [self._px(p) for p in data]
                pts = [p for p in pts if p is not None]
                if len(pts) > 1:
                    _poly(pts, (0.85, 0.4, 1.0, 0.9), 3.5, region)
            else:
                p = self._px(data)
                if p is not None:
                    _marker("Uç", p[0], p[1], 6 * s, region)
        x0, y0, x1, y1 = gm["box"]
        _rect(x0, y0, x1, y1, (0.1, 0.1, 0.12, 0.92))
        for r, act in gm["buttons"]:
            on = gm.get("hover") == act
            col = (0.75, 0.25, 0.22, 1.0) if (act == "delete" and on) else \
                ((0.32, 0.32, 0.36, 1.0) if on else (0.2, 0.2, 0.22, 1.0))
            if act == "toggle" and not gm["enabled"]:
                col = (0.25, 0.45, 0.75, 1.0)    # donmuş: vurgulu
            _rect(r[0], r[1], r[2], r[3], col)
            palette.draw_icon("FREEZE" if act == "toggle" else "TRASH", (r[0] + r[2]) / 2,
                              (r[1] + r[3]) / 2, (r[2] - r[0]) * 0.7, COL_TEXT, region, 1.4)
        if gm.get("hover"):
            tip = {"toggle": "Çöz" if not gm["enabled"] else "Dondur (devre dışı)",
                   "delete": "Sil"}[gm["hover"]]
            _text(x0, y1 + 4 * s, f"{gm['name']}: {tip}", COL_TEXT, int(10 * s))
