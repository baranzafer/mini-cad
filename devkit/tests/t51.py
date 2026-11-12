# v0.18.0: shapemath (bpy'siz): dikdörtgen çeşitleri, çokgen, kanallar, yay kanal, elips,
# üç doğruya teğet daire, geometri yansıtma
exec(open("t.py").read().split("def seg(")[0])
import math, importlib
import numpy as np
shm = importlib.import_module("mini_cad.shapemath")
dm = importlib.import_module("mini_cad.drawmath")
sm = importlib.import_module("mini_cad.sketchmath")

def check(cond, msg):
    print(("  tamam  " if cond else "  HATA   ") + msg)
    if not cond:
        raise SystemExit(1)

A = lambda *v: np.array(v, dtype=float)
XY = dm.Plane.axis("XY", (0, 0, 0))
def closed_ok(segs):
    return np.allclose(segs[-1]["p"][3], segs[0]["p"][0]) and all(
        np.allclose(segs[i]["p"][3], segs[i + 1]["p"][0]) for i in range(len(segs) - 1))
def corners(segs):
    return sorted(tuple(np.round(sg["p"][0][:2], 6)) for sg in segs)

print("Dikdörtgenler")
r = shm.rect3(A(0, 0, 0), A(2, 2, 0), A(1, 4, 0), XY)
L = [np.linalg.norm(np.asarray(s["p"][3]) - np.asarray(s["p"][0])) for s in r]
check(closed_ok(r) and np.allclose(L, [math.sqrt(8), 1.5 * math.sqrt(2), math.sqrt(8), 1.5 * math.sqrt(2)]), f"3 nokta (döndürülmüş): kenarlar {np.round(L, 4)}")
check(corners(shm.rect_center(A(1, 1, 0), A(3, 2, 0), XY)) == [(-1, 0), (-1, 2), (3, 0), (3, 2)], "merkezden")
check(corners(shm.rect3_center(A(0, 0, 0), A(2, 0, 0), A(5, 1, 0), XY)) == [(-2, -1), (-2, 1), (2, -1), (2, 1)], "3 nokta merkezden")
print("Çokgen")
p = shm.polygon(A(0, 0, 0), A(1, 0, 0), 6, XY, True)
check(len(p) == 6 and closed_ok(p) and np.allclose(p[0]["p"][0], (1, 0, 0)), "iç teğet: köşe imleçte")
p = shm.polygon(A(0, 0, 0), A(1, 0, 0), 4, XY, False)
mids = [0.5 * (np.asarray(s["p"][0]) + np.asarray(s["p"][3])) for s in p]
check(any(np.allclose(m, (1, 0, 0)) for m in mids), "dış teğet: kenar ortası imleçte")
print("Kanallar")
s = shm.slot_cc(A(0, 0, 0), A(4, 0, 0), 1.0, XY)
P = np.vstack([dm.sample(sg, 9) for sg in s])
check(closed_ok(s) and abs(P[:, 0].min() + 1) < 1e-3 and abs(P[:, 0].max() - 5) < 1e-3 and abs(P[:, 1].max() - 1) < 1e-9, "merkezden merkeze: x -1..5, y ±1")
check(len(sm.entities({"segs": s, "cyclic": True})) == 4, "4 nesne: 2 doğru + 2 yay")
s = shm.slot_overall(A(0, 0, 0), A(6, 0, 0), 1.0, XY)
P = np.vstack([dm.sample(sg, 9) for sg in s])
check(abs(P[:, 0].min()) < 1e-3 and abs(P[:, 0].max() - 6) < 1e-3, "toplam boy: x 0..6")
check(shm.slot_overall(A(0, 0, 0), A(1, 0, 0), 1.0, XY) is None, "boy < genişlik: yok")
s = shm.slot_center(A(0, 0, 0), A(2, 0, 0), 0.5, XY)
P = np.vstack([dm.sample(sg, 9) for sg in s])
check(abs(P[:, 0].min() + 2.5) < 1e-3 and abs(P[:, 0].max() - 2.5) < 1e-3, "merkez noktalı: simetrik ±2.5")
a = shm.arc_slot(A(3, 0, 0), A(-3, 0, 0), A(0, 3, 0), 0.5, XY)
P = np.vstack([dm.sample(sg, 17) for sg in a])
R = np.linalg.norm(P[:, :2], axis=1)
check(closed_ok(a) and R.max() <= 3.5 + 1e-3 and R.min() >= 2.5 - 1e-3, f"yay kanal: R 2.5..3.5 ({R.min():.4f}..{R.max():.4f})")
print("Elips")
e = shm.ellipse(A(0, 0, 0), A(2, 0, 0), A(0.3, 1, 0), XY)
P = np.vstack([dm.sample(sg, 17) for sg in e])
val = (P[:, 0] / 2) ** 2 + P[:, 1] ** 2
check(closed_ok(e) and abs(val - 1).max() < 3e-3, f"x²/4 + y² = 1 (sapma {abs(val - 1).max():.2e})")
print("Teğet daire")
lines = [(A(0, 0, 0), A(3, 0, 0)), (A(0, 0, 0), A(0, 4, 0)), (A(3, 0, 0), A(0, 4, 0))]
c, r = shm.tangent_circle_3lines(lines, XY)
check(np.allclose(c, (1, 1, 0)) and abs(r - 1) < 1e-9, f"3-4-5 üçgeni: merkez {np.round(c, 6)}, r {r:.6f}")
check(shm.tangent_circle_3lines([(A(0, 0, 0), A(1, 0, 0)), (A(0, 1, 0), A(1, 1, 0)), (A(0, 2, 0), A(1, 2, 0))], XY) is None, "paralel doğrular: yok")
print("Yansıtma")
pl = dm.Plane.axis("XY", (0, 0, 0))
t = np.linspace(0, 2 * np.pi, 65)
circle3d = np.c_[np.cos(t) + 2, np.sin(t), np.full_like(t, 5.0)]
segs, closed = shm.segs_from_poly(shm.project_poly(circle3d, pl))
arc = dm.arc_of_bezier(segs[0]["p"])
check(closed and arc is not None and np.allclose(arc[0], (2, 0, 0)) and abs(arc[1] - 1) < 1e-6, "daire: z=0'a izdüştü, kapalı yay")
segs, closed = shm.segs_from_poly(shm.project_poly(np.array([[0, 0, 3], [2, 1, 7]], float), pl))
check(segs[0]["kind"] == "line" and np.allclose(segs[0]["p"][3], (2, 1, 0)), "doğru")
ta = np.linspace(0, np.pi / 2, 33)
segs, closed = shm.segs_from_poly(shm.project_poly(np.c_[np.cos(ta), np.sin(ta), np.full_like(ta, 2.0)], pl))
check(not closed and dm.arc_of_bezier(segs[0]["p"]) is not None, "yay")
q = shm.project_bezier([A(0, 0, 1), A(1, 2, 3), A(2, -1, 2), A(3, 0, 9)], pl)
check(all(abs(float(x[2])) < 1e-12 for x in q), "bezier kontrol noktaları izdüştü")
print("t51 bitti")
