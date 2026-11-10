"""Viewport çizimleri.

Boolean vurgusu: Gövde mavi, İkincil turuncu kenar çizgileriyle viewport'ta gösterilir.
Hayalet fillet: sürüklerken gerçek fillet yerine yarı saydam mor bir şerit çizilir.

CAD gövdelerinde mesh üçgenleri değil, gerçek CAD kenarları çizilir (temiz dış hat).
Vurgu yalnızca İkincil alanı doluyken görünür.
"""

import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from . import core, kernel

COL_BODY = (0.25, 0.62, 1.0, 0.95)    # mavi
COL_TOOL = (1.0, 0.55, 0.10, 0.95)    # turuncu
WIDTH = 2.5

_cache = {}        # obje adı -> (anahtar, çizgi koordinatları)
_handles = []


def _pairs(polys):
    coords = []
    for pts in polys:
        for k in range(len(pts) - 1):
            coords.append(tuple(pts[k]))
            coords.append(tuple(pts[k + 1]))
    return coords


def _cad_lines(ob):
    """CAD gövdesinin kenar çizgileri: hesap sürecinin son tam kalite sonucundan gelir
    (Blender tarafında OCC şekline dokunulmaz)."""
    edges = core._display.get(ob.name, {}).get("edges")
    if not edges:
        return []
    key = ("cad", id(edges))
    hit = _cache.get(ob.name)
    if hit is not None and hit[0] == key:
        return hit[1]
    lines = _pairs(edges)
    _cache[ob.name] = (key, lines)
    return lines


def _mesh_lines(ob):
    mw = ob.matrix_world
    try:
        sig = core.mesh_signature(ob)
    except Exception:
        sig = None
    key = ("mesh", sig, tuple(round(x, 6) for row in mw for x in row))
    hit = _cache.get(ob.name)
    if hit is not None and hit[0] == key:
        return hit[1]
    me = ob.data
    co = [mw @ v.co for v in me.vertices]
    lines = []
    for e in me.edges:
        a, b = e.vertices
        lines.append(tuple(co[a]))
        lines.append(tuple(co[b]))
    _cache[ob.name] = (key, lines)
    return lines


def _draw():
    try:
        ctx = bpy.context
        sc = ctx.scene
        if not getattr(sc, "minicad_bool_highlight", False):
            return
        body, tool = sc.minicad_target, sc.minicad_bool_tool
        if tool is None and body is not None and body.cad.is_cad:
            # Alan boşsa: listede seçili uygulanmış boolean'ın ikincil parçası
            p = body.cad
            i = p.active_bool
            if 0 <= i < len(p.features) and p.features[i].op == "BOOLEAN" and \
                    p.features[i].enabled and p.use_booleans:
                tool = p.features[i].tool
        if tool is None or not kernel.kernel_available():
            return
        region = ctx.region
        shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("NONE")
        for ob, col in ((body, COL_BODY), (tool, COL_TOOL)):
            if ob is None or ob.name not in sc.objects:
                continue
            try:
                if not ob.visible_get():
                    continue
            except Exception:
                pass
            lines = _cad_lines(ob) if ob.cad.is_cad else _mesh_lines(ob)
            if not lines:
                continue
            batch = batch_for_shader(shader, "LINES", {"pos": lines})
            shader.bind()
            shader.uniform_float("viewportSize", (region.width, region.height))
            shader.uniform_float("lineWidth", WIDTH)
            shader.uniform_float("color", col)
            batch.draw(shader)
        gpu.state.blend_set("NONE")
    except Exception as e:
        print("[Mini CAD] boolean vurgusu çizilemedi:", e)


COL_GHOST = (0.85, 0.4, 1.0, 0.30)
COL_GHOST_RIM = (0.95, 0.6, 1.0, 0.95)
_ghost_cache = {}  # obje adı -> (anahtar, tris batch, lines batch)


def _draw_ghosts():
    try:
        ctx = bpy.context
        region = ctx.region
        sc = ctx.scene
        items = [(name, d.get("ghost")) for name, d in list(core._display.items())
                 if d.get("ghost") is not None]
        if not items:
            return
        tri_sh = gpu.shader.from_builtin("UNIFORM_COLOR")
        line_sh = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
        gpu.state.blend_set("ALPHA")
        gpu.state.depth_test_set("NONE")
        gpu.state.depth_mask_set(False)
        for name, g in items:
            ob = sc.objects.get(name)
            if ob is None:
                continue
            try:
                if not ob.visible_get():
                    continue
            except Exception:
                pass
            key = id(g)
            hit = _ghost_cache.get(name)
            if hit is None or hit[0] != key:
                tb = batch_for_shader(tri_sh, "TRIS", {"pos": g["verts"].tolist()},
                                      indices=g["tris"].tolist())
                lb = batch_for_shader(line_sh, "LINES", {"pos": g["lines"].tolist()}) \
                    if len(g["lines"]) else None
                hit = (key, tb, lb)
                _ghost_cache[name] = hit
            _, tb, lb = hit
            tri_sh.bind()
            tri_sh.uniform_float("color", COL_GHOST)
            tb.draw(tri_sh)
            if lb is not None:
                line_sh.bind()
                line_sh.uniform_float("viewportSize", (region.width, region.height))
                line_sh.uniform_float("lineWidth", 1.5)
                line_sh.uniform_float("color", COL_GHOST_RIM)
                lb.draw(line_sh)
        gpu.state.depth_mask_set(True)
        gpu.state.blend_set("NONE")
    except Exception as e:
        print("[Mini CAD] hayalet fillet çizilemedi:", e)


def register():
    _handles.append(bpy.types.SpaceView3D.draw_handler_add(_draw, (), "WINDOW", "POST_VIEW"))
    _handles.append(bpy.types.SpaceView3D.draw_handler_add(_draw_ghosts, (), "WINDOW",
                                                           "POST_VIEW"))


def unregister():
    while _handles:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_handles.pop(), "WINDOW")
        except Exception:
            pass
    _cache.clear()
    _ghost_cache.clear()
