"""Ölçü Ustası testleri — gerçek bpy (pip 'bpy' modülü) ile, pencere olmadan.

Çalıştır:  <bpy python> olcu_devkit/test_olcu.py
"""
import math
import os
import sys
import time
import traceback
from types import SimpleNamespace

import bpy
import numpy as np
from mathutils import Matrix, Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import olcu_ustasi  # noqa: E402
from olcu_ustasi import geom, scaling, selection, snapping, units  # noqa: E402

RESULTS = []


def test(fn):
    RESULTS.append(fn)
    return fn


def close(a, b, tol=1e-5):
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))


def vclose(a, b, tol=1e-5):
    return (Vector(a) - Vector(b)).length <= tol * max(1.0, Vector(a).length)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    try:
        olcu_ustasi.unregister()
    except Exception:
        pass
    olcu_ustasi.register()
    return bpy.context.scene


def world_verts(dg=None):
    """Tüm görünür geometrinin değerlendirilmiş dünya köşeleri: {nesne: (N,3)}"""
    dg = dg or bpy.context.evaluated_depsgraph_get()
    out = {}
    for inst in dg.object_instances:
        ob = inst.object
        if ob.type != 'MESH':
            continue
        me = ob.data
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        M = np.array(inst.matrix_world)
        key = (inst.parent.original.name + ">" if inst.is_instance else "") + ob.original.name
        out[key] = co @ M[:3, :3].T + M[:3, 3]
    return out


def world_normals():
    dg = bpy.context.evaluated_depsgraph_get()
    out = {}
    for inst in dg.object_instances:
        ob = inst.object
        if ob.type != 'MESH' or inst.is_instance:
            continue
        me = ob.data
        M = inst.matrix_world.to_3x3()
        N = M.inverted().transposed()
        out[ob.original.name] = [(N @ p.normal).normalized() for p in me.polygons]
    return out


def apply_M(arr, M):
    A = np.array(M)
    return arr @ A[:3, :3].T + A[:3, 3]


def make_car(sc):
    """Araç benzeri çok parçalı model."""
    col = sc.collection
    car = bpy.data.objects.new("Car", None)
    col.objects.link(car)
    car.location = (1.0, 2.0, 0.0)
    car.rotation_euler = (0, 0, math.radians(30))
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
    body = bpy.context.active_object
    body.name = "Body"
    body.scale = (2.0, 1.0, 0.5)
    body.location = (1.0, 2.0, 0.8)
    bev = body.modifiers.new("bev", 'BEVEL')
    bev.width = 0.05
    sol = body.modifiers.new("sol", 'SOLIDIFY')
    sol.thickness = 0.02
    body.parent = car
    body.matrix_parent_inverse = car.matrix_world.inverted()
    bpy.ops.mesh.primitive_cylinder_add(radius=0.35, depth=0.25, vertices=24)
    w0 = bpy.context.active_object
    w0.name = "Wheel0"
    wheels = [w0]
    for i in range(1, 4):
        w = bpy.data.objects.new(f"Wheel{i}", w0.data)   # paylaşılan mesh
        col.objects.link(w)
        wheels.append(w)
    pos = [(-1.3, 1.0, -0.4), (1.3, 1.0, -0.4), (-1.3, -1.0, -0.4), (1.3, -1.0, -0.4)]
    for w, p in zip(wheels, pos):
        w.rotation_euler = (math.radians(90), 0, 0)
        w.parent = body
        w.location = Vector(p)
        # gövde ölçeği tekere geçmesin diye ters matris (Ctrl+P gibi)
        w.matrix_parent_inverse = Matrix.Diagonal((0.5, 1.0, 2.0, 1.0))
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.1, location=(0, 0, 0))
    lamp = bpy.context.active_object
    lamp.name = "Lamp"
    lamp.parent = w0           # torun
    lamp.location = (0, 0, 0.3)
    bpy.context.view_layer.update()
    return car, body, wheels, lamp


def select(objs, active=None):
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = active or (objs[0] if objs else None)


# =========================================================================== testler

@test
def t_units():
    u = units.UnitCtx('CM', 1.0, 'METRIC', 2)
    assert close(units.parse_length("150", u), 1.5)
    assert close(units.parse_length("4.5m", u), 4.5)
    assert close(units.parse_length("1,5 m", u), 1.5)
    assert close(units.parse_length("1m 20cm", u), 1.2)
    assert close(units.parse_length("2*30cm", u), 0.6)
    assert close(units.parse_length("1m + 20", u), 1.2)       # birimsiz -> cm
    assert close(units.parse_length("10in", u), 0.254)
    assert close(units.parse_length("5'", u), 1.524)
    assert units.parse_target("150%", u) == ('FACTOR', 1.5)
    assert units.parse_target("*2", u) == ('FACTOR', 2.0)
    assert units.parse_target("x0.5", u) == ('FACTOR', 0.5)
    assert units.parse_target("/4", u) == ('FACTOR', 0.25)
    assert units.safe_parse_target("abc", u) is None
    assert units.safe_parse_target("2 parsecs", u) is None
    assert units.safe_parse_target("__import__('os')", u) is None
    assert u.fmt(1.234) == "123.40 cm", u.fmt(1.234)
    assert u.fmt(1.23456).startswith("~123.46"), u.fmt(1.23456)
    u2 = units.UnitCtx(None, 1.0, 'METRIC', 2)
    assert u2.fmt(0.005).endswith("mm") and u2.fmt(2.0).endswith(" m") and u2.fmt(0.5).endswith("cm")
    u3 = units.UnitCtx('M', 0.01, 'METRIC', 3)          # scale_length 0.01: 1 BU = 1 cm
    assert close(units.parse_length("1m", u3), 100.0)
    assert u3.fmt(100.0) == "1.000 m"


