"""Yakalama ve çıkarım: nokta yakalama, sezgisel kılavuzlar (FORGE snap_math), teğet
uzantılar, yay devamı, eksen kilitleri, önizleme ve T ile iz (başlangıç noktası tayini).

MINICAD_OT_draw (draw.py) bu mixin'den miras alır; metotlar self üzerinden birbirini çağırır.
"""
import bpy
import math
import numpy as np
from mathutils import Vector

from . import constraints
from . import core
from . import drawmath as dm
from .draw_common import (
    COL_GUIDE, COL_SNAP, FIELDS, GRID_PX, GUIDE_PX, MODIFY_TOOLS, PRIORITY, REF_PX, SHAPE_TOOLS,
    _Refs,
    _axis_col, _dashed, _marker, _project, _seg_px_dist, _text, parse_angle, parse_length,
)


class SnapMixin:
    """Yakalama ve çıkarım: nokta yakalama, sezgisel kılavuzlar (FORGE snap_math), teğet
    uzantılar, yay devamı, eksen kilitleri, önizleme ve T ile iz (başlangıç noktası tayini)."""

    def _anchor(self):
        if self.segs:
            return self.segs[-1]["p"][3]
        return self.start

    def _prev_tangent(self):
        if self.segs:
            return dm.end_tangent(self.segs[-1])
        return self.start_tan[0] if self.start_tan is not None else None

    def _end_tangent_of(self, pid):
        """Var olan bir çizginin ucundan dışarı doğru teğet (uç değilse None).
        (yön, (obje adı, spline, uca bağlı segment))"""
        ob = bpy.data.objects.get(pid[0])
        if ob is None or ob.type != "CURVE":
            return None
        try:
            sp = ob.data.splines[pid[1]]
        except Exception:
            return None
        if sp.use_cyclic_u:
            return None
        mw = ob.matrix_world
        k = pid[2]
        if sp.type == "BEZIER":
            bps = sp.bezier_points
            n = len(bps)
            if k == 0 and n > 1:
                t = np.array(mw @ bps[0].co) - np.array(mw @ bps[0].handle_right)
                if np.linalg.norm(t) < 1e-12:
                    t = np.array(mw @ bps[0].co) - np.array(mw @ bps[1].co)
                seg = 0
            elif k == n - 1 and n > 1:
                t = np.array(mw @ bps[k].co) - np.array(mw @ bps[k].handle_left)
                if np.linalg.norm(t) < 1e-12:
                    t = np.array(mw @ bps[k].co) - np.array(mw @ bps[k - 1].co)
                seg = k - 1
            else:
                return None
        else:
            pts = sp.points
            n = len(pts)
            if k == 0 and n > 1:
                t, seg = np.array(mw @ pts[0].co.xyz) - np.array(mw @ pts[1].co.xyz), 0
            elif k == n - 1 and n > 1:
                t, seg = np.array(mw @ pts[k].co.xyz) - np.array(mw @ pts[k - 1].co.xyz), k - 1
            else:
                return None
        t = dm.unit(t)
        return None if t is None else (t, (pid[0], pid[1], seg))

    def _temp_tangent(self, st):
        """Geçici zeminde başlangıç teğetini zemine izdüşürür; kısıt kaynağı olmaz."""
        tp = self._temp_plane()
        if st is None or tp is None or self.snap_src is None:
            return st
        t = np.asarray(st[0]) - tp.n * float(np.dot(st[0], tp.n))
        t = dm.unit(t)
        return None if t is None or float(np.linalg.norm(t)) < 1e-6 else (t, ("@proj", 0, 0, 0))

    def _sketch_end_tangent(self, p):
        """Taslaktaki açık bir çizginin ucundan dışarı doğru teğet (p o uçtaysa; en son
        çizilen öncelikli). (yön, ("@sketch", çizgi, uca bağlı segment, uç: 0 / 3))"""
        if p is None:
            return None
        p = np.asarray(p, dtype=np.float64)
        tol = 1e-7 * (1.0 + float(np.abs(p).max()))
        for k in range(len(self.sketch) - 1, -1, -1):
            st = self.sketch[k]
            segs = st["segs"]
            if st["cyclic"] or not segs:
                continue
            for j, end in ((len(segs) - 1, 3), (0, 0)):
                sg = segs[j]
                if float(np.linalg.norm(np.asarray(sg["p"][end]) - p)) > tol:
                    continue
                t = dm.end_tangent(sg) if end == 3 else dm.start_tangent(sg)
                if t is None:
                    continue
                return (t if end == 3 else -t), ("@sketch", k, j, end)
        return None

    def _lock_anchor(self):
        """Yazılan değerlerin ve kılavuzların ölçüldüğü nokta."""
        if self.tool in SHAPE_TOOLS and self.stage:
            return self.stage[0]
        if self.tool in ("CV", "FIT") and self.stage:
            return self.stage[-1]
        return self._anchor()

    def _point_snap(self, mx, my, ro, rd):
        M = np.array(self.rv3d.perspective_matrix, dtype=np.float64)
        m = np.array([mx, my])
        refs = self.refs
        extra = self._extra_pts()
        anchor = self._lock_anchor()
        P = refs.P
        kinds = list(refs.kinds)
        ids = list(refs.ids)
        if extra:
            P = np.vstack([P] + [np.asarray(p).reshape(1, 3) for p, _ in extra])
            kinds += [k for _, k in extra]
            ids += [None] * len(extra)
        if len(P):
            px, ok, z = _project(P, M, self.region)
            d = np.linalg.norm(px - m, axis=1)
            d = np.where(ok, d, np.inf)
            idx = np.where(d <= self.radius)[0]
            if anchor is not None:            # kendi çapasına yapışmasın
                idx = [i for i in idx if np.linalg.norm(P[i] - anchor) > 1e-9]
            if len(idx):
                best = min(idx, key=lambda i: (PRIORITY[kinds[i]], d[i], z[i]))
                return P[best], kinds[best], ids[best]
        if refs.chords:
            A = np.array([c[0] for c in refs.chords])
            B = np.array([c[1] for c in refs.chords])
            pa, oka, _ = _project(A, M, self.region)
            pb, okb, _ = _project(B, M, self.region)
            dd, _ = _seg_px_dist(pa, pb, m)
            dd = np.where(oka & okb, dd, np.inf)
            near = [int(i) for i in np.argsort(dd)[:16] if dd[i] <= self.radius]
            best = None
            for ii in range(len(near)):
                for jj in range(ii + 1, len(near)):
                    a, b = refs.chords[near[ii]]
                    c, e = refs.chords[near[jj]]
                    tol = 1e-4 * min(np.linalg.norm(b - a), np.linalg.norm(e - c)) + 1e-9
                    q = dm.segment_intersection(a, b, c, e, tol)
                    if q is None:
                        continue
                    qp = self._px(q)
                    if qp is None:
                        continue
                    dq = math.hypot(qp[0] - mx, qp[1] - my)
                    if dq <= self.radius and (best is None or dq < best[0]):
                        best = (dq, q)
            if best is not None:
                return best[1], "Kesişim", None
        if len(refs.A):
            pa, oka, za = _project(refs.A, M, self.region)
            pb, okb, zb = _project(refs.B, M, self.region)
            dd, t = _seg_px_dist(pa, pb, m)
            dd = np.where(oka & okb, dd, np.inf)
            dmin = dd.min()
            if np.isfinite(dmin) and dmin <= self.radius * 0.8:
                near = np.where(dd <= dmin + 2.0)[0]
                z = za + (zb - za) * t
                k = int(near[np.argmin(z[near])])
                q = dm.closest_on_segment_to_ray(refs.A[k], refs.B[k], ro, rd)
                return q, "Yakın", None
        return None

    def _inference_refs(self, plane, mx, my):
        M = np.array(self.rv3d.perspective_matrix, dtype=np.float64)
        m = np.array([mx, my])
        refs = self.refs
        lim = REF_PX * self.ui_scale
        ref_pts = []
        pts = [refs.P[i] for i, k in enumerate(refs.kinds) if k in ("Uç", "Merkez", "Orta")]
        pts += [p for p, _ in self._extra_pts()]
        if pts:
            P = np.array(pts)
            px, ok, _ = _project(P, M, self.region)
            d = np.where(ok, np.linalg.norm(px - m, axis=1), np.inf)
            for i in np.argsort(d)[:30]:
                if d[i] > lim:
                    break
                u, v = plane.uv(P[i])
                ref_pts.append((u, v, int(i)))
        chords = [(a, b, cid) for (a, b), cid in zip(refs.chords, refs.chord_ids)]
        chords += [(s["p"][0], s["p"][3], ("chain", j)) for j, s in enumerate(self.segs)
                   if s["kind"] == "line"]
        self._cur_chords = []
        ref_dirs, ref_segs = [], []
        if chords:
            A = np.array([c[0] for c in chords])
            B = np.array([c[1] for c in chords])
            pa, oka, _ = _project(A, M, self.region)
            pb, okb, _ = _project(B, M, self.region)
            dd, _ = _seg_px_dist(pa, pb, m)
            dd = np.where(oka & okb, dd, np.inf)
            for i in np.argsort(dd)[:12]:
                if dd[i] > lim * 0.8:
                    break
                a, b, cid = chords[int(i)]
                dvec = dm.unit(b - a)
                if dvec is None or abs(float(np.dot(dvec, plane.n))) > 0.02:
                    continue                    # düzlemde değil
                j = len(self._cur_chords)
                self._cur_chords.append((a, b, cid))
                ua, va = plane.uv(a)
                ub, vb = plane.uv(b)
                ref_dirs.append((ub - ua, vb - va, j))
                ref_segs.append(((ua, va), (ub, vb), j))
        # eğri / yay uçlarından teğet doğrultusunda uzantılar
        rays = list(refs.rays)
        for s in self.segs:
            if s["kind"] != "line":
                t1 = dm.unit(s["p"][3] - s["p"][2])
                if t1 is not None:
                    rays.append((s["p"][3], t1))
        if rays:
            E = np.array([r[0] for r in rays])
            pe, oke, _ = _project(E, M, self.region)
            de = np.where(oke, np.linalg.norm(pe - m, axis=1), np.inf)
            for i in np.argsort(de)[:16]:
                if de[i] > lim * 1.5:
                    break
                e, t = rays[int(i)]
                if abs(float(np.dot(t, plane.n))) > 0.02:
                    continue
                ue, ve = plane.uv(e)
                ut = (float(np.dot(t, plane.u)), float(np.dot(t, plane.v)))
                k = 1e-3 * (1.0 + abs(ue) + abs(ve))
                ref_segs.append(((ue - ut[0] * k, ve - ut[1] * k), (ue, ve), "ray"))
        return ref_pts, ref_dirs, ref_segs

    def _update(self, context, mx, my):
        self.mouse = (mx, my)
        if self.dirty:
            try:
                self.refs = _Refs(context, self.sketch)
            except Exception:
                pass
            self.dirty = False
        if self.phase == "PLANE":
            self._hover_plane(context, mx, my)
            self.plane_snap = None                 # yön seçerken de noktalara yapışır
            if not self.ctrl and self.snap_on and getattr(self, "temp_pick", None) is not None:
                ro, rd = self._ray(mx, my)
                sn = self._point_snap(mx, my, ro, rd)
                if sn is not None and sn[1] != "Yakın":
                    self.plane_snap = (np.asarray(sn[0], dtype=np.float64), sn[1])
            self.cursor = None
            self.preview = []
            return
        if self.tool == "SELECT":
            self.cursor, self.preview, self.info, self.snap_kind = None, [], None, None
            return
        if self.tool in MODIFY_TOOLS:
            self._mod_update(context, mx, my)
            return
        if self.track is not None:
            self._track_update(context, mx, my)
            return
        if self.tool.startswith("C_"):
            n, is_pt = constraints.needed(self.tool[2:])
            self.c_hover = self._pick_entity(mx, my, is_pt)
            return
        ro, rd = self._ray(mx, my)
        anchor = self._lock_anchor()
        no_snap = self.ctrl or not self.snap_on
        snap = None if no_snap else self._point_snap(mx, my, ro, rd)
        f0, f1 = FIELDS.get(self.tool, ("Uzunluk", "Açı"))
        v0 = (parse_length(self.typed[0]) if f0 else None) if anchor is not None else None
        v1 = None
        if anchor is not None and f1:
            v1 = parse_length(self.typed[1]) if self.tool == "RECT" else parse_angle(self.typed[1])
        locked = v0 is not None or v1 is not None

        # Çalışma düzlemi
        plane = self._cur_plane()
        if plane is None:
            if snap is not None:
                plane = self._make_plane(self.plane_mode, snap[0])
            else:
                face_n, origin = None, np.array(context.scene.cursor.location)
                if self.plane_mode == "AUTO":
                    try:
                        hit, loc, nor, _i, obj, _m = context.scene.ray_cast(
                            context.evaluated_depsgraph_get(), Vector(tuple(ro)),
                            Vector(tuple(rd)))
                        if hit and obj is not None and obj.type == "MESH" and \
                                obj.display_type in ("SOLID", "TEXTURED"):
                            face_n, origin = np.array(nor), np.array(loc)
                    except Exception:
                        pass
                plane = self._make_plane(self.plane_mode, origin, face_n)
            self.tmp_plane = plane
        elif anchor is not None and abs(plane.dist(anchor)) > 1e-9:
            plane = plane.moved(anchor)

        self.info = None
        self.snap_kind = self.snap_id = None
        if snap is not None and not locked:
            p = np.asarray(snap[0], dtype=np.float64)
            self.snap_kind, self.snap_id = snap[1], snap[2]
        else:
            p = plane.ray_hit(ro, rd)
            if p is None:
                p = self.cursor if self.cursor is not None else plane.o
            if not no_snap and not locked:
                tol = GUIDE_PX * self.ui_scale * self._px_size(p)
                ref_pts, ref_dirs, ref_segs = self._inference_refs(plane, mx, my)
                a_uv = plane.uv(anchor) if anchor is not None else None
                pt = self._prev_tangent() if self.tool not in SHAPE_TOOLS else None
                prev = None
                if pt is not None:
                    prev = (float(np.dot(pt, plane.u)), float(np.dot(pt, plane.v)))
                q, info = dm.refine(a_uv, plane.uv(p), ref_dirs, ref_pts, ref_segs, tol,
                                    shift=self.shift, prev_dir=prev)
                if info is None or info.get("kind") == "Hiza":
                    p2 = self._arc_continue(plane, plane.xyz(q) if info else p, tol,
                                            info.get("guides") if info else None)
                    if p2 is not None:
                        p = p2
                        kind = "Yay uzantısı" + (" + Hiza" if info else "")
                        info = dict(info or {}, kind=kind)
                        q = plane.uv(p)
                if info is not None:
                    p = plane.xyz(q) + plane.n * plane.dist(p)
                    info["plane"] = plane
                    self.info = info
                if self.grid_on:
                    p2, g = self._grid_snap(plane, p, self.info)
                    if g:
                        p = p2
                        if self.info is None:
                            self.info = {"kind": "Izgara", "plane": plane}
                        else:
                            self.info["kind"] += " + Izgara"
            if locked:
                p = self._apply_locks(plane, anchor, p, v0, v1)
        self.cursor = self._on_temp(np.asarray(p, dtype=np.float64))
        self._make_preview(plane)

    def _temp_plane(self):
        """Geçici zemin açıksa o düzlem (çizim hep bu düzlemde kalır), değilse None."""
        tmp = getattr(self, "temp", None)
        if tmp is None or self.plane_mode != "LOCK" or self.locked is None:
            return None
        return self.locked

    def _on_temp(self, p):
        """Geçici zeminde: eski düzlemdeki bir noktaya yapışıldıysa nokta zemine paralel
        izdüşürülür (çizim yeni yükseklikte başlar / sürer). Asıl nokta snap_src'de kalır."""
        self.snap_src = self.snap_src_id = None
        tp = self._temp_plane()
        if tp is None or p is None:
            return p
        h = tp.dist(p)
        if abs(h) <= 1e-9 * (1.0 + float(np.abs(p).max())):
            return p
        if self.snap_kind is not None:
            self.snap_src = np.asarray(p, dtype=np.float64).copy()
            self.snap_src_id = self.snap_id       # teğet kaynağı için saklanır
            self.snap_id = None                   # farklı yükseklik: çakışık kısıtı yazılmaz
        return p - tp.n * h

    def _arc_continue(self, plane, p, tol, guides=None):
        """İmleç bir tel kafes yayının çemberine yakınsa çember üzerine al (yayın devamı).
        Hiza kılavuzu varsa kılavuzla çemberin kesişimi alınır."""
        best = None
        q = np.asarray(p, dtype=np.float64)
        quv = plane.uv(q)
        for c, R, n in self.refs.arcs:
            if abs(abs(float(np.dot(n, plane.n))) - 1.0) > 1e-3:
                continue
            cuv = plane.uv(c)
            cands = []
            for g, ref in (guides or ()):
                ax = 0 if g == "V" else 1
                o = 1 - ax
                dd = R * R - (ref[ax] - cuv[ax]) ** 2
                if dd < 0:
                    continue
                for sgn in (1.0, -1.0):
                    w = [0.0, 0.0]
                    w[ax] = ref[ax]
                    w[o] = cuv[o] + sgn * math.sqrt(dd)
                    cands.append(tuple(w))
            if not guides:
                v = np.array([quv[0] - cuv[0], quv[1] - cuv[1]])
                d = float(np.linalg.norm(v))
                if d > 1e-12:
                    cands.append((cuv[0] + v[0] / d * R, cuv[1] + v[1] / d * R))
            for w in cands:
                e = math.hypot(w[0] - quv[0], w[1] - quv[1])
                if e <= tol and (best is None or e < best[0]):
                    best = (e, plane.xyz(w) + plane.n * plane.dist(q))
        return None if best is None else best[1]

    def _apply_locks(self, plane, anchor, p, v0, v1):
        if self.tool == "CIRCLE":
            d = dm.unit(np.asarray(p) - anchor)
            if d is None:
                d = plane.u
            return anchor + d * v0 if v0 is not None else p
        if self.tool == "RECT":
            a, q = plane.uv(anchor), plane.uv(p)
            du, dv = q[0] - a[0], q[1] - a[1]
            if v0 is not None:
                du = math.copysign(v0, du if du else 1.0)
            if v1 is not None:
                dv = math.copysign(v1, dv if dv else 1.0)
            return plane.xyz((a[0] + du, a[1] + dv)) + plane.n * plane.dist(anchor)
        return dm.apply_locks(plane, anchor, p, v0, v1)

    def _make_preview(self, plane):
        self.preview = []
        self.arc_info = None
        anchor = self._anchor()
        cur = self.cursor
        t = self.tool
        if t in SHAPE_TOOLS:
            if not self.stage:
                return
            c0 = self.stage[0]
            if np.linalg.norm(cur - c0) < 1e-12:
                return
            if t == "CIRCLE":
                v = cur - c0
                R = float(np.linalg.norm(v - np.dot(v, plane.n) * plane.n))
                if R > 1e-12:
                    self.preview = dm.circle(c0, R, plane)
                    self.arc_info = {"radius": R, "circle": True}
            else:
                self.preview = dm.rectangle(c0, cur, plane)
            return
        if anchor is None:
            return
        if t == "CARC":
            if not self.stage:
                if np.linalg.norm(cur - anchor) > 1e-12:
                    self.preview = [dm.line_seg(anchor, cur)]
                    self.preview[0]["kind"] = "guide"
                return
            arc = dm.center_arc(self.stage[0], anchor, cur, plane.n, self.carc_flip)
            if arc is not None:
                self.preview, self.arc_info = arc["segs"], arc
            return
        if np.linalg.norm(cur - anchor) <= 1e-12:
            return
        if t == "TARC" and self._prev_tangent() is not None:
            arc = dm.tangent_arc(anchor, self._prev_tangent(), cur)
            if arc is not None:
                self.preview, self.arc_info = arc["segs"], arc
                if not self.segs:
                    for sg in self.preview:
                        sg["tan_start"] = True
            else:
                self.preview = [dm.line_seg(anchor, cur)]
        elif t in ("ARC3", "TARC"):
            if not self.stage:
                self.preview = [dm.line_seg(anchor, cur)]
                self.preview[0]["kind"] = "guide"
            else:
                arc = dm.arc_3pt(anchor, cur, self.stage[0])
                if arc is not None:
                    self.preview, self.arc_info = arc["segs"], arc
        elif t == "CV":
            self.preview = dm.bspline_bezier([anchor] + self.stage + [cur])
        elif t == "FIT":
            self.preview = dm.fit_bezier([anchor] + self.stage + [cur])
        elif t == "PEN":
            if self.pen is not None:
                self.preview = [dm.pen_seg(anchor, self.out_h, self.pen["co"], self.pen["h"])]
            else:
                self.preview = [dm.pen_seg(anchor, self.out_h, cur, None)]
        else:
            self.preview = [dm.line_seg(anchor, cur)]

    def _track_update(self, context, mx, my):
        self.mouse = (mx, my)
        tr = self.track
        ro, rd = self._ray(mx, my)
        plane = self._cur_plane() or self.tmp_plane
        if plane is None:
            plane = self._make_plane(self.plane_mode, np.array(context.scene.cursor.location))
            self.tmp_plane = plane
        self.info = None
        self.snap_kind = self.snap_id = None
        if not tr["pts"]:
            snap = None if self.ctrl else self._point_snap(mx, my, ro, rd)
            if snap is not None:
                self.cursor = np.asarray(snap[0], dtype=np.float64)
                self.snap_kind = snap[1]
            else:
                p = plane.ray_hit(ro, rd)
                self.cursor = p if p is not None else plane.o
            self.snap_src = self.snap_src_id = None
            tr["axis"] = None
            self.preview = []
            return
        base = tr["pts"][-1]
        m = np.array([mx, my])
        best = None
        for ax in (plane.u, plane.v, plane.n):
            a = self._px(base)
            b = self._px(base + ax * 50.0 * self.ui_scale * self._px_size(base))
            if a is None or b is None:
                continue
            a, b = np.array(a), np.array(b)
            d = b - a
            L = float(np.linalg.norm(d))
            if L < 1e-6:
                continue
            e = d / L
            v = m - a
            dist = abs(float(e[0] * v[1] - e[1] * v[0]))
            if best is None or dist < best[0]:
                best = (dist, ax)
        ax = best[1] if best is not None else plane.u
        rdn = rd / max(float(np.linalg.norm(rd)), 1e-15)
        w0 = ro - base
        bb = float(np.dot(rdn, ax))
        den = 1.0 - bb * bb
        t = float(bb * np.dot(w0, rdn) - np.dot(w0, ax)) / den if den > 1e-9 else 0.0
        t = -t
        typed = self._signed_len(self.typed[0]) if self.typed[0] else None
        if typed is not None:
            t = math.copysign(abs(typed), t if t != 0 else 1.0) if not \
                self.typed[0].strip().startswith("-") else typed
        elif self.grid_on and not self.ctrl:
            p = base + ax * t
            gs = self._grid_step(p)
            g = round(t / gs) * gs
            if abs(g - t) <= GRID_PX * self.ui_scale * self._px_size(p):
                t = g
        tr["axis"], tr["t"] = ax, t
        self.cursor = self._on_temp(base + ax * t)
        pl = self._cur_plane() or self.tmp_plane
        self._make_preview(pl.moved(self._lock_anchor()) if self._lock_anchor() is not None
                           else pl)

    def _track_event(self, context, event, mx, my, press):
        tr = self.track
        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            try:
                self._track_update(context, mx, my)
            except Exception as e:
                print("[Mini CAD] iz güncellenemedi:", e)
            self.area.tag_redraw()
            return {"PASS_THROUGH"}
        if not press:
            return {"RUNNING_MODAL"} if event.type in {"LEFTMOUSE", "RIGHTMOUSE"} else None
        if event.type == "LEFTMOUSE":
            self._track_update(context, mx, my)
            tr["pts"].append(self.cursor.copy())
            self.typed, self.field = ["", ""], 0
            self._status(context, f"İz: {len(tr['pts'])}. nokta · eksen boyunca devam et ya da "
                                  "Enter / sağ tık ile son noktayı kullan")
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type in {"RIGHTMOUSE", "RET", "NUMPAD_ENTER", "SPACE"}:
            if not tr["pts"]:
                self.track = None
                return {"RUNNING_MODAL"}
            final = self.cursor.copy() if self.typed[0] else tr["pts"][-1]
            self.track = None
            self.typed, self.field = ["", ""], 0
            self.cursor = np.asarray(final, dtype=np.float64)
            self.snap_kind = self.snap_id = None
            self.info = None
            pl = self._cur_plane() or self.tmp_plane
            if pl is not None:
                self._make_preview(pl.moved(self._lock_anchor()) if
                                   self._lock_anchor() is not None else pl)
            self._place(context)
            self._status(context, "İz noktası kullanıldı")
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type == "BACK_SPACE":
            if self.typed[0]:
                self.typed[0] = self.typed[0][:-1]
            elif tr["pts"]:
                tr["pts"].pop()
            self._track_update(context, mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        return None

    def _draw_track2d(self, region):
        tr = self.track
        if tr is None:
            return
        s = self.ui_scale
        pts = [self._px(p) for p in tr["pts"]]
        cur = self._px(self.cursor) if self.cursor is not None else None
        chain = [p for p in pts if p is not None] + ([cur] if cur is not None else [])
        for a, b in zip(chain[:-1], chain[1:]):
            _dashed(a, b, COL_GUIDE, region, dash=8, gap=5)
        for p in pts:
            if p is not None:
                _marker("Kesişim", p[0], p[1], 5 * s, region)
        if cur is not None:
            if tr.get("axis") is not None and tr["pts"]:
                ax = tr["axis"]
                k = int(np.argmax(np.abs(ax)))
                name = "XYZ"[k] if abs(ax[k]) > 0.999 else "Eksen"
                val = self.typed[0] + "_" if self.typed[0] else core.fmt_len(tr.get("t", 0.0))
                txt = f"İz {name}: {val}"
                col = _axis_col(ax)
            else:
                txt = "İz: referans nokta" + (f" ({self.snap_kind})" if self.snap_kind else "")
                col = COL_SNAP
                if self.snap_kind:
                    _marker(self.snap_kind, cur[0], cur[1], 6 * s, region)
            _text(cur[0] + 14 * s, cur[1] + 12 * s, txt, col, int(12 * s))

    def _point_snap_excluding(self, mx, my, ro, rd, own):
        M = np.array(self.rv3d.perspective_matrix, dtype=np.float64)
        P = self.refs.P
        if not len(P):
            return None
        px, ok, _ = _project(P, M, self.region)
        dd = np.where(ok, np.linalg.norm(px - np.array([mx, my]), axis=1), np.inf)
        for i in np.argsort(dd)[:8]:
            if dd[i] > self.radius:
                return None
            if np.linalg.norm(P[i] - own) > 1e-9 and self.refs.kinds[i] in ("Uç", "Merkez",
                                                                               "Orta"):
                return P[i], self.refs.kinds[i]
        return None
