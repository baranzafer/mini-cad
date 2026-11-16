# SPDX-License-Identifier: GPL-3.0-or-later
"""Yoğunluktan bağımsız, akıcı yakalama.

Eski yöntem (her fare hareketinde tüm mesh'ler için bmesh + KDTree) yerine:
  * Blender'ın önbellekli BVH ağacıyla imleç çevresine birkaç ışın atılır
    (scene.ray_cast, C tarafında, mesh yoğunluğundan neredeyse bağımsız).
  * Yalnızca çarpılan yüzlerin köşe / kenar / merkezleri aday olur.
  * Kutu, köken, imleç gibi az sayıdaki referans noktası doğrudan izdüşürülür.
  * Yüzü olmayan (tel / nokta) mesh'ler bir kez numpy dizisine alınır ve
    vektörel izdüşürülür.
Böylece 10 milyon üçgenli sahnede de fare başına iş sabit kalır.
"""
import math

import numpy as np
from mathutils import Vector

from . import geom
from .selection import object_box

POINT_KINDS_T1 = {'VERT', 'BOX_CORNER', 'ORIGIN', 'CURSOR'}
POINT_KINDS_T2 = {'EDGE_MID', 'FACE_CENTER', 'BOX_MID', 'BOX_FACE', 'BOX_CENTER', 'PERP'}
LINE_KINDS = {'EDGE', 'BOX_EDGE'}
# geometriden gelmeyen (görünürlüğü ışınla sınanan) referans noktaları
OVERLAY_KINDS = {'BOX_CORNER', 'BOX_MID', 'BOX_FACE', 'BOX_CENTER', 'ORIGIN', 'CURSOR'}

KIND_LABEL = {
    'VERT': "Köşe", 'EDGE_MID': "Kenar ortası", 'EDGE': "Kenar", 'FACE': "Yüzey",
    'FACE_CENTER': "Yüz merkezi", 'PERP': "Dik", 'BOX_CORNER': "Kutu köşesi",
    'BOX_MID': "Kutu kenar ortası", 'BOX_FACE': "Kutu yüz merkezi", 'BOX_CENTER': "Kutu merkezi",
    'BOX_EDGE': "Kutu kenarı", 'ORIGIN': "Köken", 'CURSOR': "3B imleç", 'FREE': "Serbest",
    'AXIS': "Eksen", 'PLANE': "Düzlem",
}

LOOSE_LIMIT = 2_000_000


class Snap:
    __slots__ = ("co", "kind", "obj", "local", "normal", "edge", "dist")

    def __init__(self, co, kind, obj=None, local=None, normal=None, edge=None, dist=0.0):
        self.co = Vector(co)
        self.kind = kind
        self.obj = obj
        self.local = local
        self.normal = normal
        self.edge = edge
        self.dist = dist

    @property
    def label(self):
        return KIND_LABEL.get(self.kind, self.kind)


def _ring(r, n, phase=0.0):
    return [(r * math.cos(phase + 2 * math.pi * i / n), r * math.sin(phase + 2 * math.pi * i / n))
            for i in range(n)]


def _instanced_names(group):
    out = set()
    if group:
        for o in group.objects:
            if o.instance_type == 'COLLECTION' and o.instance_collection:
                out |= {x.name for x in o.instance_collection.all_objects}
    return out


