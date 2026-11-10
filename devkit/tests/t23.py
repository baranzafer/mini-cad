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
cl = jobs.client(); cl.want_process = True; jobs.__file__ = '/tmp/fk/fakepkg/jobs.py'; import os; os.environ['FAKE_SLOW']='0.5'
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
props = NS(patches=[NS(enabled=True, name="Y1", method="AUTO", info="", ok=True, segs=[], curves=[])],
           features=[feat("b1","BEVEL",.002), feat("b2","BEVEL",.003), feat("k1","BOOLEAN"), feat("b3","BEVEL",.001)],
           bevels=Coll(), curves=Coll(), join_tol=1e-3, mirror_x=False, mirror_y=False, mirror_z=False, mirror_center=None,
           make_solid=True, preview_bevel=False, ghost_bevel=True, use_mirror=True, use_booleans=True, use_bevels=True,
           corner_mode="JOINT", transition_factor=3.0, smooth_corners=True, lin_defl=3e-4, ang_defl=0.08, status="", is_cad=True, live=True, preview=True)
obj = NS(name="CAD", cad=props, data=None, matrix_world=[[1,0,0,0],[0,1,0,0],[0,0,1,0],[0,0,0,1]])
bpy.data = NS(objects={"CAD": obj})

print("senkron final:", core.rebuild(obj, preview=False), "| motor:", cl.describe(), "|", props.status.split(" · ")[0])
# canlı güncelleme asenkron: eğri sürükleniyormuş gibi önizleme iste
core._signature_parts_orig = core._signature_parts
bump = [0]
core._signature_parts = lambda p: (("drag", bump[0]),) + core._signature_parts_orig(p)[1:]
bump[0] += 1; core.schedule(obj, preview=True)
loops = 0; t0 = time.time(); seen = []
while time.time() - t0 < 6:
    r = core._tick(); loops += 1
    st = props.status.split(" · ")[0]
    if not seen or seen[-1] != st: seen.append(st)
    if r is None: break
    time.sleep(r)
print("durumlar:", seen, "| ana döngü", loops, "kez döndü (Blender donmadı)")
# asenkron iş sürerken senkron operatör çağrısı
bump[0] += 1; core.schedule(obj, preview=True); core._tick()
print("iş sürüyor mu:", cl.busy())
print("operatör (senkron) araya girdi:", core.rebuild(obj, preview=False), "| meşgul değil:", not cl.busy())
cl.stop()