@test
def t_group_roots():
    sc = reset()
    car, body, wheels, lamp = make_car(sc)
    g = selection.Group([body] + wheels + [lamp])
    assert [o.name for o in g.roots] == ["Body"], [o.name for o in g.roots]
    assert set(o.name for o in g.hierarchy) == {"Body", "Wheel0", "Wheel1", "Wheel2", "Wheel3", "Lamp"}
    g2 = selection.Group([wheels[0], lamp])
    assert [o.name for o in g2.roots] == ["Wheel0"]


def _check_uniform_scale(apply_data):
    sc = reset()
    car, body, wheels, lamp = make_car(sc)
    select([body] + wheels, body)
    before = world_verts()
    pinv = {w.name: w.matrix_parent_inverse.copy() for w in wheels}
    g = selection.Group(bpy.context.selected_objects)
    piv = Vector((0.3, -0.2, 0.0))
    M = geom.scale_matrix(piv, 2.5)
    msgs, emp = scaling.Scaler(g).finalize(bpy.context, M, pivot=piv, apply_data=apply_data)
    bpy.context.view_layer.update()
    after = world_verts()
    for k, v in before.items():
        err = np.abs(after[k] - apply_M(v, M)).max()
        assert err < 1e-4, (k, err, msgs)
    assert not emp
    # ilişkiler: ebeveynler aynı, paylaşım aynı
    assert all(w.parent == body for w in wheels)
    assert lamp.parent == wheels[0]
    assert len({w.data.name for w in wheels}) == 1, "tekerlek mesh paylaşımı bozuldu"
    if not apply_data:
        for w in wheels:
            assert geom.matrices_close(w.matrix_parent_inverse, pinv[w.name])
    return body, wheels, lamp, msgs


@test
def t_uniform_scale_direct():
    body, wheels, lamp, msgs = _check_uniform_scale(False)
    assert close(body.modifiers["bev"].width, 0.05), "değiştirici değeri değişmemeli (nesne ölçeği)"


@test
def t_uniform_scale_apply_data():
    body, wheels, lamp, msgs = _check_uniform_scale(True)
    for o in wheels + [lamp]:
        sc_ = o.matrix_world.to_scale()
        assert all(close(x, 1.0, 1e-4) for x in sc_), (o.name, sc_, msgs)
    # gövde: eşit olmayan ölçek + bevel -> uygulanırsa bevel bozulur, bilerek korunur
    assert any("Body" in m for m in msgs), msgs
    assert close(body.modifiers["bev"].width, 0.05)


@test
def t_apply_modifiers_scaled():
    sc = reset()
    bpy.ops.mesh.primitive_cube_add(size=2)
    c = bpy.context.active_object
    c.scale = (3, 3, 3)
    b = c.modifiers.new("b", 'BEVEL')
    b.width = 0.1
    s_ = c.modifiers.new("s", 'SOLIDIFY')
    s_.thickness = 0.05
    a = c.modifiers.new("a", 'ARRAY')
    a.use_constant_offset = True
    a.constant_offset_displace = (0.5, 0, 0)
    before = world_verts()
    rep = scaling.apply_scale(bpy.context, [c])
    bpy.context.view_layer.update()
    after = world_verts()
    assert c.name in rep.applied, rep.messages()
    assert close(b.width, 0.3) and close(s_.thickness, 0.15)
    assert vclose(a.constant_offset_displace, (1.5, 0, 0))
    k = list(before)[0]
    # aynı değerlendirilmiş geometri (sıra aynı)
    assert np.abs(after[k] - before[k]).max() < 1e-4, np.abs(after[k] - before[k]).max()


@test
def t_apply_negative_scale_normals():
    sc = reset()
    bpy.ops.mesh.primitive_cube_add(size=2)
    c = bpy.context.active_object
    c.scale = (-2, 1, 1)
    n0 = world_normals()[c.name]
    v0 = world_verts()[c.name]
    rep = scaling.apply_scale(bpy.context, [c])
    bpy.context.view_layer.update()
    n1 = world_normals()[c.name]
    assert c.name in rep.applied
    assert all(vclose(a, b, 1e-4) for a, b in zip(n0, n1)), "aynalı nesnede normaller ters döndü"
    assert np.abs(world_verts()[c.name] - v0).max() < 1e-5


