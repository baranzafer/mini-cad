# v0.19.0: solver yeni denklemler (bpy'siz): SYMLINE, PTLINE, LINEDIST, RADIUSN, EQDIST
exec(open("t.py").read().split("def seg(")[0])
import math, importlib
import numpy as np
solver = importlib.import_module("mini_cad.solver")

def check(cond, msg):
    print(("  tamam  " if cond else "  HATA   ") + msg)
    if not cond:
        raise SystemExit(1)

A = lambda *v: np.array(v, dtype=float)
print("Simetrik (çizgi): doğru sabit, noktalar uyar")
X0 = np.array([A(-1, 1, 0), A(1.5, 1.2, 0), A(0, -1, 0), A(0, 3, 0)])
w = [1, 1, 1e6, 1e6]
X, ok, per = solver.solve(X0, [("SYMLINE", (0, 1, 2, 3), {})], w)
check(ok and abs(X[0][0] + X[1][0]) < 1e-5 and abs(X[0][1] - X[1][1]) < 1e-5, f"x=0'a göre simetrik: {np.round(X[:2], 5).tolist()}")
print("Nokta-doğru / doğru-doğru uzaklığı")
X0 = np.array([A(1, 1, 0), A(0, 0, 0), A(4, 0, 0)])
X, ok, _ = solver.solve(X0, [("PTLINE", (0, 1, 2), {"value": 2.5})], [1, 1e6, 1e6])
check(ok and abs(X[0][1] - 2.5) < 1e-5, f"nokta y=2.5: {X[0]}")
check(abs(solver.measure("PTLINE", X0) - 1) < 1e-12, "ölçü: 1")
X0 = np.array([A(0, 1, 0), A(3, 1.3, 0), A(0, 0, 0), A(4, 0, 0)])
X, ok, _ = solver.solve(X0, [("LINEDIST", (0, 1, 2, 3), {"value": 2.0})], [1, 1, 1e6, 1e6])
check(ok and abs(X[0][1] - 2) < 1e-5 and abs(X[1][1] - 2) < 1e-5, "iki uç da 2 uzaklıkta: paralel")
check(abs(solver.measure("LINEDIST", X0) - 1.15) < 1e-12, "ölçü: uçların ortalaması")
print("Yay merkezi (sanal) ile yarıçap / eş uzaklık")
X0 = np.array([A(0, 0, 0), A(1, 0, 0), A(0, 1, 0), A(-1, 0, 0)])
X, ok, _ = solver.solve(X0, [("RADIUSN", (0, 1, 2, 3), {"value": 2.0})], [1e6, 1, 1, 1])
check(ok and np.allclose(np.linalg.norm(X[1:], axis=1), 2.0), f"noktalar R=2'de: {np.round(np.linalg.norm(X[1:], axis=1), 7)}")
X0 = np.array([A(0.3, 0, 0), A(1, 0, 0), A(0, 1, 0), A(-1, 0, 0)])
X, ok, _ = solver.solve(X0, [("EQDIST", (0, 1, 2, 3), {})], [1, 1e6, 1e6, 1e6])
check(ok and np.allclose(X[0], 0, atol=1e-5), f"eş uzaklık: merkez çembere oturdu {np.round(X[0], 7)}")
print("t54 bitti")
