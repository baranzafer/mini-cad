# SPDX-License-Identifier: GPL-3.0-or-later
"""Sabitlenmiş ölçüler: nesnelere bağlı kalır, model değişince değerleri canlı güncellenir."""
import bpy
from mathutils import Vector

from . import draw as D
from . import geom
from .units import UnitCtx

_handles = []


def pin_points(p):
    """(A, B_izdüşümlü, B_ham) dünya noktaları."""
    a = (p.a_obj.matrix_world @ Vector(p.a_co)) if p.a_obj else Vector(p.a_co)
    b = (p.b_obj.matrix_world @ Vector(p.b_co)) if p.b_obj else Vector(p.b_co)
    bp = b
    if p.mode == 'AXIS':
        d = Vector(p.axis).normalized()
        bp = a + d * (b - a).dot(d)
    elif p.mode == 'PLANE':
        n = Vector(p.axis).normalized()
        bp = b - n * (b - a).dot(n)
    return a, bp, b


def pin_length(p):
    a, bp, _b = pin_points(p)
    return (bp - a).length


def _draw_3d():
    sc = bpy.context.scene
    s = getattr(sc, "olcu_ustasi", None)
    if s is None or not s.show_pins or not len(s.pins):
        return
    with D.State():
        for p in s.pins:
            if not p.visible:
                continue
            a, bp, b = pin_points(p)
            D.lines([a, bp], D.COL_PIN, 2.0)
            if (b - bp).length > 1e-9:
                D.dashed(bp, b, (D.COL_PIN[0], D.COL_PIN[1], D.COL_PIN[2], 0.4), 1.0, 12)


def _draw_2d():
    ctx = bpy.context
    sc = ctx.scene
    s = getattr(sc, "olcu_ustasi", None)
    if s is None or not s.show_pins or not len(s.pins):
        return
    region, rv3d = ctx.region, ctx.region_data
    if region is None or rv3d is None:
        return
    view = geom.View.from_region(region, rv3d)
    u = UnitCtx.from_settings(s, sc)
    with D.State():
        for i, p in enumerate(s.pins):
            if not p.visible:
                continue
            a, bp, _b = pin_points(p)
            pa, pb = view.project(a), view.project(bp)
            if pa is None or pb is None:
                continue
            D.point(pa, D.COL_PIN, 3.0)
            D.point(pb, D.COL_PIN, 3.0)
            mid = (pa + pb) * 0.5
            tag = f"#{i + 1}  " if len(s.pins) > 1 else ""
            D.text(mid.x, mid.y + 10, tag + u.fmt((bp - a).length), 12, D.COL_TEXT,
                   (0.25, 0.12, 0.45, 0.8), 4, 'CENTER')


def register():
    _handles.append(bpy.types.SpaceView3D.draw_handler_add(_draw_3d, (), 'WINDOW', 'POST_VIEW'))
    _handles.append(bpy.types.SpaceView3D.draw_handler_add(_draw_2d, (), 'WINDOW', 'POST_PIXEL'))


def unregister():
    while _handles:
        h = _handles.pop()
        try:
            bpy.types.SpaceView3D.draw_handler_remove(h, 'WINDOW')
        except (ValueError, ReferenceError):
            pass
