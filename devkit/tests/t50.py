# v0.17.0: sketchmath dönüşümleri (bpy'siz): taşı / döndür / ölçekle / ayna / desen / esnet
exec(open("t.py").read().split("def seg(")[0])
import math, importlib
import numpy as np
sm = importlib.import_module("mini_cad.sketchmath")
dm = importlib.import_module("mini_cad.drawmath")

def check(cond, msg):
    print(("  tamam  " if cond else "  HATA   ") + msg)
    if not cond:
        raise SystemExit(1)

A = np.array
XY = dm.Plane.axis("XY", (0, 0, 0))
circ = {"segs": dm.circle(A([2., 0, 0]), 1.0, XY), "cyclic": True, "node_ids": {5: "x"}, "start_tan": None}
for sg in circ["segs"]:
    sg["grp"] = 9
ln = {"segs": [dict(dm.line_seg(A([0., 0, 0]), A([1., 0, 0])), grp=1, auto=[("AXIS", 0), ("DIST", 1.0)])],
      "cyclic": False, "node_ids": {0: ("Tel", 0, 0)}, "start_tan": None}

print("Döndür / ayna / ölçek: yay yay kalır, yarıçap doğru")
r = sm.xform_stroke(circ, sm.T_rotate(A([0., 0, 0]), A([0., 0, 1]), math.pi / 2))
arc = dm.arc_of_bezier([A(q) for q in r["segs"][0]["p"]])
check(arc is not None and np.allclose(arc[0], (0, 2, 0)) and abs(arc[1] - 1) < 1e-9, "döndürülen daire: merkez (0,2), R 1")
check(r["node_ids"] == {} and r["start_tan"] is None, "taşınan çizginin dış bağlantıları düştü")
m = sm.xform_stroke(circ, sm.T_mirror(A([0., -1, 0]), A([0., 1, 0]), A([0., 0, 1])))
arc = dm.arc_of_bezier([A(q) for q in m["segs"][1]["p"]])
check(arc is not None and np.allclose(arc[0], (-2, 0, 0)), "aynalanan daire merkez (-2,0)")
s = sm.xform_stroke(circ, sm.T_scale(A([0., 0, 0]), 3.0))
arc = dm.arc_of_bezier([A(q) for q in s["segs"][2]["p"]])
check(abs(arc[1] - 3) < 1e-9 and np.allclose(arc[0], (6, 0, 0)), "3 kat: merkez (6,0), R 3")
print("Kopyada gruplar yenilenir, oto kısıtlar korunur (Bitir ayıklar)")
c = sm.xform_stroke(circ, sm.T_move(A([1., 0, 0])), copy_=True)
gs = {sg["grp"] for sg in c["segs"]}
check(len(gs) == 1 and 9 not in gs, f"yeni tek grup: {gs}")
c2 = sm.xform_stroke(ln, sm.T_move(A([0., 1, 0])))
check(c2["segs"][0]["auto"] == [("AXIS", 0), ("DIST", 1.0)], "oto kısıtlar korundu")
print("Desenler")
fns = sm.rect_pattern(A([2., 0, 0]), 3, A([0., 1, 0]), 2)
check(len(fns) == 5, "3×2 → 5 kopya")
fns = sm.circ_pattern(A([0., 0, 0]), A([0., 0, 1]), 3, 90.0)
pts = [np.round(f(A([1., 0, 0])), 6).tolist() for f in fns]
r2 = math.sqrt(0.5)
check(np.allclose(pts, [[r2, r2, 0], [0, 1, 0]]), f"90° içine 3 adet, uçlar dahil (0°, 45°, 90°): {pts}")
pts = [np.round(f(A([1., 0, 0])), 6).tolist() for f in sm.circ_pattern(A([0., 0, 0]), A([0., 0, 1]), 4)]
check(np.allclose(pts, [[0, 1, 0], [-1, 0, 0], [0, -1, 0]]), "tam tur 4 adet: 90° aralık")
check(len(sm.circ_pattern(A([0., 0, 0]), A([0., 0, 1]), 1)) == 0, "1 adet: kopya yok")
new = sm.apply_many([ln], [0], sm.rect_pattern(A([0., 1, 0]), 3))
check(len(new) == 3 and new[0]["node_ids"] == {0: ("Tel", 0, 0)}, "desen: asıl çizgi ve bağlantısı korunur")
print("Esnet")
L = {"segs": [dm.line_seg(A([0., 0, 0]), A([1., 0, 0])), dm.tangent_arc(A([1., 0, 0]), A([1., 0, 0]), A([2., 1, 0]))["segs"][0]],
     "cyclic": False, "node_ids": {}, "start_tan": None}
L["segs"][1]["kind"] = "arc"
out = sm.stretch([L], {(0, 2)}, A([0., 1, 0]))
P = out[0]["segs"][1]["p"]
check(np.allclose(P[3], (2, 2, 0)) and np.allclose(P[0], (1, 0, 0)), "son nokta taşındı, birleşim yerinde")
check(np.allclose(np.asarray(P[2]) - np.asarray(L["segs"][1]["p"][2]), (0, 1, 0)), "bağlı tutamaç noktayla kaydı")
out = sm.stretch([L], {(0, 0), (0, 1), (0, 2)}, A([5., 0, 0]))
check(np.allclose(out[0]["segs"][0]["p"][0], (5, 0, 0)) and np.allclose(out[0]["segs"][1]["p"][3], (7, 1, 0)), "bütün noktalar: olduğu gibi taşındı")
dl = {"segs": [dict(dm.line_seg(A([0., 0, 0]), A([1., 0, 0])), auto=[("DIST", 1.0), ("AXIS", 0)])], "cyclic": False, "node_ids": {}, "start_tan": None}
out = sm.stretch([dl], {(0, 1)}, A([1., 0, 0]))
check(out[0]["segs"][0]["auto"] == [("AXIS", 0)], "esnetilen doğrunun uzunluk kısıtı düştü")
print("t50 bitti")
