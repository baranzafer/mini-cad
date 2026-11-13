"""Yüzeyi Böl (v0.25.0) GERÇEK OCC ile: bölünen eğri yüzeyin iki yarısı yeniden kurulunca
biçim korunuyor mu, yeni dikişte kırılma var mı. OCP 7.9 gerekir:
    /tmp/occ/bin/python devkit/tools/occ_split_check.py <eklenti klasörü>
Model: occ_blend_ring_check.py'deki halka (yuvarlatılmış dikdörtgen → daire); yan yama ortasından
(Coons u = 0.5) kesilir, kesim noktaları gerçek yüzeye izdüşürülüp surfmath.fit_chain ile
eğriye çevrilir (eklentideki akışın aynısı, mesh yerine OCC yüzeyi)."""
import math, os, sys, importlib.util
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/mini_cad")
sys.argv = [sys.argv[0], SRC]
ring = os.path.join(HERE, "occ_blend_ring_check.py")
ns = {"__name__": "ring", "__file__": ring}
exec(compile(open(ring).read().split('if __name__ == "__main__":')[0], ring, "exec"), ns)
g, patches, normal_at = ns["g"], ns["patches"], ns["normal_at"]
spec = importlib.util.spec_from_file_location("surfmath", os.path.join(SRC, "surfmath.py"))
sm = importlib.util.module_from_spec(spec); spec.loader.exec_module(sm)
from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf
from OCP.BRep import BRep_Tool
from OCP.BRepTools import BRepTools
from OCP.gp import gp_Pnt

def build(ps, blend):
    for p in ps: p["blend"] = blend
    b = g.Builder(); order = g.blend_order(ps)
    if blend != "SHARP": g.blend_prepare(b, order)
    return {p["idx"]: b.face(p["chain"], p["sides"], p["method"], False,
                             **({"blend": blend} if blend != "SHARP" else {})) for p in order}

ok = True
for blend in ("SHARP", "TANGENT"):
    orig = build(patches, blend)
    P = patches[1]
    surf = BRep_Tool.Surface_s(orig[1][0])
    def onface(q):
        pr = GeomAPI_ProjectPointOnSurf(gp_Pnt(*map(float, q)), surf)
        r = pr.NearestPoint(); return np.array([r.X(), r.Y(), r.Z()]), pr.LowerDistance()
    sides = [[sm.cubic(s["p"])] for s in P["chain"]]
    pts = [sm.coons(sides, 0.5, v) for v in np.linspace(0, 1, 33)]
    pts = [pts[0]] + [onface(q)[0] for q in pts[1:-1]] + [pts[-1]]
    cut = sm.fit_chain(pts, 5e-4)
    bL, bR = sm.split_bez(sides[0][0], 0.5); tL, tR = sm.split_bez(sides[2][0], 0.5)
    sg = lambda P_: {"p": [tuple(x) for x in P_]}
    cutF = [sg(c) for c in cut]; cutR = [sg(c[::-1]) for c in cut[::-1]]
    left = [sg(bL)] + cutF + [sg(tR), P["chain"][3]]
    right = [sg(bR), P["chain"][1], sg(tL)] + cutR
    new = [dict(p) for p in patches if p["idx"] != 1]
    new += [{"idx": 100, "name": "sol", "chain": left, "sides": [[left[0]], cutF, [left[-2]], [left[-1]]], "method": "AUTO"},
            {"idx": 101, "name": "sağ", "chain": right, "sides": [[right[0]], [right[1]], [right[2]], cutR], "method": "AUTO"}]
    b2 = build(new, blend)
    fa, fb = b2[100][0], b2[101][0]
    kink = max(math.degrees(math.acos(min(1, abs(float(np.dot(na, nb)) / np.linalg.norm(na) / np.linalg.norm(nb)))))
               for c in cut for t in np.linspace(0.05, 0.95, 9)
               for na, nb in [(normal_at(fa, sm.bez(c, t)), normal_at(fb, sm.bez(c, t)))] if na is not None and nb is not None)
    dev = 0.0
    for f in (fa, fb):
        s2 = BRep_Tool.Surface_s(f); u0, u1, v0, v1 = BRepTools.UVBounds_s(f)
        for a in np.linspace(0.1, 0.9, 7):
            for c_ in np.linspace(0.1, 0.9, 7):
                p_ = s2.Value(u0 + (u1 - u0) * a, v0 + (v1 - v0) * c_)
                dev = max(dev, onface((p_.X(), p_.Y(), p_.Z()))[1])
    print(f"[{blend}] kesim {len(cut)} segment · yeni dikişte kırılma {kink:.2f}° · orijinal yüzeyden "
          f"sapma {dev:.4f} (yama boyu ~3) · {b2[100][1]}")
    ok &= kink < 0.5 and dev < (0.03 if blend == "SHARP" else 0.01)
assert ok, "bölünen yüzey biçimi korumadı"
print("SONUÇ: bölme biçimi koruyor")
