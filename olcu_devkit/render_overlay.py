"""Araç arayüzünü (görünüm üstü çizimler) yazılımsal GPU ile PNG'ye çizer.

Kullanım: <bpy python> olcu_devkit/render_overlay.py <çıktı klasörü>
Sahne basit gölgelendirmeyle, araç çizimleri gerçek çizim fonksiyonlarıyla çizilir.
"""
import math
import os
import sys

import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
gpu.init()
import test_olcu as T  # noqa: E402
from olcu_ustasi import op_cage, op_measure, pins, selection  # noqa: E402

W, H = 1280, 760


def look(eye, target, fov=42.0):
    v = T._view(eye, target, W, H, fov)
    return v


def draw_scene(view):
    """Nesneleri düz gölgeli üçgen olarak çiz (bağlam için)."""
    dg = bpy.context.evaluated_depsgraph_get()
    sh = gpu.shader.from_builtin('SMOOTH_COLOR')
    light = Vector((0.4, -0.6, 0.7)).normalized()
    pts, cols = [], []
    for inst in dg.object_instances:
        ob = inst.object
        if ob.type != 'MESH':
            continue
        me = ob.data
        me.calc_loop_triangles()
        M = inst.matrix_world
        N = M.to_3x3().inverted().transposed()
        base = (0.55, 0.57, 0.62) if "Ref" not in ob.name else (0.35, 0.55, 0.42)
        if ob.original.select_get():
            base = (0.72, 0.62, 0.50)
        for tri in me.loop_triangles:
            n = (N @ tri.normal).normalized()
            k = 0.35 + 0.65 * max(0.0, n.dot(light))
            c = (base[0] * k, base[1] * k, base[2] * k, 1.0)
            for vi in tri.vertices:
                pts.append(M @ me.vertices[vi].co)
                cols.append(c)
    if not pts:
        return
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.depth_mask_set(True)
    b = batch_for_shader(sh, 'TRIS', {"pos": [tuple(p) for p in pts], "color": cols})
    b.draw(sh)
    gpu.state.depth_test_set('NONE')


class R:
    def __init__(self, view):
        self.type = 'WINDOW'
        self.x = self.y = 0
        self.width, self.height = W, H
        self.data = type("RV", (), {"perspective_matrix": view.P})()


def render(view, area, draw3d, draw2d, path, op=None):
    off = gpu.types.GPUOffScreen(W, H)
    region = R(view)
    ctx = T.Ctx(area)
    ctx.region = region
    ctx.region_data = region.data
    with off.bind():
        fb = gpu.state.active_framebuffer_get()
        fb.clear(color=(0.16, 0.16, 0.17, 1.0), depth=1.0)
        gpu.state.viewport_set(0, 0, W, H)
        with gpu.matrix.push_pop():
            gpu.matrix.load_matrix(Matrix.Identity(4))
            gpu.matrix.load_projection_matrix(view.P)
            draw_scene(view)
            for fn in draw3d:
                fn(op, ctx) if op is not None else fn()
        with gpu.matrix.push_pop():
            gpu.matrix.load_matrix(Matrix.Identity(4))
            P = Matrix.Identity(4)
            P[0][0] = 2.0 / W
            P[1][1] = 2.0 / H
            P[0][3] = -1.0
            P[1][3] = -1.0
            gpu.matrix.load_projection_matrix(P)
            for fn in draw2d:
                fn(op, ctx) if op is not None else fn()
        buf = fb.read_color(0, 0, W, H, 4, 0, 'FLOAT')
    off.free()
    arr = np.array(buf.to_list(), dtype=np.float32).reshape(H, W, 4)
    img = bpy.data.images.new("shot", W, H, alpha=False)
    img.pixels.foreach_set(arr.ravel())
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    bpy.data.images.remove(img)
    print("yazıldı:", path)


def patch_ctx():
    # çizim fonksiyonları context.area == op.area kontrol eder
    pass


