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
# 1) pencereden Dikdörtgen aracı
op.palette._layout(region)
it = next(i for i in op.palette.items if i[4] == "tool" and i[5] == "RECT")
cx, cy = (it[0]+it[2])/2, (it[1]+it[3])/2
op.modal(ctx, NS(type="MOUSEMOVE", value="NOTHING", mouse_x=cx, mouse_y=cy, unicode="", shift=False, ctrl=False, alt=False))
print("pencere ipucu:", op.palette.tooltip())
op.modal(ctx, NS(type="LEFTMOUSE", value="PRESS", mouse_x=cx, mouse_y=cy, unicode="", shift=False, ctrl=False, alt=False))
print("pencereden araç:", op.tool)
click((0,0)); typ("2"); key("TAB"); typ("1"); key("RET"); key("RET", ctrl=True)
sp = cu.splines[-1]; print("dikdörtgen:", sp_info(sp), [tuple(np.round(b.co,3)) for b in sp.bezier_points])
print("  oto kısıtlar:", [(c.kind, "XYZ"[c.axis]) for c in curve.cad.constraints])
# 2) 3 noktalı yay sıfırdan
op._set_tool(ctx, "ARC3"); click((3,0)); click((5,0)); click((4,1)); key("RET"); key("RET", ctrl=True)
sp = cu.splines[-1]; print("3 noktalı yay:", sp_info(sp), "| tepe:", np.round(sp.bezier_points[1].co,3) if len(sp.bezier_points)>2 else "")
# 3) merkezli yay sıfırdan: merkez, başlangıç, bitiş
op._set_tool(ctx, "CARC"); click((7,0)); click((8,0)); click((7,1)); key("RET"); key("RET", ctrl=True)
sp = cu.splines[-1]; print("merkezli yay:", sp_info(sp), "| uç:", np.round(sp.bezier_points[-1].co,3))
# 4) CV spline
key("S"); click((0,3)); click((1,4)); click((2,3)); click((3,4)); click((4,3)); key("RET"); key("RET", ctrl=True)
sp = cu.splines[-1]; print("CV spline:", sp_info(sp))
# 5) Kalem
key("P")
move((0,6)); op.modal(ctx, ev("LEFTMOUSE",(0,6))); op.modal(ctx, ev("MOUSEMOVE",(0.6,6.3))); op.modal(ctx, ev("LEFTMOUSE",(0.6,6.3),val="RELEASE"))
move((2,6)); op.modal(ctx, ev("LEFTMOUSE",(2,6))); op.modal(ctx, ev("MOUSEMOVE",(2.5,5.6))); op.modal(ctx, ev("LEFTMOUSE",(2.5,5.6),val="RELEASE"))
key("RET"); key("RET", ctrl=True); sp = cu.splines[-1]; print("kalem:", sp_info(sp), "| tutamaç:", np.round(sp.bezier_points[0].handle_right,3), np.round(sp.bezier_points[1].handle_left,3))
# 6) Daire
key("O"); click((6,-6)); typ("1.5"); key("RET"); key("RET", ctrl=True)
sp = cu.splines[-1]; print("daire:", sp_info(sp), "| yarıçap:", round(float(np.linalg.norm(np.asarray(sp.bezier_points[0].co)-np.array([6,-6,0]))),4))
# 7) Doğru: dikdörtgen köşesinden yatay -> çakışık + eksen
key("L"); op.dirty=True; click((2,1)); click((3.5,1.05)); key("RET"); key("RET", ctrl=True)
print("doğru oto kısıt:", [(c.kind, c.auto) for c in curve.cad.constraints][-2:])
# 8) Kısıt aracı: dikdörtgenin alt kenarı ile son doğru paralel (zaten) -> eşit boy
op.dirty=True; op._set_tool(ctx, "C_EQUAL"); click((1.0,0.0)); click((2.8,1.0))
print("eşit kısıtı:", curve.cad.constraints[-1].kind, curve.cad.constraints[-1].ok, "| doğru ucu:", np.round(cu.splines[-1].bezier_points[1].co,4))
# 9) kullanıcı dikdörtgenin bir köşesini çekerse
rect = cu.splines[0]; rect.bezier_points[2].co = Vec((2.4, 1.3, 0.0))
cmod.solve_all(ctx.scene)
print("köşe çekildikten sonra dikdörtgen:", [tuple(np.round(b.co,3)) for b in rect.bezier_points])
print("tüm kısıtlar sağlandı:", all(c.ok for c in curve.cad.constraints), [(c.kind, [(r.spline, r.index, r.point) for r in c.refs]) for c in curve.cad.constraints])
print("1. Esc (duraklat):", op.modal(ctx, ev("ESC", None)), op.tool)
print("Seç modunda tık Blender'a gider:", op.modal(ctx, ev("LEFTMOUSE", (1,1))), "| R tuşu:", op.modal(ctx, ev("R", None)), "| parça yok:", len(op.segs))
# kısıt simgesi: üstüne gelince bir şey açılmaz, SAĞ tık menü açar
def mv(x,y): op.modal(ctx, NS(type="MOUSEMOVE", value="NOTHING", mouse_x=x, mouse_y=y, unicode="", shift=False, ctrl=False, alt=False))
def btn(t,x,y,v="PRESS"): return op.modal(ctx, NS(type=t, value=v, mouse_x=x, mouse_y=y, unicode="", shift=False, ctrl=False, alt=False))
cmod._glyph_boxes[:] = [(600, 600, 613, 613, "Tel", 0)]
mv(606,606); print("üstüne gelince menü:", op.gmenu)
print("sağ tık:", btn("RIGHTMOUSE",606,606), "| menü:", [a for _, a in op.gmenu["buttons"]])
b = op.gmenu["buttons"][0][0]; mv((b[0]+b[2])/2,(b[1]+b[3])/2)
btn("LEFTMOUSE",(b[0]+b[2])/2,(b[1]+b[3])/2); print("dondur:", curve.cad.constraints[0].enabled)
cmod._glyph_boxes[:] = [(600, 600, 613, 613, "Tel", 0)]
btn("RIGHTMOUSE",606,606); b = op.gmenu["buttons"][1][0]; n0=len(curve.cad.constraints)
btn("LEFTMOUSE",(b[0]+b[2])/2,(b[1]+b[3])/2); print("sil:", n0, "->", len(curve.cad.constraints))
btn("RIGHTMOUSE",606,606); mv(900,100); print("uzaklaşınca kapanır:", op.gmenu)
op._set_tool(ctx, "LINE"); key("Q"); print("Q (LINE->önceki):", op.tool); key("Q"); print("Q tekrar:", op.tool)
key("E"); print("E:", op.tool); key("W"); print("W:", op.tool)
print("eksen renkleri XZ düzlemi u,v:", draw._axis_col((1,0,0))[:3], draw._axis_col((0,0,1))[:3])
# yay merkezi ve yay/teğet uzantısı
op._set_tool(ctx, "LINE"); op.dirty = True
c = move((4.0, 0.05)); print("yay merkezine yakın:", np.round(c,3), op.snap_kind)
c = move((4.0, -0.97)); print("yayın devamı (çember):", np.round(c,3), op.snap_kind, op.info and op.info["kind"])
print("2. Esc (duraklat):", op.modal(ctx, ev("ESC", None)), "| 3. Esc (kapat):", op.modal(ctx, ev("ESC", None)))
# Inventor gibi düzlem seçimi + ızgara
ctx.scene.minicad_pick_plane = True; ctx.scene.minicad_grid_snap = True
ctx.space_data = NS(overlay=NS(grid_scale=1.0))
op = draw.MINICAD_OT_draw.__new__(draw.MINICAD_OT_draw); op.report = lambda *a: None
op.invoke(ctx, NS()); op._view_dir = lambda: np.array([0, 0, -1.0]); op._view_right = lambda: np.array([1.0, 0, 0])
print("başlangıç aşaması:", op.phase)
move((0.5, 0.4)); print("üzerindeki düzlem:", op.hover_plane[0] if op.hover_plane else None)
op.modal(ctx, ev("LEFTMOUSE", (0.5, 0.4))); print("1/2 yön seçildi -> aşama:", op.phase)
typ("0.5"); key("RET"); print("2/2 yükseklik yazıldı:", op.phase, op.plane_mode, op.locked.name, "| düzlem z:", op.locked.o[2])
c = move((-3.03, -2.97)); print("ızgara yakalama:", np.round(c, 4), op.info and op.info["kind"])
c = move((-3.2, -2.75)); print("ızgaradan uzak:", np.round(c, 4), op.info and op.info["kind"])
key("I"); c = move((-3.03, -2.97)); print("I ile kapalı:", np.round(c, 4), op.grid_on)
key("Q"); print("Q -> yeniden düzlem seçimi:", op.phase)
key("Y"); print("Y tuşu:", op.phase, op.locked.name)

