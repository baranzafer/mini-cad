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
print("final ok:", core.rebuild(obj, preview=False), "|", props.status.split(" · ")[0], "| motor:", cl.mode)
print("fillet çağrıları:", geo.CALLS); geo.CALLS.clear()
print("bilgiler:", [(f.name, f.ok, f.info) for f in props.features])
print("uid atandı:", all(f.uid for f in props.features), "| gövde kenarları:", len(core._display["CAD"]["bool_edges"]))
core.rebuild(obj, preview=True)
gh = core._display["CAD"]["ghost"]
print("önizleme: fillet hesaplanmadı:", geo.CALLS == [], "| hayalet üçgen:", None if gh is None else len(gh["tris"]), "| durum:", props.status.split(" · ")[0])
core.rebuild(obj, preview=False); geo.CALLS.clear()
# canlı: sadece ölçü değişti -> hayalet işi (gövde yeniden hesaplanmaz)
props.features[0].size = 0.01; nwrites = len(writes)
core.schedule(obj, preview=True)
cmds = []; orig = cl.submit
def spy(cmd, data, cb): cmds.append(cmd); return orig(cmd, data, cb)
cl.submit = spy
t0 = time.time()
while time.time() - t0 < 3:
    r = core._tick()
    if r is None: break
    time.sleep(r)
print("canlı komut sırası:", cmds, "| mesh yazımı:", len(writes) - nwrites, "| son fillet ölçüleri:", geo.CALLS[-1] if geo.CALLS else None)
print("bırakınca hayalet temizlendi:", core._display["CAD"]["ghost"] is None, "|", props.status.split(" · ")[0])
# gövde kenarı referanslı fillet (pick + B)
k1 = props.features[2]; bd = core._display["CAD"]["bool_edges"]
f = feat("g1", "BEVEL", 0.05, segs=0); props.features.append(f)
g = f.geo_edges.add(); g.id, g.src, g.data = "e1", bd[0][0], core.geo_desc_json(bd[0][1])
geo.CALLS.clear(); core.rebuild(obj, preview=False)
print("gövde kenarı fillet:", f.ok, f.info, "| çağrı:", geo.CALLS[-1], "| kenar işaretli:", [u for _, _, u in core._display["CAD"]["bool_edges"]])
# fillet'i boolean'ın üstüne taşı -> çözülemez
props.features.insert(0, props.features.pop()); core.rebuild(obj, preview=False)
print("boolean'dan önce:", props.features[0].ok, props.features[0].info)
import pickle
cmd, job = core.gather(obj, False)
print("iş süreç sınırından geçebilir (pickle):", len(pickle.dumps(job)) > 0, "| komut:", cmd)
cmd, job = core.gather(obj, True); print("ölçü değişmeden önizleme komutu:", cmd)
