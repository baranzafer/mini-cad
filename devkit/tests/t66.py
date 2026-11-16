# v0.25.9: Kenar Seç düzenleme modunda bekler (tutamaç seçimi / kutu seçimi Blender'ın),
# Tab tel kafesi düzenlemeye alır, gövde mesh'i düzenleme modundayken sonuç kaybolmaz
exec(open("t4.py").read().split("# overlapping")[0])
import types, math
NS = types.SimpleNamespace
target = NS(name="CAD", visible_get=lambda: True, cad=NS(patches=[], features=[], curves=[]))
pick.core_target = lambda c: target
ob.type = "CURVE"
sel = {"ob": False}
ob.select_get = lambda: sel["ob"]
ob.select_set = lambda v: sel.__setitem__("ob", v)
ob.visible_get = lambda: True
P = np.array([[2/3,0,0,-1/3],[0,2/3,0,-1/3],[0,0,-1,0],[0,0,0,1]])
region = NS(width=300, height=300, x=0, y=0, type="WINDOW"); rv3d = NS(perspective_matrix=P.tolist())
def px(x, y): return ((x*2/3-1/3)+1)*150, ((y*2/3-1/3)+1)*150
area = NS(regions=[region], tag_redraw=lambda: None)
vl = NS(objects=NS(active=None))
ctx = NS(visible_objects=[ob], mode="OBJECT", view_layer=vl, selected_objects=[],
         workspace=NS(status_text_set=lambda t: status.append(t)))
status = []
modes = []
def mode_set(mode="OBJECT"):
    modes.append(mode); ctx.mode = "EDIT_CURVE" if mode == "EDIT" else "OBJECT"
bpy.ops = NS(object=NS(mode_set=mode_set)); pick.bpy.ops = bpy.ops
op = object.__new__(pick.MINICAD_OT_pick_edges)
op.area, op.region, op.rv3d = area, region, rv3d
op.scene = pick._Scene(ctx); op.selected = []; op.hover = None; op.hover_set = []
op.dirty = False; op.created = 0; op.radius = 10; op.stop_request = False; op._handle = None
op.used = set(); op.beveled = set(); op.report = lambda *a: None
pick._STATE["active"] = op
def ev(t, v="PRESS", xy=(1.0, 0.5), **k):
    x, y = px(*xy)
    return NS(type=t, value=v, mouse_x=x, mouse_y=y, ctrl=k.get("ctrl", False), alt=k.get("alt", False), shift=False)
ok = True
def check(name, cond):
    global ok
    ok &= bool(cond); print(("tamam  " if cond else "HATA   ") + name)
h = op.scene.pick(region, rv3d, *px(1.0, 0.5), 10)
check("kenar bulunuyor", h is not None)
# A) obje modunda tık kenarı seçer (eski davranış)
r = op.modal(ctx, ev("LEFTMOUSE"))
check("obje modunda tık kenar seçer", r == {"RUNNING_MODAL"} and len(op.selected) > 0)
n_sel = len(op.selected)
# B) düzenleme modunda her şey Blender'a geçer, seçim bozulmaz
ctx.mode = "EDIT_CURVE"
r1 = op.modal(ctx, ev("LEFTMOUSE"))
r2 = op.modal(ctx, ev("RET"))
r3 = op.modal(ctx, ev("F"))
r4 = op.modal(ctx, ev("B"))
r5 = op.modal(ctx, ev("BACK_SPACE"))
r6 = op.modal(ctx, ev("ESC"))
check("düzenleme modunda tık / Enter / F / B / Backspace / Esc Blender'a geçer",
      all(r == {"PASS_THROUGH"} for r in (r1, r2, r3, r4, r5, r6)))
check("kenar seçimi korunur, mod kapanmaz", len(op.selected) == n_sel and pick._STATE["active"] is op)
check("durum satırı bekliyor der", "BEKLİYOR" in status[-1])
check("bekleyince üzerinde vurgusu yok", op.hover is None and op.waiting)
# C) obje moduna dönünce yeniden çalışır
ctx.mode = "OBJECT"
op.modal(ctx, ev("MOUSEMOVE", "NOTHING"))
check("obje moduna dönünce yeniden etkin", not op.waiting and op.hover is not None and "BEKLİYOR" not in status[-1])
# D) Tab: aktif obje yokken üzerinde durulan kenarın eğrisi düzenlemeye alınır
r = op.modal(ctx, ev("TAB"))
check("Tab eğriyi aktif yapıp düzenlemeye alır", r == {"RUNNING_MODAL"} and modes == ["EDIT"]
      and vl.objects.active is ob and sel["ob"] and ctx.mode == "EDIT_CURVE")
r = op.modal(ctx, ev("TAB"))
check("düzenleme modunda Tab Blender'ın (çıkış)", r == {"PASS_THROUGH"} and modes == ["EDIT"])
ctx.mode = "OBJECT"
op.modal(ctx, ev("MOUSEMOVE", "NOTHING"))
r = op.modal(ctx, ev("TAB"))
check("eğri zaten aktif ve seçiliyse Tab Blender'ın", r == {"PASS_THROUGH"} and modes == ["EDIT"])
# E) aktif obje gövde (mesh) ise ve fare boşluktaysa: yine tel kafes düzenlenir
body = NS(type="MESH", select_get=lambda: True, select_set=lambda v: None, name="CAD")
vl.objects.active = body; ctx.selected_objects = [body]; sel["ob"] = False
op.modal(ctx, ev("MOUSEMOVE", "NOTHING", xy=(0.02, 0.02)))
r = op.modal(ctx, ev("TAB", xy=(0.02, 0.02)))
check("gövde aktifken Tab tel kafesi düzenlemeye alır", r == {"RUNNING_MODAL"} and modes == ["EDIT", "EDIT"]
      and vl.objects.active is ob)
# F) gövde mesh'i düzenleme modunda: sonuç yazılmaz, durum açıklar, çıkınca yeniden hesap
core._notify = lambda *a: None
written = []
core.write_mesh = lambda *a: written.append(1)
cad = NS(patches=[], features=[], status="", is_cad=True, live=True)
bo = NS(name="CADX", cad=cad, data=NS(is_editmode=True))
res = {"ok": True, "verts": [], "tris": [], "normals": None, "patches": {}, "features": {}}
r = core._apply(bo, {"preview": False}, res)
check("düzenleme modundaki gövdeye yazılmaz", r is False and not written and "düzenleme modunda" in cad.status
      and "CADX" in core._edit_blocked)
sched = []
core.schedule = lambda o, preview=False: sched.append((o.name, preview))
scn = NS(objects=NS(get=lambda n: bo if n == "CADX" else None, __iter__=lambda s: iter([])))
class Objs(list):
    def get(self, n): return bo if n == "CADX" else None
scn = NS(objects=Objs())
dg = NS(updates=[])
core.on_depsgraph_update(scn, dg)
check("hâlâ düzenleme modunda: beklenir", not sched and "CADX" in core._edit_blocked)
bo.data.is_editmode = False
core.on_depsgraph_update(scn, dg)
check("moddan çıkınca tam hesap istenir", sched == [("CADX", False)] and "CADX" not in core._edit_blocked)
assert ok
print("SONUÇ: tamam")
