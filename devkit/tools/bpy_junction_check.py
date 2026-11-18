"""GERÇEK Blender + OCC: kesişim noktasını eğriler üzerinde kaydırma (v0.34.0).

Kullanım: python bpy_junction_check.py <mini_cad'in üst klasörü> [çıktı.png]

Kutu tel kafesinin üst köşesi (3 kenarın birleşimi) üst kenar boyunca kaydırılır;\nyüzeyler yeniden kurulur, gövde kapalı kalır, hacim beklenen yönde değişir.\n"""
import math
import sys

PNG = sys.argv[-1] if sys.argv[-1].endswith(".png") else None
ROOT = sys.argv[-2] if PNG else sys.argv[-1]
sys.path.insert(0, ROOT)
import bpy  # noqa: E402
import addon_utils  # noqa: E402

fails = []


def check(ok, msg):
    print(("  ok  " if ok else "  HATA ") + msg)
    if not ok:
        fails.append(msg)


def _raise(e):
    raise e


addon_utils.enable("mini_cad", default_set=True, handle_error=_raise)
from mini_cad import core, holemath, ui  # noqa: E402

C = bpy.context
sc = C.scene
C.preferences.addons["mini_cad"].preferences.background = False
L, W, H = 1.0, 0.6, 0.4
P = [(0, 0, 0), (L, 0, 0), (L, W, 0), (0, W, 0), (0, 0, H), (L, 0, H), (L, W, H), (0, W, H)]
EDGES = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5),
         (2, 6), (3, 7)]
FACES = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 9, 4, 8), (2, 11, 6, 10), (1, 10, 5, 9),
         (3, 8, 7, 11)]
cu = bpy.data.curves.new("Tel", "CURVE")
cu.dimensions = "3D"
for a, b in EDGES:
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(1)
    for bp, co in zip(sp.bezier_points, (P[a], P[b])):
        bp.co = co
        bp.handle_left_type = bp.handle_right_type = "VECTOR"
wire = bpy.data.objects.new("Tel", cu)
sc.collection.objects.link(wire)
ui.apply_surface(C, "segs", [(wire, i, 0) for i in FACES[0]], new_body=True)
body = sc.minicad_target
for fc in FACES[1:]:
    ui.apply_surface(C, "segs", [(wire, i, 0) for i in fc])
core.rebuild(body)
check("Kapalı katı" in body.cad.status, f"kutu: {body.cad.status}")
eng = next(m for n, m in sys.modules.items()
           if isinstance(getattr(m, "_final", None), dict) and hasattr(m, "_bool_new"))
geo = next(m for n, m in sys.modules.items() if n.endswith(".geometry") and hasattr(m, "apply_holes"))
from mini_cad import draw_junction as dj, slide as sl  # noqa: E402
import numpy as np  # noqa: E402


def vol():
    return geo.volume(eng._final[body.name]["shape"])


V0 = vol()
check(abs(V0 - 0.24) < 1e-6, f"kutu hacmi {V0:.6f}")


class Fake(dj.JunctionMixin):
    sketch = []


f = Fake()
corner = np.array([0.0, 0.0, H])
g = f._jn_gather(C, corner)
check(g is not None and len(g[1]) == 3, f"köşe birleşimi: {0 if g is None else len(g[1])} düğüm")
chains, nodes, passing = g
S = sl.Slider([(c[1], c[2], c[3]) for c in chains], nodes, passing, ext_len=0.5)
# kenar 4-5 (üst ön kenar, +X) boyunca: o zincirin 'f' dalı
bi = next(i for i, (b, j) in enumerate(S.branches)
          if b.kind == "f" and np.allclose(chains[b.owner][1][0][3], [L, 0, H]))
b = S.branches[bi][0]
par, p = b.at(0.2)
out, new = S.apply(bi, par)
check(np.allclose(new, [0.2, 0, H], atol=1e-6), f"yeni nokta {np.round(new, 6)}")
f.jn_drag = {"chains": chains, "slider": S, "out": out}
f.refs = None
f.sk_points = ()
f._status = lambda *a, **k: None
ok = f._jn_commit(C)
check(ok, "geri yazıldı")
sp = wire.data.splines
pts = {i: [tuple(round(v, 6) for v in bp.co) for bp in sp[i].bezier_points] for i in (4, 7, 8)}
check(pts[4][0] == (0.2, 0.0, H) and pts[4][1] == (L, 0.0, H), f"üst ön kenar kısaldı: {pts[4]}")
check(pts[7][1] == (0.2, 0.0, H), f"üst sol kenar ucu taşındı: {pts[7]}")
check(pts[8][1] == (0.2, 0.0, H) and pts[8][0] == (0.0, 0.0, 0.0), f"dikey kenar ucu taşındı: {pts[8]}")
core.rebuild(body)
check("Kapalı katı" in body.cad.status, f"kaydırma sonrası: {body.cad.status}")
V1 = vol()
# sol yüz artık eğik: (0,0,0)-(0.2,0,H)-(0,W,H)-(0,W,0); kesilen kama ≈ 0.2*H*W/2 /… → hacim azalır
check(V1 < V0 - 1e-3, f"hacim azaldı: {V0:.5f} → {V1:.5f}")
# serbest olmayan dalda yay uzunluğu ölçüsü
check(abs(b.length_at(par) - 0.2) < 1e-6, "yay uzunluğu ölçüsü 0.2")

print("SONUÇ:", "tamam" if not fails else f"{len(fails)} hata")
sys.exit(1 if fails else 0)
