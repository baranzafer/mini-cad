# v0.15.5: yüzey birleşimi (Keskin / Teğet): gather -> motor kurma sırası, gövde sırası
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
def face(s, chain, sides, method, preview, blend="SHARP"):
    _orig_face(s, chain, sides, method, preview, blend)
    return ("face", method, blend), "Dolgu"
geo.Builder.face = face
_orig_asm = geo.assemble
geo.assemble = lambda faces, *a: (got.append(list(faces)), _orig_asm(faces, *a))[1]
props.features = []
print("A) Gövde ayarı Teğet; Y1 Düzlem, Y2 gövde ayarı, Y3 Keskin")
ok = core.rebuild(obj, preview=False)
check(ok, f"hesaplandı: {props.status.split(' · ')[0]}")
print("   kurma sırası:", geo.BLENDS)
check([b[1:] for b in geo.BLENDS] == [("PLANE", "TANGENT"), ("FILL", "SHARP"), ("AUTO", "TANGENT")],
      "sabit yamalar önce, kaynaşan (Y2) en son kuruldu")
check([f[1] for f in got[-1]] == ["PLANE", "AUTO", "FILL"], "gövdeye asıl sırayla eklendi")
check(all(p.ok for p in props.patches), "yüzey bilgileri yazıldı")
print("B) Hepsi Keskin: eski davranış (sıra değişmez, blend argümanı gönderilmez)")
geo.BLENDS.clear(); props.surface_blend = "SHARP"; props.patches[0].blend = "BODY"; props.patches[1].blend = "BODY"
s1 = core._signature_parts(props)
core.rebuild(obj, preview=False)
check([b[1:] for b in geo.BLENDS] == [("PLANE", "SHARP"), ("AUTO", "SHARP"), ("FILL", "SHARP")], f"sıra aynı: {geo.BLENDS}")
print("C) Ayar değişince imza değişir (canlı güncelleme yeniden hesaplar)")
props.surface_blend = "TANGENT"
check(core._signature_parts(props) != s1, "gövde ayarı imzada")
props.surface_blend = "SHARP"; props.patches[1].blend = "TANGENT"
check(core._signature_parts(props) != s1, "yüzey ayarı imzada")
geo.BLENDS.clear(); core.rebuild(obj, preview=False)
check([b[1:] for b in geo.BLENDS][-1] == ("AUTO", "TANGENT"), "yüzey başına Teğet tek başına çalışır")
print("D) Eski dosya (alan yok): Keskin varsayılır")
del props.patches[1].blend; del props.surface_blend
geo.BLENDS.clear(); core.rebuild(obj, preview=False)
check(all(b[2] == "SHARP" for b in geo.BLENDS), "alan yoksa Keskin")
print("t46 bitti")
