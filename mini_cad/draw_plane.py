"""Çalışma düzlemi: ışın / piksel yardımcıları, düzlem seçimi (1/2 yön, 2/2 yükseklik),
ızgara ve ızgara yakalaması, düzleme bakış.

MINICAD_OT_draw (draw.py) bu mixin'den miras alır; metotlar self üzerinden birbirini çağırır.
"""
import bpy
import gpu
import math
import numpy as np
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

from . import core
from . import drawmath as dm
from .draw_common import (
    COL_ACTIVE, COL_BOX, COL_GRID, COL_GUIDE, COL_SNAP, COL_TEXT, GRID_MIN_PX, GRID_PX,
    MODIFIERS, PLANE_COLS, SHAPE_TOOLS, _Refs, _axis_col, _dashed, _marker, _poly, _rect, _text,
    parse_length,
)


class PlaneMixin:
    """Çalışma düzlemi: ışın / piksel yardımcıları, düzlem seçimi (1/2 yön, 2/2 yükseklik),
    ızgara ve ızgara yakalaması, düzleme bakış."""

    def _ray(self, mx, my):
        ro = view3d_utils.region_2d_to_origin_3d(self.region, self.rv3d, (mx, my))
        rd = view3d_utils.region_2d_to_vector_3d(self.region, self.rv3d, (mx, my))
        return np.array(ro), np.array(rd)

    def _view_dir(self):
        return np.array(self.rv3d.view_matrix.inverted().to_3x3() @ Vector((0, 0, -1)))

    def _view_right(self):
        return np.array(self.rv3d.view_matrix.inverted().to_3x3() @ Vector((1, 0, 0)))

    def _px(self, p):
        v = view3d_utils.location_3d_to_region_2d(self.region, self.rv3d, Vector(tuple(p)))
        return None if v is None else (v.x, v.y)

    def _px_size(self, p):
        """p derinliğinde 1 pikselin dünya boyu."""
        a = self._px(p)
        r = self._view_right()
        d = max(self.rv3d.view_distance * 0.01, 1e-6)
        b = self._px(np.asarray(p) + r * d)
        if a is None or b is None:
            return d / 100.0
        pix = math.hypot(b[0] - a[0], b[1] - a[1])
        return d / max(pix, 1e-6)

    def _make_plane(self, mode, origin, face_normal=None):
        if mode == "LOCK" and self.locked is not None:
            return self.locked
        if mode in dm.AXIS_PLANES:
            return dm.Plane.axis(mode, origin)
        if mode == "VIEW":
            return dm.Plane.from_normal(origin, -self._view_dir(), "VIEW",
                                        u_hint=self._view_right())
        if face_normal is not None:
            return dm.Plane.from_normal(origin, face_normal, "FACE")
        return dm.Plane.axis(dm.auto_axis_plane(self._view_dir()), origin)

    def _extra_pts(self):
        out = []
        if self.start is not None:
            out.append((self.start, "Başlangıç" if self.segs else "Uç"))
        for s in self.segs[:-1]:
            out.append((s["p"][3], "Uç"))
        for p in self.stage:
            out.append((p, "Uç"))
        return out

    def _cur_plane(self):
        if self.tool in SHAPE_TOOLS and self.shape_plane is not None:
            return self.shape_plane
        return self.plane

    def _grid_step(self, p):
        try:
            base = float(bpy.context.space_data.overlay.grid_scale) or 1.0
        except Exception:
            base = 1.0
        need = GRID_MIN_PX * self.ui_scale * self._px_size(p)
        k = math.ceil(math.log10(max(need / base, 1e-12)))
        return base * (10.0 ** k)

    def _grid_snap(self, plane, p, info):
        """Izgaraya zayıf yakalama: her eksen ayrı ayrı, sadece kılavuzun serbest bıraktığı
        eksenlerde. (yeni nokta, yakalandı mı)"""
        lock_u = lock_v = False
        if info is not None:
            kind = (info.get("kind") or "").split(" + ")[0]
            if kind == "Yatay":
                lock_v = True
            elif kind == "Dikey":
                lock_u = True
            elif kind == "Hiza":
                for g, _ in info.get("guides", ()):
                    lock_u |= g == "V"
                    lock_v |= g == "H"
            else:
                return p, False
            if info.get("guides") and kind in ("Yatay", "Dikey"):
                return p, False
        gs = self._grid_step(p)
        tol = GRID_PX * self.ui_scale * self._px_size(p)
        q = list(plane.uv(p))
        g0 = plane.uv(self._grid_origin())
        hit = False
        for ax, locked in ((0, lock_u), (1, lock_v)):
            if locked:
                continue
            n = g0[ax] + round((q[ax] - g0[ax]) / gs) * gs
            if abs(n - q[ax]) <= tol:
                q[ax] = n
                hit = True
        if not hit:
            return p, False
        return plane.xyz(q) + plane.n * plane.dist(p), True

    def _plane_candidates(self):
        S = max(self.rv3d.view_distance * 0.35, 1e-4)
        return S, [(n, dm.Plane.axis(n, (0.0, 0.0, 0.0))) for n in ("XY", "XZ", "YZ")]

    def _hover_plane(self, context, mx, my):
        ro, rd = self._ray(mx, my)
        S, cands = self._plane_candidates()
        best = None
        for name, pl in cands:
            hit = pl.ray_hit(ro, rd)
            if hit is None:
                continue
            t = float(np.dot(hit - ro, rd))
            u, v = pl.uv(hit)
            if t > 0 and abs(u) <= S / 2 and abs(v) <= S / 2 and (best is None or t < best[0]):
                best = (t, name, pl, None)
        try:
            ok, loc, nor, _i, obj, _m = context.scene.ray_cast(
                context.evaluated_depsgraph_get(), Vector(tuple(ro)), Vector(tuple(rd)))
            if ok and obj is not None and obj.type == "MESH" and \
                    obj.display_type in ("SOLID", "TEXTURED"):
                t = float(np.dot(np.array(loc) - ro, rd))
                if best is None or t < best[0]:
                    pl = dm.Plane.from_normal(np.array(loc), np.array(nor), "FACE")
                    best = (t, "FACE", pl, obj.name)
        except Exception:
            pass
        self.hover_plane = None if best is None else (best[1], best[2], best[3])

    def _lock_plane(self, context, name, plane):
        self.locked = plane
        self.plane_mode = "LOCK"
        self.phase = "DRAW"
        self.hover_plane = None
        a = self._anchor()
        self.plane = plane.moved(a) if a is not None else None
        if getattr(context.scene, "minicad_look_at", True):
            self._look_at(plane)
        self._status(context, f"Çizim düzlemi: {dm.PLANE_LABELS.get(name, name)}")

    def _look_at(self, plane):
        try:
            from mathutils import Matrix
            M = Matrix((tuple(plane.u), tuple(plane.v), tuple(plane.n))).transposed()
            loc = np.array(self.rv3d.view_location)
            loc = loc - plane.n * float(np.dot(loc - plane.o, plane.n))
            self.rv3d.view_rotation = M.to_quaternion()
            self.rv3d.view_location = Vector(tuple(loc))
        except Exception as e:
            print("[Mini CAD] görünüm çevrilemedi:", e)

    def _set_plane(self, mode):
        self.temp = self.temp_pick = None          # açık düzlem seçimi: geçici zemin biter
        if mode == "PICK":
            self.phase = "PLANE"
            self.hover_plane = None
            return
        if mode != "LOCK":
            self.locked = None
        self.phase = "DRAW"
        self.plane_mode = mode
        a = self._anchor()
        if a is not None:
            self.plane = self._make_plane(mode, a)
        if self.shape_plane is not None:
            self.shape_plane = self._make_plane(mode, self.shape_plane.o)

    def _modal_plane(self, context, event, mx, my, press):
        """Inventor gibi: çizime başlamadan önce düzlem seçimi."""
        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            old = self.hover_plane
            self._update(context, mx, my)
            if (old is None) != (self.hover_plane is None) or (
                    old is not None and self.hover_plane is not None and
                    (old[0], old[2]) != (self.hover_plane[0], self.hover_plane[2])) or \
                    (self.hover_plane is not None and self.hover_plane[0] == "FACE"):
                self.area.tag_redraw()
            return {"PASS_THROUGH"}
        if not press:
            return {"RUNNING_MODAL"} if event.type in {"LEFTMOUSE", "RIGHTMOUSE"} \
                else {"PASS_THROUGH"}
        if event.type == "LEFTMOUSE":
            self._update(context, mx, my)
            ps = getattr(self, "plane_snap", None)
            if ps is not None:                    # noktaya tık: yön + o noktanın yüksekliği
                if self.hover_plane is not None:
                    name, base = self.hover_plane[0], self.hover_plane[1]
                else:
                    base = self._base_plane()
                    name = base.name
                self._start_offset(context, name, base)
                t = float(np.dot(ps[0] - base.o, base.n))
                self.off.update(t=t, kind=ps[1] + " yüksekliği", snap=ps[0], snap_kind=ps[1])
                self.plane_snap = None
                self._accept_offset(context)
            elif self.hover_plane is not None:
                name, pl, _obj = self.hover_plane
                self._start_offset(context, name, pl)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type in {"RIGHTMOUSE", "RET", "NUMPAD_ENTER", "SPACE"} and \
                getattr(self, "temp_pick", None) is not None:
            base = self._base_plane()               # yön aynı kalır, sadece yükseklik
            self._start_offset(context, base.name, base)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type in {"RIGHTMOUSE", "RET", "NUMPAD_ENTER", "SPACE"}:
            self.phase = "DRAW"
            self.hover_plane = None
            self._status(context, "Düzlem: otomatik")
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type in {"X", "Y", "Z"} and not event.ctrl:
            name = {"X": "YZ", "Y": "XZ", "Z": "XY"}[event.type]
            self._start_offset(context, name, dm.Plane.axis(name, (0.0, 0.0, 0.0)))
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type == "V" and not event.ctrl and getattr(self, "temp_pick", None) is not None:
            self._start_offset(context, "VIEW", self._make_plane("VIEW", np.zeros(3)))
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type == "V" and not event.ctrl:
            self._set_plane("VIEW")
            self._status(context, "Düzlem: görünüş")
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.unicode and event.unicode.isdigit():
            return {"RUNNING_MODAL"}
        return {"PASS_THROUGH"}

    def _start_offset(self, context, name, plane):
        self.off = {"name": name, "base": plane, "t": 0.0, "kind": None}
        self.phase = "OFFSET"
        self.hover_plane = None
        self.typed, self.field = ["", ""], 0
        self._status(context)

    def _signed_len(self, txt):
        t = txt.strip()
        neg = t.startswith("-")
        v = parse_length(t[1:] if neg else t)
        return None if v is None else (-v if neg else v)

    def _offset_update(self, context, mx, my):
        self.mouse = (mx, my)
        off = self.off
        base = off["base"]
        o, n = base.o, base.n
        ro, rd = self._ray(mx, my)
        rd = rd / max(float(np.linalg.norm(rd)), 1e-15)
        w0 = ro - o
        b = float(np.dot(rd, n))
        den = 1.0 - b * b
        t = float(np.dot(w0, n) - b * np.dot(w0, rd)) / den if den > 1e-9 else off["t"]
        off["kind"] = None
        off["snap"] = off["snap_kind"] = None
        typed = self._signed_len(self.typed[0]) if self.typed[0] else None
        t_main = self._main_height(base)
        if typed is not None:
            t, off["kind"] = typed, "Yazılan"
        elif not self.ctrl:
            snap = self._point_snap(mx, my, ro, rd)
            p = o + n * t
            tol = GRID_PX * self.ui_scale * self._px_size(p)
            if snap is not None:
                t = float(np.dot(np.asarray(snap[0]) - o, n))
                off["kind"] = snap[1] + " yüksekliği"
                off["snap"] = np.asarray(snap[0], dtype=np.float64)
                off["snap_kind"] = snap[1]
            elif t_main is not None and abs(t - t_main) <= tol * 2.0:
                t, off["kind"] = t_main, "Ana düzlem"
            elif self.grid_on:
                gs = self._grid_step(p)
                g = round(t / gs) * gs
                if abs(g - t) <= tol * 1.5:
                    t, off["kind"] = g, "Izgara"
        off["t"] = t

    def _accept_offset(self, context, t=None):
        off = self.off
        if t is None:
            t = off["t"]
        base = off["base"]
        plane = base.moved(base.o + base.n * t)
        self.off = None
        tp = getattr(self, "temp_pick", None)
        self._lock_plane(context, off["name"], plane)
        if tp is not None:
            self.temp_pick = None
            label = f"{dm.PLANE_LABELS.get(off['name'], off['name'])} · yükseklik {core.fmt_len(t)}"
            self.temp = {"saved": tp["saved"], "plane": plane, "label": label,
                         "grid_o": off.get("snap") if off.get("snap") is not None else None}
            self._status(context, f"Geçici zemin: {label} · yeni çizgiler bu zemine çizilir · "
                                  "G: normal düzleme dön")
            return
        if abs(t) > 1e-12:
            self._status(context, f"Çizim düzlemi: {dm.PLANE_LABELS.get(off['name'], off['name'])}"
                                  f" · yükseklik {core.fmt_len(t)}")

    def _modal_offset(self, context, event, mx, my, press):
        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            self._offset_update(context, mx, my)
            self.area.tag_redraw()
            return {"PASS_THROUGH"}
        if event.type in MODIFIERS:
            return {"PASS_THROUGH"}
        if not press:
            return {"RUNNING_MODAL"} if event.type in {"LEFTMOUSE", "RIGHTMOUSE"} \
                else {"PASS_THROUGH"}
        if event.type in {"LEFTMOUSE", "RET", "NUMPAD_ENTER"}:
            self._offset_update(context, mx, my)
            self._accept_offset(context)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type == "RIGHTMOUSE":
            self._accept_offset(context, 0.0)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type == "BACK_SPACE":
            self.typed[0] = self.typed[0][:-1]
            self._offset_update(context, mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        ch = event.unicode or ""
        if ch and (ch in "0123456789.,-+" or (self.typed[0] and ch.isalpha())):
            self.typed[0] += ch
            self._offset_update(context, mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        return {"PASS_THROUGH"}

    def _draw_offset3d(self, region):
        off = self.off
        if off is None:
            return
        base = off["base"]
        S = max(self.rv3d.view_distance * 0.35, 1e-4)
        if base.name == "FACE":
            S *= 0.35
        pl = base.moved(base.o + base.n * off["t"])
        sh = gpu.shader.from_builtin("UNIFORM_COLOR")
        for P, a_fill, a_line in ((base, 0.03, 0.18), (pl, 0.12, 0.75)):
            q = self._quad(P, (0.0, 0.0), S)
            batch = batch_for_shader(sh, "TRIS", {"pos": [tuple(x) for x in q]},
                                     indices=[(0, 1, 2), (0, 2, 3)])
            sh.bind()
            sh.uniform_float("color", (0.75, 0.75, 0.78, a_fill))
            batch.draw(sh)
            _poly([tuple(x) for x in q], (0.8, 0.8, 0.82, a_line), 1.5, region, closed=True)
        _poly([tuple(base.o), tuple(pl.o)], _axis_col(base.n), 2.0, region)

    def _draw_offset2d(self, region):
        off = self.off
        if off is None:
            return
        s = self.ui_scale
        mx, my = self.mouse
        base, t = off["base"], off["t"]
        a, b = self._px(base.o), self._px(base.o + base.n * t)
        if a is not None and b is not None:
            _dashed(a, b, COL_GUIDE, region)
            if abs(t) > 1e-12:                       # ölçü: taban → yeni düzlem
                _text((a[0] + b[0]) * 0.5 + 6 * s, (a[1] + b[1]) * 0.5 + 6 * s,
                      core.fmt_len(t), COL_TEXT, int(12 * s))
        sp = off.get("snap")
        if sp is not None:                           # hiza: yakalanan nokta → taban düzlemi
            p, q = self._px(sp), self._px(sp - base.n * t)
            if p is not None:
                if q is not None:
                    _dashed(q, p, COL_GUIDE, region)
                _marker(off.get("snap_kind") or "Uç", p[0], p[1], 6 * s, region)
                if b is not None:
                    _dashed(p, b, COL_GUIDE, region, dash=3, gap=4)
        if off["kind"]:
            _text(mx + 12 * s, my + 10 * s, off["kind"], COL_SNAP, int(11 * s))
        val = self.typed[0] + "_" if self.typed[0] else core.fmt_len(t)
        rows = [("Yükseklik", val, True)]
        t_main = self._main_height(base) if getattr(self, "temp_pick", None) else None
        if t_main is not None:
            rows.append(("Fark", core.fmt_len(t - t_main), False))
        self._draw_rows((mx, my), rows)

    def _quad(self, pl, center_uv, S):
        h = S / 2
        cu, cv = center_uv
        return [pl.xyz((cu + a, cv + b)) for a, b in ((-h, -h), (h, -h), (h, h), (-h, h))]

    def _draw_plane_pick(self, region):
        S, cands = self._plane_candidates()
        hov = self.hover_plane
        quads = []
        for name, pl in cands:
            on = hov is not None and hov[0] == name
            quads.append((self._quad(pl, (0.0, 0.0), S), PLANE_COLS[name], on))
        if hov is not None and hov[0] == "FACE":
            quads.append((self._quad(hov[1], (0.0, 0.0), S * 0.35), PLANE_COLS["FACE"], True))
        sh = gpu.shader.from_builtin("UNIFORM_COLOR")
        for q, col, on in quads:
            batch = batch_for_shader(sh, "TRIS", {"pos": [tuple(p) for p in q]},
                                     indices=[(0, 1, 2), (0, 2, 3)])
            sh.bind()
            sh.uniform_float("color", col + ((0.16 if on else 0.05),))
            batch.draw(sh)
            _poly([tuple(p) for p in q], col + ((0.8 if on else 0.3),), 2.0 if on else 1.0,
                  region, closed=True)

    def _draw_grid(self, region):
        pl = self._cur_plane() or self.tmp_plane
        if pl is None:
            return
        c = self.cursor
        sc = bpy.context.scene
        a = float(getattr(sc, "minicad_grid_alpha", COL_GRID[3]))
        if a <= 0.001:
            return
        gs = self._grid_step(c)
        g0 = pl.uv(self._grid_origin())
        q = pl.uv(c)
        R = gs * float(getattr(sc, "minicad_grid_size", 6.0))
        fade = float(getattr(sc, "minicad_grid_fade", 0.7))
        off = pl.n * pl.dist(c)
        pos, col = [], []
        for p0, p1, a0, a1 in dm.grid_segments(q, g0, gs, R, fade):
            pos += [tuple(pl.xyz(p0) + off), tuple(pl.xyz(p1) + off)]
            col += [COL_GRID[:3] + (a * a0,), COL_GRID[:3] + (a * a1,)]
        if not pos:
            return
        sh = gpu.shader.from_builtin("POLYLINE_SMOOTH_COLOR")   # spot ışığı gibi geçiş
        batch = batch_for_shader(sh, "LINES", {"pos": pos, "color": col})
        sh.bind()
        sh.uniform_float("viewportSize", (region.width, region.height))
        sh.uniform_float("lineWidth", 1.0)
        batch.draw(sh)

    # ------------------------------------------------------------ geçici zemin (U)

    def _grid_origin(self):
        """Izgaranın kökeni: geçici zeminde yükseklik bir noktadan alındıysa o nokta."""
        tmp = getattr(self, "temp", None)
        if tmp is not None and tmp.get("grid_o") is not None:
            return tmp["grid_o"]
        return np.zeros(3)

    def _base_plane(self):
        """Şu anki çizim düzleminin yönü (yükseklik bu düzlemden ölçülür)."""
        if self.plane_mode == "LOCK" and self.locked is not None:
            return self.locked
        if self.plane_mode in dm.AXIS_PLANES:
            return dm.Plane.axis(self.plane_mode, (0.0, 0.0, 0.0))
        pl = self.tmp_plane or self._make_plane(self.plane_mode, np.zeros(3))
        if pl.name in dm.AXIS_PLANES:
            return dm.Plane.axis(pl.name, (0.0, 0.0, 0.0))
        return pl

    def _main_plane(self):
        """Geçici zemin seçilirken / açıkken asıl (geri dönülecek) düzlem; yoksa None."""
        src = getattr(self, "temp_pick", None) or getattr(self, "temp", None)
        if src is None:
            return None
        mode, locked = src["saved"]
        if mode == "LOCK" and locked is not None:
            return locked
        if mode in dm.AXIS_PLANES:
            return dm.Plane.axis(mode, (0.0, 0.0, 0.0))
        return None

    def _main_height(self, base):
        """Asıl düzlemin, taban düzleminin normali boyunca yüksekliği (paralel değilse None)."""
        main = self._main_plane()
        if main is None or abs(abs(float(np.dot(main.n, base.n))) - 1.0) > 1e-6:
            return None
        return float(np.dot(main.o - base.o, base.n))

    def _temp_begin(self, context):
        """U: geçici zemin seç (1/2 yön, 2/2 yükseklik). Süren çizgi taslağa eklenir."""
        if self.segs or self.start is not None or self.stage:
            self._commit(context)
        tmp = getattr(self, "temp", None)
        saved = tmp["saved"] if tmp is not None else (self.plane_mode, self.locked)
        self.temp_pick = {"saved": saved}
        try:
            self.refs = _Refs(context, self.sketch, getattr(self, "sk_points", None) or ())
            self.dirty = False
        except Exception:
            pass
        self.track = None
        self.sk_sel = self.sk_hover = None
        self.typed, self.field = ["", ""], 0
        self.preview, self.cursor, self.info, self.snap_kind = [], None, None, None
        self.phase = "PLANE"
        self.hover_plane = None
        self._status(context, "Geçici zemin")

    def _temp_end(self, context):
        """U (geçici zemin açıkken): asıl düzleme dön; normal akış devam eder."""
        tmp = getattr(self, "temp", None)
        if tmp is None:
            return
        if self.segs or self.start is not None or self.stage:
            self._commit(context)
        mode, locked = tmp["saved"]
        self.temp = None
        self.plane_mode, self.locked = mode, locked
        self.plane = None
        self.tmp_plane = None
        self.shape_plane = None
        self._status(context, "Geçici zemin kapandı · asıl çizim düzlemine dönüldü")

    def _temp_cancel(self, context):
        """Esc (geçici zemin seçilirken): seçimden vazgeç, önceki duruma dön."""
        self.temp_pick = None
        self.off = None
        self.phase = "DRAW"
        self.hover_plane = None
        self._status(context, "Geçici zemin seçimi iptal edildi")
