# v0.22.0: delikli yüz (B harfi gibi): birden çok kapalı döngü → dış sınır + delikler;
# ayrı dış döngüler ayrı yüz; çizim aracında F iç içe çizgileri birlikte alır
# core: gather -> engine (Blender içi) -> _apply, canlı güncelleme ve hayalet yolu
exec(open("t.py").read().split("def seg(")[0])
import types, importlib.util, time, json, numpy as np
NS = types.SimpleNamespace
spec = importlib.util.spec_from_file_location("mini_cad.geometry", "/tmp/fk/fakepkg/geometry.py")
geo = importlib.util.module_from_spec(spec); sys.modules["mini_cad.geometry"] = geo; spec.loader.exec_module(geo)
core.kernel.kernel_available = lambda *a: True
registered = []
bpy.app.timers = NS(register=lambda f, first_interval=0: registered.append(f), is_registered=lambda f: f in registered)
from mini_cad import jobs
cl = jobs.client(); cl.want_process = False
writes = []; core.write_mesh = lambda me, v, t, n: writes.append(len(t)); core.link_wires = lambda o: None
core._watched_objects = lambda p: []
core._transform_running = lambda: False
A, B, C, D = V(0,0,0), V(1,0,0), V(1,1,0), V(0,1,0)
def segd(a, b, i): return {"p": [a, b], "tag": ("w", 0), "ref": ("w", 0, i)}
SEGS = {}
core.patch_segments = lambda p: SEGS[p.name]
core.collect_segrefs = lambda refs: [segd(A,B,0)] if len(refs) else []
class Coll(list):
    def clear(s): del s[:]
    def add(s):
        x = NS(id="", src="", data=""); s.append(x); return x
def feat(name, op, size=0.002, segs=1):
    return NS(name=name, op=op, enabled=True, kind="FILLET", size=size, segs=[1]*segs, bool_type="CUT", tool=NS(name="T", cad=NS(is_cad=False), matrix_world=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]]),
              edge_size=0.0, edge_mode="SECTION", mirror_tool=True, ok=True, info="", uid="", geo_edges=Coll())
core.tool_signature = lambda t, o: ("t", 1)
core._read_tool_mesh = lambda t, mw: ([(0,0,0)]*4, [[0,1,2]])
props = NS(patches=[NS(enabled=True, name="Y1", method="AUTO", info="", ok=True, segs=[], curves=[])],
           features=[feat("b1","BEVEL",.002), feat("b2","BEVEL",.003), feat("k1","BOOLEAN"), feat("b3","BEVEL",.001)],
           bevels=Coll(), curves=Coll(), join_tol=1e-3, mirror_x=False, mirror_y=False, mirror_z=False, mirror_center=None,
           make_solid=True, preview_bevel=False, ghost_bevel=True, use_mirror=True, use_booleans=True, use_bevels=True,
           corner_mode="JOINT", transition_factor=3.0, smooth_corners=True, lin_defl=3e-4, ang_defl=0.08, status="", is_cad=True, live=True, preview=True)
obj = NS(name="CAD", cad=props, data=None, matrix_world=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]])
bpy.data = NS(objects={"CAD": obj})

def check(cond, msg):
    print(("  tamam  " if cond else "  HATA   ") + msg)
    if not cond:
        raise SystemExit(1)
def rect(x0, y0, x1, y1, k0, z=0.0):
    P = [V(x0, y0, z), V(x1, y0, z), V(x1, y1, z), V(x0, y1, z)]
    return [segd(P[i], P[(i + 1) % 4], k0 + i) for i in range(4)]
props.features = []
props.patches[0].name = "B"
print("A) chain_loops / nest_loops")
loops = core.chain_loops(rect(0, 0, 4, 6, 0) + rect(1, 1, 3, 2.5, 10) + rect(1, 3.5, 3, 5, 20), 1e-6)
check(len(loops) == 3 and all(len(l) == 4 for l in loops), f"3 döngü: {[len(l) for l in loops]}")
g = core.nest_loops(loops)
check(len(g) == 1 and len(g[0][1]) == 2, f"1 dış sınır, 2 delik")
g = core.nest_loops(core.chain_loops(rect(0, 0, 6, 6, 0) + rect(1, 1, 5, 5, 10) + rect(2, 2, 4, 4, 20), 1e-6))
check(len(g) == 2 and sorted(len(x[1]) for x in g) == [0, 1], "iç içe 3 kare: dış + delik, ortadaki adacık ayrı yüz")
g = core.nest_loops(core.chain_loops(rect(0, 0, 1, 1, 0) + rect(3, 0, 4, 1, 10), 1e-6))
check(len(g) == 2 and all(not x[1] for x in g), "ayrı iki döngü: iki yüz")
try:
    core.nest_loops(core.chain_loops(rect(0, 0, 4, 4, 0) + rect(1, 1, 2, 2, 10, z=1.0), 1e-6))
    check(False, "düzlemsel olmayan delik reddedilmeli")
except core.CadError as e:
    check("düzlem" in str(e), f"düzlemsel değil: {e}")
print("B) gather → motor: delikli yüz")
SEGS["B"] = rect(0, 0, 4, 6, 0) + rect(1, 1, 3, 2.5, 10) + rect(1, 3.5, 3, 5, 20)
geo.HOLES.clear()
ok = core.rebuild(obj, preview=False)
check(ok and props.patches[0].ok, f"hesaplandı: {props.patches[0].info}")
check(geo.HOLES == [(4, [4, 4])], f"yüz 2 delikle kuruldu: {geo.HOLES}")
check("2 delik" in props.patches[0].info, "bilgi: delik sayısı")
print("C) ayrı iki dış döngü: bir yüzey kaydından iki yüz")
SEGS["B"] = rect(0, 0, 1, 1, 0) + rect(3, 0, 4, 1, 10)
geo.HOLES.clear(); ok = core.rebuild(obj, preview=False)
check(ok and len(geo.HOLES) == 2, f"iki yüz: {geo.HOLES}")
print("D) açık zincir hâlâ anlaşılır hata")
SEGS["B"] = rect(0, 0, 1, 1, 0)[:3]
core.rebuild(obj, preview=False)
check(not props.patches[0].ok and "kapalı" in props.patches[0].info, props.patches[0].info)
print("t57 bitti")
