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
    NAMES, PT_COUNT, SEG_COUNT, _co, _constraint_points, _last_pos, _npts, _spline, _world,
    all_constraints, has_any, needed, ref_points,
)
from .constraints_tangent import (
    DIR_KINDS, _arc_run, _arc_slide, _bez, _handle_vec, _joint, _line_constrained, _pick_side,
    _seg_straight, _set_handle_dir, _set_world, _side, _tangent_plan,
)
from .constraints_glyphs import ICON, _anchor, _draw_glyphs, _glyph_boxes, glyph_at

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
    return {}


def solve_all(scene=None, force=False, prefer=None):
    """Sahnedeki bütün kısıtları çözer. prefer: yerinde kalması istenen nokta anahtarları."""
    if _flags["solving"]:
        return True
    scene = scene or bpy.context.scene
    _flags["solving"] = True
    try:
        keys, var_of, cons, owners, post = [], {}, [], [], []
        hold = set()                     # eğri / yay noktaları: şekil bozulmasın diye sabit
        for ob, _i, c in all_constraints(scene):
            if not c.enabled:
                continue
            if c.kind == "TANGENT":
                plan, why = _tangent_plan(c, scene)
                if plan is None:
                    c.ok, c.info = False, why
                    continue
                if plan[0] == "tline":
                    _, tpts, tdir, tkeep = plan
                    hold.update(tkeep)
                    idx = []
                    for o, si, pi in tpts:
                        k = (o.name, si, pi)
                        if k not in var_of:
                            var_of[k] = len(keys)
                            keys.append((o, si, pi))
                        idx.append(var_of[k])
                    cons.append(("TLINE", tuple(idx), {"dir": tuple(tdir)}))
                    owners.append(c)
                else:
                    post.append((c, plan[1]))
                continue
            pts = _constraint_points(c)
            if pts is None:
                c.ok, c.info = False, "referans kayboldu (eğri yapısı değişmiş)"
                continue
            idx = []
            for o, si, pi in pts:
                k = (o.name, si, pi)
                if k not in var_of:
                    var_of[k] = len(keys)
                    keys.append((o, si, pi))
                idx.append(var_of[k])
            cons.append((c.kind, tuple(idx), _params(c, ob, None)))
            owners.append(c)
        if not cons:
            _run_post(post)
            return True
        X0 = np.array([_world(o, si, pi) for o, si, pi in keys])
        moved, w = False, np.ones(len(keys))
        for j, (o, si, pi) in enumerate(keys):
            k = (o.name, si, pi)
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
        for c, r in zip(owners, per):
            c.ok = r <= 1e-6 * scale
            c.info = "" if c.ok else "sağlanamadı: diğer kısıtlarla çelişiyor olabilir"
        _write(keys, X0, X)
        for j, (o, si, pi) in enumerate(keys):
            _last_pos[(o.name, si, pi)] = X[j].copy()
        _run_post(post)
        return ok
    except Exception:
        traceback.print_exc()
        return False
    finally:
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
    for j, (o, si, pi) in enumerate(keys):
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
    if c.kind == "TANGENT":
        return True
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
