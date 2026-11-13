"""Coons sınır yüzeyi doğru mu (v0.25.1) — GERÇEK OCC. OCP 7.9 gerekir:
    /tmp/occ/bin/python devkit/tools/occ_coons_check.py <eklenti klasörü>
Model (kullanıcı raporu): küçük ön kemer + büyük arka kemer (yarım elips, 2 bezier) ve iki düz
kenar. Doğru yüzey: kemerlerin karşılıklı noktalarını birleştiren doğrular (regle). OCC'nin
GeomFill_CoonsStyle'ı kübik harmanlamayla S biçimli sırt veriyordu (sapma 0.12, yükseklik 2);
StretchStyle (doğrusal Coons) 0.0004. Keskin / Teğet / serbest hepsi denenir."""
import math, os, sys, tempfile
import numpy as np
SRC = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/mini_cad")
pkg = tempfile.mkdtemp(); os.makedirs(os.path.join(pkg, "mc")); open(os.path.join(pkg, "mc", "__init__.py"), "w").close()
for f in ("geometry.py", "errors.py"):
    os.symlink(os.path.join(SRC, f), os.path.join(pkg, "mc", f))
sys.path.insert(0, pkg)
from mc import geometry as g
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.BRep import BRep_Tool
from OCP.gp import gp_Pnt
K = 0.5522847498

def arch(x, w, h):
    return [[(x, -w, 0), (x, -w, h * K), (x, -w * K, h), (x, 0, h)],
            [(x, 0, h), (x, w * K, h), (x, w, h * K), (x, w, 0)]]

def line(a, b):
    a, b = np.array(a, float), np.array(b, float)
    return [tuple(a + (b - a) * t) for t in (0, 1 / 3, 2 / 3, 1)]

def run(blend, w=1.0):
    a, b = arch(0.0, 0.3, 0.6), arch(3.0, 1.2, 2.0)
    near, far = line((0, 0.3, 0), (3, 1.2, 0)), line((3, -1.2, 0), (0, -0.3, 0))
    big = [list(reversed(s)) for s in reversed(b)]
    chain = [{"p": s} for s in a] + [{"p": near}] + [{"p": s} for s in big] + [{"p": far}]
    sides = [[{"p": s} for s in a], [{"p": near}], [{"p": s} for s in big], [{"p": far}]]
    p = {"idx": 0, "name": "y", "chain": chain, "sides": sides, "method": "AUTO", "blend": blend}
    bld = g.Builder()
    if blend != "SHARP":
        g.blend_prepare(bld, [p])
    f, lab = bld.face(chain, sides, "AUTO", False,
                      **({"blend": blend, "weight": w} if blend != "SHARP" else {}))
    surf = BRep_Tool.Surface_s(f)
    dev = 0.0
    for th in np.linspace(0.1, math.pi - 0.1, 9):
        pa = np.array([0.0, -0.3 * math.cos(th), 0.6 * math.sin(th)])
        pb = np.array([3.0, -1.2 * math.cos(th), 2.0 * math.sin(th)])
        for s in np.linspace(0.1, 0.9, 9):
            pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*(pa + (pb - pa) * s)), surf)
            if pr.NbPoints():
                dev = max(dev, pr.LowerDistance())
    return lab, dev

ok = True
for bl, w in (("SHARP", 1.0), ("TANGENT", 1.0), ("TANGENT", 1.07), ("TANGENT_FREE", 1.0)):
    lab, dev = run(bl, w)
    print(f"[{bl} ağırlık {w}] {lab} · düz çizgili (regle) yüzeyden sapma {dev:.4f}")
    ok &= dev < 2e-3
assert ok, "Coons sınır yüzeyi düz çizgili değil (S biçimli?)"
print("SONUÇ: Coons doğru")
