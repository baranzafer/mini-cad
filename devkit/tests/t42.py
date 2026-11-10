# Çizim aracı: modal olay simülasyonu (üstten ortografik görünüş, 1 birim = 100 px)
exec(open("t.py").read().split("def seg(")[0])
import types, numpy as np, math
NS = types.SimpleNamespace
for n in ["gpu", "gpu_extras", "gpu_extras.batch", "blf", "bpy_extras", "mathutils"]:
    sys.modules[n] = types.ModuleType(n)
sys.modules["gpu_extras.batch"].batch_for_shader = None
class Vec(np.ndarray):
    def __new__(cls, v): return np.asarray(v, dtype=float).view(cls)
    x = property(lambda s: float(s[0])); y = property(lambda s: float(s[1]))
    length = property(lambda s: float(np.linalg.norm(np.asarray(s))))
    def copy(s): return Vec(np.asarray(s).copy())
class Mat3:
    def __init__(s, M): s.M = np.asarray(M, float)
    def __matmul__(s, v): return Vec(s.M @ np.asarray(v, float))
class Mat:
    def __init__(s, M): s.M = np.asarray(M, float)
    def inverted(s): return Mat(np.linalg.inv(s.M))
    def to_3x3(s): return Mat3(s.M[:3,:3])
    def __matmul__(s, v): return Vec((s.M @ np.r_[np.asarray(v, float), 1.0])[:3])
    def __iter__(s): return iter(s.M.tolist())
sys.modules["mathutils"].Vector = Vec
W = 1000
def to_px(p): return Vec((p[0] * 50 + 500, p[1] * 50 + 500))
vu = types.ModuleType("bpy_extras.view3d_utils")
vu.region_2d_to_origin_3d = lambda r, rv, xy: Vec(((xy[0] - 500) / 50, (xy[1] - 500) / 50, 50.0))
vu.region_2d_to_vector_3d = lambda r, rv, xy: Vec((0, 0, -1.0))
vu.location_3d_to_region_2d = lambda r, rv, p: to_px(p)
sys.modules["bpy_extras.view3d_utils"] = vu; sys.modules["bpy_extras"].view3d_utils = vu
bpy.types.Operator = object; bpy.types.SpaceView3D = NS(draw_handler_add=lambda *a: object(), draw_handler_remove=lambda *a: None)
bpy.app.handlers.persistent = lambda f: f
bpy.utils = NS(units=NS(to_value=lambda sys_, cat, t: float(t.replace("mm", "")) / 1000 if t.endswith("mm") else float(t.rstrip("m"))))
undo = []; bpy.ops = NS(ed=NS(undo_push=lambda message="": undo.append(message)), object=NS(mode_set=lambda mode: None))
import importlib
draw = importlib.import_module("mini_cad.draw")
dm = draw.dm
# eğri verisi
class BP(NS): pass
class BPList(list):
    def add(s, n): s.extend(BP(co=None, handle_left=None, handle_right=None, handle_left_type="", handle_right_type="") for _ in range(n))
class Spline(NS): pass
class Splines(list):
    def new(s, t):
        sp = Spline(type="BEZIER", bezier_points=BPList([BP(co=None, handle_left=None, handle_right=None, handle_left_type="", handle_right_type="")]), use_cyclic_u=False, points=[])
        s.append(sp); return sp
def bez(a, b):
    a, b = Vec(a), Vec(b)
    return a, b
sq = [(0,0,0),(2,0,0),(2,2,0),(0,2,0)]
sp0 = Spline(type="BEZIER", use_cyclic_u=True, points=[], bezier_points=[BP(co=Vec(p), handle_left=Vec(p), handle_right=Vec(p)) for p in sq])
for i, b in enumerate(sp0.bezier_points):  # düz kenarlar: tutamaçlar 1/3'te
    nx, pv = Vec(sq[(i+1)%4]), Vec(sq[i-1])
    b.handle_right = b.co + (nx - b.co) / 3; b.handle_left = b.co + (pv - b.co) / 3
cu = NS(splines=Splines([sp0]), dimensions="3D", update_tag=lambda: None)
I4 = Mat(np.eye(4))
curve = NS(type="CURVE", name="Tel", data=cu, matrix_world=I4, mode="OBJECT", cad=NS(is_cad=False), visible_get=lambda: True)

