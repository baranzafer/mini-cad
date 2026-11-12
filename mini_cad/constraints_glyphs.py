"""Kısıt simgeleri: görünümde silik kısıt simgelerinin çizimi (POST_PIXEL) ve tıklanan
simgenin bulunması (glyph_at). Sağ tık menüsü draw_glyphs.py'de.
"""

import bpy
import math
import numpy as np
from mathutils import Vector

from . import core
from .constraints_refs import _spline, _world, all_constraints, has_any, ref_points


ICON = {"AXIS": "AXIS", "PARALLEL": "PARALLEL", "PERP": "PERP", "COLLINEAR": "COLLINEAR",
        "EQUAL": "EQUAL", "FIX": "FIX", "COINCIDENT": "COINCIDENT", "SYMMETRIC": "SYMMETRIC",
        "TANGENT": "TANGENT", "DISTANCE": "DISTANCE", "ANGLE": "ANGLE",
        "CONCENTRIC": "CONCENTRIC", "RADIUS": "RADIUS", "SMOOTH": "SMOOTH",
        "SYMLINE": "SYMMETRIC", "PTLINE": "DISTANCE", "LINEDIST": "DISTANCE",
        "CENTERDIST": "DISTANCE"}

DIM_KINDS = ("DISTANCE", "ANGLE", "RADIUS", "PTLINE", "LINEDIST", "CENTERDIST")


_glyph_boxes = []       # son çizimdeki (x0, y0, x1, y1, obje adı, indeks)


def _anchor(r):
    pts = ref_points(r.obj, r.spline, r.index, r.point)
    if pts is None:
        return None
    if r.point:
        return _world(*pts[0])
    sp = _spline(r.obj, r.spline)
    if sp.type == "BEZIER":
        a = sp.bezier_points[pts[0][2]]
        b = sp.bezier_points[pts[1][2]]
        p = [a.co, a.handle_right, b.handle_left, b.co]
        q = 0.125 * (p[0] + 3 * p[1] + 3 * p[2] + p[3])
        return np.array(r.obj.matrix_world @ q)
    return 0.5 * (_world(*pts[0]) + _world(*pts[1]))


# ---------------------------------------------------------------- ölçü çizgileri

def _foot(p, a, b):
    d = b - a
    L = float(np.dot(d, d))
    return a if L < 1e-24 else a + d * float(np.dot(p - a, d)) / L


