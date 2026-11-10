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
def to_px(p): return Vec((p[0] * 100 + 500, p[1] * 100 + 500))
vu = types.ModuleType("bpy_extras.view3d_utils")
vu.region_2d_to_origin_3d = lambda r, rv, xy: Vec(((xy[0] - 500) / 100, (xy[1] - 500) / 100, 50.0))
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
region = NS(type="WINDOW", x=0, y=0, width=W, height=W)
P = np.array([[0.01,0,0,0],[0,0.01,0,0],[0,0,-0.01,0],[0,0,0,1]])   # ndc = x/100*... (dünya*100+500 px)
P = np.array([[0.2,0,0,0],[0,0.2,0,0],[0,0,-0.01,0],[0,0,0,1]])
area = NS(type="VIEW_3D", regions=[region], spaces=NS(active=NS(region_3d=NS(perspective_matrix=P.tolist(), view_distance=10.0, view_matrix=Mat(np.eye(4))))), tag_redraw=lambda: None)
ctx = NS(area=area, visible_objects=[curve], preferences=NS(system=NS(ui_scale=1.0)), window_manager=NS(modal_handler_add=lambda op: None),
         workspace=NS(status_text_set=lambda t: None), scene=NS(cursor=NS(location=(0,0,0)), objects={"Tel": curve}, unit_settings=NS(system="METRIC", length_unit="METERS", scale_length=1.0),
         ray_cast=lambda *a: (False, None, None, None, None, None), minicad_pick_plane=False, minicad_grid_snap=False), evaluated_depsgraph_get=lambda: None, active_object=curve, collection=None)
bpy.context = ctx; bpy.data = NS(objects={"Tel": curve})
class _Objs(dict):
    def __iter__(s): return iter(s.values())
bpy.data.objects = _Objs({"Tel": curve})
core.fmt_len = lambda v: f"{v:.3f} m"
op = draw.MINICAD_OT_draw.__new__(draw.MINICAD_OT_draw); op.report = lambda *a: None
op.invoke(ctx, NS())
op._view_dir = lambda: np.array([0, 0, -1.0]); op._view_right = lambda: np.array([1.0, 0, 0])
def ev(t, p=None, val="PRESS", uni="", shift=False, ctrl=False):
    x, y = to_px(p) if p is not None else (op.mouse[0], op.mouse[1])
    return NS(type=t, value=val, mouse_x=x, mouse_y=y, unicode=uni, shift=shift, ctrl=ctrl, alt=False)