core._display.clear()
class Coll(list):
    def __init__(s, factory=None, *a): super().__init__(*a); s.f = factory
    def add(s):
        x = s.f(); s.append(x); return x
    def remove(s, i): del s[i]
def cref(): return NS(obj=None, spline=0, index=0, point=False)
def cons(): return NS(kind="PARALLEL", refs=Coll(cref), enabled=True, length=0.0, angle=0.0, axis=0, offset=0.0, pos=(0,0,0), auto=False, ok=True, info="")
cu = NS(splines=Splines([]), dimensions="3D", update_tag=lambda: None)
I4 = Mat(np.eye(4))
curve = NS(type="CURVE", name="Tel", data=cu, matrix_world=I4, mode="OBJECT", cad=NS(is_cad=False, constraints=Coll(cons), patches=[]), visible_get=lambda: True)
class Objs(dict):
    def __iter__(s): return iter(s.values())
region = NS(type="WINDOW", x=0, y=0, width=W, height=W)
P = np.array([[0.1,0,0,0],[0,0.1,0,0],[0,0,-0.01,0],[0,0,0,1]])
area = NS(type="VIEW_3D", regions=[region], spaces=NS(active=NS(region_3d=NS(perspective_matrix=P.tolist(), view_distance=10.0, view_matrix=Mat(np.eye(4))))), tag_redraw=lambda: None)
ctx = NS(area=area, visible_objects=[curve], preferences=NS(system=NS(ui_scale=1.0)), window_manager=NS(modal_handler_add=lambda op: None),
         workspace=NS(status_text_set=lambda t: None), scene=NS(cursor=NS(location=(0,0,0)), objects=Objs({"Tel": curve}), unit_settings=NS(system="METRIC", length_unit="METERS", scale_length=1.0),
         ray_cast=lambda *a: (False, None, None, None, None, None), minicad_auto_constraints=True, minicad_show_constraints=True, minicad_pick_plane=False, minicad_grid_snap=False, minicad_look_at=True), evaluated_depsgraph_get=lambda: None, active_object=curve, collection=None)
bpy.context = ctx; bpy.data = NS(objects=Objs({"Tel": curve}))
bpy.app.timers = NS(register=lambda f, first_interval=0: None, is_registered=lambda f: True)
core.fmt_len = lambda v: f"{v:.3f} m"
core._transform_running = lambda: False
cmod = importlib.import_module("mini_cad.constraints"); dm_ = importlib.import_module("mini_cad.drawmath")
op = draw.MINICAD_OT_draw.__new__(draw.MINICAD_OT_draw); op.report = lambda *a: print("RAPOR", a)
op.invoke(ctx, NS())
op._view_dir = lambda: np.array([0, 0, -1.0]); op._view_right = lambda: np.array([1.0, 0, 0])
def ev(t, p=None, val="PRESS", uni="", shift=False, ctrl=False):
    x, y = to_px(p) if p is not None else (op.mouse[0], op.mouse[1])
    return NS(type=t, value=val, mouse_x=x, mouse_y=y, unicode=uni, shift=shift, ctrl=ctrl, alt=False)
def move(p, **k): op.modal(ctx, ev("MOUSEMOVE", p, **k)); return op.cursor
def click(p): move(p); op.modal(ctx, ev("LEFTMOUSE", p)); op.modal(ctx, ev("LEFTMOUSE", p, val="RELEASE"))
def typ(t):
    for ch in t: op.modal(ctx, ev(ch.upper() if ch.isalpha() else "ONE", None, uni=ch))
def key(k, **kw): op.modal(ctx, ev(k, None, **kw))
def sp_info(sp): return (len(sp.bezier_points), sp.use_cyclic_u, [(b.handle_left_type[0], b.handle_right_type[0]) for b in sp.bezier_points])

def tang(): 
    sp=cu.splines
    a=sp[1].bezier_points[0]; l=sp[0].bezier_points
    t_arc=np.asarray(a.handle_right)-np.asarray(a.co); d=np.asarray(l[1].co)-np.asarray(l[0].co)
    t_arc/=np.linalg.norm(t_arc); d/=np.linalg.norm(d)
    return round(float(np.linalg.norm(np.cross(t_arc,d))),6)
