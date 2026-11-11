# v0.16.0: sketchmath (Kırp / Uzat / Böl / Ötele / Köşe yuvarla / Pah) matematiği, bpy'siz
exec(open("t.py").read().split("def seg(")[0])
import math, importlib
import numpy as np
sm = importlib.import_module("mini_cad.sketchmath")
dm = importlib.import_module("mini_cad.drawmath")
V = lambda *a: np.array(a, float)
XY = dm.Plane.axis("XY", (0, 0, 0))
def rect_st():
    segs = dm.rectangle(V(0,0,0), V(4,2,0), XY)
    return {"segs": segs, "cyclic": True, "node_ids": {}, "start_tan": None}
def line_st(a, b, g):
    s = dm.line_seg(V(*a), V(*b)); s["grp"] = g
    return {"segs": [s], "cyclic": False, "node_ids": {}, "start_tan": None}
sk = [rect_st(), line_st((2,-1,0), (2,3,0), 1)]
print("varlıklar dikdörtgen:", sm.entities(sk[0]))
# dikdörtgenin alt kenarı (seg 0) dikey doğruyla x=2'de kesişir
cuts = sm.entity_cuts(sk, 0, 0, 1)
print("alt kenar kesişimleri:", cuts)
assert len(cuts) == 1 and abs(cuts[0] - 0.5) < 1e-9
sk2 = sm.trim(sk, 0, 0, 1, 0.25, cuts)       # sol yarıyı kırp
st = sk2[0]
print("kırpılınca:", len(sk2), "çizgi · kapalı:", st["cyclic"], "· segment:", len(st["segs"]))
pts = [tuple(np.round(sg["p"][0], 6)) for sg in st["segs"]] + [tuple(np.round(st["segs"][-1]["p"][3], 6))]
print("  düğümler:", pts)
assert not st["cyclic"] and np.allclose(st["segs"][0]["p"][0], (2,0,0)) and np.allclose(st["segs"][-1]["p"][3], (0,0,0))
# dikey doğrunun kesişimleri: y=0 ve y=2
c2 = sm.entity_cuts(sk, 1, 0, 1)
print("dikey doğru kesişimleri:", np.round(c2, 6))
assert len(c2) == 2
sk3 = sm.trim(sk, 1, 0, 1, 0.1, c2)          # alttaki taşan kısmı kırp
print("taşan kırpıldı:", [np.round(sg["p"][0],3).tolist() for sg in sk3[1]["segs"]])
assert np.allclose(sk3[1]["segs"][0]["p"][0], (2,0,0))
# uzat: kısa doğru dikdörtgenin içinde, sağa uzat
sk4 = [rect_st(), line_st((1,1,0), (2,1,0), 7)]
new, why = sm.extend(sk4, 1, 1)
print("uzat:", why or np.round(new[1]["segs"][0]["p"][3], 6))
assert np.allclose(new[1]["segs"][0]["p"][3], (4,1,0))
new, why = sm.extend(sk4, 1, 0)
assert np.allclose(new[1]["segs"][0]["p"][0], (0,1,0)), new[1]["segs"][0]["p"][0]
print("uzat (baş): ok")
# böl
sp = sm.split(sk, 1, 0, 1, c2[0])
print("böl: segment", len(sp[1]["segs"]), "varlık", sm.entities(sp[1]))
assert len(sm.entities(sp[1])) == 2
# daire kırp
circ = {"segs": dm.circle(V(0,0,0), 1.0, XY), "cyclic": True, "node_ids": {}, "start_tan": None}
sk5 = [circ, line_st((-2,0,0), (2,0,0), 3)]
print("daire varlıkları:", sm.entities(circ))
cc = sm.entity_cuts(sk5, 0, 0, 4)
print("daire kesişimleri:", np.round(cc, 6))
r = sm.trim(sk5, 0, 0, 4, 1.0, cc)            # üst yarıyı kırp (u=1: 90°)
arc = r[0]
r3 = sm.trim(sk5, 0, 0, 4, 3.0, cc)           # alt yarıyı kırp (u=3: 270°, başlangıçtan geçmez)
ys3 = [sm.seg_point(sg, 0.5)[1] for sg in r3[0]["segs"]]
print("alt yarı kırpıldı: üst kalır", round(min(ys3), 4))
assert min(ys3) > 0
print("daire kırpıldı: kapalı", arc["cyclic"], "segment", len(arc["segs"]), "uçlar", np.round(arc["segs"][0]["p"][0],3), np.round(arc["segs"][-1]["p"][3],3))
ys = [sm.seg_point(sg, 0.5)[1] for sg in arc["segs"]]
assert not arc["cyclic"] and max(ys) < 1e-9, ys
assert len(sm.split(sk5, 0, 0, 4, 1.0, cc)[0]["segs"]) >= 2 and len(sm.entities(sm.split(sk5, 0, 0, 4, 1.0, cc)[0])) == 2
# ötele: dikdörtgen içe/dışa
o, why = sm.offset(rect_st(), 0.5, V(0,0,1))
P = np.array([sg["p"][0] for sg in o["segs"]])
print("ötele 0.5:", np.round(P, 3).tolist())
d, q = sm.offset_distance(rect_st(), V(2,-0.5,0), V(0,0,1))
print("imleç uzaklığı (dışarıda):", round(d, 4))
o2, _ = sm.offset(rect_st(), d, V(0,0,1))
P2 = np.array([sg["p"][0] for sg in o2["segs"]])
print("dışa ötele:", np.round(P2, 3).tolist())
assert np.allclose(sorted(P2[:, 0]), [-0.5, -0.5, 4.5, 4.5])
# daire ötele
oc, _ = sm.offset(circ, -0.25, V(0,0,1))
R = [np.linalg.norm(sm.seg_point(sg, t)) for sg in oc["segs"] for t in (0, .3, .7)]
print("daire ötele R:", round(min(R),5), round(max(R),5))
# köşe yuvarla
st = rect_st()
print("köşeler:", sm.corners(st))
res, why = sm.fillet_at(st, 1, 0.5)
print("yuvarla:", why or ("merkez", np.round(res["center"], 4)))
assert np.allclose(res["center"], (3.5, 0.5, 0))
f = sm.apply_corner([st], 0, 1, res)[0]
print("  segment:", len(f["segs"]), "kapalı", f["cyclic"], "köşeler kaldı:", sm.corners(f))
res0, why = sm.fillet_at(st, 0, 0.5)
f0 = sm.apply_corner([st], 0, 0, res0)[0]
print("  0. düğüm:", len(f0["segs"]), "köşeler:", sm.corners(f0), "kapalı", f0["cyclic"])
assert len(sm.corners(f0)) == 3 and len(sm.corners(f)) == 3
# yay-doğru köşesi
tarc = dm.tangent_arc(V(0,0,0), V(1,0,0), V(1,1,0))["segs"]
lin = dm.line_seg(V(1,1,0), V(2,1,0))
mix = {"segs": [dm.line_seg(V(-1,0,0), V(0,0,0))] + tarc + [lin], "cyclic": False, "node_ids": {}, "start_tan": None}
for sg in tarc: sg["grp"] = 5
print("yay-doğru köşeleri:", sm.corners(mix))
j = sm.corners(mix)[0]
res, why = sm.fillet_at(mix, j, 0.2)
print("yay-doğru yuvarla:", why or np.round(res["center"], 4))
ch, why = sm.chamfer_at(st, 1, 0.5, 0.25)
c = sm.apply_corner([st], 0, 1, ch)[0]
print("pah:", why or [np.round(sg["p"][0], 3).tolist() for sg in c["segs"]])
# birleşik uçlar
a = line_st((0,0,0), (1,0,0), 1); b = line_st((1,0,0), (1,1,0), 2)
jn, kk, jj = sm.join_ends([a, b], 0, 1, 1, 0)
print("birleştir:", len(jn), "çizgi, düğüm", jj, "köşeler", sm.corners(jn[kk]))
print("HEPSİ TAMAM")
