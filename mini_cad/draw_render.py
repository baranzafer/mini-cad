"""Ekrana çizim: 3D (POST_VIEW) ve 2D (POST_PIXEL) çizim işleyicileri, ölçü giriş kutusu.

MINICAD_OT_draw (draw.py) bu mixin'den miras alır; metotlar self üzerinden birbirini çağırır.
"""
import bpy
import gpu
import math
import numpy as np

from . import core
from . import drawmath as dm
from .draw_common import (
    COL_ACTIVE, COL_BOX, COL_DONE, COL_GUIDE, COL_REF, COL_RUBBER, COL_SNAP, COL_TEXT,
    MODIFY_TOOLS, PLANE_COLS, _STATE, _axis_col, _dashed, _marker, _poly, _rect, _text,
)


class RenderMixin:
    """Ekrana çizim: 3D (POST_VIEW) ve 2D (POST_PIXEL) çizim işleyicileri, ölçü giriş kutusu."""

    def _draw3d(self):
        if _STATE["active"] is not self or getattr(self, "stop_request", False):
            return
        try:
            region = bpy.context.region
            gpu.state.blend_set("ALPHA")
            gpu.state.depth_test_set("NONE")
            if self.phase in ("PLANE", "OFFSET"):
                self._draw_sketch3d(region)          # taslak seçim sırasında da görünür kalır
            if self.phase == "PLANE":
                self._draw_plane_pick(region)
                gpu.state.blend_set("NONE")
                return
            if self.phase == "OFFSET":
                self._draw_offset3d(region)
                gpu.state.blend_set("NONE")
                return
            self._draw_sketch3d(region)
            self._txt_draw3d(region)
            if self.tool in MODIFY_TOOLS:
                self._draw_modify3d(region)
            if self.grid_on and self.cursor is not None and not self.tool.startswith("C_"):
                self._draw_grid(region)
            for s in self.segs:
                _poly([tuple(p) for p in dm.sample(s, 2 if s["kind"] == "line" else 16)],
                      COL_DONE, 2.5, region)
            for s in self.preview:
                col = COL_GUIDE if s["kind"] == "guide" else COL_RUBBER
                _poly([tuple(p) for p in dm.sample(s, 2 if s["kind"] in ("line", "guide")
                                                   else 24)], col, 2.0, region)
            if self.tool in ("CV", "FIT") and self._anchor() is not None:
                cps = [self._anchor()] + self.stage + ([self.cursor] if self.cursor is not None
                                                       else [])
                if self.tool == "CV" and len(cps) > 1:
                    _poly([tuple(p) for p in cps], COL_REF, 1.2, region)
            if self.tool == "PEN" and self.pen is not None and self.pen["h"] is not None:
                c, h = self.pen["co"], self.pen["h"]
                _poly([tuple(c - h), tuple(c + h)], COL_GUIDE, 1.5, region)
            if self.tool in ("CARC", "CIRCLE") and self.stage and self.cursor is not None:
                _poly([tuple(self.stage[0]), tuple(self.cursor)], COL_REF, 1.2, region)
            pl = self._cur_plane() or self.tmp_plane
            c = self.cursor if self.cursor is not None else (pl.o if pl is not None else None)
            if pl is not None and c is not None and not self.tool.startswith("C_") and \
                    self.tool != "SELECT" and self.tool not in MODIFY_TOOLS:
                o = self._lock_anchor() if self._lock_anchor() is not None else c
                L = 30.0 * self.ui_scale * self._px_size(o)
                _poly([tuple(o), tuple(o + pl.u * L)], _axis_col(pl.u), 1.8, region)
                _poly([tuple(o), tuple(o + pl.v * L)], _axis_col(pl.v), 1.8, region)
            info = self.info
            if info is not None and isinstance(info.get("ref_seg"), int):
                j = info["ref_seg"]
                if 0 <= j < len(self._cur_chords):
                    a, b, _ = self._cur_chords[j]
                    _poly([tuple(a), tuple(b)], COL_REF, 4.0, region)
            if self.tool.startswith("C_"):
                for r in self.c_refs:
                    if r[0] == "seg":
                        _poly([tuple(p) for p in r[4]], COL_DONE, 4.0, region)
                h = self.c_hover
                if h is not None and h[0] == "seg":
                    _poly([tuple(p) for p in h[4]], COL_RUBBER, 4.0, region)
            gpu.state.blend_set("NONE")
        except Exception as e:
            print("[Mini CAD] çizim katmanı hatası:", e)

    def _draw2d(self):
        if _STATE["active"] is not self or getattr(self, "stop_request", False):
            return
        try:
            region = bpy.context.region
            gpu.state.blend_set("ALPHA")
            s = 6.0 * self.ui_scale
            if self.phase == "PLANE":
                S, cands = self._plane_candidates()
                for name, pl in cands:
                    p = self._px(pl.xyz((S * 0.42, S * 0.42)))
                    if p is not None:
                        _text(p[0], p[1], name, PLANE_COLS[name] + (0.55,), int(12 * self.ui_scale))
                self._draw_sketch2d(region)
                ps = getattr(self, "plane_snap", None)
                if ps is not None:                   # noktaya tık: bu noktadan geçen düzlem
                    p = self._px(ps[0])
                    if p is not None:
                        _marker(ps[1], p[0], p[1], s, region)
                        _text(p[0] + 12 * self.ui_scale, p[1] + 10 * self.ui_scale,
                              f"{ps[1]} · bu noktadan geçen düzlem", COL_SNAP,
                              int(11 * self.ui_scale))
                hov = self.hover_plane
                if hov is not None and ps is None:
                    mx, my = self.mouse
                    _text(mx + 14 * self.ui_scale, my + 12 * self.ui_scale,
                          "Gövde yüzü" if hov[0] == "FACE" else dm.PLANE_LABELS[hov[0]],
                          COL_SNAP, int(12 * self.ui_scale))
            if self.tool.startswith("C_"):
                self._dim_draw2d(region)
                for r, col in [(r, COL_DONE) for r in self.c_refs] + \
                        ([(self.c_hover, COL_RUBBER)] if self.c_hover else []):
                    if r[0] == "pt":
                        p = self._px(r[4])
                        if p is not None:
                            _marker("Uç", p[0], p[1], s, region)
            cur = self._px(self.cursor) if self.cursor is not None and \
                not self.tool.startswith("C_") else None
            info = self.info
            if cur is not None and info is not None:
                pl = info.get("plane")
                for kind, ref in info.get("guides", ()):
                    rp = self._px(pl.xyz(ref)) if pl is not None else None
                    if rp is not None:
                        _dashed(rp, cur, COL_GUIDE, region)
                        _poly([(rp[0] - 3, rp[1] - 3), (rp[0] + 3, rp[1] + 3)], COL_GUIDE,
                              1.5, region)
                rs = info.get("ref_seg")
                if rs is not None and isinstance(rs, tuple) and pl is not None:
                    a, b = self._px(pl.xyz(rs[0])), self._px(pl.xyz(rs[1]))
                    if a is not None and b is not None:
                        near = a if math.hypot(a[0] - cur[0], a[1] - cur[1]) < \
                            math.hypot(b[0] - cur[0], b[1] - cur[1]) else b
                        _dashed(near, cur, COL_GUIDE, region)
                anc = self._drag_anchor() if self.sk_drag is not None else self._lock_anchor()
                if info.get("dir") is not None and anc is not None:
                    ap = self._px(anc)
                    if ap is not None and info["kind"] != "Hiza":
                        dx, dy = cur[0] - ap[0], cur[1] - ap[1]
                        ln = math.hypot(dx, dy)
                        if ln > 1:
                            k = 90.0 * self.ui_scale / ln
                            _dashed(cur, (cur[0] + dx * k, cur[1] + dy * k), COL_GUIDE,
                                    region, dash=10, gap=6)
            src = getattr(self, "snap_src", None)
            if cur is not None and src is not None:   # geçici zemin: asıl nokta → izdüşümü
                sp = self._px(src)
                if sp is not None:
                    _dashed(sp, cur, COL_GUIDE, region, dash=4, gap=3)
                    _marker(self.snap_kind or "Uç", sp[0], sp[1], s * 0.7, region)
            if cur is not None and self.snap_kind is not None:
                _marker(self.snap_kind, cur[0], cur[1], s, region)
            if cur is not None:
                label = self.snap_kind or (info["kind"] if info is not None else "")
                if label:
                    _text(cur[0] + 12 * self.ui_scale, cur[1] + 10 * self.ui_scale, label,
                          COL_SNAP, int(11 * self.ui_scale))
                if self.sk_drag is None:
                    self._draw_input(region, cur)
                else:
                    self._draw_drag_input(region, cur)
            st = {"tool": self.tool, "plane": self.plane_mode,
                  "opts": {"auto": getattr(bpy.context.scene, "minicad_auto_constraints", True),
                           "show": getattr(bpy.context.scene, "minicad_show_constraints", True),
                           "snap": self.snap_on, "grid": self.grid_on,
                           "look": getattr(bpy.context.scene, "minicad_look_at", True),
                           "first": getattr(bpy.context.scene, "minicad_pick_plane", True)},
                  "status": "Düzlem seç: eksen düzlemi ya da gövde yüzü" if self.phase == "PLANE"
                  else self.msg,
                  "picking": self.phase in ("PLANE", "OFFSET"),
                  "target": getattr(bpy.context.scene, "minicad_draw_target", "ACTIVE"),
                  "sketch": len(self.sketch)}
            if self.phase == "DRAW" and getattr(self, "temp", None) is not None:
                sc = self.ui_scale
                txt = f"Geçici zemin: {self.temp['label']}  ·  U: normale dön"
                _rect(10 * sc, 10 * sc, 10 * sc + 7.2 * sc * len(txt) + 14 * sc, 34 * sc, COL_BOX)
                _text(17 * sc, 17 * sc, txt, COL_SNAP, int(12 * sc))
            if self.phase == "DRAW":
                self._draw_points2d(region)
                self._skc_draw2d(region)
                self._txt_draw2d(region)
                self._draw_sketch2d(region)
                self._draw_pivot(region)
                self._draw_track2d(region)
                if self.tool in MODIFY_TOOLS:
                    self._draw_modify2d(region)
            if self.phase == "OFFSET":
                self._draw_sketch2d(region)
                self._draw_offset2d(region)
            self._draw_gmenu(region)
            self.palette.draw(region, st)
            gpu.state.blend_set("NONE")
        except Exception as e:
            print("[Mini CAD] çizim etiketi hatası:", e)

    def _draw_input(self, region, cur):
        """Dinamik ölçü: segmentin ortasında uzunluk, imleç yanında ölçü kutusu."""
        anchor = self._lock_anchor()
        pl = self._cur_plane()
        if self._coord_on() and self.cursor is not None and (pl or self.tmp_plane) is not None:
            pl = pl or self.tmp_plane                   # hassas giriş: X / Y
            base = pl.uv(anchor) if anchor is not None else pl.uv(np.zeros(3))
            q = pl.uv(self.cursor)
            names = (("ΔX", q[0] - base[0]), ("ΔY", q[1] - base[1])) if anchor is not None \
                else (("X", q[0] - base[0]), ("Y", q[1] - base[1]))
            rows = []
            for i, (name, live) in enumerate(names):
                txt = self.typed[i]
                val = (txt + ("_" if i == self.field else "")) if txt else core.fmt_len(live)
                rows.append((name, val, i == self.field))
            self._draw_rows(cur, rows)
            return
        if anchor is None or self.cursor is None or pl is None:
            return
        sc = self.ui_scale
        size = int(12 * sc)
        t = self.tool
        arc = self.arc_info
        L = float(np.linalg.norm(self.cursor - anchor))
        ang = dm.seg_angle(pl, anchor, self.cursor)
        rows = []
        if t in ("LINE", "CV", "FIT", "PEN") or (t == "TARC" and arc is None):
            mid = self._px(0.5 * (anchor + self.cursor))
            if mid is not None:
                _text(mid[0] + 6 * sc, mid[1] + 6 * sc, core.fmt_len(L), COL_TEXT, size)
            ap = self._px(anchor)
            if ap is not None:
                _text(ap[0] + 8 * sc, ap[1] - 16 * sc, f"{ang:.1f}°", COL_TEXT, size)
            names = (("Uzunluk", core.fmt_len(L)), ("Açı", f"{ang:.1f}°"))
        elif t == "CIRCLE":
            R = arc["radius"] if arc else L
            names = (("Yarıçap", core.fmt_len(R)),)
        elif t in ("RECT3", "RECTC", "RECT3C", "POLYGON", "SLOTCC", "SLOTO", "SLOTC",
                   "ARCSLOT", "ELLIPSE"):
            rows = list(getattr(self, "shape_rows", None) or [])
            names = ()
            if rows:
                self._draw_rows(cur, rows)
            return
        elif t == "RECT":
            a, q = pl.uv(anchor), pl.uv(self.cursor)
            names = (("Genişlik", core.fmt_len(abs(q[0] - a[0]))),
                     ("Yükseklik", core.fmt_len(abs(q[1] - a[1]))))
        else:
            names = ()
            if arc is not None and "angle" in arc:
                rows = [("R", core.fmt_len(arc["radius"]), False),
                        ("Yay", f"{math.degrees(arc['angle']):.1f}°", False)]
            elif t in ("ARC3", "CARC"):
                step = {"ARC3": ["bitiş noktası", "eğrilik noktası"],
                        "CARC": ["merkez", "bitiş"]}[t][min(len(self.stage), 1)]
                rows = [("Sıradaki", step, False)]
        for i, (name, live) in enumerate(names):
            txt = self.typed[i]
            val = (txt + ("_" if i == self.field else "")) if txt else live
            rows.append((name, val, i == self.field))
        self._draw_rows(cur, rows)

    def _draw_rows(self, cur, rows):
        """İmleç yanında ölçü kutusu: [(ad, değer, etkin alan mı)]."""
        if not rows:
            return
        sc = self.ui_scale
        size = int(12 * sc)
        x = cur[0] + 18 * sc
        y = cur[1] - 22 * sc
        h = 18 * sc
        w = 175 * sc
        _rect(x - 6 * sc, y - h * (len(rows) - 1) - 6 * sc, x + w, y + h - 2 * sc, COL_BOX)
        for k, (name, val, active) in enumerate(rows):
            yy = y - k * h
            _text(x, yy, ("> " if active else "  ") + name, COL_ACTIVE if active else COL_TEXT,
                  size)
            _text(x + 80 * sc, yy, val, COL_ACTIVE if (active and self.typed[min(k, 1)])
                  else COL_TEXT, size)