def _arc_info(r):
    from .constraints_arcs import arc_group, seg_bez
    g = arc_group(r.obj, r.spline, r.index)
    if g is None:
        return None
    P = seg_bez(r.obj, r.spline, g["segs"][len(g["segs"]) // 2])
    q = 0.125 * (P[0] + 3 * P[1] + 3 * P[2] + P[3])
    return g, q


def dim_geometry(c):
    """Ölçünün dünya geometrisi: ("lin", A, B) doğrusal, ("rad", C, Q, çap mı),
    ("ang", X, d1, d2) açı ya da None."""
    from .constraints_refs import _constraint_points
    k = c.kind
    if k == "RADIUS":
        ai = _arc_info(c.refs[0]) if len(c.refs) else None
        if ai is None:
            return None
        g, q = ai
        return ("rad", g["c"], q, c.axis == 1)
    if k == "CENTERDIST":
        if len(c.refs) != 2:
            return None
        ai = _arc_info(c.refs[0])
        if ai is None:
            return None
        C = ai[0]["c"]
        rb = c.refs[1]
        if rb.point:
            pts = ref_points(rb.obj, rb.spline, rb.index, True)
            return None if pts is None else ("lin", C, _world(*pts[0]))
        bi = _arc_info(rb)
        if bi is not None:
            return ("lin", C, bi[0]["c"])
        pts = ref_points(rb.obj, rb.spline, rb.index, False)
        if pts is None:
            return None
        a, b = _world(*pts[0]), _world(*pts[1])
        return ("lin", C, _foot(C, a, b))
    pts = _constraint_points(c)
    if pts is None:
        return None
    P = [_world(*q) for q in pts]
    if k == "DISTANCE":
        return ("lin", P[0], P[-1])
    if k == "PTLINE":
        return ("lin", P[0], _foot(P[0], P[1], P[2]))
    if k == "LINEDIST":
        m = 0.5 * (P[0] + P[1])
        return ("lin", m, _foot(m, P[2], P[3]))
    if k == "ANGLE":
        a1, b1, a2, b2 = P
        d1, d2 = b1 - a1, b2 - a2
        w = a1 - a2
        A, B, C_, D, E = (float(np.dot(d1, d1)), float(np.dot(d1, d2)), float(np.dot(d2, d2)),
                          float(np.dot(d1, w)), float(np.dot(d2, w)))
        den = A * C_ - B * B
        if abs(den) < 1e-18:
            return None
        t1 = (B * E - C_ * D) / den
        X = a1 + d1 * t1
        m1, m2 = 0.5 * (a1 + b1), 0.5 * (a2 + b2)
        return ("ang", X, m1 - X, m2 - X)
    return None


def _arrow(tip, d, s):
    """tip'te biten ok (d: oka doğru birim yön, ekran)."""
    nrm = np.array([-d[1], d[0]])
    base = tip - d * 8 * s
    return [tuple(base + nrm * 3 * s), tuple(tip), tuple(base - nrm * 3 * s), tuple(tip)]


def dim_layout(geo, to_px, s):
    """Ölçünün ekran çizimi: (yazı merkezi, [nokta çiftleri]) ya da None."""
    if geo is None:
        return None
    if geo[0] == "lin":
        a, b = to_px(geo[1]), to_px(geo[2])
        if a is None or b is None:
            return None
        a, b = np.array(a), np.array(b)
        L = float(np.linalg.norm(b - a))
        if L < 2:
            return tuple(a + np.array([10 * s, 10 * s])), []
        u = (b - a) / L
        n = np.array([-u[1], u[0]])
        if n[1] < -1e-9 or (abs(n[1]) <= 1e-9 and n[0] > 0):
            n = -n
        o = 18 * s
        pa, pb = a + n * o, b + n * o
        seg = [tuple(a + n * 3 * s), tuple(pa + n * 4 * s), tuple(b + n * 3 * s),
               tuple(pb + n * 4 * s), tuple(pa), tuple(pb)]
        seg += _arrow(pa, -u, s) + _arrow(pb, u, s)
        return tuple(0.5 * (pa + pb) + n * 9 * s), seg
    if geo[0] == "rad":
        C, Q, dia = geo[1], geo[2], geo[3]
        c, q = to_px(C), to_px(Q)
        if c is None or q is None:
            return None
        c, q = np.array(c), np.array(q)
        L = float(np.linalg.norm(q - c))
        if L < 2:
            return tuple(c), []
        u = (q - c) / L
        seg = [tuple(c - u * L if dia else c), tuple(q)] + _arrow(q, u, s)
        if dia:
            seg += _arrow(c - u * L, -u, s)
        return tuple(q + u * 16 * s), seg
    if geo[0] == "ang":
        X = to_px(geo[1])
        e1, e2 = to_px(geo[1] + geo[2]), to_px(geo[1] + geo[3])
        if X is None or e1 is None or e2 is None:
            return None
        X = np.array(X)
        a1 = math.atan2(e1[1] - X[1], e1[0] - X[0])
        a2 = math.atan2(e2[1] - X[1], e2[0] - X[0])
        da = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
        R = 30 * s
        pts = [X + R * np.array([math.cos(a1 + da * t), math.sin(a1 + da * t)])
               for t in np.linspace(0, 1, 13)]
        seg = []
        for p, q in zip(pts[:-1], pts[1:]):
            seg += [tuple(p), tuple(q)]
        am = a1 + da * 0.5
        return tuple(X + (R + 14 * s) * np.array([math.cos(am), math.sin(am)])), seg
    return None


def dim_text(c):
    if c.kind == "ANGLE":
        txt = f"{math.degrees(c.angle):.1f}°"
    elif c.kind == "RADIUS":
        txt = f"Ø{core.fmt_len(c.length * 2)}" if c.axis == 1 else f"R{core.fmt_len(c.length)}"
    else:
        txt = core.fmt_len(c.length)
    return f"({txt})" if getattr(c, "driven", False) else txt


def glyph_at(mx, my):
    for x0, y0, x1, y1, name, i in _glyph_boxes:
        if x0 <= mx <= x1 and y0 <= my <= y1:
            return name, i
    return None


def _draw_glyphs():
    _glyph_boxes.clear()
    try:
        ctx = bpy.context
        sc = ctx.scene
        if not getattr(sc, "minicad_show_constraints", True) or not has_any(sc):
            return
        from bpy_extras import view3d_utils
        from . import palette
        region, rv3d = ctx.region, ctx.region_data
        if rv3d is None:
            return
        s = ctx.preferences.system.ui_scale
        size = 13 * s
        stack = {}
        gpu_state = __import__("gpu").state
        gpu_state.blend_set("ALPHA")
        for ob, i, c in all_constraints(sc):
            try:
                if not ob.visible_get():
                    continue
            except Exception:
                pass
            col = (0.9, 0.9, 0.9, 0.42) if c.ok else (1.0, 0.35, 0.3, 0.75)
            if not c.enabled:
                col = (0.45, 0.65, 1.0, 0.45)          # dondurulmuş
            for r in c.refs:
                a = _anchor(r)
                if a is None:
                    continue
                px = view3d_utils.location_3d_to_region_2d(region, rv3d, Vector(tuple(a)))
                if px is None:
                    continue
                key = (round(px.x / 4), round(px.y / 4))
                k = stack.get(key, 0)
                stack[key] = k + 1
                x = px.x + 10 * s + k * (size + 3 * s)
                y = px.y + 8 * s
                if c.kind in DIM_KINDS:
                    txt = dim_text(c)
                    w = 8 * s + len(txt) * 6.5 * s
                    lay = None
                    try:
                        def to_px(p):
                            v = view3d_utils.location_3d_to_region_2d(region, rv3d,
                                                                       Vector(tuple(p)))
                            return None if v is None else (v.x, v.y)
                        lay = dim_layout(dim_geometry(c), to_px, s)
                    except Exception:
                        lay = None
                    if lay is not None:                  # ölçü çizgisi + değer
                        (tx, ty), seg = lay
                        if seg:
                            palette._lines(seg, col, 1.2, region)
                        x0, y0 = tx - w / 2, ty - size / 2
                        palette.rect(x0, y0, x0 + w, y0 + size, (0.1, 0.1, 0.12, 0.45))
                        palette.text(x0 + 4 * s, y0 + 4 * s, txt, col, int(10 * s))
                        _glyph_boxes.append((x0, y0, x0 + w, y0 + size, ob.name, i))
                        break
                    palette.rect(x, y, x + w, y + size, (0.1, 0.1, 0.12, 0.3))
                    palette.text(x + 4 * s, y + 4 * s, txt, col, int(10 * s))
                    _glyph_boxes.append((x, y, x + w, y + size, ob.name, i))
                    stack[key] += int(w / (size + 3 * s))
                    break                # ölçü bir kez yazılsın
                palette.rect(x, y, x + size, y + size, (0.1, 0.1, 0.12, 0.3))
                palette.draw_icon(ICON[c.kind], x + size / 2, y + size / 2, size * 0.75, col,
                                  region, 1.3)
                _glyph_boxes.append((x, y, x + size, y + size, ob.name, i))
        gpu_state.blend_set("NONE")
    except Exception as e:
        print("[Mini CAD] kısıt simgeleri çizilemedi:", e)
