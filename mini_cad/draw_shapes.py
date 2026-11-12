"""Oluştur araçları (Inventor 2D gibi) — Aşama 3:

  Dikdörtgen    3 noktalı (kenar, genişlik) · merkezden (merkez, köşe) · 3 noktalı merkezden
                (merkez, kenar ortası, köşe). R'ye tekrar basınca türler arasında geçilir.
  Çokgen        merkez → köşe (iç teğet) ya da kenar ortası (dış teğet; D ile değişir);
                Kenar sayısı yazılır (Tab), varsayılan 6.
  Kanal         merkezden merkeze · toplam boy · merkez noktalı · 3 noktalı yay kanal;
                son tıkta genişlik (yazılabilir).
  Elips         merkez → 1. eksen ucu → 2. yarı eksen.
  Teğet daire   üç doğruya tıkla: üçüne teğet daire (iç teğet). O'ya tekrar basınca
                Daire → Teğet daire → Elips.
  Nokta         tıklanan yere nokta (yakalanır, Bitir'de tek noktalı spline olarak yazılır).
  Yansıt        CAD gövde kenarına ya da tel kafes eğrisine tıkla: çizim düzlemine
                izdüşümü taslağa eklenir.

Çok tıklamalı şekiller çizimin normal akışını kullanır (draw_sketch._place / draw_snap
._make_preview), her tıkta bütün yakalamalar geçerlidir. Matematik shapemath.py'de.
"""
import math
import numpy as np

from . import drawmath as dm
from . import shapemath as shm
from . import sketchmath as sm
from .draw_common import (
    CLICK_SHAPES, COL_GUIDE, COL_RUBBER, COL_SNAP, _marker, _poly, _project, _seg_px_dist,
    _text, parse_angle, parse_length,
)

SHAPE_NAMES = {
    "RECT3": "Dikdörtgen (3 nokta)", "RECTC": "Dikdörtgen (merkezden)",
    "RECT3C": "Dikdörtgen (3 nokta, merkezden)", "POLYGON": "Çokgen",
    "SLOTCC": "Kanal (merkezden merkeze)", "SLOTO": "Kanal (toplam boy)",
    "SLOTC": "Kanal (merkez noktalı)", "ARCSLOT": "Yay kanal (3 nokta)",
    "SLOTARCC": "Yay kanal (merkez noktalı)", "ELLIPSE": "Elips",
}
STEPS = {
    "RECT3": ["1. köşe", "kenarın ucu (uzunluk / açı yazılabilir)", "genişlik"],
    "RECTC": ["merkez", "köşe (genişlik / yükseklik yazılabilir)"],
    "RECT3C": ["merkez", "kenar ortası (yön)", "köşe (genişlik)"],
    "POLYGON": ["merkez", "köşe / kenar ortası (yarıçap, kenar sayısı yazılabilir; D: iç / dış)"],
    "SLOTCC": ["1. yay merkezi", "2. yay merkezi", "genişlik"],
    "SLOTO": ["1. uç", "2. uç", "genişlik"],
    "SLOTC": ["kanal merkezi", "yay merkezi", "genişlik"],
    "ARCSLOT": ["yay başlangıcı", "yay bitişi", "yay üzerinde bir nokta", "genişlik"],
    "SLOTARCC": ["yay merkezi", "yay başlangıcı", "yay bitişi (D: yön)", "genişlik"],
    "ELLIPSE": ["merkez", "1. eksen ucu", "2. yarı eksen"],
}
NEEDED = {"RECT3": 3, "RECTC": 2, "RECT3C": 3, "POLYGON": 2, "SLOTCC": 3, "SLOTO": 3,
          "SLOTC": 3, "ARCSLOT": 4, "SLOTARCC": 4, "ELLIPSE": 3}
