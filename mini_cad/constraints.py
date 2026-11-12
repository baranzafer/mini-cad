"""Tel kafes kısıtları: veri erişimi, çözücüyü çalıştırma, canlı tetikleme ve simgeler.

Kısıtlar, ilk referansın eğri objesinde (obj.cad.constraints) saklanır; başka eğri
objelerindeki segment ve noktalara da referans verebilir. Çözüm dünya koordinatında
yapılır, sonuç objelerin kendi uzayına yazılır (tutamaçlar noktayla birlikte taşınır,
böylece eğrinin şekli bozulmaz).

Ne zaman çözülür: kısıt eklenince / değeri değişince hemen; eğri düzenlenince kullanıcı
sürüklemeyi BIRAKINCA (G/R/S sürerken Blender'ın taşıma aracıyla çakışmamak için).
Kullanıcının taşıdığı noktalar yerinde kalır, diğerleri uyum sağlar.
"""

import math
import time
import traceback

import bpy
import numpy as np
from bpy.app.handlers import persistent
from mathutils import Vector

from . import core, solver

# Bölünmüş parçalar (v0.15.2); adlar geriye dönük uyum için burada da erişilebilir.
from .constraints_refs import (
    MIXED, NAMES, PT_COUNT, SEG_COUNT, slot_type, _co, _constraint_points, _last_pos, _npts, _spline, _world,
    all_constraints, has_any, needed, ref_points,
)
from .constraints_tangent import (
    DIR_KINDS, _arc_run, _arc_slide, _bez, _handle_vec, _joint, _line_constrained, _pick_side,
    _seg_straight, _set_handle_dir, _set_world, _side, _tangent_plan,
)
from .constraints_glyphs import ICON, _anchor, _draw_glyphs, _glyph_boxes, glyph_at
from .constraints_arcs import arc_group, center_dist_value, centers_dist, group_key, \
    radius_of, rebuild_group, smooth_post

_flags = {"solving": False, "force": False, "prefer": None}

_handles = []


# ---------------------------------------------------------------- çözüm

def _params(c, owner, P):
    if c.kind == "AXIS":
        return {"axis": c.axis}
    if c.kind == "DISTANCE":
        return {"value": c.length}
    if c.kind == "ANGLE":
        return {"value": math.degrees(c.angle)}
    if c.kind == "FIX":
        return {"pos": tuple(owner.matrix_world @ Vector(c.pos))}
    if c.kind == "SYMMETRIC":
        return {"axis": c.axis, "offset": c.offset}
    if c.kind in ("PTLINE", "LINEDIST"):
        return {"value": c.length}
    return {}


def _kname(k):
    """Değişken anahtarının adı: gerçek (obje adı, spline, nokta) ya da sanal yay merkezi."""
    return k[:4] if k[0] == "@c" else (k[0].name, k[1], k[2])


def _kpos(k):
    return np.asarray(k[4], dtype=np.float64) if k[0] == "@c" else _world(*k)


VALUE_KINDS = ("DISTANCE", "ANGLE", "RADIUS", "PTLINE", "LINEDIST", "CENTERDIST")


def _is_arc_ref(r):
    return r is not None and not r.point and arc_group(r.obj, r.spline, r.index) is not None


def measure_value(c):
    """Ölçü kısıtının şu anki geometrideki değeri (referans ölçüler için). None: ölçülemez."""
    if c.kind == "RADIUS":
        return radius_of(c)
    if c.kind == "CENTERDIST":
        return center_dist_value(c)
    pts = _constraint_points(c)
    if pts is None:
        return None
    P = np.array([_world(o, si, pi) for o, si, pi in pts])
    if c.kind in ("DISTANCE", "PTLINE", "LINEDIST", "ANGLE"):
        return solver.measure(c.kind, P)
    return None


def _set_measured(c):
    v = measure_value(c)
    if v is None:
        c.ok, c.info = False, "ölçülemedi (referans kayboldu)"
        return
    if c.kind == "ANGLE":
        if abs(math.radians(v) - c.angle) > 1e-12:
            c.angle = math.radians(v)
    elif abs(v - c.length) > 1e-12:
        c.length = v
    c.ok, c.info = True, ""


