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
class Mat:
    def __init__(s, M): s.M = np.asarray(M, float)
    def inverted(s): return Mat(np.linalg.inv(s.M))
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
cmod = importlib.import_module("mini_cad.constraints")
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

op._set_tool(ctx, "LINE"); op.dirty=True
# taslak: çizgi hafızada kalır
click((0,0)); click((2,0)); click((2,1)); key("RET")
print("taslakta:", len(op.sketch), "çizgi | eğride spline:", len(cu.splines))
# taslak noktasını sürükle (düzlemde)
def drag(p0, p1, axis=None):
    op.modal(ctx, ev("MOUSEMOVE", p0)); op.modal(ctx, ev("LEFTMOUSE", p0))
    if axis: op.modal(ctx, ev(axis, None))
    op.modal(ctx, ev("MOUSEMOVE", ((p0[0]+p1[0])/2, (p0[1]+p1[1])/2))); op.modal(ctx, ev("MOUSEMOVE", p1)); op.modal(ctx, ev("LEFTMOUSE", p1, val="RELEASE"))
drag((2,1), (2.5,1.5))
print("köşe sürüklendi:", [tuple(np.round(sg["p"][3],3)) for sg in op.sketch[0]["segs"]], "| doğru düz kaldı:", np.allclose(op.sketch[0]["segs"][1]["p"][1], (op.sketch[0]["segs"][1]["p"][0]*2+op.sketch[0]["segs"][1]["p"][3])/3))
# eğri (spline) çiz, tutamaç sürükle
key("K"); click((-3,-3)); click((-2,-2)); click((-1,-3)); key("RET")
sg = op.sketch[1]["segs"][0]; h0 = sg["p"][2].copy(); h1 = op.sketch[1]["segs"][1]["p"][1].copy()
drag(tuple(h0[:2]), (h0[0]-0.3, h0[1]+0.2))
sg0, sg1 = op.sketch[1]["segs"]
node = sg0["p"][3]; a = sg0["p"][2]-node; b = sg1["p"][1]-node
print("tutamaç sürüklendi, karşı tutamaç hizalı:", round(float(np.dot(a/np.linalg.norm(a), -b/np.linalg.norm(b))),6), "| boyu korundu:", round(float(np.linalg.norm(b)),4), round(float(np.linalg.norm(h1-node)),4))
# eksen kilidi (Z): üstten bakışta ışın Z'ye paralel -> değişmez; X kilidi ile
drag((-3,-3), (-2.5,-2.2), axis="X")
print("X kilitli sürükleme:", np.round(op.sketch[1]["segs"][0]["p"][0],3))
# sürüklemeden tık = normal tık (çizim başlar)
op.modal(ctx, ev("MOUSEMOVE", (0,0))); op.modal(ctx, ev("LEFTMOUSE", (0,0))); op.modal(ctx, ev("LEFTMOUSE", (0,0), val="RELEASE"))
print("taslak ucuna tık -> çizgi başladı:", op.start is not None and np.round(op.start,3))
key("BACK_SPACE")
# İz: referans (0,0) -> X boyunca 1.0 -> Y boyunca 0.5 -> Enter
key("T"); click((0,0)); move((1.0,0.05)); typ("1"); op.modal(ctx, ev("LEFTMOUSE",(1.0,0.05))); move((1.0,0.6)); typ("0.5"); key("RET")
print("iz ile başlangıç:", np.round(op.start,3) if op.start is not None else None)
click((3,-1)); key("RET")
# --- geri al / yinele (taslak aşaması)
def cz(shift=False): return op.modal(ctx, ev("Z", None, ctrl=True, shift=shift))
n0 = len(op.sketch)
key("L"); click((-4,2)); click((-3,2)); print("çizgi sürerken parça:", len(op.segs))
print("Ctrl+Z:", cz(), "| parça:", len(op.segs), "| başlangıç var:", op.start is not None)
print("Ctrl+Z:", cz(), "| başlangıç:", op.start)
print("Ctrl+Shift+Z:", cz(True), "| başlangıç:", op.start is not None)
print("Ctrl+Shift+Z:", cz(True), "| parça:", len(op.segs))
key("RET"); print("taslak:", n0, "->", len(op.sketch))
cz(); print("Enter geri alındı -> taslak:", len(op.sketch), "| zincir parça:", len(op.segs))
cz(True); print("yinelendi -> taslak:", len(op.sketch))
before = np.round(op.sketch[0]["segs"][0]["p"][0],3)
drag((0,0),(0.4,-0.6)); print("sürükleme:", before, "->", np.round(op.sketch[0]["segs"][0]["p"][0],3))
cz(); print("sürükleme geri alındı:", np.round(op.sketch[0]["segs"][0]["p"][0],3))
# --- pivot: noktaya bas-bırak (Seç aracında) -> pivot; X okunu sürükle
op._set_tool(ctx, "SELECT")
p_ = op.sketch[0]["segs"][0]["p"][0]
op.modal(ctx, ev("MOUSEMOVE", tuple(p_[:2]))); op.modal(ctx, ev("LEFTMOUSE", tuple(p_[:2]))); op.modal(ctx, ev("LEFTMOUSE", tuple(p_[:2]), val="RELEASE"))
print("pivot seçili:", op.sk_sel, "| eksen okları:", [k for k,_,_ in op._pivot_axes()])
k, c, e = op._pivot_axes()[0]; tipx = (c[0]+e[0])/2, (c[1]+e[1])/2
op.modal(ctx, NS(type="LEFTMOUSE", value="PRESS", mouse_x=tipx[0], mouse_y=tipx[1], unicode="", shift=False, ctrl=False, alt=False))
print("ok üstünde basınca eksen kilidi:", op.sk_drag and op.sk_drag["axis"])
op.modal(ctx, NS(type="MOUSEMOVE", value="NOTHING", mouse_x=tipx[0]+37, mouse_y=tipx[1]+25, unicode="", shift=False, ctrl=False, alt=False))
print("X boyunca (ızgaraya) kaydı:", np.round(op.sketch[0]["segs"][0]["p"][0],3), op.info and op.info["kind"])
op.modal(ctx, NS(type="LEFTMOUSE", value="RELEASE", mouse_x=tipx[0]+37, mouse_y=tipx[1]+25, unicode="", shift=False, ctrl=False, alt=False))
# --- tutamaç sürüklerken yatay kılavuz + ızgara
op._set_tool(ctx, "LINE")
sg = op.sketch[1]["segs"][0]; node = sg["p"][3]; h = sg["p"][2]
target = (node[0]+0.8, node[1]+0.03)
op.modal(ctx, ev("MOUSEMOVE", tuple(h[:2]))); op.modal(ctx, ev("LEFTMOUSE", tuple(h[:2])))
op.modal(ctx, ev("MOUSEMOVE", ((h[0]+target[0])/2, (h[1]+target[1])/2))); op.modal(ctx, ev("MOUSEMOVE", target))
print("tutamaç yakalama:", op.info and op.info["kind"], "| tutamaç-düğüm dy:", round(float(op.sketch[1]["segs"][0]["p"][2][1]-node[1]),6))
op.modal(ctx, ev("LEFTMOUSE", target, val="RELEASE"))
# hedef: yeni eğri
ctx.scene.minicad_draw_target = "NEW"
newobjs = []
bpy.data.curves = NS(new=lambda n, t: NS(splines=Splines([]), dimensions="2D", update_tag=lambda: None))
def newob(n, cu_):
    o = NS(type="CURVE", name=f"{n}.{len(newobjs)+1:03d}", data=cu_, matrix_world=I4, mode="OBJECT", cad=NS(is_cad=False, constraints=Coll(cons), patches=[]), visible_get=lambda: True)
    newobjs.append(o); bpy.data.objects[o.name] = o; return o
bpy.data.objects.new = newob
ctx.collection = NS(objects=NS(link=lambda o: None))
print("bitir öncesi taslak:", len(op.sketch))
op._finish_sketch(ctx)
print("yeni eğri objesi:", [o.name for o in newobjs], "| spline:", len(newobjs[0].data.splines) if newobjs else 0, "| taslak:", len(op.sketch))
print("kısıtlar (yeni objede):", [(c.kind, c.auto) for c in newobjs[0].cad.constraints] if newobjs else None)