def move(p, **k): op.modal(ctx, ev("MOUSEMOVE", p, **k)); return op.cursor, op.snap_kind, (op.info or {}).get("kind")
def click(p): move(p); op.modal(ctx, ev("LEFTMOUSE", p))
c, k, i = move((2.05, 0.04)); print("köşeye yakın:", np.round(c, 3), k, "| düzlem:", op.tmp_plane.name)
click((2.05, 0.04)); print("başlangıç:", op.start)
c, k, i = move((1.0, 0.03)); print("kenar üstü:", np.round(c, 3), k)
c, k, i = move((1.0, 1.0)); print("karenin ortasına doğru (çapraz=kesişim değil):", np.round(c, 3), k, i)
c, k, i = move((4.0, 0.08)); print("sağa sürükle:", np.round(c, 3), k, i)
c, k, i = move((4.0, 1.97)); print("yukarı köşe hizası:", np.round(c, 3), k, i)
click((4.0, 0.08)); print("2. nokta:", np.round(op._anchor(), 3))
for ch in "1.5": op.modal(ctx, ev(ch, None, uni=ch))
op.modal(ctx, ev("TAB", None)); 
for ch in "90": op.modal(ctx, ev(ch, None, uni=ch))
print("yazılan:", op.typed)
op.modal(ctx, ev("RET", None)); print("Enter ile 3. nokta:", np.round(op._anchor(), 4), "| parça:", len(op.segs))
op.modal(ctx, ev("A", None)); c, k, i = move((2.6, 3.0)); print("yay modu önizleme parça:", len(op.preview), "R=%.3f" % op.arc_info["radius"])
click((2.6, 3.0)); print("yay eklendi, parça:", len(op.segs))
op.modal(ctx, ev("BACK_SPACE", None)); print("Backspace yayı geri aldı:", len(op.segs))
op.modal(ctx, ev("A", None)); click((2.6, 3.0)); print("doğru eklendi:", len(op.segs))
c, k, i = move((2.03, 0.02)); print("başlangıca dön:", np.round(c, 3), k)
called = {}
uimod = types.ModuleType("mini_cad.ui")
def apply_surface(c, kind, refs, new_body=False): called["refs"] = [(r[0].name, r[1], r[2]) for r in refs]; called["new"] = new_body; return True, "ok"
uimod.apply_surface = apply_surface; uimod.get_target = lambda c: None; sys.modules["mini_cad.ui"] = uimod
op.modal(ctx, ev("LEFTMOUSE", (2.03, 0.02)))
op._finish_sketch(ctx); sp = cu.splines[-1]
print("yazılan spline:", len(cu.splines), "| nokta:", len(sp.bezier_points), "| kapalı:", sp.use_cyclic_u, "| geri alma:", undo)
print("tutamaç türleri:", [(b.handle_left_type, b.handle_right_type) for b in sp.bezier_points])
print("noktalar:", [tuple(np.round(b.co, 3)) for b in sp.bezier_points])
op.modal(ctx, ev("F", None)); print("F -> yüzey refs:", called)
# rakam ilk noktadan önce Blender'a gitmez
print("ilk noktadan önce '1':", op.modal(ctx, ev("ONE", None, uni="1")))

import time as _t
rec = importlib.import_module("mini_cad.recorder")
rec.log("test", "kayıt öncesi olay")
print("hata günlüğe düştü mü (tee):", end=" "); rec._install_tee(); print("[Mini CAD] örnek hata", file=sys.stderr)
bpy.app.version_string = "5.2.3 LTS"; bpy.data.filepath = "/x/jant.blend"
bpy.utils.extension_path_user = lambda pkg, path="", create=False: "/tmp/fk"
class Objs(list):
    pass
ctx.scene.objects = Objs([curve]); ctx.selected_objects = [curve]; ctx.mode = "OBJECT"
ctx.scene.minicad_rec_seconds = 0.3; ctx.scene.minicad_rec_shot = False
ctx.window = NS(screen=NS(areas=[NS(type="VIEW_3D", x=0, y=0, width=1000, height=1000, regions=[region], tag_redraw=lambda: None)]))
ctx.window_manager.event_timer_add = lambda dt, window=None: "T"; ctx.window_manager.event_timer_remove = lambda t: None
r = rec.MINICAD_OT_record.__new__(rec.MINICAD_OT_record); r.report = lambda lvl, m: print("RAPOR:", m)
print(r.invoke(ctx, NS()))
r.modal(ctx, NS(type="MOUSEMOVE", value="NOTHING", mouse_x=300, mouse_y=400, ctrl=False, shift=False, alt=False, unicode=""))
op.modal(ctx, ev("LEFTMOUSE", (1.0, 1.0)))
r.modal(ctx, NS(type="LEFTMOUSE", value="PRESS", mouse_x=600, mouse_y=600, ctrl=False, shift=False, alt=False, unicode=""))
r.modal(ctx, NS(type="ONE", value="PRESS", mouse_x=600, mouse_y=600, ctrl=False, shift=False, alt=False, unicode="1"))
_t.sleep(0.35)
print(r.modal(ctx, NS(type="TIMER", value="NOTHING", mouse_x=0, mouse_y=0, ctrl=False, shift=False, alt=False, unicode="")))
txt = ctx.window_manager.clipboard
print("---- panodaki rapor ----"); print(txt)
