# SPDX-License-Identifier: GPL-3.0-or-later
"""Çoklu seçimi tek bütün olarak ele alma: kökler, hiyerarşi, sıkı sınır kutusu."""
import numpy as np
from mathutils import Matrix, Vector

from . import geom

TO_MESH_TYPES = {'CURVE', 'SURFACE', 'FONT', 'META'}
NON_GEOM = {'EMPTY', 'LIGHT', 'CAMERA', 'SPEAKER', 'LIGHT_PROBE', 'ARMATURE', 'LATTICE'}


def ancestors(o):
    p = o.parent
    while p is not None:
        yield p
        p = p.parent


def descendants(o):
    try:
        return list(o.children_recursive)
    except AttributeError:          # eski sürümler
        out, stack = [], list(o.children)
        while stack:
            c = stack.pop()
            out.append(c)
            stack.extend(c.children)
        return out


def depth(o):
    return sum(1 for _ in ancestors(o))


class Group:
    """Seçili nesneler ve onlara bağlı her şey."""

    def __init__(self, selected, include_children=True):
        self.selected = [o for o in selected if o is not None]
        sel = set(self.selected)
        # kök: atası seçimde olmayan seçili nesne -> ölçek yalnız köklere uygulanır,
        # alt nesneler ebeveyn ilişkisiyle birlikte gelir (ilişkiler hiç değişmez)
        self.roots = [o for o in self.selected if not any(a in sel for a in ancestors(o))]
        full = []
        seen = set()
        for o in self.roots:
            for x in [o] + descendants(o):
                if x not in seen:
                    seen.add(x)
                    full.append(x)
        for o in self.selected:          # (her durumda listede olsun)
            if o not in seen:
                seen.add(o)
                full.append(o)
        self.hierarchy = full                     # köklerin tüm ağacı
        self.objects = full if include_children else list(self.selected)
        self.names = {o.name for o in self.objects}
        self.hier_names = {o.name for o in self.hierarchy}

    def __bool__(self):
        return bool(self.roots)

    def contains(self, ob):
        return ob is not None and ob.name in self.hier_names


# --------------------------------------------------------------- nokta toplama

def _mesh_local_np(me):
    n = len(me.vertices)
    if n == 0:
        return None
    co = np.empty(n * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    return co.reshape(-1, 3).astype(np.float64)


def eval_local_points(ob_eval):
    """Değerlendirilmiş nesnenin yerel noktaları (N,3) ya da None."""
    t = ob_eval.type
    if t == 'MESH':
        try:
            return _mesh_local_np(ob_eval.data)
        except (AttributeError, RuntimeError, ReferenceError):
            pass
    if t in TO_MESH_TYPES or t == 'MESH':
        try:
            me = ob_eval.to_mesh()
            try:
                return _mesh_local_np(me) if me else None
            finally:
                ob_eval.to_mesh_clear()
        except (RuntimeError, AttributeError, ReferenceError):
            pass
    if t in NON_GEOM:
        return None
    try:
        bb = np.array([tuple(c) for c in ob_eval.bound_box], dtype=np.float64)
        if np.allclose(bb, 0):
            return None
        return bb
    except (AttributeError, ReferenceError):
        return None


def _accumulate(loc_pts, M, F, acc):
    A = np.array(M, dtype=np.float64)
    Fn = np.array(F, dtype=np.float64)
    # dünya = A3 p + t ; çerçeve = F^T dünya
    W = A[:3, :3].T @ Fn
    t = A[:3, 3] @ Fn
    q = loc_pts @ W + t
    lo = q.min(axis=0)
    hi = q.max(axis=0)
    if acc[0] is None:
        acc[0], acc[1] = lo, hi
    else:
        acc[0] = np.minimum(acc[0], lo)
        acc[1] = np.maximum(acc[1], hi)


def group_box(depsgraph, names, frame=None):
    """names içindeki nesnelerin (ve örnekledikleri koleksiyonların) sıkı kutusu."""
    F = Matrix(frame) if frame is not None else Matrix.Identity(3)
    acc = [None, None]
    cache = {}
    origins = []
    for inst in depsgraph.object_instances:
        ob = inst.object
        if inst.is_instance:
            par = inst.parent
            owner = par.original if par is not None else None
        else:
            owner = ob.original
        if owner is None or owner.name not in names:
            continue
        if not inst.is_instance:
            try:
                if not owner.visible_get():
                    continue
            except (RuntimeError, ReferenceError):
                pass
            origins.append(Vector(owner.matrix_world.translation))
        if ob.type in NON_GEOM:
            continue
        key = (ob.original.name, ob.type)
        if key not in cache:
            cache[key] = eval_local_points(ob)
        pts = cache[key]
        if pts is None:
            continue
        _accumulate(pts, inst.matrix_world.copy(), F, acc)
    if acc[0] is None:
        if not origins:
            return None
        loc = [F.transposed() @ o for o in origins]
        lo = Vector(tuple(min(v[i] for v in loc) for i in range(3)))
        hi = Vector(tuple(max(v[i] for v in loc) for i in range(3)))
        return geom.Box(lo, hi, F)
    return geom.Box(Vector(acc[0].tolist()), Vector(acc[1].tolist()), F)


def object_box(ob_eval, matrix, frame=None):
    """Tek nesnenin sıkı kutusu (verilen matrisle)."""
    pts = eval_local_points(ob_eval)
    if pts is None:
        return None
    F = Matrix(frame) if frame is not None else geom.frame_from_matrix(matrix)
    acc = [None, None]
    _accumulate(pts, matrix, F, acc)
    return geom.Box(Vector(acc[0].tolist()), Vector(acc[1].tolist()), F)


def frame_for(space, group, context):
    """Kutu yönelimi: 'WORLD' ya da 'LOCAL' (aktif nesne / ilk kök)."""
    if space == 'LOCAL':
        ob = context.active_object if context.active_object in group.objects else None
        if ob is None and group.roots:
            ob = group.roots[0]
        if ob is not None:
            return geom.frame_from_matrix(ob.matrix_world)
    return Matrix.Identity(3)


# ------------------------------------------------------------------ animasyon

TRANSFORM_PATHS = {"location", "rotation_euler", "rotation_quaternion", "rotation_axis_angle",
                   "scale", "delta_location", "delta_scale", "delta_rotation_euler",
                   "delta_rotation_quaternion"}


def iter_fcurves(ob):
    ad = ob.animation_data
    if ad is None or ad.action is None:
        return
    act = ad.action
    if hasattr(act, "layers"):
        slot = getattr(ad, "action_slot", None)
        for layer in act.layers:
            for strip in layer.strips:
                try:
                    cb = strip.channelbag(slot) if slot is not None else None
                except (TypeError, RuntimeError):
                    cb = None
                if cb is not None:
                    yield from cb.fcurves
    elif hasattr(act, "fcurves"):
        yield from act.fcurves


def transform_fcurves(ob):
    return [fc for fc in iter_fcurves(ob) if fc.data_path in TRANSFORM_PATHS]


def has_transform_anim(ob):
    if transform_fcurves(ob):
        return True
    ad = ob.animation_data
    if ad is not None:
        for d in ad.drivers:
            if d.data_path in TRANSFORM_PATHS:
                return True
        if len(ad.nla_tracks):
            return True
    return False