def solve_all(scene=None, force=False, prefer=None, dry=False):
    """Sahnedeki bütün kısıtları çözer. prefer: yerinde kalması istenen nokta anahtarları.
    dry: çözüm hesaplanır, kısıtların ok / info durumu yazılır ama geometri değişmez (yeni
    ölçünün çelişip çelişmediğini anlamak için). Referans (driven) ölçüler çözüme girmez,
    değerleri geometriden ölçülür."""
    if _flags["solving"]:
        return True
    scene = scene or bpy.context.scene
    _flags["solving"] = True
    driven = []
    try:
        keys, var_of, cons, owners, post = [], {}, [], [], []
        hold = set()                     # eğri / yay noktaları: şekil bozulmasın diye sabit
        arc_jobs = {}                    # sanal merkez adı -> (obje, spline, grup)

        def var(name, key):
            if name not in var_of:
                var_of[name] = len(keys)
                keys.append(key)
            return var_of[name]

        sized = set()                    # yarıçap ölçüsü / eşit yarıçapı olan yay grupları
        for _o, _j, c in all_constraints(scene):
            if not c.enabled or getattr(c, "driven", False):
                continue
            arcs = []
            if c.kind == "RADIUS":
                arcs = c.refs[:1]
            elif c.kind == "EQUAL" and len(c.refs) == 2 and all(_is_arc_ref(r) for r in c.refs):
                arcs = c.refs
            for r in arcs:
                if r.point:
                    continue
                g = arc_group(r.obj, r.spline, r.index)
                if g is not None:
                    sized.add(group_key(r.obj, r.spline, g))

        def center(r, keep_radius):
            """Yayın sanal merkez değişkeni (düğümler merkeze bağlanır). (indeks, düğümler)"""
            g = arc_group(r.obj, r.spline, r.index) if not r.point else None
            if g is None:
                return None, None
            ck = group_key(r.obj, r.spline, g)
            ci = var(ck, ck + (g["c"],))
            arc_jobs.setdefault(ck, (r.obj, r.spline, g))
            nid = tuple(var((r.obj.name, r.spline, k), (r.obj, r.spline, k)) for k in g["nodes"])
            if keep_radius and ck not in sized:
                # boyutu ölçülmeyen yay: boyutu korunur (Inventor gibi)
                cons.append(("RADIUSN", (ci,) + nid, {"value": g["R"]}))
                owners.append(None)
                sized.add(ck)
            return ci, (nid, g)

        def pt_vars(r):
            pts = ref_points(r.obj, r.spline, r.index, r.point)
            if pts is None:
                return None
            return [var((o.name, si, pi), (o, si, pi)) for o, si, pi in pts]

        for ob, _i, c in all_constraints(scene):
            if not c.enabled:
                continue
            if getattr(c, "driven", False):
                driven.append(c)
                continue
            if c.kind in ("RADIUS", "CONCENTRIC") or (
                    c.kind == "EQUAL" and len(c.refs) == 2 and
                    all(_is_arc_ref(r) for r in c.refs)):
                got = [center(r, c.kind == "CONCENTRIC") for r in c.refs]
                if any(ci is None for ci, _ in got) or not got:
                    c.ok, c.info = False, "yay / daire gerekli (ya da referans kayboldu)"
                    continue
                if c.kind == "RADIUS":
                    ci, (nid, g) = got[0]
                    cons.append(("RADIUSN", (ci,) + nid, {"value": c.length}))
                    owners.append(c)
                elif c.kind == "CONCENTRIC":
                    cons.append(("COINCIDENT", (got[0][0], got[1][0]), {}))
                    owners.append(c)
                else:                                  # eşit yarıçap
                    for ci, (nid, g) in got:
                        if len(nid) >= 2:
                            cons.append(("EQDIST", (ci,) + nid, {}))
                            owners.append(c)
                    (c1, (n1, _)), (c2, (n2, _)) = got
                    cons.append(("EQUAL", (c1, n1[0], c2, n2[0]), {}))
                    owners.append(c)
                continue
            if c.kind == "CENTERDIST":
                ra, rb = c.refs[0], c.refs[1]
                ca, _ga = center(ra, True)
                if ca is None:
                    c.ok, c.info = False, "ilk referans yay / daire olmalı"
                    continue
                if _is_arc_ref(rb):
                    cb, _gb = center(rb, True)
                    cons.append(("DISTANCE", (ca, cb), {"value": c.length}))
                else:
                    pv = pt_vars(rb)
                    if pv is None:
                        c.ok, c.info = False, "referans kayboldu"
                        continue
                    if rb.point:
                        cons.append(("DISTANCE", (ca, pv[0]), {"value": c.length}))
                    else:
                        cons.append(("PTLINE", (ca, pv[0], pv[1]), {"value": c.length}))
                owners.append(c)
                continue
            if c.kind in ("TANGENT", "SMOOTH"):
                plan, why = _tangent_plan(c, scene)
                if plan is None:
                    c.ok, c.info = False, why
                    continue
                if plan[0] == "tline":
                    _, tpts, tdir, tkeep = plan
                    hold.update(tkeep)
                    idx = [var((o.name, si, pi), (o, si, pi)) for o, si, pi in tpts]
                    cons.append(("TLINE", tuple(idx), {"dir": tuple(tdir)}))
                    owners.append(c)
                elif not dry:
                    post.append((c, plan[1]))
                if c.kind == "SMOOTH" and not dry:
                    post.append((c, lambda c=c: smooth_post(c, _joint(c)[0])))
                continue
            pts = _constraint_points(c)
            if pts is None:
                c.ok, c.info = False, "referans kayboldu (eğri yapısı değişmiş)"
                continue
            idx = [var((o.name, si, pi), (o, si, pi)) for o, si, pi in pts]
            cons.append((c.kind, tuple(idx), _params(c, ob, None)))
            owners.append(c)
        if not cons:
            _run_post(post)
            return True
        X0 = np.array([_kpos(k) for k in keys])
        moved, w = False, np.ones(len(keys))
        for j, key in enumerate(keys):
            k = _kname(key)
            last = _last_pos.get(k)
            if prefer is not None and k in prefer:
                w[j] = 1e3
            if last is not None and np.linalg.norm(last - X0[j]) > 1e-9:
                w[j] = 1e4
                moved = True
            elif last is None:
                moved = True
            if k in hold:
                w[j] = max(w[j], 1e7)
        if not moved and not force:
            _run_post(post)
            return True
        X, ok, per = solver.solve(X0, cons, w)
        scale = 1.0 + float(np.abs(X0).max())
        res = {}
        for c, r in zip(owners, per):           # bir kısıt birden çok denklem olabilir
            if c is None:
                continue
            res[id(c)] = (c, res.get(id(c), (c, True))[1] and r <= 1e-6 * scale)
        for c, good in res.values():
            c.ok = good
            c.info = "" if c.ok else "sağlanamadı: diğer kısıtlarla çelişiyor olabilir"
        if dry:
            return ok
        _write(keys, X0, X)
        for ck, (o, si, g) in arc_jobs.items():   # yaylar yeni merkez ve uçlardan kurulur
            try:
                rebuild_group(o, si, g, X[var_of[ck]])
            except Exception:
                traceback.print_exc()
        for j, key in enumerate(keys):
            _last_pos[_kname(key)] = X[j].copy()
        _run_post(post)
        return ok
    except Exception:
        traceback.print_exc()
        return False
    finally:
        if not dry:
            for c in driven:                   # referans ölçüler: geometriden ölçülür
                try:
                    _set_measured(c)
                except Exception:
                    traceback.print_exc()
        _flags["solving"] = False