@test
def t_apply_shared_with_outside():
    sc = reset()
    bpy.ops.mesh.primitive_cube_add(size=2)
    a = bpy.context.active_object
    b = bpy.data.objects.new("B", a.data)
    sc.collection.objects.link(b)
    b.location = (5, 0, 0)
    a.scale = (2, 2, 2)
    before = world_verts()
    rep = scaling.apply_scale(bpy.context, [a])
    bpy.context.view_layer.update()
    after = world_verts()
    assert a.data != b.data and rep.copied == 1
    for k in before:
        assert np.abs(after[k] - before[k]).max() < 1e-5, k


@test
def t_apply_shear_hierarchy():
    """Eşit olmayan ebeveyn + dönük çocuk (eğiklik) -> veri afin dönüşür, görünüm aynı."""
    sc = reset()
    bpy.ops.mesh.primitive_cube_add(size=1)
    p = bpy.context.active_object
    p.name = "P"
    p.scale = (3, 1, 1)
    bpy.ops.mesh.primitive_cone_add()
    ch = bpy.context.active_object
    ch.name = "Ch"
    ch.parent = p
    ch.rotation_euler = (0.3, 0.6, 0.9)
    ch.location = (1, 1, 0)
    bpy.context.view_layer.update()
    before = world_verts()
    rep = scaling.apply_scale(bpy.context, [p, ch])
    bpy.context.view_layer.update()
    after = world_verts()
    for k in before:
        assert np.abs(after[k] - before[k]).max() < 1e-4, (k, np.abs(after[k] - before[k]).max())
    for o in (p, ch):
        assert all(close(x, 1, 1e-4) for x in o.matrix_world.to_scale()), (o.name, rep.messages())
    assert ch.parent == p


@test
def t_nonuniform_rotated_uses_empty():
    sc = reset()
    car, body, wheels, lamp = make_car(sc)
    body.rotation_euler = (0, 0, math.radians(30))
    bpy.context.view_layer.update()
    select([body], body)
    before = world_verts()
    g = selection.Group([body])
    piv = Vector((0, 0, 0))
    M = geom.axis_scale_matrix(piv, Vector((1, 0, 0)), 1.7)
    msgs, emp = scaling.Scaler(g).finalize(bpy.context, M, frame=Matrix.Identity(3), pivot=piv)
    bpy.context.view_layer.update()
    after = world_verts()
    for k, v in before.items():
        err = np.abs(after[k] - apply_M(v, M)).max()
        assert err < 1e-4, (k, err, msgs)
    assert emp, "dönük gövde eşit olmayan ölçekte Empty kullanmalıydı"
    e = emp[0]
    assert body.parent == e and e.parent == car, "eski ebeveyn ilişkisi korunmalı"


@test
def t_nonuniform_aligned_direct():
    sc = reset()
    bpy.ops.mesh.primitive_cube_add(size=2)
    c = bpy.context.active_object
    before = world_verts()
    g = selection.Group([c])
    M = geom.axis_scale_matrix(Vector((1, 0, 0)), Vector((1, 0, 0)), 3.0)
    msgs, emp = scaling.Scaler(g).finalize(bpy.context, M, pivot=Vector((1, 0, 0)))
    bpy.context.view_layer.update()
    after = world_verts()
    k = c.name
    assert np.abs(after[k] - apply_M(before[k], M)).max() < 1e-5
    assert not emp and c.parent is None


@test
def t_animated_root_fcurves():
    sc = reset()
    bpy.ops.mesh.primitive_cube_add(size=1)
    c = bpy.context.active_object
    c.location = (0, 0, 0)
    c.keyframe_insert("location", frame=1)
    c.location = (4, 1, 2)
    c.keyframe_insert("location", frame=11)
    sc.frame_set(1)
    snaps = {}
    for f in (1, 6, 11):
        sc.frame_set(f)
        snaps[f] = world_verts()[c.name].copy()
    sc.frame_set(1)
    g = selection.Group([c])
    piv = Vector((1, 1, 0))
    M = geom.scale_matrix(piv, 0.5)
    msgs, emp = scaling.Scaler(g).finalize(bpy.context, M, pivot=piv)
    assert not emp, msgs
    for f in (1, 6, 11):
        sc.frame_set(f)
        err = np.abs(world_verts()[c.name] - apply_M(snaps[f], M)).max()
        assert err < 1e-4, (f, err)


@test
def t_animated_place_translation():
    sc = reset()
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 3))
    c = bpy.context.active_object
    c.delta_location = (0.5, 0, 0)
    c.keyframe_insert("location", frame=1)
    c.location = (2, 0, 5)
    c.keyframe_insert("location", frame=11)
    snaps = {}
    for f in (1, 11):
        sc.frame_set(f)
        snaps[f] = world_verts()[c.name].copy()
    sc.frame_set(1)
    select([c], c)
    assert bpy.ops.olcu.place(target='FLOOR') == {'FINISHED'}
    sc.frame_set(1)
    dz = -snaps[1][:, 2].min()
    for f in (1, 11):
        sc.frame_set(f)
        exp = snaps[f] + np.array([0, 0, dz])
        assert np.abs(world_verts()[c.name] - exp).max() < 1e-4, f


