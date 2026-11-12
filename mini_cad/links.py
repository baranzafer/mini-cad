"""İlişkisel geometri (v0.21.0): desen kopyaları ve yansıtmalar kaynağa bağlı kalır.

Kayıtlar tel kafes eğrisinin obj.cad.links listesindedir (core.MINICAD_Link):
  RPAT / CPAT  kaynak spline'ların dönüşmüş kopyaları (dst, örnek sırasıyla). Adet değişince
               eksik kopyalar sona eklenir, fazlalar silinir (referanslar remap_splines ile
               yeniden eşlenir).
  PROJ         kaynak segmentin (başka bir eğride de olabilir) çizim düzlemine izdüşümü.

Ne zaman güncellenir: ilişki değerleri değişince ve eğri geometrisi değişince (zamanlayıcı ile,
kısıt çözümünden sonra). Kopyalar kaynaktan üretildiği için elle düzenlenmeleri kalıcı olmaz
(Inventor'daki desen gibi). Değişiklik yoksa yazılmaz (sonsuz güncelleme döngüsü olmasın).
"""

import math
import traceback

import bpy
import numpy as np
from bpy.app.handlers import persistent
from mathutils import Vector

from . import core
from . import sketchmath as sm

_flags = {"busy": False}


def transforms(lk):
    """İlişkinin dönüşümleri (özdeşlik hariç), örnek sırasıyla."""
    if lk.kind == "RPAT":
        d1 = np.array(lk.dir1, dtype=np.float64) * lk.s1
        d2 = np.array(lk.dir2, dtype=np.float64) * lk.s2
        return sm.rect_pattern(d1, lk.n1, d2 if lk.n2 > 1 else None, lk.n2)
    if lk.kind == "CPAT":
        return sm.circ_pattern(np.array(lk.center, dtype=np.float64),
                               np.array(lk.axis, dtype=np.float64), lk.n1,
                               math.degrees(lk.angle))
    return []


def remove_splines(ob, idxs):
    """Spline'ları siler; bütün referanslar yeniden eşlenir."""
    sps = ob.data.splines
    idxs = sorted({i for i in idxs if 0 <= i < len(sps)}, reverse=True)
    for si in idxs:
        sps.remove(sps[si])
    gone = set(idxs)

    def fn(si):
        if si in gone:
            return None
        return si - sum(1 for r in gone if r < si)
    core.remap_splines(ob, fn)


def _new_like(ob, src):
    sp = ob.data.splines.new("BEZIER")
    if len(src.bezier_points) > 1:
        sp.bezier_points.add(len(src.bezier_points) - 1)
    sp.use_cyclic_u = src.use_cyclic_u
    return sp


def _write_spline(ob, sp, pts, types, cyclic):
    """pts: [(co, hl, hr)] dünya; değişmediyse yazmaz. Değişti mi."""
    mw = ob.matrix_world
    mwi = mw.inverted()
    tol = 1e-9 * (1.0 + max(float(np.abs(np.asarray(q)).max()) for p in pts for q in p))
    same = len(sp.bezier_points) == len(pts) and sp.use_cyclic_u == cyclic
    if same:
        for b, (co, hl, hr) in zip(sp.bezier_points, pts):
            if (np.linalg.norm(np.array(mw @ b.co) - co) > tol or
                    np.linalg.norm(np.array(mw @ b.handle_left) - hl) > tol or
                    np.linalg.norm(np.array(mw @ b.handle_right) - hr) > tol):
                same = False
                break
    if same:
        return False
    for b, (co, hl, hr) in zip(sp.bezier_points, pts):
        b.handle_left_type = b.handle_right_type = "FREE"
        b.co = mwi @ Vector(tuple(co))
        b.handle_left = mwi @ Vector(tuple(hl))
        b.handle_right = mwi @ Vector(tuple(hr))
    for b, (tl, tr) in zip(sp.bezier_points, types):
        b.handle_left_type, b.handle_right_type = tl, tr
    sp.use_cyclic_u = cyclic
    try:
        ob.data.update_tag()
    except Exception:
        pass
    return True


def _spline_pts(ob, sp, f=None):
    mw = ob.matrix_world
    out, types = [], []
    for b in sp.bezier_points:
        co, hl, hr = (np.array(mw @ v, dtype=np.float64) for v in
                      (b.co, b.handle_left, b.handle_right))
        if f is not None:
            co, hl, hr = f(co), f(hl), f(hr)
        out.append((co, hl, hr))
        types.append((b.handle_left_type, b.handle_right_type))
    return out, types


