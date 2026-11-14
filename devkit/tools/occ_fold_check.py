"""Yüzey katlanma denetimi (v0.25.7) — GERÇEK OCC. OCP 7.9 gerekir:
    /tmp/occ/bin/python devkit/tools/occ_fold_check.py <eklenti klasörü>
Karşılıklı yarım daireler (doğru) uyarı vermemeli; iki uçta zıt yarılar (yüzey raylarda
kendi üstüne katlanır) ve çapraz raylı kelebek uyarı vermeli. Koni tepesi gibi noktaya inen
kenarlar yanlış alarm vermemeli (occ_blend_check köşe yamaları)."""
import math, os, sys, tempfile, numpy as np
_src = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/mini_cad")
_pkg = tempfile.mkdtemp(); os.makedirs(os.path.join(_pkg, "mc")); open(os.path.join(_pkg, "mc", "__init__.py"), "w").close()
for _f in ("geometry.py", "errors.py"): os.symlink(os.path.join(_src, _f), os.path.join(_pkg, "mc", _f))
sys.path.insert(0, _pkg)
from mc import geometry as g
K = 0.5522847498
def half(x, R, upper):
    """x düzleminde yarım daire: (x,R,0) → (x,-R,0), üstten (z>0) ya da alttan."""
    s = 1 if upper else -1
    return [[(x, R, 0), (x, R, s*R*K), (x, R*K, s*R), (x, 0, s*R)], [(x, 0, s*R), (x, -R*K, s*R), (x, -R, s*R*K), (x, -R, 0)]]
def L(a, b):
    a, b = np.array(a, float), np.array(b, float); return [tuple(a + (b - a) * t) for t in (0, 1/3, 2/3, 1)]
def build(upper_far):
    top = half(0.0, 1.0, True)
    far = half(6.0, 1.0, upper_far)
    side0 = [{"p": s} for s in top]
    side1 = [{"p": L((0, -1, 0), (6, -1, 0))}]
    side2 = [{"p": list(reversed(s))} for s in reversed(far)]
    side3 = [{"p": L((6, 1, 0), (0, 1, 0))}]
    chain = side0 + side1 + side2 + side3
    b = g.Builder()
    return b.face(chain, [side0, side1, side2, side3], "AUTO", False)
# kelebek: raylar çapraz
side0 = [{"p": L((0, 0, 0), (2, 0, 0))}]
side1 = [{"p": L((2, 0, 0), (0, 2, 1))}]
side2 = [{"p": L((0, 2, 1), (2, 2, 1))}]
side3 = [{"p": L((2, 2, 1), (0, 0, 0))}]
chain = side0 + side1 + side2 + side3
f, lab = g.Builder().face(chain, [side0, side1, side2, side3], "AUTO", False)
print("KELEBEK ->", lab)
ok = "UYARI" in lab
f1, l1 = build(True); f2, l2 = build(False)
ok &= "UYARI" not in l1 and "UYARI" in l2
print("karşılıklı:", l1, "| zıt yarılar:", l2)
assert ok, "katlanma denetimi beklendiği gibi değil"
print("SONUÇ: katlanma denetimi çalışıyor")
