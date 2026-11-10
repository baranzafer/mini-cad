"""Kısıt veri erişimi: referans sayıları, spline / nokta okuma, referans noktalarının dünya
konumu, bütün kısıtları toplama. constraints.py bu adları yeniden dışa aktarır.
"""

import numpy as np

from . import core


SEG_COUNT = {"AXIS": 1, "PARALLEL": 2, "PERP": 2, "COLLINEAR": 2, "EQUAL": 2,
             "DISTANCE": 1, "ANGLE": 2, "TANGENT": 2}


PT_COUNT = {"FIX": 1, "COINCIDENT": 2, "SYMMETRIC": 2}


NAMES = {k: n for k, n, _ in core.CONSTRAINT_KINDS}


_last_pos = {}         # (obje, spline, nokta) -> son çözümdeki dünya konumu


def needed(kind):
    """(kaç referans, nokta mı)"""
    if kind in PT_COUNT:
        return PT_COUNT[kind], True
    return SEG_COUNT.get(kind, 1), False


def _spline(ob, si):
    sps = ob.data.splines
    return sps[si] if 0 <= si < len(sps) else None


def _npts(sp):
    return len(sp.bezier_points) if sp.type == "BEZIER" else len(sp.points)


def _co(ob, si, i):
    sp = _spline(ob, si)
    if sp.type == "BEZIER":
        return sp.bezier_points[i].co.copy()
    return sp.points[i].co.xyz.copy()


def ref_points(ob, si, idx, point):
    """Referansın noktaları [(obje, spline, nokta)] ya da geçersizse None."""
    if ob is None or ob.type != "CURVE":
        return None
    sp = _spline(ob, si)
    if sp is None or sp.type not in ("BEZIER", "POLY"):
        return None
    n = _npts(sp)
    if point:
        return [(ob, si, idx)] if 0 <= idx < n else None
    if not (0 <= idx < core._seg_count(sp)):
        return None
    return [(ob, si, idx), (ob, si, (idx + 1) % n)]


def _world(ob, si, i):
    return np.array(ob.matrix_world @ _co(ob, si, i))


def _constraint_points(c):
    pts = []
    for r in c.refs:
        p = ref_points(r.obj, r.spline, r.index, r.point)
        if p is None:
            return None
        pts += p
    return pts


def all_constraints(scene):
    for ob in scene.objects:
        if ob.type == "CURVE":
            for i, c in enumerate(ob.cad.constraints):
                yield ob, i, c


def has_any(scene):
    for ob in scene.objects:
        if ob.type == "CURVE" and len(ob.cad.constraints):
            return True
    return False
