"""Delikli düzlemsel yüz (B harfi gibi) GERÇEK OCC ile denenir. OCP 7.9 gerekir:
    /tmp/occ/bin/python devkit/tools/occ_holes_check.py <eklenti klasörü>
Model: B harfine benzer dış çizgi (doğrular + iki yay çıkıntısı) ve iki "D" deliği.
Ölçülen: yüz geçerli mi, alanı = dış alan − delik alanları mı, delik kenarları ortak mı."""
import math, os, sys, tempfile
import numpy as np
_src = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/mini_cad")
_pkg = tempfile.mkdtemp()
os.makedirs(os.path.join(_pkg, "mc"))
open(os.path.join(_pkg, "mc", "__init__.py"), "w").close()
for _f in ("geometry.py", "errors.py"):
    os.symlink(os.path.join(_src, _f), os.path.join(_pkg, "mc", _f))
sys.path.insert(0, _pkg)
from mc import geometry as g
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

def L(a, b):
    return {"p": [tuple(map(float, a)) + (0.0,), tuple(map(float, b)) + (0.0,)]}

def arc(c, R, a0, a1):
    """c merkezli R yarıçaplı yay, a0 → a1 (radyan), çeyrek parçalara bölünür."""
    out = []
    n = max(1, int(math.ceil(abs(a1 - a0) / (math.pi / 2) - 1e-9)))
    step = (a1 - a0) / n
    k = 4.0 / 3.0 * math.tan(step / 4.0) * R
    for i in range(n):
        t0, t1 = a0 + i * step, a0 + (i + 1) * step
        p0 = np.array([c[0] + R * math.cos(t0), c[1] + R * math.sin(t0)])
        p3 = np.array([c[0] + R * math.cos(t1), c[1] + R * math.sin(t1)])
        d0 = np.array([-math.sin(t0), math.cos(t0)])
        d1 = np.array([-math.sin(t1), math.cos(t1)])
        P = [p0, p0 + d0 * k, p3 - d1 * k, p3]
        out.append({"p": [tuple(map(float, q)) + (0.0,) for q in P]})
    return out

outer = [L((0, 0), (0, 4)), L((0, 4), (1.5, 4))] + arc((1.5, 3), 1.0, math.pi / 2, -math.pi / 2) + \
    arc((1.5, 1), 1.0, math.pi / 2, -math.pi / 2) + [L((1.5, 0), (0, 0))]
def D(cy):
    return [L((0.5, cy - 0.4), (0.5, cy + 0.4)), L((0.5, cy + 0.4), (1.5, cy + 0.4))] + \
        arc((1.5, cy), 0.4, math.pi / 2, -math.pi / 2) + [L((1.5, cy - 0.4), (0.5, cy - 0.4))]
holes = [D(3.0), D(1.0)]
area_outer = 1.5 * 4 + math.pi * 1.0 ** 2          # dikdörtgen + iki yarım daire
area_hole = 1.0 * 0.8 + math.pi * 0.4 ** 2 / 2
expect = area_outer - 2 * area_hole

b = g.Builder()
face, label = b.face(outer, [[s] for s in outer], "AUTO", False, holes=holes)
pr = GProp_GProps()
BRepGProp.SurfaceProperties_s(face, pr)
area = pr.Mass()
print(f"etiket: {label} · alan {area:.5f} (beklenen {expect:.5f}) · kullanılabilir {g.face_usable(face)}")
assert abs(area - expect) < 2e-3 * expect, "alan yanlış: delikler düşülmemiş olabilir"
# ortak topoloji: deliğin bir kenarı Builder'daki kenar nesnesiyle aynı mı
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
e_hole = b.edge(holes[0][0]["p"])
exp = TopExp_Explorer(face, TopAbs_EDGE)
shared = False
while exp.More():
    if exp.Current().IsSame(e_hole):
        shared = True
    exp.Next()
print("delik kenarı ortak topolojide:", shared)
assert shared
shape, info = g.assemble([face], [], 1e-6, False)
v, t, n = g.tessellate(shape, 0.002, 0.2)
print(f"üçgenleme: {len(t)} üçgen")
# delikler ters yönde çizilmiş olsa da (kullanıcı hangi yönde çizerse) yüz geçerli olmalı
rev = [[{"p": list(reversed(x["p"]))} for x in reversed(h)] for h in holes]
face2, _ = g.Builder().face(outer, [[s] for s in outer], "AUTO", False, holes=rev)
pr2 = GProp_GProps()
BRepGProp.SurfaceProperties_s(face2, pr2)
print(f"ters yönlü delikler: alan {pr2.Mass():.5f} · kullanılabilir {g.face_usable(face2)}")
assert abs(pr2.Mass() - expect) < 2e-3 * expect
print("SONUÇ: delikli yüz çalışıyor")
