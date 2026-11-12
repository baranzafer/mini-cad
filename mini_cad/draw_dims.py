"""Kısıt / Ölçü arayüzü — Aşama 4 (Inventor 2D gibi):

  Ölçü (genel)   doğruya tık + Enter / sağ tık → uzunluk · yay → yarıçap · daire → çap ·
                 iki doğru → açı (paralelse aralarındaki uzaklık) · iki nokta → mesafe ·
                 nokta + doğru → uzaklık. Ölçü oluşunca değeri yazılır (Enter); mevcut
                 ölçü değerine tıklayınca düzenlenir.
  Yatay / Dikey  çizim düzleminin eksenlerine göre (AXIS kısıtı).
  Eş merkezli, Yarıçap, Pürüzsüz (G2), Simetrik (çizgi): constraints_arcs / solver.

MINICAD_OT_draw (draw.py) bu mixin'den miras alır.
"""
import math

import bpy
import numpy as np

from . import constraints
from . import drawmath as dm
from .draw_common import COL_SNAP, _text, parse_angle, parse_length

AXES = {"XY": (0, 1), "XZ": (0, 2), "YZ": (1, 2)}
VALUE_KINDS = ("DISTANCE", "ANGLE", "RADIUS", "PTLINE", "LINEDIST", "CENTERDIST")


