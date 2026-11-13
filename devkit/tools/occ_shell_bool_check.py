"""Açık kabukta boolean (v0.25.4) — GERÇEK OCC. OCP 7.9 gerekir:
    /tmp/occ/bin/python devkit/tools/occ_shell_bool_check.py <eklenti klasörü>
Model: alt yüzü olmayan kutu (açık kabuk, kullanıcı raporundaki gibi 4 serbest kenar) ve üst
yüzden geçen silindir. Kesim üst yüzde π·0.4² delik açmalı, Kesişim yalnız o diski bırakmalı,
Birleşim ve gövdeye değmeyen araç açıklayıcı hata vermeli."""
import os, sys, tempfile, numpy as np
_src = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/mini_cad")
_pkg = tempfile.mkdtemp(); os.makedirs(os.path.join(_pkg, "mc")); open(os.path.join(_pkg, "mc", "__init__.py"), "w").close()
for _f in ("geometry.py", "errors.py"): os.symlink(os.path.join(_src, _f), os.path.join(_pkg, "mc", _f))
sys.path.insert(0, _pkg)
from mc import geometry as g
from mc.errors import CadError
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeBox
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
def L(a, b):
    a, b = np.array(a, float), np.array(b, float); return {"p": [tuple(a + (b - a) * t) for t in (0, 1/3, 2/3, 1)]}
V = [(0,0,0),(2,0,0),(2,2,0),(0,2,0),(0,0,1),(2,0,1),(2,2,1),(0,2,1)]
faces_idx = [(4,5,6,7), (0,1,5,4), (1,2,6,5), (2,3,7,6), (3,0,4,7)]          # alt yok: açık
b = g.Builder(); fs = []
for q in faces_idx:
    ch = [L(V[q[i]], V[q[(i+1)%4]]) for i in range(4)]
    fs.append(b.face(ch, [[c] for c in ch], "AUTO", False)[0])
shape, info = g.assemble(fs, [], 1e-6, True)
print("gövde:", info, "katı var:", g._has_solid(shape), "alan", round(g.area(shape), 4))
cyl = BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(1, 1, 0.5), gp_Dir(0, 0, 1)), 0.4, 2.0).Shape()
for op in ("CUT", "INTERSECT", "UNION"):
    try:
        r, ok, msg = g.apply_boolean(shape, [cyl], op, 0.0, "SECTION", 1e-6)
        print(op, ok, msg, "· yüz", len(g._shape_faces(r)), "· alan", round(g.area(r), 4))
        v, t, n = g.tessellate(r, 0.002, 0.2); print("   üçgen", len(t))
    except CadError as e:
        print(op, "HATA:", e)
far = BRepPrimAPI_MakeBox(gp_Pnt(5, 5, 5), 1, 1, 1).Shape()
try: g.apply_boolean(shape, [far], "CUT", 0.0, "SECTION", 1e-6)
except CadError as e: print("uzaktaki araç:", e)
import math
r, ok, _m = g.apply_boolean(shape, [cyl], "CUT", 0.0, "SECTION", 1e-6)
assert ok and abs(g.area(shape) - g.area(r) - math.pi * 0.16) < 1e-4, "kesim deliği yanlış"
r, ok, _m = g.apply_boolean(shape, [cyl], "INTERSECT", 0.0, "SECTION", 1e-6)
assert ok and abs(g.area(r) - math.pi * 0.16) < 1e-4, "kesişim yanlış"
print("SONUÇ: açık kabukta boolean çalışıyor")