def regen_pattern(ob, lk):
    sps = ob.data.splines
    src = core._int_list(lk.src)
    if not src or any(not (0 <= s < len(sps)) or sps[s].type != "BEZIER" for s in src):
        lk.info = "kaynak eğri kayboldu"
        return False
    fns = transforms(lk)
    need = len(fns) * len(src)
    dst = [d for d in core._int_list(lk.dst) if 0 <= d < len(sps) and d not in src]
    changed = False
    if len(dst) > need:                         # adet azaldı: fazla kopyalar silinir
        extra = dst[need:]
        lk.dst = ",".join(str(x) for x in dst[:need])
        remove_splines(ob, extra)
        src = core._int_list(lk.src)
        dst = core._int_list(lk.dst)
        changed = True
    while len(dst) < need:                      # adet arttı: sona yeni kopya
        s = src[len(dst) % len(src)]
        _new_like(ob, sps[s])
        dst.append(len(sps) - 1)
        changed = True
    lk.dst = ",".join(str(x) for x in dst)
    for i, f in enumerate(fns):
        for j, s in enumerate(src):
            d = dst[i * len(src) + j]
            if len(sps[d].bezier_points) != len(sps[s].bezier_points):
                # kaynağın nokta sayısı değişti: kopya yeniden kurulur (sona taşınır)
                _new_like(ob, sps[s])
                nd = len(sps) - 1
                remove_splines(ob, [d])
                dst = core._int_list(lk.dst)
                nd -= 1 if d < nd else 0
                dst[i * len(src) + j] = nd
                lk.dst = ",".join(str(x) for x in dst)
                src = core._int_list(lk.src)
                changed = True
                d = nd
            pts, types = _spline_pts(ob, sps[src[j]], f)
            changed |= _write_spline(ob, sps[d], pts, types, sps[src[j]].use_cyclic_u)
    lk.info = ""
    return changed


def regen_projection(ob, lk):
    so = lk.src_obj
    try:
        si, seg = (int(x) for x in lk.src.split(":")[:2])
        sp = so.data.splines[si]
        g = core._spline_segment(so, si, sp, seg, so.matrix_world)
    except Exception:
        g = None
    dst = core._int_list(lk.dst)
    if g is None or not dst or not (0 <= dst[0] < len(ob.data.splines)):
        lk.info = "kaynak kenar kayboldu"
        return False
    n = np.array(lk.plane_n, dtype=np.float64)
    n = n / max(float(np.linalg.norm(n)), 1e-15)
    o = np.array(lk.plane_o, dtype=np.float64)
    P = [np.array(tuple(v), dtype=np.float64) for v in g["p"]]
    P = [p - n * float(np.dot(p - o, n)) for p in P]
    if len(P) == 2:
        P = [P[0], P[0] + (P[1] - P[0]) / 3.0, P[0] + (P[1] - P[0]) * (2.0 / 3.0), P[1]]
        types = [("VECTOR", "VECTOR"), ("VECTOR", "VECTOR")]
    else:
        types = [("FREE", "FREE"), ("FREE", "FREE")]
    pts = [(P[0], P[0] - (P[1] - P[0]), P[1]), (P[3], P[2], P[3] + (P[3] - P[2]))]
    dsp = ob.data.splines[dst[0]]
    if len(dsp.bezier_points) != 2:
        lk.info = "yansıtılan eğri değiştirilmiş"
        return False
    lk.info = ""
    return _write_spline(ob, dsp, pts, types, False)


def update_all(scene=None):
    """Bütün ilişkileri günceller. Değişen ilişki sayısı."""
    if _flags["busy"]:
        return 0
    scene = scene or bpy.context.scene
    _flags["busy"] = True
    n = 0
    try:
        for ob in list(scene.objects):
            if ob.type != "CURVE" or not len(getattr(ob.cad, "links", ())):
                continue
            for lk in list(ob.cad.links):
                if not lk.enabled:
                    continue
                try:
                    fn = regen_projection if lk.kind == "PROJ" else regen_pattern
                    if fn(ob, lk):
                        n += 1
                except Exception as e:
                    lk.info = f"güncellenemedi: {e}"
                    traceback.print_exc()
    finally:
        _flags["busy"] = False
    return n


def has_any(scene):
    for ob in scene.objects:
        if ob.type == "CURVE" and len(getattr(ob.cad, "links", ())):
            return True
    return False


def _tick():
    try:
        if core._transform_running():
            return 0.1
        update_all(bpy.context.scene)
    except Exception:
        traceback.print_exc()
    return None


def request(force=False):
    if _flags["busy"]:
        return
    try:
        if not bpy.app.timers.is_registered(_tick):
            bpy.app.timers.register(_tick, first_interval=0.1)
    except Exception:
        pass


@persistent
def on_depsgraph_update(scene, depsgraph):
    if _flags["busy"]:
        return
    try:
        if not has_any(scene):
            return
        for u in depsgraph.updates:
            idd = u.id
            if isinstance(idd, bpy.types.Curve) or (
                    isinstance(idd, bpy.types.Object) and idd.type == "CURVE" and
                    (u.is_updated_geometry or u.is_updated_transform)):
                request()
                return
    except Exception:
        pass


class MINICAD_OT_link_remove(bpy.types.Operator):
    bl_idname = "minicad.link_remove"
    bl_label = "İlişkiyi Kaldır"
    bl_description = "İlişkiyi kaldırır; kopyalar / yansıtma bağımsız eğri olarak kalır"
    bl_options = {"REGISTER", "UNDO"}

    obj: bpy.props.StringProperty()
    index: bpy.props.IntProperty()

    def execute(self, context):
        ob = bpy.data.objects.get(self.obj)
        if ob is not None and 0 <= self.index < len(ob.cad.links):
            ob.cad.links.remove(self.index)
        return {"FINISHED"}


classes = (MINICAD_OT_link_remove,)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)


def unregister():
    if on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
