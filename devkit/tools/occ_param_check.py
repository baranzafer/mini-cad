"""Karşılıklı kenar eşleşmesi (v0.25.8) — GERÇEK OCC. OCP 7.9 gerekir:
    /tmp/occ/bin/python devkit/tools/occ_param_check.py <eklenti klasörü>
Yarım tüp: iki uçta aynı yarım daire profili ama farklı parçalanmış (2 / 3 / 1 segment, eşit
olmayan parçalar, tutamakları dengesiz tek bezier). Doğru yüzey yarım silindir (koni): profilin
aynı açıdaki noktaları düz çizgiyle birleşir. Önce (v0.25.7) parçalar segment sayısına göre
eşleşiyor, yüzey çapraz kırışıyor / katlanıyordu (kullanıcı: damla profilli tüp)."""
import math, os, sys, tempfile, numpy as np
_src = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/mini_cad")
_pkg = tempfile.mkdtemp(); os.makedirs(os.path.join(_pkg, "mc")); open(os.path.join(_pkg, "mc", "__init__.py"), "w").close()
for _f in ("geometry.py", "errors.py"): os.symlink(os.path.join(_src, _f), os.path.join(_pkg, "mc", _f))
sys.path.insert(0, _pkg)
from mc import geometry as g
from OCP.BRep import BRep_Tool
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.gp import gp_Pnt

def arc(x, R, a0, a1):
    """x düzleminde daire yayı (açı a0→a1, radyan) kübik bezier."""
    k = 4.0 / 3.0 * math.tan((a1 - a0) / 4.0)
    p0 = np.array([x, R * math.cos(a0), R * math.sin(a0)]); p3 = np.array([x, R * math.cos(a1), R * math.sin(a1)])
    t0 = np.array([0, -math.sin(a0), math.cos(a0)]) * R; t3 = np.array([0, -math.sin(a1), math.cos(a1)]) * R
    return [tuple(p0), tuple(p0 + k * t0), tuple(p3 - k * t3), tuple(p3)]
def profile(x, R, cuts):
    """Yarım daire (0→π), verilen açı oranlarında parçalanmış."""
    a = [0.0] + [math.pi * c for c in cuts] + [math.pi]
    return [arc(x, R, a[i], a[i + 1]) for i in range(len(a) - 1)]
def split(P, t):
    a, b = g._bez_split(np.array(P, float), t); return [tuple(q) for q in a], [tuple(q) for q in b]
def lopsided(x, R):
    """Yarım daireye yakın TEK bezier, tutamakları dengesiz (hız çok değişken)."""
    return [[(x, R, 0), (x, R, 0.35 * R), (x, 0.9 * R, 2.2 * R), (x, -R, 0)]]
def L(a, b):
    a, b = np.array(a, float), np.array(b, float); return [tuple(a + (b - a) * t) for t in (0, 1/3, 2/3, 1)]
def build(near, far, R2, blend="SHARP"):
    side0 = [{"p": s} for s in near]
    side1 = [{"p": L(near[-1][-1], far[-1][-1])}]
    side2 = [{"p": list(reversed(s))} for s in reversed(far)]
    side3 = [{"p": L(far[0][0], near[0][0])}]
    chain = side0 + side1 + side2 + side3
    return g.Builder().face(chain, [side0, side1, side2, side3], "AUTO", False, blend)
def dev(face, R1, R2, X):
    """Doğru yüzeyden (aynı açıdaki noktaları birleştiren doğrular) en büyük sapma."""
    surf = BRep_Tool.Surface_s(face); worst = 0.0
    for th in np.linspace(0.05, math.pi - 0.05, 15):
        for s in np.linspace(0.1, 0.9, 7):
            R = R1 + (R2 - R1) * s
            pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(X * s, R * math.cos(th), R * math.sin(th)), surf)
            worst = max(worst, pr.LowerDistance() if pr.NbPoints() else 9.0)
    return worst
X, R1, R2 = 6.0, 1.0, 1.6
cases = {
    "2 eşit / 3 eşit olmayan": (profile(0, R1, [0.5]), profile(X, R2, [0.15, 0.4])),
    "1 / 2 eşit olmayan": (profile(0, R1, []), profile(X, R2, [0.2])),
    "3 / 3 farklı yerlerde": (profile(0, R1, [0.1, 0.2]), profile(X, R2, [0.7, 0.85])),
    "3 / 3 yakın köşeler": (profile(0, R1, [0.3, 0.6]), profile(X, R2, [0.35, 0.7])),
    "4 / 2": (profile(0, R1, [0.1, 0.5, 0.9]), profile(X, R2, [0.3])),
}
ok = True
for name, (near, far) in cases.items():
    f, lab = build(near, far, R2)
    d = dev(f, R1, R2, X)
    good = "UYARI" not in lab and d < (0.12 if "yakın" in name else 0.02)
    ok &= good
    print(f"{'tamam' if good else 'HATA '}  {name:26s} sapma {d:.4f} · {lab}")
# tutamakları dengesiz tek bezier iki uçta ters yönlerde: katlanmamalı
a = lopsided(0, R1); b = [[tuple(np.array(q) * np.array([1, -1, 1]) + np.array([X, 0, 0])) for q in reversed(lopsided(0, R1)[0])]]
f, lab = build(a, b, R1)
good = "UYARI" not in lab
ok &= good
print(f"{'tamam' if good else 'HATA '}  dengesiz tutamaklı tek bezier · {lab}")
assert ok, "karşılıklı kenar eşleşmesi beklendiği gibi değil"
print("SONUÇ: karşılıklı kenarlar yay uzunluğuna göre eşleşiyor")
# teğet ağırlıklı sınır yüzeyi (Hermite yolu) de aynı eşleşmeyi kullanmalı
near, far = cases["2 eşit / 3 eşit olmayan"]
side0 = [{"p": s} for s in near]; side1 = [{"p": L(near[-1][-1], far[-1][-1])}]
side2 = [{"p": list(reversed(s))} for s in reversed(far)]; side3 = [{"p": L(far[0][0], near[0][0])}]
f, lab = g.Builder().face(side0 + side1 + side2 + side3, [side0, side1, side2, side3], "AUTO", False, "TANGENT", None, 1.05)
d = dev(f, R1, R2, X)
print(f"sınır yüzeyi (ağırlık 1.05): sapma {d:.4f} · {lab}")
assert "Sınır yüzeyi" in lab and "UYARI" not in lab and d < 0.03
print("SONUÇ: sınır yüzeyi de doğru")
