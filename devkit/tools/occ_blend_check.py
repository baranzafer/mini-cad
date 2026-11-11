"""Yüzey birleşimi (Keskin / Teğet G1) GERÇEK OCC ile ölçülür. OCP 7.9 gerekir:
    python3 -m venv /tmp/occ && /tmp/occ/bin/pip install "cadquery-ocp-novtk>=7.9.3,<8" numpy
    /tmp/occ/bin/python devkit/tools/occ_blend_check.py <eklenti klasörü>
Model: kare taban + üstte daire; 4 düzlem üçgen, 4 köşe yaması (3 kenarlı Dolgu).
Ölçülen: üçgen–köşe yaması ortak kenarında iki yüzün normalleri arasındaki açı."""
import math, os, sys, tempfile, time
import numpy as np
_src = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/mini_cad")
_pkg = tempfile.mkdtemp()
os.makedirs(os.path.join(_pkg, "mc"))
open(os.path.join(_pkg, "mc", "__init__.py"), "w").close()
for _f in ("geometry.py", "errors.py"):
    os.symlink(os.path.join(_src, _f), os.path.join(_pkg, "mc", _f))
sys.path.insert(0, _pkg)
from mc import geometry as g
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomLProp import GeomLProp_SLProps
from OCP.ShapeAnalysis import ShapeAnalysis_Surface
from OCP.BRep import BRep_Tool
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_REVERSED

R, H, A = 0.6, 1.0, 1.0
K = 0.5522847498 * R
def line(a, b): a, b = np.array(a, float), np.array(b, float); return {"p": [tuple(a), tuple(b)]}
def arc(t0, t1):   # çeyrek daire z=H
    c0 = np.array([R*math.cos(t0), R*math.sin(t0), H]); c1 = np.array([R*math.cos(t1), R*math.sin(t1), H])
    d0 = np.array([-math.sin(t0), math.cos(t0), 0]); d1 = np.array([-math.sin(t1), math.cos(t1), 0])
    return {"p": [tuple(c0), tuple(c0 + d0*K), tuple(c1 - d1*K), tuple(c1)]}
top = [(R*math.cos(k*math.pi/2), R*math.sin(k*math.pi/2), H) for k in range(4)]
corners = [(A, A, 0), (-A, A, 0), (-A, -A, 0), (A, -A, 0)]   # k. köşe: top[k] ile top[k+1] arası
patches = []
for k in range(4):     # üçgen: taban kenarı corners[k-1]..corners[k] , tepe top[k]
    a, b, t = corners[k-1], corners[k], top[k]
    ch = [line(a, b), line(b, t), line(t, a)]
    patches.append({"idx": len(patches), "name": f"üçgen{k}", "chain": ch, "sides": [[s] for s in ch], "method": "AUTO"})
for k in range(4):     # köşe yaması
    c, t0, t1 = corners[k], top[k], top[(k+1) % 4]
    ch = [line(c, t0), arc(k*math.pi/2, (k+1)*math.pi/2), line(t1, c)]
    patches.append({"idx": len(patches), "name": f"köşe{k}", "chain": ch, "sides": [[s] for s in ch], "method": "AUTO"})
bottom = [line(corners[k-1], corners[k]) for k in range(4)]
patches.append({"idx": len(patches), "name": "taban", "chain": bottom, "sides": [[s] for s in bottom], "method": "AUTO"})

def normal_at(face, p):
    surf = BRep_Tool.Surface_s(face)
    uv = ShapeAnalysis_Surface(surf).ValueOfUV(gp_Pnt(*p), 1e-7)
    pr = GeomLProp_SLProps(surf, uv.X(), uv.Y(), 1, 1e-9)
    if not pr.IsNormalDefined(): return None
    n = pr.Normal(); n = np.array([n.X(), n.Y(), n.Z()])
    return -n if face.Orientation() == TopAbs_REVERSED else n

def run(blend, preview=False):
    for p in patches: p["blend"] = blend
    b = g.Builder()
    order = g.blend_order(patches) if blend != "SHARP" else patches
    built, info = {}, {}
    t0 = time.perf_counter()
    for p in order:
        kw = {"blend": blend} if blend != "SHARP" else {}
        f, lab = b.face(p["chain"], p["sides"], p["method"], preview, **kw)
        built[p["idx"]], info[p["name"]] = f, lab
    ms = (time.perf_counter() - t0) * 1000
    # üçgen–köşe ortak kenarları (doğrular): orta 5 noktada normal açısı (uçlar tekil olabilir)
    worst = 0.0; worst_mid = 0.0
    for k in range(4):
        tri = built[k]; cor = built[4 + k]; tri2 = built[(k+1) % 4]
        for fa, fb, a, c in ((tri, cor, corners[k], top[k]), (tri2, cor, corners[k], top[(k+1) % 4])):
            for s in np.linspace(0.05, 0.95, 19):
                q = np.array(a) * (1 - s) + np.array(c) * s
                na, nb = normal_at(fa, q), normal_at(fb, q)
                if na is None or nb is None: continue
                ang = math.degrees(math.acos(min(1, abs(float(np.dot(na, nb)) / np.linalg.norm(na) / np.linalg.norm(nb)))))
                worst = max(worst, ang)
                if 0.2 <= s <= 0.8: worst_mid = max(worst_mid, ang)
    shape, sinfo = g.assemble([built[p["idx"]] for p in patches], [], 1e-6, False)
    usable = all(g.face_usable(f) for f in built.values())
    print(f"[{blend}{' önizleme' if preview else ''}] {ms:.0f} ms · {sinfo} · yüzler kullanılabilir={usable}")
    print(f"   köşe yaması etiketi: {info['köşe0']}")
    print(f"   ortak kenarda en büyük kırılma: {worst:.2f}° (kenarın orta %60'ında {worst_mid:.2f}°)")
    return worst_mid

r0 = run("SHARP"); r1 = run("TANGENT"); r1p = run("TANGENT", preview=True)
assert r1 < 0.5 * r0 and r1 < 3.0, "teğet birleşim kırılmayı gidermedi"
print("SONUÇ: teğet birleşim çalışıyor")

print("Blender'a giden mesh normalleri (kenar boyunca, 0.2<z<0.8):")
for blend in ("SHARP", "TANGENT"):
    for p in patches: p["blend"] = blend
    b = g.Builder(); built = {}
    for p in (g.blend_order(patches) if blend != "SHARP" else patches):
        built[p["idx"]] = b.face(p["chain"], p["sides"], p["method"], False, **({"blend": blend} if blend != "SHARP" else {}))[0]
    shape, _ = g.assemble([built[p["idx"]] for p in patches], [], 1e-6, False)
    v, t, n = g.tessellate(shape, 0.002, 0.2)
    V, N = np.array(v), np.array(n)
    groups = {}
    for i, q in enumerate(V):
        if 0.2 < q[2] < 0.8: groups.setdefault(tuple(np.round(q, 5)), []).append(i)
    worst = 0.0
    for ids in groups.values():
        for i in ids:
            for j in ids:
                c = float(np.dot(N[i], N[j]) / np.linalg.norm(N[i]) / np.linalg.norm(N[j]))
                worst = max(worst, math.degrees(math.acos(max(-1, min(1, c)))))
    note = " (keskinde düz kenarda ortak ara nokta yok; ölçü anlamsız)" if blend == "SHARP" else ""
    print(f"   [{blend}] {len(V)} köşe · aynı noktadaki normaller arası en büyük açı: {worst:.2f}°{note}")