class Snapper:
    def __init__(self, context, settings, group=None, exclude=None):
        self.s = settings
        self.group = group
        self.exclude = exclude        # bu gruba ait nesneler yok sayılır (ör. ölçeklenen seçim)
        self.xray = False             # X-ray açıksa arkada kalan referans noktaları da yakalanır
        self.box = None              # seçim kutusu (geom.Box)
        self.hover_box = None        # imleç altındaki nesnenin kutusu
        self.hover_obj = None
        self._box_cache = {}
        self._loose = None
        self._inst_names = _instanced_names(group)
        self._ex_inst = _instanced_names(exclude)
        ui = (context.preferences.system.ui_scale if context.preferences else 1.0) or 1.0
        self.radius = float(settings.snap_radius) * ui
        r = self.radius
        self.offsets = [(0.0, 0.0)] + _ring(r * 0.45, 6) + _ring(r * 0.9, 10, 0.3)

    # ------------------------------------------------------------------ önbellek
    def invalidate(self):
        self._box_cache.clear()
        self._loose = None
        self.hover_box = None

    def _belongs(self, ob, is_inst):
        g = self.group
        if g is None:
            return False
        if g.contains(ob):
            return True
        return is_inst and ob.name in self._inst_names

    # ---------------------------------------------------------------- ışın
    def _cast(self, scene, dg, ro, rd, only_sel):
        for _ in range(8):
            hit, loc, nor, idx, ob, M = scene.ray_cast(dg, ro, rd)
            if not hit:
                return None
            is_inst = not geom.matrices_close(M, ob.matrix_world, 1e-6)
            ok = True
            if not is_inst:
                try:
                    ok = ob.visible_get()
                except (RuntimeError, ReferenceError):
                    ok = True
            if ok and only_sel and not self._belongs(ob, is_inst):
                ok = False
            if ok and self.exclude is not None and (
                    self.exclude.contains(ob) or (is_inst and ob.name in self._ex_inst)):
                ok = False
            if ok:
                return loc, nor, idx, ob, M.copy(), is_inst
            ro = loc + rd * (1e-4 * max(1.0, (loc - ro).length))
        return None

    @staticmethod
    def _face_points(dg, ob, idx, M):
        """Yüzün dünya köşeleri ve merkezi; değerlendirilmiş mesh'ten."""
        ob_eval = ob.evaluated_get(dg)
        me = None
        temp = False
        if ob_eval.type == 'MESH':
            me = ob_eval.data
            if me is None or idx >= len(me.polygons):
                me = None
        if me is None:
            try:
                me = ob_eval.to_mesh()
                temp = True
            except RuntimeError:
                return None
        try:
            if me is None or idx < 0 or idx >= len(me.polygons):
                return None
            poly = me.polygons[idx]
            verts = me.vertices
            pts = [M @ verts[v].co for v in poly.vertices]
            nor = (M.to_3x3().inverted_safe().transposed() @ poly.normal).normalized()
            return pts, M @ poly.center, nor
        finally:
            if temp:
                ob_eval.to_mesh_clear()

    # ------------------------------------------------------------ gevşek geometri
    def _build_loose(self, context, dg):
        out = []
        total = 0
        only = self.s.snap_only_selection and self.exclude is None
        for ob in context.visible_objects:
            if ob.type != 'MESH':
                continue
            if only and not self._belongs(ob, False):
                continue
            if self.exclude is not None and self.exclude.contains(ob):
                continue
            ob_eval = ob.evaluated_get(dg)
            me = ob_eval.data
            if me is None or len(me.polygons) or not len(me.vertices):
                continue
            n = len(me.vertices)
            if total + n > LOOSE_LIMIT:
                break
            total += n
            co = np.empty(n * 3, dtype=np.float32)
            me.vertices.foreach_get("co", co)
            co = co.reshape(-1, 3).astype(np.float64)
            A = np.array(ob.matrix_world, dtype=np.float64)
            w = co @ A[:3, :3].T + A[:3, 3]
            ed = np.empty(len(me.edges) * 2, dtype=np.int32)
            me.edges.foreach_get("vertices", ed)
            out.append((ob, w, ed.reshape(-1, 2)))
        self._loose = out

    def _loose_candidates(self, view, m, ro, rd, pts, lines):
        r = self.radius
        for ob, w, ed in self._loose:
            sc, ok = view.project_np(w)
            d2 = ((sc - np.array(m)) ** 2).sum(axis=1)
            d2[~ok] = np.inf
            if self.s.snap_vert and len(d2):
                i = int(np.argmin(d2))
                if d2[i] <= r * r:
                    pts.append((Vector(w[i].tolist()), 'VERT', ob, False))
            if self.s.snap_edge and len(ed):
                a = sc[ed[:, 0]]
                b = sc[ed[:, 1]]
                ab = b - a
                L2 = (ab ** 2).sum(axis=1)
                L2[L2 < 1e-9] = 1e-9
                t = np.clip(((np.array(m) - a) * ab).sum(axis=1) / L2, 0.0, 1.0)
                pr = a + ab * t[:, None]
                dd = ((pr - np.array(m)) ** 2).sum(axis=1)
                valid = ok[ed[:, 0]] & ok[ed[:, 1]]
                dd[~valid] = np.inf
                j = int(np.argmin(dd))
                if dd[j] <= r * r:
                    p0 = Vector(w[ed[j, 0]].tolist())
                    p1 = Vector(w[ed[j, 1]].tolist())
                    lines.append((p0, p1, 'EDGE', ob, False))
                    if self.s.snap_mid:
                        pts.append(((p0 + p1) * 0.5, 'EDGE_MID', ob, False))

    def _occluded(self, scene, dg, view, co):
        """Göz -> nokta arasında başka yüzey var mı (arkada kalan kutu köşesi vb.)."""
        sc = view.project(co)
        if sc is None:
            return True
        ro, rd = view.ray(sc.x, sc.y)
        dist = (Vector(co) - ro).dot(rd)
        if dist <= 0:
            return True
        hit = scene.ray_cast(dg, ro, rd, distance=dist)
        if not hit[0]:
            return False
        return (hit[1] - ro).length < dist - max(1e-4, dist * 1e-4)

    # ----------------------------------------------------------------- ana sorgu
    def find(self, context, view, mx, my, ref=None, extra_points=(), extra_lines=()):
        """En iyi yakalama (Snap) ya da None. Ayrıca self.surface (yüzey isabeti) doldurulur."""
        s = self.s
        scene = context.scene
        dg = context.evaluated_depsgraph_get()
        m = Vector((mx, my))
        r = self.radius
        only = s.snap_only_selection and self.exclude is None
        self.surface = None

        faces = {}
        center_hit = None
        for k, (dx, dy) in enumerate(self.offsets):
            ro, rd = view.ray(mx + dx, my + dy)
            h = self._cast(scene, dg, ro, rd, only)
            if h is None:
                continue
            loc, nor, idx, ob, M, is_inst = h
            if k == 0:
                center_hit = h
            key = (ob.name, idx, tuple(round(x, 5) for x in M.translation))
            if key not in faces:
                faces[key] = (ob, idx, M, is_inst)

        ro, rd = view.ray(mx, my)
        pts = []      # (co, kind, ob, is_inst)
        lines = []    # (a, b, kind, ob, is_inst)
        need_geo = s.snap_vert or s.snap_edge or s.snap_mid or s.snap_face_center or s.snap_perp
        if need_geo:
            for ob, idx, M, is_inst in faces.values():
                fp = self._face_points(dg, ob, idx, M)
                if fp is None:
                    continue
                vs, cen, _n = fp
                if s.snap_vert:
                    for v in vs:
                        pts.append((v, 'VERT', ob, is_inst))
                if s.snap_face_center:
                    pts.append((cen, 'FACE_CENTER', ob, is_inst))
                n = len(vs)
                for i in range(n):
                    a, b = vs[i], vs[(i + 1) % n]
                    if s.snap_edge or s.snap_perp:
                        lines.append((a, b, 'EDGE', ob, is_inst))
                    if s.snap_mid:
                        pts.append(((a + b) * 0.5, 'EDGE_MID', ob, is_inst))

        if s.snap_vert or s.snap_edge:
            if self._loose is None:
                self._build_loose(context, dg)
            if self._loose:
                self._loose_candidates(view, m, ro, rd, pts, lines)

        # kutular
        self.hover_obj = None
        self.hover_box = None
        if s.snap_box:
            boxes = []
            if self.box is not None and self.box.valid:
                boxes.append(self.box)
            if center_hit is not None:
                ob, M = center_hit[3], center_hit[4]
                self.hover_obj = ob
                key = (ob.name, tuple(round(x, 6) for row in M for x in row))
                hb = self._box_cache.get(key, False)
                if hb is False:
                    hb = object_box(ob.evaluated_get(dg), M)
                    if len(self._box_cache) > 64:
                        self._box_cache.clear()
                    self._box_cache[key] = hb
                if hb is not None:
                    self.hover_box = hb
                    boxes.append(hb)
            for bx in boxes:
                for co, kind in bx.snap_points():
                    pts.append((co, kind, None, True))
                if s.snap_edge:
                    for a, b in bx.edges():
                        lines.append((a, b, 'BOX_EDGE', None, True))

        if s.snap_origin:
            if self.group:
                for o in self.group.objects:
                    pts.append((o.matrix_world.translation.copy(), 'ORIGIN', o, False))
            if self.hover_obj is not None and not (self.group and self.group.contains(self.hover_obj)):
                pts.append((self.hover_obj.matrix_world.translation.copy(), 'ORIGIN', self.hover_obj, False))
            pts.append((scene.cursor.location.copy(), 'CURSOR', None, True))
        for co, kind in extra_points:
            pts.append((Vector(co), kind, None, True))
        for a, b in extra_lines:
            lines.append((Vector(a), Vector(b), 'BOX_EDGE', None, True))

        # dik ayak
        if s.snap_perp and ref is not None:
            for a, b, kind, ob, is_inst in lines:
                t, foot = geom.foot_on_line(ref, a, b - a)
                if 0.0 < t < 1.0:
                    pts.append((foot, 'PERP', ob, is_inst))

        best = None
        best_score = None
        for co, kind, ob, is_inst in pts:
            sc = view.project(co)
            if sc is None:
                continue
            d = (sc - m).length
            lim = r if kind in POINT_KINDS_T1 else r * 0.85
            if d > lim:
                continue
            if kind in OVERLAY_KINDS and not self.xray and self._occluded(scene, dg, view, co):
                continue
            score = d - (5.0 if kind in POINT_KINDS_T1 else (2.0 if kind == 'PERP' else 0.0))
            if best_score is None or score < best_score:
                best_score = score
                best = (co, kind, ob, is_inst, d, None)
        if best is None and s.snap_edge:
            for a, b, kind, ob, is_inst in lines:
                p, _t = geom.closest_on_segment_to_ray(a, b, ro, rd)
                sc = view.project(p)
                if sc is None:
                    continue
                d = (sc - m).length
                if d > r * 0.7 or (best_score is not None and d >= best_score):
                    continue
                if kind == 'BOX_EDGE' and not self.xray and self._occluded(scene, dg, view, p):
                    continue
                best_score = d
                best = (p, kind, ob, is_inst, d, (a.copy(), b.copy()))

        if center_hit is not None:
            loc, nor, idx, ob, M, is_inst = center_hit
            self.surface = Snap(loc, 'FACE', None if is_inst else ob,
                                None if is_inst else M.inverted_safe() @ loc, nor.copy(), dist=0.0)
        if best is None:
            if center_hit is not None and s.snap_face:
                return self.surface
            return None
        co, kind, ob, is_inst, d, edge = best
        local = None
        if ob is not None and not is_inst:
            local = ob.matrix_world.inverted_safe() @ co
        return Snap(co, kind, None if is_inst else ob, local, None, edge, d)