@test
def t_animated_child_parented_empty():
    sc = reset()
    p = bpy.data.objects.new("Par", None)
    sc.collection.objects.link(p)
    p.rotation_euler = (0, 0, 0.5)
    bpy.ops.mesh.primitive_cube_add(size=1)
    c = bpy.context.active_object
    c.parent = p
    c.location = (1, 0, 0)
    c.keyframe_insert("location", frame=1)
    c.location = (3, 0, 0)
    c.keyframe_insert("location", frame=11)
    snaps = {}
    for f in (1, 11):
        sc.frame_set(f)
        snaps[f] = world_verts()[c.name].copy()
    sc.frame_set(1)
    M = geom.scale_matrix(Vector((0, 0, 0)), 2.0)
    msgs, emp = scaling.Scaler(selection.Group([c])).finalize(bpy.context, M)
    assert emp and c.parent == emp[0] and emp[0].parent == p
    for f in (1, 11):
        sc.frame_set(f)
        err = np.abs(world_verts()[c.name] - apply_M(snaps[f], M)).max()
        assert err < 1e-4, (f, err)


@test
def t_group_box_tight_and_instances():
    sc = reset()
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 1))
    c = bpy.context.active_object
    c.rotation_euler = (0, 0, math.radians(45))
    m = c.modifiers.new("s", 'SUBSURF')
    m.levels = 3
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    b = selection.group_box(dg, {c.name})
    wv = world_verts()[c.name]
    assert vclose(b.lo, wv.min(axis=0).tolist()) and vclose(b.hi, wv.max(axis=0).tolist())
    # yerel kutu
    bl = selection.group_box(dg, {c.name}, geom.frame_from_matrix(c.matrix_world))
    assert close(bl.size.x, bl.size.y) and bl.size.x < b.size.x
    # koleksiyon örneği
    colx = bpy.data.collections.new("Asset")
    sc.collection.children.link(colx)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    k = bpy.context.active_object
    sc.collection.objects.unlink(k)
    colx.objects.link(k)
    colx.hide_viewport = False
    e = bpy.data.objects.new("Inst", None)
    e.instance_type = 'COLLECTION'
    e.instance_collection = colx
    sc.collection.objects.link(e)
    e.location = (10, 0, 0)
    e.scale = (2, 2, 2)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    bi = selection.group_box(dg, {e.name})
    assert bi is not None and vclose(bi.lo, (9, -1, -1)) and vclose(bi.hi, (11, 1, 1)), (bi.lo, bi.hi)


def _view(eye, target, w=1000, h=800, fov=50.0):
    eye, target = Vector(eye), Vector(target)
    f = (target - eye).normalized()
    up = Vector((0, 0, 1))
    if abs(f.dot(up)) > 0.99:
        up = Vector((0, 1, 0))
    s_ = f.cross(up).normalized()
    u_ = s_.cross(f)
    V = Matrix((
        (s_.x, s_.y, s_.z, -s_.dot(eye)),
        (u_.x, u_.y, u_.z, -u_.dot(eye)),
        (-f.x, -f.y, -f.z, f.dot(eye)),
        (0, 0, 0, 1)))
    n, fa = 0.01, 1000.0
    t = 1.0 / math.tan(math.radians(fov) / 2)
    a = w / h
    P = Matrix((
        (t / a, 0, 0, 0), (0, t, 0, 0),
        (0, 0, (fa + n) / (n - fa), 2 * fa * n / (n - fa)), (0, 0, -1, 0)))
    return geom.View(P @ V, w, h)


def _snap_settings():
    return SimpleNamespace(snap_vert=True, snap_edge=True, snap_mid=True, snap_face=True,
                           snap_face_center=False, snap_box=True, snap_origin=False,
                           snap_perp=True, snap_only_selection=False, snap_radius=16)


@test
def t_snapping_elements():
    sc = reset()
    bpy.ops.mesh.primitive_cube_add(size=2)
    c = bpy.context.active_object
    bpy.context.view_layer.update()
    view = _view((6, -7, 5), (0, 0, 0))
    s = _snap_settings()
    sn = snapping.Snapper(bpy.context, s, selection.Group([c]))
    corner = Vector((1, -1, 1))
    p = view.project(corner)
    r = sn.find(bpy.context, view, p.x + 4, p.y - 3)
    assert r is not None and r.kind in ('VERT', 'BOX_CORNER') and vclose(r.co, corner), (r and r.kind, r and r.co)
    mid = Vector((0, -1, 1))
    p = view.project(mid)
    r = sn.find(bpy.context, view, p.x + 2, p.y + 1)
    assert r.kind in ('EDGE_MID', 'BOX_MID') and vclose(r.co, mid), (r.kind, r.co)
    on_edge = Vector((0.55, -1, 1))
    p = view.project(on_edge)
    s.snap_mid = False
    r = sn.find(bpy.context, view, p.x, p.y + 1)
    assert r.kind in ('EDGE', 'BOX_EDGE') and abs(r.co.y + 1) < 1e-4 and abs(r.co.z - 1) < 1e-4, (r.kind, r.co)
    s.snap_mid = True
    face_pt = Vector((0.6, -1, 0.5))
    p = view.project(face_pt)
    r = sn.find(bpy.context, view, p.x, p.y)
    assert r.kind == 'FACE' and vclose(r.co, face_pt, 1e-3), (r.kind, r.co)
    assert r.obj == c and r.local is not None
    # dik ayak: A=(3,-1,1)'den üst ön kenara dik -> (1,-1,1)?  kenar y=-1,z=1, x∈[-1,1]: ayak x=?  ref (0.3,-1,3)
    ref = Vector((0.3, -1, 3))
    foot = Vector((0.3, -1, 1))
    p = view.project(foot)
    r = sn.find(bpy.context, view, p.x + 1, p.y, ref=ref)
    assert r.kind == 'PERP' and vclose(r.co, foot), (r.kind, r.co)