def shot_measure(out):
    sc = T.reset()
    car, body, wheels, lamp = T.make_car(sc)
    car.rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()
    T.select([body] + wheels, body)
    s = sc.olcu_ustasi
    s.display_unit = 'CM'
    dg = bpy.context.evaluated_depsgraph_get()
    g = selection.Group([body] + wheels)
    box0 = selection.group_box(dg, g.names)
    view = look((box0.center.x + 5, box0.center.y - 11, box0.center.z + 5), box0.center)
    area = T.FakeArea(view)
    ctx = T.Ctx(area)
    op = T._make_op(op_measure.OU_OT_measure)
    a = Vector((box0.lo.x, box0.lo.y, box0.hi.z))
    b = Vector((box0.hi.x, box0.lo.y, box0.hi.z))
    pa, pb = view.project(a), view.project(b)
    op.invoke(ctx, T.ev('MOUSEMOVE', 'NOTHING', pa.x, pa.y))
    op.modal(ctx, T.ev('MOUSEMOVE', 'NOTHING', pa.x + 2, pa.y + 1))
    render(view, area, [op_measure._draw_3d_impl], [op_measure._draw_2d_impl],
           os.path.join(out, "1_hover_A.png"), op)
    op.modal(ctx, T.ev('LEFTMOUSE', 'PRESS', pa.x + 2, pa.y + 1))
    op.modal(ctx, T.ev('X', 'PRESS', pb.x, pb.y))
    op.modal(ctx, T.ev('MOUSEMOVE', 'NOTHING', pb.x - 30, pb.y - 60))
    render(view, area, [op_measure._draw_3d_impl], [op_measure._draw_2d_impl],
           os.path.join(out, "2_axis_lock_B.png"), op)
    op.modal(ctx, T.ev('MOUSEMOVE', 'NOTHING', pb.x + 1, pb.y + 3))
    op.modal(ctx, T.ev('LEFTMOUSE', 'PRESS', pb.x + 1, pb.y + 3))
    for ch in "450":
        op.modal(ctx, T.ev('NONE', 'PRESS', unicode=ch))
    render(view, area, [op_measure._draw_3d_impl], [op_measure._draw_2d_impl],
           os.path.join(out, "3_target_preview.png"), op)
    op.modal(ctx, T.ev('NONE', 'PRESS', unicode='k'))   # 'k' boşken sabitle -> yazılı olduğu için birim
    op._finish(ctx, cancel=True)


def shot_cage(out):
    sc = T.reset()
    car, body, wheels, lamp = T.make_car(sc)
    car.rotation_euler = (0, 0, 0)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(7, 0, 0.75))
    ref = bpy.context.active_object
    ref.name = "Ref"
    ref.scale = (1, 1, 1.5)
    bpy.context.view_layer.update()
    T.select([body], body)
    sc.olcu_ustasi.display_unit = 'M'
    dg = bpy.context.evaluated_depsgraph_get()
    box0 = selection.group_box(dg, selection.Group([body]).names)
    view = look((box0.center.x + 7, box0.center.y - 14, box0.center.z + 6), box0.center + Vector((1.5, 0, 0)))
    area = T.FakeArea(view)
    ctx = T.Ctx(area)
    op = T._make_op(op_cage.OU_OT_cage)
    op.invoke(ctx, T.ev('MOUSEMOVE', 'NOTHING', 0, 0))
    hx = view.project(box0.point((1.0, 0.5, 0.5)))
    op.modal(ctx, T.ev('MOUSEMOVE', 'NOTHING', hx.x, hx.y))
    op.modal(ctx, T.ev('LEFTMOUSE', 'PRESS', hx.x, hx.y))
    tgt = view.project(Vector((6.5, -0.5, 1.5)))        # referans küpün köşesine yapış (Ctrl)
    op.modal(ctx, T.ev('MOUSEMOVE', 'NOTHING', tgt.x + 2, tgt.y + 2, ctrl=True))
    render(view, area, [op_cage._draw_3d], [op_cage._draw_2d], os.path.join(out, "4_cage_snap.png"), op)
    op._finish(ctx, cancel=True)


def shot_pins(out):
    sc = T.reset()
    car, body, wheels, lamp = T.make_car(sc)
    bpy.context.view_layer.update()
    s = sc.olcu_ustasi
    s.display_unit = 'CM'
    p = s.pins.add()
    p.a_obj = wheels[0]
    p.a_co = (0, 0, 0)
    p.b_obj = wheels[1]
    p.b_co = (0, 0, 0)
    p2 = s.pins.add()
    p2.a_co = (body.matrix_world @ Vector((-1, -1, -1)))
    p2.b_co = (body.matrix_world @ Vector((-1, -1, 1)))
    view = look((7, -9, 6), (1, 2, 0.5))
    area = T.FakeArea(view)

    class C:
        pass
    ctx = T.Ctx(area)
    bpy_ctx_region = R(view)
    orig = pins.bpy.context

    class Fake:
        def __getattr__(self, k):
            if k == "region":
                return bpy_ctx_region
            if k == "region_data":
                return bpy_ctx_region.data
            return getattr(orig, k)
    pins.bpy = type("B", (), {"context": Fake(), "types": bpy.types})
    try:
        render(view, area, [pins._draw_3d], [pins._draw_2d], os.path.join(out, "5_pins.png"))
    finally:
        pins.bpy = bpy


if __name__ == "__main__":
    out = sys.argv[-1] if len(sys.argv) > 1 else "."
    os.makedirs(out, exist_ok=True)
    shot_measure(out)
    shot_cage(out)
    shot_pins(out)
