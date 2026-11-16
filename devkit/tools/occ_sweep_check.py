"""Profil Süpürme (v0.26.0) — GERÇEK OCC. OCP 7.9 gerekir:
    /tmp/occ/bin/python devkit/tools/occ_sweep_check.py <eklenti klasörü> [kayıt raporu]
  1) 2×2×2 kutunun üst ön kenarı boyunca 45° pah üçgeni (kapalı profil, Yolun başına):
     çıkan hacim d² (uzatılmış uçlar kenarı baştan sona keser)
  2) Aynı pah, AÇIK profil (yalnız pah çizgisi) + "köşeden kapat": aynı hacim
  3) Üst yüzün 4 kenarı (kapalı, keskin köşeli yol) boyunca pah: 4 kenar pahlanır
  4) Yay profili (çeyrek daire, köşeden kapat) → içbükey değil, dışbükey yuvarlatma: hacim
     d²(1 − π/4) · L
  6) Gövde kenarı olmayan yol (üst yüzde çizgi) boyunca yarım daire oluk: π r²/2 · 2
  5) (rapor verilirse) kullanıcı modeli: fillet'in kuramadığı Kesim 3'ün 14 kenarlık kesit
     döngüsü boyunca 0.05 pah — fillet yerine profil süpürme ile
"""
import math
import os
import sys
import tempfile
import time

import numpy as np

SRC = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/mini_cad")
pkg = tempfile.mkdtemp()
os.makedirs(os.path.join(pkg, "mc"))
open(os.path.join(pkg, "mc", "__init__.py"), "w").close()
for f in ("geometry.py", "errors.py", "sweep.py"):
    os.symlink(os.path.join(SRC, f), os.path.join(pkg, "mc", f))
sys.path.insert(0, pkg)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mc import geometry as g  # noqa: E402
from mc import sweep as sw  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402
from OCP.gp import gp_Pnt  # noqa: E402

AX = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


def cut(shape, pieces, segs, d=None, **params):
    prof = {"segs": segs, "origin": (0, 0, 0), "axes": AX}
    tools, info = sw.make_tool(shape, pieces, prof, params, 1e-4)
    out, ok, msg = g.apply_boolean(shape, tools, "CUT", 0.0, "SECTION", 1e-4)
    dv = g.volume(shape) - g.volume(out)
    return ok, msg, info, dv, out


def L(a, b):
    return [tuple(map(float, a)), tuple(map(float, b))]


ok = True
box = BRepPrimAPI_MakeBox(gp_Pnt(0, 0, 0), gp_Pnt(2, 2, 2)).Shape()
edge = [("bez", L((0, 0, 2), (2, 0, 2)))]
d = 0.3
# profil XY düzleminde: orijin = kenar, +Y = dışarı (açıortay); yüzler -Y'nin ±45° yanında
a1 = (-d * math.sin(math.pi / 4), -d * math.cos(math.pi / 4), 0)
a2 = (d * math.sin(math.pi / 4), -d * math.cos(math.pi / 4), 0)
tri = [L((0, 0, 0), a1), L(a1, a2), L(a2, (0, 0, 0))]
r = cut(box, edge, tri)
print("[1 kapalı pah]", r[0], r[1], "·", r[2], f"· hacim {r[3]:.5f} (beklenen {d * d / 2 * 2:.5f})")
# pah üçgeninin bacakları d → alan d²/2, kenar 2 → d²
ok &= r[0] and abs(r[3] - d * d) < 1e-3

r = cut(box, edge, [L(a1, a2)], close="ORIGIN")
print("[2 açık pah + köşeden kapat]", r[0], f"hacim {r[3]:.5f}")
ok &= r[0] and abs(r[3] - d * d) < 1e-3

loop = [("bez", L((0, 0, 2), (2, 0, 2))), ("bez", L((2, 0, 2), (2, 2, 2))),
        ("bez", L((2, 2, 2), (0, 2, 2))), ("bez", L((0, 2, 2), (0, 0, 2)))]