@test
def t_snapping_box_of_selection():
    sc = reset()
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=(0, 0, 1))
    sph = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(size=0.5, location=(3, 0, 0.25))
    cube = bpy.context.active_object
    g = selection.Group([sph, cube])
    dg = bpy.context.evaluated_depsgraph_get()
    box = selection.group_box(dg, g.names)
    view = _view((2, -9, 6), (1.5, 0, 0.8))
    sn = snapping.Snapper(bpy.context, _snap_settings(), g)
    sn.box = box
    tgt = Vector((box.lo.x, box.lo.y, box.hi.z))      # boşlukta kutu köşesi (küre ~ -1,-1,2)
    p = view.project(tgt)
    r = sn.find(bpy.context, view, p.x + 3, p.y + 2)
    assert r is not None and r.kind == 'BOX_CORNER' and vclose(r.co, tgt), (r and r.kind, r and r.co, tgt)


@test
def t_snapping_only_selection_sees_through():
    sc = reset()
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 0))
    back = bpy.context.active_object
    bpy.ops.mesh.primitive_plane_add(size=6, location=(0, -3, 0), rotation=(math.radians(90), 0, 0))
    front = bpy.context.active_object
    view = _view((0, -10, 0.3), (0, 0, 0))
    s = _snap_settings()
    s.snap_box = False
    s.snap_only_selection = True
    sn = snapping.Snapper(bpy.context, s, selection.Group([back]))
    p = view.project(Vector((0.1, -1, 0.2)))
    r = sn.find(bpy.context, view, p.x, p.y)
    assert r is not None and r.obj == back and abs(r.co.y + 1) < 1e-3, (r and r.obj, r and r.co)


@test
def t_snapping_performance_dense():
    sc = reset()
    n = 1000 if os.environ.get("OLCU_HEAVY") else 300
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=n, y_subdivisions=n, size=4)
    g1 = bpy.context.active_object
    k = 512 if os.environ.get("OLCU_HEAVY") else 160
    bpy.ops.mesh.primitive_uv_sphere_add(segments=k, ring_count=k, radius=1, location=(0, 0, 1))
    sph = bpy.context.active_object
    m = sph.modifiers.new("s", 'SUBSURF')
    m.levels = 1
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    nf = sum(len(o.evaluated_get(dg).data.polygons) for o in (g1, sph))
    view = _view((4, -5, 4), (0, 0, 0.5))
    s = _snap_settings()
    g = selection.Group([sph])
    t0 = time.perf_counter()
    box = selection.group_box(dg, g.names)
    tb = time.perf_counter() - t0
    sn = snapping.Snapper(bpy.context, s, g)
    sn.box = box
    sn.find(bpy.context, view, 500, 400)           # ilk çağrı BVH kurar
    t0 = time.perf_counter()
    n = 0
    for x in range(200, 800, 12):
        for y in range(250, 550, 30):
            sn.find(bpy.context, view, x, y)
            n += 1
    dt = (time.perf_counter() - t0) / n
    print(f"    {nf/1e6:.2f}M yüz: fare başı {dt*1000:.2f} ms ({n} sorgu), kutu {tb*1000:.0f} ms")
    assert dt < 0.012, f"yakalama çok yavaş: {dt*1000:.1f} ms"


@test
def t_loose_wire_snap():
    sc = reset()
    me = bpy.data.meshes.new("wire")
    me.from_pydata([(0, 0, 0), (2, 0, 0), (2, 2, 0)], [(0, 1), (1, 2)], [])
    ob = bpy.data.objects.new("Wire", me)
    sc.collection.objects.link(ob)
    bpy.context.view_layer.update()
    view = _view((1, -6, 5), (1, 1, 0))
    s = _snap_settings()
    s.snap_box = False
    sn = snapping.Snapper(bpy.context, s, None)
    p = view.project(Vector((2, 0, 0)))
    r = sn.find(bpy.context, view, p.x + 3, p.y)
    assert r is not None and r.kind == 'VERT' and vclose(r.co, (2, 0, 0)), (r and r.kind)


