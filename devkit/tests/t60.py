# v0.24.0: Teğet ağırlığı ve serbest dolgu: gather -> motor, imza, eski dosya
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
core.patch_segments = lambda p: [segd(A,B,0), segd(B,C,1), segd(C,D,2), segd(D,A,3)]
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
props = NS(patches=[NS(enabled=True, name="Y1", method="PLANE", info="", ok=True, segs=[], curves=[], blend="BODY"),
                    NS(enabled=True, name="Y2", method="AUTO", info="", ok=True, segs=[], curves=[], blend="BODY"),
                    NS(enabled=True, name="Y3", method="FILL", info="", ok=True, segs=[], curves=[], blend="SHARP")],
           surface_blend="TANGENT",
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
got = []
_orig_face = geo.Builder.face
def face(s, chain, sides, method, preview, blend="SHARP", holes=None, weight=1.0):
    _orig_face(s, chain, sides, method, preview, blend, weight=weight)
    return ("face", method, blend), "Dolgu"
geo.Builder.face = face
_orig_asm = geo.assemble
geo.assemble = lambda faces, *a: (got.append(list(faces)), _orig_asm(faces, *a))[1]
props.features = []

print("A) Teğet, ağırlık 1: motora ağırlık gönderilmez (eski çağrı aynı)")
props.surface_blend = "TANGENT"; props.tangent_weight = 1.0
for p in props.patches: p.blend = "BODY"; p.own_weight = False; p.tangent_weight = 1.0
props.patches[2].blend = "SHARP"
geo.BLENDS.clear(); core.rebuild(obj, preview=False)
check(all(len(b) == 3 for b in geo.BLENDS), f"ağırlıksız çağrı: {geo.BLENDS}")
print("B) Gövde ağırlığı 1.5: kaynaşan yamalara gider, keskin yamaya gitmez")
s1 = core._signature_parts(props)
props.tangent_weight = 1.5
check(core._signature_parts(props) != s1, "gövde ağırlığı imzada")
geo.BLENDS.clear(); core.rebuild(obj, preview=False)
w = {b[1]: (b[3] if len(b) > 3 else 1.0) for b in geo.BLENDS}
check(w == {"PLANE": 1.5, "AUTO": 1.5, "FILL": 1.0}, f"ağırlıklar: {w}")
print("C) Yüzeye özel ağırlık")
s2 = core._signature_parts(props)
props.patches[1].own_weight = True; props.patches[1].tangent_weight = 0.6
check(core._signature_parts(props) != s2, "yüzey ağırlığı imzada")
geo.BLENDS.clear(); core.rebuild(obj, preview=False)
w = {b[1]: (b[3] if len(b) > 3 else 1.0) for b in geo.BLENDS}
check(w["AUTO"] == 0.6 and w["PLANE"] == 1.5, f"Y2 kendi ağırlığı: {w}")
print("D) Teğet – serbest dolgu motora gider")
props.surface_blend = "TANGENT_FREE"
geo.BLENDS.clear(); core.rebuild(obj, preview=False)
check(("AUTO", "TANGENT_FREE") == geo.BLENDS[-1][1:3], f"serbest: {geo.BLENDS}")
print("E) Eski dosya (ağırlık alanları yok): ağırlık 1")
props.surface_blend = "TANGENT"
del props.tangent_weight
for p in props.patches:
    del p.own_weight; del p.tangent_weight
geo.BLENDS.clear(); core.rebuild(obj, preview=False)
check(all(len(b) == 3 for b in geo.BLENDS), "alan yoksa ağırlık gönderilmez")
print("t60 bitti")