def scenario(with_axis):
    cu.splines.clear(); curve.cad.constraints.clear(); cmod._last_pos.clear()
    ctx.scene.minicad_auto_constraints = with_axis
    op._set_tool(ctx, "LINE"); op.dirty=True
    click((-1,-2)); click((-1.0,0.0) if with_axis else (-0.6,0.0)); key("RET"); key("RET", ctrl=True)
    ctx.scene.minicad_auto_constraints = True
    op._set_tool(ctx, "ARC3"); op.dirty=True
    lp = cu.splines[0].bezier_points[1].co
    click(tuple(np.asarray(lp)[:2])); click((1.5,0)); click((0.25,1.2)); key("RET"); key("RET", ctrl=True)
    print(" kısıtlar:", [c.kind for c in curve.cad.constraints], "| teğet öncesi sapma:", tang())
    sp1=cu.splines[1]; P=[np.asarray(v) for v in (sp1.bezier_points[0].co, sp1.bezier_points[0].handle_right, sp1.bezier_points[1].handle_left, sp1.bezier_points[1].co)]
    arc0 = dm_.arc_of_bezier(P); print(" yay önce: merkez", np.round(arc0[0],3), "R=%.4f" % arc0[1], "| B ucu", np.round(sp1.bezier_points[-1].co,3))
    op._set_tool(ctx, "C_TANGENT"); op.dirty=True
    op._update(ctx, *to_px((1.4, 0.4))); print(" 1. seçim (yayın 2. yarısı):", op.c_hover[:4] if op.c_hover else None)
    click((1.4,0.4)); click((-1.0 if with_axis else -0.8,-1.0))
    c = curve.cad.constraints[-1]
    sp1=cu.splines[1]; P=[np.asarray(v) for v in (sp1.bezier_points[0].co, sp1.bezier_points[0].handle_right, sp1.bezier_points[1].handle_left, sp1.bezier_points[1].co)]
    arc1 = dm_.arc_of_bezier(P); print(" yay sonra: merkez", np.round(arc1[0],3) if arc1 else None, "R=%.4f" % arc1[1] if arc1 else "BOZULDU", "| B ucu", np.round(sp1.bezier_points[-1].co,3),
        "| birleşim", np.round(sp1.bezier_points[0].co,3), "| doğru", np.round(cu.splines[0].bezier_points[0].co,3), np.round(cu.splines[0].bezier_points[1].co,3))
    print(" teğet:", c.ok, repr(c.info), "| sonra sapma:", tang(), "| doğru uzak ucu:", np.round(cu.splines[0].bezier_points[0].co,3), "| yay R sabit mi:", 
          round(float(np.linalg.norm(np.asarray(cu.splines[1].bezier_points[0].co)-np.asarray(cu.splines[1].bezier_points[-1].co))),3))
print("A) doğru dikey EKSEN kısıtlı -> yay ucu doğruya uyar:"); scenario(True)
print("B) serbest doğru -> doğru yaya teğet döner (yay bozulmaz):"); scenario(False)

print("C) Teğet yay (A) var olan doğrunun ucundan ilk tıkla:")
cu.splines.clear(); curve.cad.constraints.clear(); cmod._last_pos.clear()
op._set_tool(ctx, "LINE"); op.dirty=True; click((-1,-2)); click((-1,0)); key("RET"); key("RET", ctrl=True)
op._set_tool(ctx, "TARC"); op.dirty=True
click((-1,0)); print(" başlangıç teğeti:", np.round(op.start_tan[0],3) if op.start_tan else None)
move((1,0)); print(" önizleme yay mı:", op.preview and op.preview[0]["kind"], "R=%.3f" % op.arc_info["radius"])
click((1,0)); key("RET"); key("RET", ctrl=True)
print(" kısıtlar:", [(c.kind, c.ok) for c in curve.cad.constraints], "| sapma:", tang())
print("D) boşlukta Teğet yay -> 3 noktalı gibi:")
op._set_tool(ctx, "TARC"); click((2,-3)); click((4,-3)); click((3,-2)); key("RET"); key("RET", ctrl=True)
print(" yazılan:", len(cu.splines[-1].bezier_points), "nokta")