@test
def t_fit_to_active_op():
    sc = reset()
    car, body, wheels, lamp = make_car(sc)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(20, 0, 0))
    ref = bpy.context.active_object
    ref.name = "Ref"
    ref.dimensions = (4.5, 2.0, 1.5)
    bpy.context.view_layer.update()
    select([body, ref], ref)
    s = sc.olcu_ustasi
    s.box_space = 'WORLD'
    r = bpy.ops.olcu.fit_to_active(mode='X', align='BOTTOM')
    assert r == {'FINISHED'}, r
    dg = bpy.context.evaluated_depsgraph_get()
    g = selection.Group([body])
    b = selection.group_box(dg, g.names)
    tb = selection.object_box(ref.evaluated_get(dg), ref.matrix_world, Matrix.Identity(3))
    assert close(b.size.x, 4.5, 1e-4), b.size
    assert vclose(b.bottom_center(), tb.bottom_center(), 1e-4)


@test
def t_dims_property_setter():
    sc = reset()
    car, body, wheels, lamp = make_car(sc)
    select([body], body)
    s = sc.olcu_ustasi
    s.lock_ratio = True
    s.pivot = 'BOX_BOTTOM'
    z0 = sc.olcu_dim_z
    x0 = sc.olcu_dim_x
    dg = bpy.context.evaluated_depsgraph_get()
    bot0 = selection.group_box(dg, selection.Group([body]).names).bottom_center()
    sc.olcu_dim_z = z0 * 2
    bpy.context.view_layer.update()
    from olcu_ustasi import ops_misc
    ops_misc.invalidate_dims()
    assert close(sc.olcu_dim_z, z0 * 2, 1e-4) and close(sc.olcu_dim_x, x0 * 2, 1e-4)
    dg = bpy.context.evaluated_depsgraph_get()
    bot1 = selection.group_box(dg, selection.Group([body]).names).bottom_center()
    assert vclose(bot0, bot1, 1e-4), "alt merkez sabit kalmalı"
    s.lock_ratio = False
    sc.olcu_dim_x = x0
    ops_misc.invalidate_dims()
    assert close(sc.olcu_dim_x, x0, 1e-4) and close(sc.olcu_dim_z, z0 * 2, 1e-4)


@test
def t_ops_misc():
    sc = reset()
    car, body, wheels, lamp = make_car(sc)
    select([body], body)
    sc.olcu_ustasi.pivot = 'BOX_CENTER'
    before = world_verts()
    assert bpy.ops.olcu.scale_factor(factor=0.01) == {'FINISHED'}
    after = world_verts()
    dg = bpy.context.evaluated_depsgraph_get()
    assert close(np.ptp(after["Body"][:, 0]), np.ptp(before["Body"][:, 0]) * 0.01, 1e-4)
    assert bpy.ops.olcu.place(target='FLOOR') == {'FINISHED'}
    dg = bpy.context.evaluated_depsgraph_get()
    b = selection.group_box(dg, selection.Group([body]).names)
    assert abs(b.lo.z) < 1e-6
    assert bpy.ops.olcu.apply_scale_safe() == {'FINISHED'}
    for o in wheels:
        assert all(close(x, 1, 1e-4) for x in o.matrix_world.to_scale()), o.name


# ------------------------------------------------------------- modal akış (sahte olaylarla)

class FakeRegion:
    def __init__(self, view):
        self.type = 'WINDOW'
        self.x = 0
        self.y = 0
        self.width = int(view.w)
        self.height = int(view.h)
        self.data = SimpleNamespace(perspective_matrix=view.P)

    def tag_redraw(self):
        pass


class FakeArea:
    def __init__(self, view):
        self.type = 'VIEW_3D'
        self.regions = [FakeRegion(view)]

    def tag_redraw(self):
        pass

    def header_text_set(self, t):
        self.header = t


class Ctx:
    def __init__(self, area):
        self._c = bpy.context
        self.area = area
        self.region = area.regions[0]
        self.region_data = self.region.data
        self.window_manager = SimpleNamespace(modal_handler_add=lambda op: None, clipboard="")
        self.workspace = None

    def __getattr__(self, k):
        return getattr(self._c, k)


def ev(type, value='PRESS', x=0, y=0, unicode="", shift=False, ctrl=False):
    return SimpleNamespace(type=type, value=value, mouse_x=int(x), mouse_y=int(y), unicode=unicode,
                           shift=shift, ctrl=ctrl, alt=False, oskey=False)


def _make_op(cls):
    plain = type("T_" + cls.__name__, (), {k: v for k, v in cls.__dict__.items()
                                          if not k.startswith("__")})
    op = plain()
    op.report = lambda lvl, msg: op.__dict__.setdefault("_reports", []).append(msg)
    return op


