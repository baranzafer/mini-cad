"""Fillet / boolean başarısızlık teşhisi (v0.26.0) — GERÇEK OCC. OCP 7.9 gerekir:
    /tmp/occ/bin/python devkit/tools/occ_diag_check.py <eklenti klasörü> [kayıt raporu]
Kullanıcı isteği: hata verirken sebebin modelden mi (tel kafes / seçim), geometriden mi
(ölçü sığmıyor, hiçbir çekirdek yapamaz) yoksa OCC çekirdeğinden mi geldiği söylensin.
  1) İnce plaka (yükseklik 0.1) üst kenarına 0.3 fillet  → GEO "yer yok", en fazla ≈0.1
  2) İki kutunun birleşiminde üst yüzü bölen düz kenar  → MODEL "yan yüzler teğet"
  3) Normal kutu kenarına 0.1 fillet                    → başarılı (teşhis karışmamalı)
  4) (rapor verilirse) kullanıcı modeli: 0.5 fillet'li gövdeyi kesen Kesim 3'ün 14 yeni kenarı
     0.2 ile yuvarlanamıyor; 0.02 ile de olmuyor → KERNEL, "ölçüyü küçült" DEMEMELİ, işlem
     sırası ipucu verilmeli
"""
import os
import sys
import tempfile
import time

import numpy as np

SRC = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/mini_cad")
pkg = tempfile.mkdtemp()
os.makedirs(os.path.join(pkg, "mc"))
open(os.path.join(pkg, "mc", "__init__.py"), "w").close()
for f in ("geometry.py", "errors.py"):
    os.symlink(os.path.join(SRC, f), os.path.join(pkg, "mc", f))
sys.path.insert(0, pkg)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mc import geometry as g  # noqa: E402
from OCP.BRepAlgoAPI import BRepAlgoAPI_Fuse  # noqa: E402
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: E402
from OCP.gp import gp_Pnt  # noqa: E402


def box(x0, y0, z0, x1, y1, z1):
    return BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), gp_Pnt(x1, y1, z1)).Shape()


def line(a, b, n=64):
    a, b = np.array(a, float), np.array(b, float)
    return a + (b - a) * np.linspace(0, 1, n)[:, None]


def fillet(shape, poly, r, kind="FILLET"):
    out, res = g.apply_features(shape, [{"kind": kind, "size": r, "polys": [poly]}], [], 1e-4)
    return res[0]


ok = True
# 1) ince plaka: üst ön kenar (y=0, z=0.1), yan yüz yalnızca 0.1 yüksek
plate = box(0, 0, 0, 2, 2, 0.1)
fok, msg = fillet(plate, line((0, 0, 0.1), (2, 0, 0.1)), 0.3)
print("[ince plaka 0.3]", fok, msg)
ok &= (not fok) and "Geometrik olarak mümkün değil" in msg and "yer yok" in msg
fok, msg = fillet(plate, line((0, 0, 0.1), (2, 0, 0.1)), 0.05)
print("[ince plaka 0.05]", fok, msg)
ok &= fok

# 2) iki kutu birleşimi: üst yüzde x=1'de bölen düz kenar (iki yan yüz eş düzlemli)
fu = BRepAlgoAPI_Fuse(box(0, 0, 0, 1, 1, 1), box(1, 0, 0, 2, 1, 1))
fu.Build()
two = fu.Shape()
fok, msg = fillet(two, line((1, 0, 1), (1, 1, 1)), 0.1)
print("[eş düzlemli kenar]", fok, msg)
ok &= (not fok) and "Model kaynaklı" in msg and "teğet" in msg

# 3) normal kutu kenarı
fok, msg = fillet(box(0, 0, 0, 1, 1, 1), line((0, 0, 1), (1, 0, 1)), 0.1)
print("[kutu kenarı 0.1]", fok, msg)
ok &= fok

# 4) kullanıcı modeli (rapor)
if len(sys.argv) > 2:
    from report_model import build_body, load_report, samples
    rep = load_report(sys.argv[2])
    body, _, used = build_body(g, rep, "CAD_Govde")
    tool, _, _ = build_body(g, rep, "CAD_Govde.001")
    loops = [[used[("CAD_TelKafes", s, k)] for k in range(10)] for s in (0, 1)]
    fil, res = g.apply_features(body, [{"kind": "FILLET", "size": 0.5,
                                        "polys": [samples(p) for p in lp]} for lp in loops],
                                [], 1e-3)
    assert all(r[0] for r in res), res
    t = time.time()
    cut, bok, msg = g.apply_boolean(fil, [tool], "CUT", 0.2, "SECTION", 1e-3, after_bevel=True)
    print(f"[kullanıcı modeli: Kesim 3 + 0.2] {bok} {msg} · {time.time() - t:.1f} sn")
    ok &= (not bok) and "Çekirdek sınırı" in msg and "küçült" not in msg and \
        "İşlem Sırası" in msg
    t = time.time()
    c2, bok, msg = g.apply_boolean(body, [tool], "CUT", 0.2, "SECTION", 1e-3)
    print(f"[aynı kesim fillet'lerden ÖNCE] {bok} {msg} · {time.time() - t:.1f} sn")
    ok &= bok

assert ok, "teşhis beklenen kaynağı söylemedi"
print("SONUÇ: teşhis kaynakları doğru (geometrik / model / çekirdek)")
