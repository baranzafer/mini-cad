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
        "TANGENT": "TANGENT", "DISTANCE": "DISTANCE", "ANGLE": "ANGLE"}


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
                if c.kind in ("DISTANCE", "ANGLE"):
                    txt = core.fmt_len(c.length) if c.kind == "DISTANCE" else \
                        f"{math.degrees(c.angle):.1f}°"
                    w = 8 * s + len(txt) * 6.5 * s
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