@test
def t_modal_measure_scale_flow():
    """A köşe -> B köşe (X kilidi) -> '9m' yaz -> Enter: model tek bütün ölçeklenir."""
    from olcu_ustasi.op_measure import OU_OT_measure
    sc = reset()
    car, body, wheels, lamp = make_car(sc)
    car.rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()
    select([body] + wheels, body)
    s = sc.olcu_ustasi
    s.pivot = 'BOX_BOTTOM'
    s.display_unit = 'M'
    dg = bpy.context.evaluated_depsgraph_get()
    g = selection.Group([body] + wheels)
    box0 = selection.group_box(dg, g.names)
    before = world_verts()
    view = _view((box0.center.x + 3, box0.center.y - 12, box0.center.z + 5), box0.center)
    area = FakeArea(view)
    ctx = Ctx(area)
    op = _make_op(OU_OT_measure)
    a = Vector((box0.lo.x, box0.lo.y, box0.hi.z))
    b = Vector((box0.hi.x, box0.lo.y, box0.hi.z))
    pa, pb = view.project(a), view.project(b)
    assert op.invoke(ctx, ev('MOUSEMOVE', 'NOTHING', pa.x, pa.y)) == {'RUNNING_MODAL'}
    try:
        op.modal(ctx, ev('MOUSEMOVE', 'NOTHING', pa.x + 2, pa.y + 1))
        assert op.hover.kind == 'BOX_CORNER', op.hover.kind
        op.modal(ctx, ev('LEFTMOUSE', 'PRESS', pa.x + 2, pa.y + 1))
        assert op.phase == 'B'
        op.modal(ctx, ev('X', 'PRESS', pb.x, pb.y))
        assert op.cons is not None and op.cons.kind == 'AXIS' and op.cons.idx == 0
        op.modal(ctx, ev('MOUSEMOVE', 'NOTHING', pb.x + 1, pb.y + 4))
        op.modal(ctx, ev('LEFTMOUSE', 'PRESS', pb.x + 1, pb.y + 4))
        assert op.phase == 'TARGET'
        L = op._measured()
        assert close(L, box0.size.x, 1e-4), (L, box0.size.x)
        for ch in "9m":
            op.modal(ctx, ev('NONE', 'PRESS', unicode=ch))
        assert op.factor is not None and close(op.factor, 9.0 / L, 1e-6), (op.typed, op.factor, op.error)
        r = op.modal(ctx, ev('RET', 'PRESS'))
        assert r == {'FINISHED'}, r
    finally:
        for h in ("_h3d", "_h2d"):
            hd = getattr(op, h, None)
            if hd:
                bpy.types.SpaceView3D.draw_handler_remove(hd, 'WINDOW')
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    box1 = selection.group_box(dg, g.names)
    assert close(box1.size.x, 9.0, 1e-4), box1.size
    assert vclose(box1.bottom_center(), box0.bottom_center(), 1e-4)
    f = 9.0 / L
    M = geom.scale_matrix(box0.bottom_center(), f)
    after = world_verts()
    for k in before:
        assert np.abs(after[k] - apply_M(before[k], M)).max() < 1e-4, k


@test
def t_modal_measure_reference_and_cancel():
    from olcu_ustasi.op_measure import OU_OT_measure
    sc = reset()
    bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 1))
    c = bpy.context.active_object
    bpy.ops.mesh.primitive_cube_add(size=1, location=(4, 0, 0.5))
    ref = bpy.context.active_object
    ref.scale = (3, 1, 1)
    bpy.context.view_layer.update()
    select([c], c)
    view = _view((2, -12, 6), (2, 0, 0.5))
    ctx = Ctx(FakeArea(view))
    op = _make_op(OU_OT_measure)
    P = view.project
    pts = [Vector((-1, -1, 2)), Vector((1, -1, 2)), Vector((2.5, -0.5, 1)), Vector((5.5, -0.5, 1))]
    op.invoke(ctx, ev('MOUSEMOVE', 'NOTHING', P(pts[0]).x, P(pts[0]).y))
    try:
        for i, p in enumerate(pts[:2]):
            q = P(p)
            op.modal(ctx, ev('MOUSEMOVE', 'NOTHING', q.x + 1, q.y))
            op.modal(ctx, ev('LEFTMOUSE', 'PRESS', q.x + 1, q.y))
        assert op.phase == 'TARGET' and close(op._measured(), 2.0, 1e-4)
        op.modal(ctx, ev('NONE', 'PRESS', unicode='r'))
        assert op.phase == 'REF_C'
        for p in pts[2:]:
            q = P(p)
            op.modal(ctx, ev('MOUSEMOVE', 'NOTHING', q.x + 1, q.y))
            op.modal(ctx, ev('LEFTMOUSE', 'PRESS', q.x + 1, q.y))
        assert op.phase == 'TARGET' and close(op.ref_len, 3.0, 1e-4), op.ref_len
        assert close(op.factor, 1.5, 1e-4)
        # canlı önizleme uygulandı mı
        assert close(c.matrix_world.to_scale().x, 1.5, 1e-4)
        r = op.modal(ctx, ev('ESC', 'PRESS'))
        assert r == {'CANCELLED'}
        assert close(c.matrix_world.to_scale().x, 1.0, 1e-6), "iptal geri yüklemeli"
    finally:
        for h in ("_h3d", "_h2d"):
            hd = getattr(op, h, None)
            if hd:
                bpy.types.SpaceView3D.draw_handler_remove(hd, 'WINDOW')