r = cut(box, loop, tri)
print("[3 kapalı köşeli yol]", r[0], r[1], "·", r[2], f"· hacim {r[3]:.5f}")
# 4 kenar pahı: 4·(d²/2)·2 − köşe çakışmaları (≈ 4 · d³/3) → en az 3·d² olmalı
ok &= r[0] and 3.0 * d * d < r[3] < 4.0 * d * d + 1e-3

# 4) çeyrek daire yay: merkezi gövdenin içinde (−Y yönünde d·√2), uçları yüzlerde
k = 0.5522847498
c = (0.0, -d * math.sqrt(2), 0.0)
p1 = (c[0] - d * math.sin(math.pi / 4), c[1] + d * math.cos(math.pi / 4), 0)
p2 = (c[0] + d * math.sin(math.pi / 4), c[1] + d * math.cos(math.pi / 4), 0)
# p1 → p2 çeyrek yay (merkez c), bezier tutamaçları
t1 = np.array([math.cos(math.pi / 4), math.sin(math.pi / 4), 0])
t2 = np.array([math.cos(math.pi / 4), -math.sin(math.pi / 4), 0])
arc = [[p1, tuple(np.array(p1) + t1 * d * k), tuple(np.array(p2) - t2 * d * k), p2]]
r = cut(box, edge, arc, close="ORIGIN")
exp = d * d * (1 - math.pi / 4) * 2
print("[4 yay profili = dışbükey yuvarlatma]", r[0], f"hacim {r[3]:.5f} (beklenen {exp:.5f})")
ok &= r[0] and abs(r[3] - exp) < 2e-3

# 6) gövde kenarı OLMAYAN yol: üst yüzde x boyunca (gövdenin dışından dışına) çizgi, yarım
#    daire oluk (açık yay, düz çizgiyle kapat) → hacim π r²/2 · 2
rr = 0.2
q = [(-rr, 0, 0), (-rr, -rr * k, 0), (-rr * k, -rr, 0), (0, -rr, 0)]
q2 = [(0, -rr, 0), (rr * k, -rr, 0), (rr, -rr * k, 0), (rr, 0, 0)]
r = cut(box, [("bez", L((-0.5, 1, 2), (2.5, 1, 2)))], [q, q2], close="CHORD")
exp = math.pi * rr * rr / 2 * 2
print("[6 yüzeyde çizgi boyunca oluk]", r[0], r[2], f"· hacim {r[3]:.5f} (beklenen {exp:.5f})")
ok &= r[0] and abs(r[3] - exp) < 2e-3

if len(sys.argv) > 2:
    from report_model import build_body, load_report, samples
    rep = load_report(sys.argv[2])
    body, _, used = build_body(g, rep, "CAD_Govde")
    tool, _, _ = build_body(g, rep, "CAD_Govde.001")
    loops = [[used[("CAD_TelKafes", s, kk)] for kk in range(10)] for s in (0, 1)]
    fil, res = g.apply_features(body, [{"kind": "FILLET", "size": 0.5,
                                        "polys": [samples(p) for p in lp]} for lp in loops],
                                [], 1e-3)
    c0, bok, _ = g.apply_boolean(fil, [tool], "CUT", 0.0, "SECTION", 1e-3)
    es = g.boolean_new_edges(c0, fil, [tool], "SECTION", 1e-3)
    pieces = [("pts", g.edge_dense(e, 1e-3)) for e in es]
    dd = 0.05
    b1 = (-dd * math.sin(math.pi / 4), -dd * math.cos(math.pi / 4), 0)
    b2 = (dd * math.sin(math.pi / 4), -dd * math.cos(math.pi / 4), 0)
    t = time.time()
    try:
        r = cut(c0, pieces, [L(b1, b2)], close="ORIGIN")
        print(f"[5 kullanıcı modeli: 14 kenarlık döngüye 0.05 pah] {r[0]} {r[1]} · {r[2]} · "
              f"hacim {r[3]:.5f} · {time.time() - t:.1f} sn")
        ok &= r[0] and r[3] > 0
    except Exception as e:
        print("[5 kullanıcı modeli] HATA", e)
        ok = False

assert ok, "süpürme beklenen sonucu vermedi"
print("SONUÇ: profil süpürme çalışıyor")
