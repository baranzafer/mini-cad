"""Motor uçtan uca (v0.26.0) — GERÇEK OCC. OCP 7.9 gerekir:
    /tmp/occ/bin/python devkit/tools/occ_engine_sweep_check.py <eklenti klasörü>
engine.build'e Blender'ın gönderdiği biçimde iş verilir: 2×2×2 küp (6 düzlem yüzey),
  1) SWEEP: üst ön kenar boyunca 45° pah (açık profil, dışarıdan kapat) → başarılı, hacim d²
  2) BEVEL: aynı küpte tek kenara 2.5 fillet (yan yüzler 2 birim) → başarısız, kaynak
     "Geometrik olarak mümkün değil" ve sınır ölçü
  3) SWEEP profil kapalı değil + 'Kapalı Olmalı' → "Model kaynaklı"
  4) sweep_lines sonuçta (önizleme çizimi)
"""
import math
import os
import sys
import tempfile

SRC = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/mini_cad")
pkg = tempfile.mkdtemp()
os.makedirs(os.path.join(pkg, "mc"))
open(os.path.join(pkg, "mc", "__init__.py"), "w").close()
for f in ("geometry.py", "errors.py", "sweep.py", "engine.py"):
    os.symlink(os.path.join(SRC, f), os.path.join(pkg, "mc", f))
sys.path.insert(0, pkg)
from mc import engine  # noqa: E402

C = [(x, y, z) for x in (0.0, 2.0) for y in (0.0, 2.0) for z in (0.0, 2.0)]
FACES = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]


def seg(a, b, i):
    return {"p": [C[a], C[b]], "tag": ("w", 0), "ref": ("w", 0, i)}


patches = []
for k, f in enumerate(FACES):
    ch = [seg(f[i], f[(i + 1) % 4], 4 * k + i) for i in range(4)]
    patches.append({"idx": k, "name": f"Y{k}", "chain": ch, "sides": [[s] for s in ch],
                    "method": "AUTO", "blend": "SHARP"})
d = 0.3
a1 = (-d * math.sin(math.pi / 4), -d * math.cos(math.pi / 4), 0.0)
a2 = (d * math.sin(math.pi / 4), -d * math.cos(math.pi / 4), 0.0)
PROF = {"segs": [[a1, a2]], "origin": (0.0, 0.0, 0.0),
        "axes": [(1.0, 0, 0), (0, 1.0, 0), (0, 0, 1.0)]}
PARAMS = {"place": "AUTO", "ref": "FACES", "close": "ORIGIN", "angle": 0.0, "off_x": 0.0,
          "off_y": 0.0, "scale": 1.0, "flip": False, "reverse": False, "extend_auto": True,
          "extend": 0.0}


def sweep_stage(uid, params=PARAMS):
    return {"op": "SWEEP", "uid": uid, "bool_type": "CUT",
            "path": [[(0.0, 0.0, 2.0), (2.0, 0.0, 2.0)]], "geo": [], "profile": PROF,
            "params": params, "edge_size": 0.0, "edge_mode": "SECTION", "mirror_tool": False,
            "want_edges": True, "key": ("S", uid, tuple(sorted(params.items())))}


def job(stages):
    return {"name": "Küp", "preview": False, "patches": patches, "errors": [], "tol": 1e-4,
            "mirrors": [], "sew_tol": 1e-5, "make_solid": True, "run_bevels": True,
            "ghost": False, "stages": stages, "corner_mode": "JOINT", "factor": 3.0,
            "smooth": True, "lin": 1e-3, "ang": 0.3, "feature_names": {}, "deep": []}


ok = True
r = engine.build(job([sweep_stage("s1")]))
f = r["features"].get("s1")
print("[1 süpürme]", r["ok"], f, r.get("error"))
v = engine._final["Küp"]["shape"]
vol = engine._geo().volume(v)
print(f"    hacim {vol:.5f} (beklenen {8 - d * d:.5f})")
ok &= r["ok"] and f and f[0] and abs(vol - (8 - d * d)) < 1e-3
ok &= bool(r.get("sweep_lines", {}).get("s1"))
print("[4 önizleme telleri]", len(r.get("sweep_lines", {}).get("s1", [])), "çizgi")

bev = {"op": "BEVEL", "skey": ("b1",), "key": ("F",), "items": [
    {"uid": "b1", "kind": "FILLET", "size": 2.5, "geo": [],
     "polys": [[(0.0, 0.0, 2.0), (1.0, 0.0, 2.0), (2.0, 0.0, 2.0)]]}]}
r = engine.build(job([bev]))
f = r["features"].get("b1")
print("[2 sığmayan fillet]", f)
ok &= f is not None and not f[0] and "Geometrik olarak mümkün değil" in f[1] and \
    "en fazla" in f[1]

p3 = dict(PARAMS, close="NONE")
r = engine.build(job([sweep_stage("s3", p3)]))
f = r["features"].get("s3")
print("[3 açık profil, kapalı olmalı]", f)
ok &= f is not None and not f[0] and f[1].startswith("Model kaynaklı")

assert ok, "motor uçtan uca beklenen sonucu vermedi"
print("SONUÇ: motor süpürme ve teşhis uçtan uca çalışıyor")