@test
def t_modal_cage_drag_and_type():
    from olcu_ustasi.op_cage import OU_OT_cage
    sc = reset()
    car, body, wheels, lamp = make_car(sc)
    car.rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()
    select([body], body)
    sc.olcu_ustasi.box_space = 'WORLD'
    dg = bpy.context.evaluated_depsgraph_get()
    g = selection.Group([body])
    box0 = selection.group_box(dg, g.names)
    view = _view((box0.center.x + 4, box0.center.y - 10, box0.center.z + 4), box0.center)
    ctx = Ctx(FakeArea(view))
    op = _make_op(OU_OT_cage)
    op.invoke(ctx, ev('MOUSEMOVE', 'NOTHING', 0, 0))
    try:
        # +Z yüz tutamacı -> 'yükseklik 3m' yaz
        hz = view.project(box0.point((0.5, 0.5, 1.0)))
        op.modal(ctx, ev('MOUSEMOVE', 'NOTHING', hz.x, hz.y))
        assert op.hover is not None and op.hover.kind == 'FACE' and op.hover.ax == 2, op.hover and op.hover.key()
        op.modal(ctx, ev('LEFTMOUSE', 'PRESS', hz.x, hz.y))
        for ch in "3m":
            op.modal(ctx, ev('NONE', 'PRESS', unicode=ch))
        op.modal(ctx, ev('RET', 'PRESS'))
        assert op.drag is None and len(op.history) == 1
        # +X yüzünü sürükle (Shift: tek eksen)
        b1 = op.box()
        hx = view.project(b1.point((1.0, 0.5, 0.5)))
        tgt = view.project(b1.point((1.0, 0.5, 0.5)) + Vector((1.0, 0, 0)))
        op.modal(ctx, ev('MOUSEMOVE', 'NOTHING', hx.x, hx.y))
        op.modal(ctx, ev('LEFTMOUSE', 'PRESS', hx.x, hx.y))
        op.modal(ctx, ev('MOUSEMOVE', 'NOTHING', tgt.x, tgt.y, shift=True))
        op.modal(ctx, ev('LEFTMOUSE', 'RELEASE', tgt.x, tgt.y, shift=True))
        assert len(op.history) == 2
        r = op.modal(ctx, ev('RET', 'PRESS'))
        assert r == {'FINISHED'}, r
    finally:
        for h in ("_h3d", "_h2d"):
            hd = getattr(op, h, None)
            if hd:
                bpy.types.SpaceView3D.draw_handler_remove(hd, 'WINDOW')
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    b = selection.group_box(dg, g.names)
    assert close(b.size.z, 3.0, 1e-4), b.size
    f = 3.0 / box0.size.z
    assert close(b.size.x, box0.size.x * f + 1.0, 2e-3), (b.size.x, box0.size.x * f + 1.0)
    assert close(b.size.y, box0.size.y * f, 1e-4)
    assert abs(b.lo.z - box0.lo.z) < 1e-4, "zemin korunmalı"


class FakeLayout:
    """Panel çizimini kaydeder; özellik ve işlem adlarını doğrular."""

    def __init__(self):
        self.enabled = True
        self.scale_y = 1.0

    def _sub(self, *a, **k):
        return FakeLayout()
    row = column = box = grid_flow = split = _sub

    def label(self, **k):
        pass

    def separator(self, **k):
        pass

    def prop(self, data, name, **k):
        assert name in data.bl_rna.properties, f"özellik yok: {name}"

    def operator(self, idname, **k):
        mod, fn = idname.split(".")
        rna = getattr(getattr(bpy.ops, mod), fn).get_rna_type()
        props = rna.properties

        class OpProps:
            def __setattr__(self, n, v):
                assert n in props, f"{idname} özelliği yok: {n}"
        return OpProps()


@test
def t_panels_draw():
    sc = reset()
    car, body, wheels, lamp = make_car(sc)
    bpy.ops.mesh.primitive_cube_add()
    s = sc.olcu_ustasi
    p = s.pins.add()
    s.last_value = 1.0
    from olcu_ustasi import ui
    for sel in ([], [body, wheels[0], bpy.context.active_object]):
        select(sel, sel[-1] if sel else None)
        for cls in ui.classes:
            pnl = type("P", (), dict(cls.__dict__))()
            pnl.layout = FakeLayout()
            if hasattr(cls, "poll") and not cls.poll(bpy.context):
                continue
            if hasattr(pnl, "draw_header"):
                pnl.draw_header(bpy.context)
            pnl.draw(bpy.context)
    lay = FakeLayout()
    ui._menu(type("M", (), {"layout": lay})(), bpy.context)
    ui._menu_transform(type("M", (), {"layout": lay})(), bpy.context)


def main():
    fails = 0
    for fn in RESULTS:
        t0 = time.perf_counter()
        try:
            fn()
            print(f"  geçti  {fn.__name__}  ({(time.perf_counter() - t0) * 1000:.0f} ms)")
        except Exception:
            fails += 1
            print(f"  KALDI  {fn.__name__}")
            traceback.print_exc()
    print("SONUÇ:", "tamam" if not fails else f"{fails} hata")
    return fails


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