def _run_post(post):
    """Tutamaç ayarlayan teğetler: noktalar çözüldükten sonra uygulanır (değişiklik yoksa
    yazmaz, böylece tekrar tekrar tetiklenmez)."""
    for c, fn in post:
        try:
            ok, info = fn()
        except Exception as e:
            ok, info = False, f"uygulanamadı: {e}"
        c.ok, c.info = ok, info if not ok else ("" if not info else info)


def _write(keys, X0, X):
    touched = {}
    for j, key in enumerate(keys):
        if key[0] == "@c":                     # sanal yay merkezi: yazılmaz
            continue
        o, si, pi = key
        d = X[j] - X0[j]
        if float(np.linalg.norm(d)) <= 1e-12:
            continue
        mwi = o.matrix_world.inverted()
        new = mwi @ Vector(tuple(X[j]))
        sp = _spline(o, si)
        if sp.type == "BEZIER":
            bp = sp.bezier_points[pi]
            dl = new - bp.co
            bp.co = new
            if bp.handle_left_type in ("FREE", "ALIGNED"):
                bp.handle_left = bp.handle_left + dl
            if bp.handle_right_type in ("FREE", "ALIGNED"):
                bp.handle_right = bp.handle_right + dl
        else:
            p = sp.points[pi]
            p.co = (new.x, new.y, new.z, p.co[3])
        touched[o.name] = o
    for o in touched.values():
        try:
            o.data.update_tag()
        except Exception:
            pass
    try:
        from . import recorder
        if touched:
            recorder.log("kısıt", f"çözüm {len(keys)} nokta · {len(touched)} eğri güncellendi")
    except Exception:
        pass


# ---------------------------------------------------------------- ekleme / silme