PICK_HELP = {
    "CIRCT": "Teğet daire: üç doğruya tıkla, sonra imleci istediğin teğet dairenin yerine "
             "götürüp tıkla (Backspace: son seçimi geri al)",
    "PROJECT": "Yansıt: CAD gövde kenarına ya da tel kafes eğrisine tıkla; çizim düzlemine "
               "izdüşümü taslağa eklenir",
    "POINT": "Nokta: tıkla (uç / orta / merkez / ızgara yakalaması geçerli)",
}


def _len_rows(names_vals, typed, field):
    rows = []
    for i, (name, live) in enumerate(names_vals):
        txt = typed[i] if i < 2 else ""
        val = (txt + ("_" if i == field else "")) if txt else live
        rows.append((name, val, i == field))
    return rows


class ShapeMixin:
    """Çok tıklamalı şekiller, teğet daire, nokta, geometri yansıtma."""

    def _sh_init(self):
        for k, v in (("poly_n", 6), ("poly_inner", True), ("sk_points", None), ("ct_lines", None),
                     ("pk", None), ("shape_rows", None)):
            if not hasattr(self, k) or (getattr(self, k) is None and v is not None):
                setattr(self, k, v)
        if self.sk_points is None:
            self.sk_points = []
        if self.ct_lines is None:
            self.ct_lines = []

    # ------------------------------------------------------------ çok tıklamalı şekiller

    def _sh_lock(self, plane, anchor, cur, length=None, angle=None):
        """Yazılan uzunluk / açıyı imlece uygula (çizimdeki gibi)."""
        if length is None and angle is None:
            return cur
        return dm.apply_locks(plane, anchor, cur, length, angle)

    def _sh_width_point(self, plane, a, b, cur, w_full):
        """Yazılan genişlik: imlecin tarafında a-b'ye dik w_full/2 uzaklık."""
        if w_full is None:
            return cur
        d = dm.unit((b - a) - plane.n * float(np.dot(b - a, plane.n)))
        if d is None:
            return cur
        nr = np.cross(plane.n, d)
        side = 1.0 if float(np.dot(cur - b, nr)) >= 0 else -1.0
        return b + nr * side * (w_full / 2.0)

    def _shape_preview(self, plane):
        """Çok tıklamalı şekillerin önizlemesi; imleç yazılan değerlerle kilitlenir."""
        self._sh_init()
        t = self.tool
        st = self.stage
        cur = self.cursor
        self.preview, self.shape_rows, self.arc_info = [], None, None
        if not st:
            return
        from . import core
        typed = self.typed
        v0 = parse_length(typed[0]) if typed[0] else None
        k = len(st)
        segs, rows, autos = None, [], None
        if t in ("RECT3", "SLOTCC", "SLOTO", "SLOTC", "ELLIPSE", "ARCSLOT", "RECT3C") and k == 1:
            a1 = parse_angle(typed[1]) if typed[1] else None
            cur = self._sh_lock(plane, st[0], cur, v0, a1)
            L = float(np.linalg.norm(cur - st[0]))
            ang = dm.seg_angle(plane, st[0], cur)
            rows = _len_rows([("Uzunluk", core.fmt_len(L)), ("Açı", f"{ang:.1f}°")], typed,
                             self.field)
            if L > 1e-12:
                g = dm.line_seg(st[0], cur)
                g["kind"] = "guide"
                self.preview = [g]
            self.cursor = cur
            self.shape_rows = rows
            return
        if t == "RECT3":
            cur = self._sh_width_point(plane, st[0], st[1], cur, v0)
            segs = shm.rect3(st[0], st[1], cur, plane)
            w = shm.width_of(st[0], st[1], cur, plane)
            rows = _len_rows([("Genişlik", core.fmt_len(w))], typed, self.field)
            autos = "rect"
        elif t == "RECTC":
            a, q = plane.uv(st[0]), plane.uv(cur)
            du, dv = q[0] - a[0], q[1] - a[1]
            v1 = parse_length(typed[1]) if typed[1] else None
            if v0 is not None:
                du = math.copysign(v0 / 2.0, du if du else 1.0)
            if v1 is not None:
                dv = math.copysign(v1 / 2.0, dv if dv else 1.0)
            cur = plane.xyz((a[0] + du, a[1] + dv)) + plane.n * plane.dist(st[0])
            segs = shm.rect_center(st[0], cur, plane)
            rows = _len_rows([("Genişlik", core.fmt_len(abs(du) * 2)),
                              ("Yükseklik", core.fmt_len(abs(dv) * 2))], typed, self.field)
            autos = "rect"
        elif t == "RECT3C":
            cur = self._sh_width_point(plane, st[0], st[1], cur, v0)
            if v0 is not None:                    # yazılan: tam genişlik, merkezden
                cur = cur + (st[0] - st[1])
            segs = shm.rect3_center(st[0], st[1], cur, plane)
            w = shm.width_of(st[0], st[1], cur, plane) * 2
            rows = _len_rows([("Genişlik", core.fmt_len(w))], typed, self.field)
            autos = "rect"
        elif t == "POLYGON":
            if typed[1]:
                try:
                    self.poly_n = max(3, min(64, int(float(typed[1].replace(",", ".")))))
                except ValueError:
                    pass
            if v0 is not None:
                d = dm.unit((cur - st[0]) - plane.n * float(np.dot(cur - st[0], plane.n)))
                if d is not None:
                    cur = st[0] + d * v0
            segs = shm.polygon(st[0], cur, self.poly_n, plane, self.poly_inner)
            r = float(np.linalg.norm(cur - st[0]))
            rows = _len_rows([("Yarıçap", core.fmt_len(r)), ("Kenar", str(self.poly_n))],
                             typed, self.field)
            rows.append(("Tür", "iç teğet (D)" if self.poly_inner else "dış teğet (D)", False))
        elif t in ("SLOTCC", "SLOTO", "SLOTC"):
            cur = self._sh_width_point(plane, st[0], st[1], cur, v0)
            r = shm.width_of(st[0], st[1], cur, plane)
            fn = {"SLOTCC": shm.slot_cc, "SLOTO": shm.slot_overall, "SLOTC": shm.slot_center}[t]
            segs = fn(st[0], st[1], r, plane)
            rows = _len_rows([("Genişlik", core.fmt_len(2 * r))], typed, self.field)
        elif t == "ELLIPSE":
            cur = self._sh_width_point(plane, st[0], st[1], cur, None if v0 is None else 2 * v0)
            segs = shm.ellipse(st[0], st[1], cur, plane)
            b = shm.width_of(st[0], st[1], cur, plane)
            rows = _len_rows([("2. yarı eksen", core.fmt_len(b))], typed, self.field)
        elif t == "SLOTARCC":
            if k == 1:
                R = float(np.linalg.norm(cur - st[0]))
                g = dm.line_seg(st[0], cur)
                g["kind"] = "guide"
                self.preview = [g]
                self.shape_rows = [("R", core.fmt_len(R), False)]
                self.cursor = cur
                return
            if k == 2:
                arc = dm.center_arc(st[0], st[1], cur, plane.n, self.carc_flip)
                if arc is not None:
                    self.preview = list(arc["segs"])
                    self.shape_rows = [("R", core.fmt_len(arc["radius"]), False),
                                       ("Yay", f"{math.degrees(arc['angle']):.1f}°", False)]
                return
            arc = dm.center_arc(st[0], st[1], st[2], plane.n, self.carc_flip)
            if arc is not None:
                d = float(np.linalg.norm(cur - st[0]))
                r = abs(d - arc["radius"]) if v0 is None else v0 / 2.0
                segs = shm.arc_slot_center(st[0], st[1], st[2], r, plane, self.carc_flip)
                rows = _len_rows([("Genişlik", core.fmt_len(2 * r))], typed, self.field)
        elif t == "ARCSLOT":
            if k == 2:
                arc = dm.arc_3pt(st[0], cur, st[1])
                if arc is not None:
                    self.preview = list(arc["segs"])
                    self.arc_info = arc
                    rows = [("R", core.fmt_len(arc["radius"]), False)]
                self.shape_rows = rows
                return
            arc = dm.arc_3pt(st[0], st[2], st[1])
            if arc is not None:
                d = float(np.linalg.norm(cur - arc["center"]))
                r = abs(d - arc["radius"]) if v0 is None else v0 / 2.0
                segs = shm.arc_slot(st[0], st[1], st[2], r, plane)
                rows = _len_rows([("Genişlik", core.fmt_len(2 * r))], typed, self.field)
        self.cursor = cur
        self.shape_rows = rows
        if segs:
            if t == "ELLIPSE":
                g = sm.new_grp()
                for sg in segs:
                    sg["grp"] = g
            if autos == "rect":
                self._sh_rect_autos(segs, plane)
            self.preview = segs

    def _sh_rect_autos(self, segs, plane):
        """Dikdörtgen kenarları: eksene hizalıysa yatay / dikey, değilse dik / paralel."""
        AX = {"XY": (0, 1), "XZ": (0, 2), "YZ": (1, 2)}
        d0 = dm.unit(np.asarray(segs[0]["p"][3]) - np.asarray(segs[0]["p"][0]))
        if plane.name in AX and d0 is not None:
            au, av = AX[plane.name]
            u, v = np.zeros(3), np.zeros(3)
            u[au], v[av] = 1.0, 1.0
            if abs(abs(float(np.dot(d0, u))) - 1.0) < 1e-9:
                for i, sg in enumerate(segs):
                    sg["auto"] = [("AXIS", au if i % 2 == 0 else av)]
                return
            if abs(abs(float(np.dot(d0, v))) - 1.0) < 1e-9:
                for i, sg in enumerate(segs):
                    sg["auto"] = [("AXIS", av if i % 2 == 0 else au)]
                return
        autos = [[], [("REF", "PERP", ("chain", 0))], [("REF", "PARALLEL", ("chain", 0))],
                 [("REF", "PARALLEL", ("chain", 1))]]
        for sg, a in zip(segs, autos):
            sg["auto"] = a

    def _sh_place(self, context, cur):
        """Çok tıklamalı şekil: tık sayısı dolunca taslağa yazılır. True: işlendi."""
        t = self.tool
        if len(self.stage) + 1 < NEEDED[t]:
            self.stage.append(np.asarray(cur, dtype=np.float64).copy())
            self.typed, self.field = ["", ""], 0
            self._status(context, f"{SHAPE_NAMES[t]}: {STEPS[t][len(self.stage)]}")
            return True
        if not self.preview or self.preview[0].get("kind") == "guide" or \
                (t in ("ARCSLOT", "SLOTARCC") and len(self.stage) < 3):
            return True
        segs = [dict(s) for s in self.preview]
        self._write_shape(context, segs)
        self.stage, self.shape_plane = [], None
        self.typed, self.field = ["", ""], 0
        return True

    # ------------------------------------------------------------ nokta

    def _sh_point(self, context, cur):
        self._sh_init()
        self.sk_points.append(np.asarray(cur, dtype=np.float64).copy())
        self.dirty = True
        self._status(context, f"Nokta eklendi ({len(self.sk_points)} nokta) · Bitir ile "
                              "kaydedilir")

    # ------------------------------------------------------------ teğet daire / yansıt

    def _pk_plane(self):
        if self.plane_mode == "LOCK" and self.locked is not None:
            return self.locked
        return self.tmp_plane or self._make_plane(self.plane_mode, np.zeros(3))

    def _pk_line_at(self, mx, my):
        """İmlecin altındaki doğru (taslak, tel kafes ya da gövde kenarı): (a, b) ya da None."""
        M = np.array(self.rv3d.perspective_matrix, dtype=np.float64)
        m = np.array([mx, my], dtype=np.float64)
        cands = list(self.refs.chords)
        if not cands:
            return None
        A = np.array([c[0] for c in cands])
        B = np.array([c[1] for c in cands])
        pa, oka, _ = _project(A, M, self.region)
        pb, okb, _ = _project(B, M, self.region)
        d, _ = _seg_px_dist(pa, pb, m)
        d = np.where(oka & okb, d, np.inf)
        i = int(np.argmin(d))
        if d[i] > self.radius:
            return None
        return np.asarray(cands[i][0], dtype=np.float64), np.asarray(cands[i][1], dtype=np.float64)

    def _pk_edges(self):
        """Yansıtılabilecek eğriler: [(çoklu çizgi, bezier noktaları ya da None, kapalı mı)]."""
        out = []
        try:
            import bpy
            from . import core
            for ob in bpy.context.visible_objects:
                if ob.type == "MESH" and ob.cad.is_cad:
                    for E in core._display.get(ob.name, {}).get("edges") or ():
                        P = np.asarray(E, dtype=np.float64)
                        if len(P) >= 2:
                            out.append((P, None, False))
        except Exception:
            pass
        for name, si, i, S in getattr(self.refs, "wsegs", ()):
            P = None
            try:
                import bpy
                from . import core
                ob = bpy.data.objects.get(name)
                sp = ob.data.splines[si]
                g = core._spline_segment(ob, si, sp, i, ob.matrix_world)
                if g is not None:
                    P = [np.array(tuple(v), dtype=np.float64) for v in g["p"]]
            except Exception:
                P = None
            out.append((np.asarray(S, dtype=np.float64), P, False))
        return out

    def _pk_update(self, context, mx, my):
        self._sh_init()
        self.mouse = (mx, my)
        self.cursor, self.preview, self.info, self.snap_kind = None, [], None, None
        self.pk = None
        t = self.tool
        if t == "CIRCT":
            ln = self._pk_line_at(mx, my) if len(self.ct_lines) < 3 else None
            lines = list(self.ct_lines) + ([ln] if ln is not None else [])
            self.pk = {"hover": ln, "circle": None}
            if len(lines) == 3:
                hint = None
                if len(self.ct_lines) == 3:          # yerleştirme: imlece en yakın çözüm
                    ro, rd = self._ray(mx, my)
                    pl0 = self._pk_plane().moved(self.ct_lines[0][0])
                    hint = pl0.ray_hit(ro, rd)
                res = shm.tangent_circle_3lines(lines, self._pk_plane(), hint)
                if res is not None:
                    c, R = res
                    pl = dm.Plane.from_normal(c, self._pk_plane().n, "C",
                                              u_hint=self._pk_plane().u)
                    self.pk["circle"] = (c, R, dm.circle(c, R, pl))
            return
        if t == "PROJECT":
            M = np.array(self.rv3d.perspective_matrix, dtype=np.float64)
            m = np.array([mx, my], dtype=np.float64)
            best = None
            for P, B, closed in self._pk_edges():
                px, ok, _ = _project(P, M, self.region)
                if not ok.all():
                    continue
                d, _ = _seg_px_dist(px[:-1], px[1:], m)
                j = float(d.min())
                if j <= self.radius and (best is None or j < best[0]):
                    best = (j, P, B)
            if best is None:
                return
            _, P, B = best
            pl = self._pk_plane()
            if B is not None:
                Q = shm.project_bezier(B, pl)
                kind = "line" if dm.is_straight_poly(dm.sample({"p": Q}, 9)) else "curve"
                arc = dm.arc_of_bezier(list(Q)) if kind == "curve" else None
                seg = dm.line_seg(Q[0], Q[3]) if kind == "line" else \
                    {"kind": "arc" if arc is not None else "curve", "p": tuple(Q)}
                segs, closed = [seg], False
            else:
                segs, closed = shm.segs_from_poly(shm.project_poly(P, pl))
            if segs:
                g = sm.new_grp()
                if len(segs) > 1 and segs[0]["kind"] != "line":
                    for sg in segs:
                        sg["grp"] = g
                self.pk = {"segs": segs, "closed": closed, "src": P}

    def _pk_event(self, context, event, mx, my, press):
        self._sh_init()
        et = event.type
        if et in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            self._pk_update(context, mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if et == "LEFTMOUSE":
            if not press:
                return {"RUNNING_MODAL"}
            self._pk_update(context, mx, my)
            pk = self.pk or {}
            if self.tool == "CIRCT":
                if len(self.ct_lines) < 3:
                    if pk.get("hover") is not None:
                        self.ct_lines.append(pk["hover"])
                    n_ = len(self.ct_lines)
                    self._status(context, f"Teğet daire: {n_}/3 doğru seçildi" + (
                        " · imleci istediğin teğet dairenin yerine götürüp tıkla" if n_ == 3
                        else ""))
                elif len(self.ct_lines) == 3:
                    if pk.get("circle") is not None:
                        c, R, segs = pk["circle"]
                        self._write_shape(context, [dict(s) for s in segs])
                        from . import core
                        self._status(context, f"Teğet daire: R {core.fmt_len(R)} · taslağa "
                                              "eklendi")
                    else:
                        self._status(context, "Teğet daire: bu üç doğruya teğet daire yok "
                                              "(paralel doğrular?)")
                    self.ct_lines = []
            elif self.tool == "PROJECT" and pk.get("segs"):
                st = {"segs": [dict(s) for s in pk["segs"]], "cyclic": pk["closed"],
                      "node_ids": {}, "start_tan": None}
                self._set_sketch(context, self.sketch + [st],
                                 "Yansıtıldı: çizim düzlemine izdüşüm taslağa eklendi")
            self._pk_update(context, mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if not press:
            return {"RUNNING_MODAL"} if et == "RIGHTMOUSE" else None
        if et == "BACK_SPACE" and self.tool == "CIRCT" and self.ct_lines:
            self.ct_lines.pop()
            self._pk_update(context, mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if et == "RIGHTMOUSE":
            self.ct_lines = []
            self._pk_update(context, mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if (event.unicode or "") and (event.unicode or "") in "0123456789.,":
            return {"RUNNING_MODAL"}
        return None

    # ------------------------------------------------------------ çizim

    def _pk_draw3d(self, region):
        self._sh_init()
        pk = self.pk or {}
        for a, b in self.ct_lines:
            _poly([tuple(a), tuple(b)], COL_GUIDE, 4.0, region)
        if pk.get("hover") is not None:
            a, b = pk["hover"]
            _poly([tuple(a), tuple(b)], COL_RUBBER, 3.0, region)
        if pk.get("circle") is not None:
            for sg in pk["circle"][2]:
                _poly([tuple(p) for p in dm.sample(sg, 20)], COL_RUBBER, 2.2, region)
        if pk.get("segs"):
            _poly([tuple(p) for p in pk["src"]], COL_GUIDE, 3.0, region)
            for sg in pk["segs"]:
                _poly([tuple(p) for p in dm.sample(sg, 2 if sg["kind"] == "line" else 20)],
                      COL_RUBBER, 2.2, region)

    def _pk_draw2d(self, region):
        s = self.ui_scale
        mx, my = self.mouse
        label = ""
        if self.tool == "CIRCT":
            label = f"Teğet daire: {len(self.ct_lines)}/3 doğru" if len(self.ct_lines) < 3 else \
                "Teğet daire: yerine götür, tıkla"
        elif self.tool == "PROJECT":
            label = "Yansıt" if (self.pk or {}).get("segs") else "Yansıt: kenara gel"
        _text(mx + 14 * s, my + 12 * s, label, COL_SNAP, int(11 * s))

    def _draw_points2d(self, region):
        self._sh_init()
        s = self.ui_scale
        for p in self.sk_points:
            q = self._px(p)
            if q is not None:
                _poly([(q[0] - 5 * s, q[1]), (q[0] + 5 * s, q[1])], (0.55, 0.85, 1.0, 0.95), 2.0,
                      region)
                _poly([(q[0], q[1] - 5 * s), (q[0], q[1] + 5 * s)], (0.55, 0.85, 1.0, 0.95), 2.0,
                      region)