class DimMixin:
    """Genel ölçü aracı, ölçü değeri düzenleme, Yatay / Dikey, karışık referanslı kısıtlar."""

    def _dim_init(self):
        if not hasattr(self, "dim_edit"):
            self.dim_edit = None

    # ------------------------------------------------------------ seçim türü

    def _c_want(self):
        kind = self.tool[2:]
        if kind == "DIM":
            return "any"
        if kind in ("HORIZ", "VERT", "AUTODIM"):
            return "seg"
        return constraints.slot_type(kind, len(self.c_refs))

    def _c_pick(self, mx, my):
        want = self._c_want()
        if want == "any":
            p = self._pick_any(mx, my, True)
            smooth = p is not None and (self._sk_smooth_node(p) if p[1] == "@sk" else
                                        self._smooth_node(p))
            if p is not None and not smooth:
                return p                        # köşe / uç noktası
            q = self._pick_any(mx, my, False)
            return q if q is not None else p
        return self._pick_any(mx, my, want == "pt")

    def _smooth_node(self, p):
        """Yay / daire / spline ortasındaki pürüzsüz ara düğüm mü (ölçüde kenar sayılır)."""
        ob = bpy.data.objects.get(p[1])
        try:
            sp = ob.data.splines[p[2]]
            if sp.type != "BEZIER":
                return False
            n = len(sp.bezier_points)
            k = p[3]
            if not sp.use_cyclic_u and (k == 0 or k == n - 1):
                return False
            b = sp.bezier_points[k]
            a = np.array(b.co) - np.array(b.handle_left)
            c = np.array(b.handle_right) - np.array(b.co)
            la, lc = float(np.linalg.norm(a)), float(np.linalg.norm(c))
            if la < 1e-12 or lc < 1e-12:
                return False
            return float(np.dot(a, c)) / (la * lc) > 0.9999
        except Exception:
            return False

    def _c_needed(self):
        kind = self.tool[2:]
        if kind in ("HORIZ", "VERT", "AUTODIM"):
            return 1
        if kind == "DIM":
            return 2
        return constraints.needed(kind)[0]

    def _c_status_text(self):
        kind = self.tool[2:]
        if kind == "DIM":
            if self.dim_edit is not None:
                return "Ölçü: değeri yaz · Enter: uygula · sağ tık / Esc: ölçülen değer kalsın"
            if not self.c_refs:
                return ("Ölçü: doğru / yay / daire / noktaya tıkla · mevcut ölçü değerine tıkla: "
                        "düzenle")
            return ("Ölçü: Enter / sağ tık: uzunluk / yarıçap · ikinci doğru: açı · nokta / "
                    "doğru: uzaklık")
        n = self._c_needed()
        want = self._c_want()
        what = {"pt": "nokta", "seg": "kenar"}.get(want, "nesne")
        return f"{len(self.c_refs)}/{n} seçildi · sıradaki: {what}"

    # ------------------------------------------------------------ yatay / dikey

    def _plane_axes(self):
        pl = self._cur_plane() or self.tmp_plane
        name = pl.name if pl is not None else None
        if name not in AXES and self.plane_mode in AXES:
            name = self.plane_mode
        if name not in AXES and pl is not None:
            for nm, (a, b) in AXES.items():
                u, v = np.zeros(3), np.zeros(3)
                u[a], v[b] = 1.0, 1.0
                if abs(abs(float(np.dot(pl.n, np.cross(u, v)))) - 1.0) < 1e-9:
                    name = nm
                    break
        return AXES.get(name)

    # ------------------------------------------------------------ ölçü

    def _refs_of(self, picks):
        out = []
        for r in picks:
            if r[1] == "@sk":                  # taslak çizgisi
                out.append((r[0], "@sk", r[2], r[3]))
                continue
            ob = bpy.data.objects.get(r[1])
            if ob is None:
                return None
            out.append((r[0], ob, r[2], r[3]))
        return out

    def _seg_info(self, r):
        """("line", a, b) ya da ("arc", grup) ya da ("curve",)"""
        from .constraints_arcs import arc_group, seg_bez
        ob, si, i = r[1], r[2], r[3]
        if ob == "@sk":
            P = self._skc_seg_bez(r)
            if P is None:
                return ("curve",)
            if dm.is_straight_poly(np.array(P)):
                return ("line", P[0], P[3])
            return ("arc", None) if dm.arc_of_bezier(P) is not None else ("curve",)
        try:
            P = seg_bez(ob, si, i)
        except Exception:
            return ("curve",)
        if dm.is_straight_poly(np.array(P)):
            return ("line", P[0], P[3])
        g = arc_group(ob, si, i)
        return ("arc", g) if g is not None else ("curve",)

    def _dim_create(self, context):
        picks = list(self.c_refs)
        self.c_refs = []
        refs = self._refs_of(picks)
        if refs is None:
            return
        kind, use = None, refs
        types = [r[0] for r in refs]
        if types == ["pt"]:
            self._status(context, "Ölçü: noktadan sonra ikinci nokta ya da doğru seç")
            self.c_refs = picks
            return
        if types == ["seg"]:
            info = self._seg_info(refs[0])
            kind = {"line": "DISTANCE", "arc": "RADIUS"}.get(info[0])
            if kind is None:
                self._status(context, "Ölçü: spline'ın boyu ölçülemez (doğru / yay / daire seç)")
                return
        elif types == ["seg", "seg"]:
            a, b = self._seg_info(refs[0]), self._seg_info(refs[1])
            if "arc" in (a[0], b[0]) and "curve" not in (a[0], b[0]):
                # yay / daire içeren: merkez mesafesi (yay önce)
                kind = "CENTERDIST"
                use = [refs[0], refs[1]] if a[0] == "arc" else [refs[1], refs[0]]
            elif a[0] != "line" or b[0] != "line":
                self._status(context, "Ölçü: iki doğru (açı / uzaklık) ya da yay / daire seç")
                return
            elif float(np.linalg.norm(np.cross(dm.unit(a[2] - a[1]), dm.unit(b[2] - b[1])))) < \
                    1e-6:
                kind = "LINEDIST"                  # paralel: aralarındaki uzaklık (paralel kalır)
                use = [refs[1], refs[0]]
            else:
                kind = "ANGLE"
        elif types == ["pt", "pt"]:
            kind = "DISTANCE"
        elif sorted(types) == ["pt", "seg"]:
            pt = refs[0] if types[0] == "pt" else refs[1]
            sg = refs[1] if types[0] == "pt" else refs[0]
            info = self._seg_info(sg)[0]
            if info == "arc":
                kind, use = "CENTERDIST", [sg, pt]      # merkezden noktaya
            elif info != "line":
                self._status(context, "Ölçü: nokta ile doğru / yay seç")
                return
            else:
                kind, use = "PTLINE", [pt, sg]
        if kind is None:
            return
        if any(x[1] == "@sk" for x in use):    # taslak ölçüsü: taslakta çözülür
            i = self._skc_add(context, kind, use)
            if i is None:
                self._status(context, "Ölçü eklenemedi")
                return
            self.dim_edit = ("@sk", i)
            self.typed, self.field = ["", ""], 0
            self._status(context, self._c_status_text())
            return
        c = constraints.add(kind, use, solve=False)
        if c is not None:
            # önce kuru çözüm: çelişiyorsa geometri bozulmadan referans ölçü yapılır
            constraints.solve_all(context.scene, force=True, dry=True)
            if not c.ok:
                c.driven = True
            constraints.solve_all(context.scene, force=True)
        self._c_done(context, c, kind)
        if c is not None and getattr(c, "driven", False):
            self._status(context, f"{constraints.NAMES.get(kind, kind)}: mevcut kısıtlarla "
                                  "çelişiyor → referans ölçü yapıldı (yalnızca gösterir)")
            return
        if c is not None:
            ob = use[0][1]
            self.dim_edit = (ob.name, len(ob.cad.constraints) - 1)
            self.typed, self.field = ["", ""], 0
            self._status(context, self._c_status_text())

    def _autodim(self, context, ref):
        """Otomatik ölçülendirme: seçilen eğrinin (spline) ölçüsüz doğrularına uzunluk,
        yay / dairelerine yarıçap / çap eklenir. Eklenen sayı."""
        from .constraints_arcs import arc_group, group_key
        ob, si = ref[1], ref[2]
        sp = ob.data.splines[si]
        from . import core
        have_len, have_rad = set(), set()
        for o2, _i, c in constraints.all_constraints(context.scene):
            for r in c.refs:
                if r.obj == ob and r.spline == si and not r.point:
                    if c.kind == "DISTANCE" and len(c.refs) == 1:
                        have_len.add(r.index)
                    if c.kind == "RADIUS":
                        g = arc_group(ob, si, r.index)
                        if g is not None:
                            have_rad.add(group_key(ob, si, g))
        made = 0
        for i in range(core._seg_count(sp)):
            info = self._seg_info(("seg", ob, si, i))
            if info[0] == "line" and i not in have_len:
                if constraints.add("DISTANCE", [("seg", ob, si, i)], solve=False) is not None:
                    made += 1
                    have_len.add(i)
            elif info[0] == "arc":
                k = group_key(ob, si, info[1])
                if k not in have_rad:
                    if constraints.add("RADIUS", [("seg", ob, si, i)], solve=False) is not None:
                        made += 1
                    have_rad.add(k)
        if made:
            constraints.solve_all(context.scene, force=True)
        return made

    def _c_done(self, context, c, kind):
        try:
            bpy.ops.ed.undo_push(message="Mini CAD: Kısıt")
        except Exception:
            pass
        self.dirty = True
        name = constraints.NAMES.get(kind, kind)
        if c is None:
            self._status(context, f"{name}: eklenemedi (geçersiz referans)")
        elif c.ok:
            self._status(context, f"{name} eklendi")
        else:
            self._status(context, f"{name} eklendi ama sağlanamadı: {c.info}")

    def _dim_constraint(self):
        if self.dim_edit is None or self.dim_edit[0] == "@sk":
            return None
        ob = bpy.data.objects.get(self.dim_edit[0])
        if ob is None or self.dim_edit[1] >= len(ob.cad.constraints):
            self.dim_edit = None
            return None
        return ob.cad.constraints[self.dim_edit[1]]

    def _dim_apply(self, context):
        if self.dim_edit is not None and self.dim_edit[0] == "@sk":
            i, txt = self.dim_edit[1], self.typed[0]
            self.typed, self.field = ["", ""], 0
            self.dim_edit = None
            self._skc_apply_value(context, i, txt)
            return
        c = self._dim_constraint()
        txt = self.typed[0]
        self.typed, self.field = ["", ""], 0
        self.dim_edit = None
        if c is None or not txt:
            return
        was_driven = getattr(c, "driven", False)
        c.driven = False                       # değer yazılan ölçü şekli yönetir
        if c.kind == "ANGLE":
            v = parse_angle(txt)
            if v is None or not (0.0 <= v <= 180.0):
                self._status(context, "Açı 0–180° olmalı")
                return
            c.angle = math.radians(v)
        else:
            v = parse_length(txt)
            if v is None:
                self._status(context, "Geçersiz değer")
                return
            c.length = v / 2.0 if (c.kind == "RADIUS" and c.axis == 1) else v
        if was_driven:
            constraints.solve_all(context.scene, force=True, dry=True)
            if not c.ok:
                c.driven = True
                constraints.solve_all(context.scene, force=True)
                self._status(context, "Bu değer mevcut kısıtlarla çelişiyor; referans ölçü kaldı")
                return
        constraints.solve_all(context.scene, force=True)
        try:
            bpy.ops.ed.undo_push(message="Mini CAD: Ölçü")
        except Exception:
            pass
        self.dirty = True
        self._status(context, "Ölçü uygulandı" if c.ok else f"Ölçü sağlanamadı: {c.info}")

    def _c_event(self, context, event, mx, my, press):
        """Kısıt araçlarının özel olayları (ölçü düzenleme); işlenmediyse None."""
        self._dim_init()
        et = event.type
        if self.dim_edit is not None:
            if not press:
                return {"RUNNING_MODAL"} if et in {"LEFTMOUSE", "RIGHTMOUSE"} else None
            if et in {"RET", "NUMPAD_ENTER"}:
                self._dim_apply(context)
                self.area.tag_redraw()
                return {"RUNNING_MODAL"}
            if et in {"RIGHTMOUSE", "ESC"}:
                self.dim_edit = None
                self.typed, self.field = ["", ""], 0
                self._status(context, "Ölçülen değer kaldı")
                self.area.tag_redraw()
                return {"RUNNING_MODAL"}
            if et == "BACK_SPACE":
                self.typed[0] = self.typed[0][:-1]
                self.area.tag_redraw()
                return {"RUNNING_MODAL"}
            ch = event.unicode or ""
            if ch and not event.ctrl and (ch in "0123456789.,-+°" or
                                          (self.typed[0] and (ch.isalpha() or ch in "'\""))):
                self.typed[0] += ch
                self.area.tag_redraw()
                return {"RUNNING_MODAL"}
            if et == "LEFTMOUSE":
                self._dim_apply(context)
            return None
        if self.tool != "C_DIM":
            return None
        if et == "LEFTMOUSE" and press and not self.c_refs:
            i = self._skc_at(mx, my)
            if i is not None and self.skc[i]["value"] is not None and \
                    self.skc[i]["kind"] != "AXIS":
                self.dim_edit = ("@sk", i)           # taslak ölçüsünü düzenle
                self.typed, self.field = ["", ""], 0
                self._status(context, self._c_status_text())
                self.area.tag_redraw()
                return {"RUNNING_MODAL"}
            g = constraints.glyph_at(mx, my)
            if g is not None:
                ob = bpy.data.objects.get(g[0])
                if ob is not None and g[1] < len(ob.cad.constraints) and \
                        ob.cad.constraints[g[1]].kind in VALUE_KINDS:
                    self.dim_edit = g
                    self.typed, self.field = ["", ""], 0
                    self._status(context, self._c_status_text())
                    self.area.tag_redraw()
                    return {"RUNNING_MODAL"}
        if press and et in {"RET", "NUMPAD_ENTER", "RIGHTMOUSE"} and len(self.c_refs) == 1:
            self._dim_create(context)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        return None

    def _dim_draw2d(self, region):
        self._dim_init()
        if self.dim_edit is not None and self.dim_edit[0] == "@sk":
            i = self.dim_edit[1]
            if 0 <= i < len(getattr(self, "skc", ())):
                from . import core
                e = self.skc[i]
                if e["kind"] == "ANGLE":
                    live, name = f"{e['value']:.1f}°", "Açı"
                elif e["kind"] == "RADIUS":
                    dia = e.get("axis") == 1
                    live = core.fmt_len(e["value"] * (2 if dia else 1))
                    name = "Çap" if dia else "Yarıçap"
                else:
                    live, name = core.fmt_len(e["value"]), "Uzunluk"
                val = self.typed[0] + "_" if self.typed[0] else live
                self._draw_rows(self.mouse, [(name, val, True)])
            return
        c = self._dim_constraint()
        if c is None:
            return
        from . import core
        if c.kind == "ANGLE":
            live = f"{math.degrees(c.angle):.1f}°"
            name = "Açı"
        elif c.kind == "RADIUS":
            live = core.fmt_len(c.length * (2 if c.axis == 1 else 1))
            name = "Çap" if c.axis == 1 else "Yarıçap"
        else:
            live = core.fmt_len(c.length)
            name = "Uzaklık" if c.kind in ("PTLINE", "LINEDIST") else "Uzunluk"
        val = self.typed[0] + "_" if self.typed[0] else live
        self._draw_rows(self.mouse, [(name, val, True)])
        s = self.ui_scale
        _text(self.mouse[0] + 14 * s, self.mouse[1] + 12 * s, "Ölçü değeri: yaz, Enter",
              COL_SNAP, int(11 * s))