def add(kind, refs, auto=False, value=None, solve=True, scene=None):
    """refs: [("seg"|"pt", obje, spline, indeks)]. Yeni kısıtı döndürür."""
    owner = refs[0][1]
    c = owner.cad.constraints.add()
    c.kind = kind
    c.auto = auto
    for t, ob, si, i in refs:
        r = c.refs.add()
        r.obj, r.spline, r.index, r.point = ob, si, i, (t == "pt")
    pts = _constraint_points(c)
    if pts is None:
        owner.cad.constraints.remove(len(owner.cad.constraints) - 1)
        return None
    P = np.array([_world(o, si, pi) for o, si, pi in pts])
    _flags["solving"] = True            # değer atamaları anında çözüm tetiklemesin
    try:
        if kind == "AXIS":
            d = P[1] - P[0]
            c.axis = int(np.argmax(np.abs(d))) if value is None else int(value)
        elif kind == "DISTANCE":
            c.length = solver.measure("DISTANCE", P) if value is None else float(value)
        elif kind == "ANGLE":
            c.angle = math.radians(solver.measure("ANGLE", P) if value is None else value)
        elif kind == "FIX":
            c.pos = tuple(_co(*pts[0]))
        elif kind == "SYMMETRIC":
            c.axis = int(np.argmax(np.abs(P[1] - P[0])))
            c.offset = 0.0
        elif kind in ("PTLINE", "LINEDIST"):
            c.length = solver.measure(kind, P) if value is None else float(value)
        elif kind == "CENTERDIST":
            v = center_dist_value(c)
            if v is None:
                owner.cad.constraints.remove(len(owner.cad.constraints) - 1)
                return None
            c.length = v if value is None else float(value)
        elif kind == "RADIUS":
            R = radius_of(c)
            if R is None:
                owner.cad.constraints.remove(len(owner.cad.constraints) - 1)
                return None
            c.length = R if value is None else float(value)
            g = arc_group(c.refs[0].obj, c.refs[0].spline, c.refs[0].index)
            c.axis = 1 if g is not None and g["closed"] else 0      # 1: çap gösterilir
        elif kind == "CONCENTRIC":
            if centers_dist(c) is None:
                owner.cad.constraints.remove(len(owner.cad.constraints) - 1)
                return None
    finally:
        _flags["solving"] = False
    if solve:
        prefer = {(o.name, si, pi) for o, si, pi in pts[:len(pts) // max(len(refs), 1)]}
        solve_all(scene, force=True, prefer=prefer)
    try:
        from . import recorder
        recorder.log("kısıt", f"{NAMES.get(kind, kind)} eklendi{' (oto)' if auto else ''}: "
                              f"{[(t, o.name, si, i) for t, o, si, i in refs]} · ok={c.ok}")
    except Exception:
        pass
    return c


def satisfied(c, tol_rel=1e-6):
    """Kısıt şu anki geometride sağlanıyor mu (oto kısıtları eklerken kontrol)."""
    if c.kind in ("TANGENT", "SMOOTH"):
        return True
    if c.kind == "RADIUS":
        R = radius_of(c)
        return R is not None and abs(R - c.length) <= tol_rel * (1.0 + R) + 1e-9
    if c.kind == "CONCENTRIC":
        d = centers_dist(c)
        return d is not None and d <= 1e-6
    if c.kind == "CENTERDIST":
        v = center_dist_value(c)
        return v is not None and abs(v - c.length) <= tol_rel * (1.0 + v) + 1e-9
    if c.kind == "EQUAL" and len(c.refs) == 2 and all(_is_arc_ref(r) for r in c.refs):
        ga = arc_group(c.refs[0].obj, c.refs[0].spline, c.refs[0].index)
        gb = arc_group(c.refs[1].obj, c.refs[1].spline, c.refs[1].index)
        return abs(ga["R"] - gb["R"]) <= tol_rel * (1.0 + ga["R"]) + 1e-9
    pts = _constraint_points(c)
    if pts is None:
        return False
    owner = c.refs[0].obj
    P = np.array([_world(o, si, pi) for o, si, pi in pts])
    try:
        r = solver.residual(c.kind, P, _params(c, owner, P))
    except Exception:
        return False
    scale = 1.0 + float(np.abs(P).max())
    return float(np.linalg.norm(r)) <= tol_rel * scale + 1e-9


def remove_last(c, scene=None):
    """Az önce eklenen kısıtı siler (kısıt ilk referansın objesinde saklanır)."""
    ob = c.refs[0].obj if len(c.refs) else None
    if ob is None:
        return
    cs = ob.cad.constraints
    for i in reversed(range(len(cs))):
        if cs[i] is c or cs[i] == c:
            cs.remove(i)
            return


def remove(ob, index):
    if ob is not None and 0 <= index < len(ob.cad.constraints):
        ob.cad.constraints.remove(index)


def describe(c):
    parts = []
    for r in c.refs:
        nm = r.obj.name if r.obj else "?"
        parts.append(f"{nm}:{r.spline}.{r.index}{'•' if r.point else ''}")
    return ", ".join(parts)


# ---------------------------------------------------------------- canlı tetikleme

def _tick():
    try:
        if core._transform_running():
            return 0.1                  # sürükleme bitince çöz
        force = _flags["force"]
        _flags["force"] = False
        solve_all(bpy.context.scene, force=force)
    except Exception:
        traceback.print_exc()
    return None


def request_solve(force=False):
    if _flags["solving"]:
        return
    if force:
        _flags["force"] = True
    try:
        if not bpy.app.timers.is_registered(_tick):
            bpy.app.timers.register(_tick, first_interval=0.05)
    except Exception:
        pass


@persistent
def on_depsgraph_update(scene, depsgraph):
    if _flags["solving"]:
        return
    try:
        if not has_any(scene):
            return
        for u in depsgraph.updates:
            idd = u.id
            if isinstance(idd, bpy.types.Curve) or (
                    isinstance(idd, bpy.types.Object) and idd.type == "CURVE" and
                    (u.is_updated_geometry or u.is_updated_transform)):
                request_solve()
                return
    except Exception:
        pass


@persistent
def on_load(_dummy):
    _last_pos.clear()


# ---------------------------------------------------------------- operatörler

class MINICAD_OT_constraint_remove(bpy.types.Operator):
    bl_idname = "minicad.constraint_remove"
    bl_label = "Kısıtı Sil"
    bl_options = {"REGISTER", "UNDO"}

    obj: bpy.props.StringProperty()
    index: bpy.props.IntProperty()

    def execute(self, context):
        remove(bpy.data.objects.get(self.obj), self.index)
        return {"FINISHED"}


class MINICAD_OT_constraint_clear(bpy.types.Operator):
    bl_idname = "minicad.constraint_clear"
    bl_label = "Kısıtları Temizle"
    bl_description = "Sahnedeki kısıtları siler"
    bl_options = {"REGISTER", "UNDO"}

    auto_only: bpy.props.BoolProperty(name="Sadece otomatikler", default=False)

    def execute(self, context):
        n = 0
        for ob in context.scene.objects:
            if ob.type != "CURVE":
                continue
            cs = ob.cad.constraints
            for i in reversed(range(len(cs))):
                if not self.auto_only or cs[i].auto:
                    cs.remove(i)
                    n += 1
        self.report({"INFO"}, f"{n} kısıt silindi")
        return {"FINISHED"}


class MINICAD_OT_constraint_solve(bpy.types.Operator):
    bl_idname = "minicad.constraint_solve"
    bl_label = "Kısıtları Çöz"
    bl_description = "Bütün kısıtları şimdi uygular"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        ok = solve_all(context.scene, force=True)
        self.report({"INFO"} if ok else {"WARNING"},
                    "Kısıtlar sağlandı" if ok else "Bazı kısıtlar sağlanamadı (kırmızı)")
        return {"FINISHED"}

classes = (MINICAD_OT_constraint_remove, MINICAD_OT_constraint_clear,
           MINICAD_OT_constraint_solve)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.minicad_auto_constraints = bpy.props.BoolProperty(
        name="Oto Kısıt", description="Çizerken yakalanan yatay/dikey, paralel, dik, uç "
        "çakışması ve yazılan uzunluk kısıt olarak kaydedilir", default=True)
    bpy.types.Scene.minicad_show_constraints = bpy.props.BoolProperty(
        name="Kısıtları Göster", description="Kısıt simgelerini görünümde göster",
        default=True)
    bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)
    bpy.app.handlers.load_post.append(on_load)
    _handles.append(bpy.types.SpaceView3D.draw_handler_add(_draw_glyphs, (), "WINDOW",
                                                           "POST_PIXEL"))


def unregister():
    while _handles:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_handles.pop(), "WINDOW")
        except Exception:
            pass
    for lst, fn in ((bpy.app.handlers.depsgraph_update_post, on_depsgraph_update),
                    (bpy.app.handlers.load_post, on_load)):
        if fn in lst:
            lst.remove(fn)
    for name in ("minicad_auto_constraints", "minicad_show_constraints"):
        try:
            delattr(bpy.types.Scene, name)
        except Exception:
            pass
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
