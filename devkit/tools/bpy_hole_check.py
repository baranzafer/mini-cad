"""GERÇEK Blender + OCC: delik aracı (v0.33.0) — çıkan hacim analitik formülle karşılaştırılır.

Kullanım: python bpy_hole_check.py <mini_cad'in üst klasörü> [çıktı.png]

Kutu 1 × 0.6 × 0.4 (hacim 0.24). Üst yüzün ortasına (0.5, 0.3, 0.4) eksen -Z:
  düz tümüyle geçen · düz kör + 118° matkap ucu · düz kör düz dip · havşa başlı · havşalı ·
  dişli M6 (kılavuz matkabı 5 mm) · iki delik birden · yan yüzden yatay delik ·
  delik kenarına (ağız) pah — delik kenarları seçilebilir
"""
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


def vol():
    return geo.volume(eng._final[body.name]["shape"])


V0 = vol()
check(abs(V0 - 0.24) < 1e-6, f"kutu hacmi {V0:.6f}")


def hole(pts, **kw):
    f = body.cad.features.add()
    f.op = "HOLE"
    f.uid = core.new_uid()
    f.name = f"Delik {len(body.cad.features)}"
    for k, v in kw.items():
        setattr(f, "hole_" + k, v)
    for co, n in pts:
        h = f.hole_pts.add()
        h.co, h.nrm = co, n
    core.rebuild(body)
    return f


def clear():
    while len(body.cad.features):
        body.cad.features.remove(0)
    core.rebuild(body)


TOP = [((0.5, 0.3, H), (0, 0, -1))]
pi = math.pi


def run(name, expect, pts=TOP, rel=2e-3, **kw):
    f = hole(pts, **kw)
    got = V0 - vol()
    ok = f.ok and abs(got - expect) <= rel * expect
    check(ok, f"{name}: çıkan {got:.7f} ≈ beklenen {expect:.7f} ({f.info[:50]})")
    clear()
    return f


r = 0.05
run("düz tümüyle geçen", pi * r * r * H, kind="SIMPLE", d=0.1, through=True)
tip = r / math.tan(math.radians(59))
run("düz kör 118° uç", pi * r * r * 0.2 + pi * r * r * tip / 3, kind="SIMPLE", d=0.1,
    through=False, depth=0.2, tip=118.0)
run("düz kör düz dip", pi * r * r * 0.2, kind="SIMPLE", d=0.1, through=False, depth=0.2,
    tip=0.0)
run("havşa başlı", pi * (0.1 ** 2 * 0.1 + r * r * 0.3), kind="CBORE", d=0.1, through=True,
    cb_d=0.2, cb_depth=0.1)
hc = 0.05
run("havşalı 90°", pi * hc / 3 * (0.1 ** 2 + 0.1 * r + r * r) + pi * r * r * (H - hc),
    kind="CSINK", d=0.1, through=True, cs_d=0.2, cs_angle=90.0)
pr = holemath.preset("TAPPED", "M6")
check(abs(pr["d"] - 0.005) < 1e-12, "M6 kılavuz matkabı 5 mm")
run("dişli M6 tümüyle", pi * 0.0025 ** 2 * H, rel=5e-3, kind="TAPPED", d=pr["d"], through=True,
    thread="M6")
run("iki delik", 2 * pi * r * r * H, pts=TOP[:0] + [((0.25, 0.3, H), (0, 0, -1)),
                                                   ((0.75, 0.3, H), (0, 0, -1))],
    kind="SIMPLE", d=0.1, through=True)
run("yan yüzden yatay (x=1, eksen -X)", pi * r * r * 0.3 + pi * r * r * tip / 3,
    pts=[((L, 0.3, 0.2), (-1, 0, 0))], kind="SIMPLE", d=0.1, through=False, depth=0.3,
    tip=118.0)

# delik ağzına pah: deliğin yeni kenarları kenar seçiminde görünür (bool_edges)
f = hole(TOP, kind="SIMPLE", d=0.1, through=True)
edges = [e for e in core._display[body.name]["bool_edges"] if e[0] == f.uid]
check(len(edges) >= 2, f"delik kenarları seçilebilir: {len(edges)} kenar")
# üst ağız çemberi (z = H) — GeoEdge ile pah ekle
top = [e for e in edges if abs(float(e[1][:, 2].mean()) - H) < 1e-6]
check(len(top) >= 1, "üst ağız kenarı bulundu")
if top:
    ok, msg = ui.add_feature(C, [("BODY", f.uid, top[0][1])])
    b = body.cad.features[-1]
    b.kind = "CHAMFER"
    b.size = 0.01
    core.rebuild(body)
    v1 = V0 - vol()
    exp = pi * r * r * H + pi * 0.01 / 3 * ((r + 0.01) ** 2 + (r + 0.01) * r + r * r) - pi * r * r * 0.01
    check(b.ok and abs(v1 - exp) < 2e-3 * exp, f"delik ağzına 1 cm pah: çıkan {v1:.7f} ≈ {exp:.7f} ({b.info[:40]})")
clear()

# hatalı değer: havşa başı delikten küçük → Model kaynaklı
f = hole(TOP, kind="CBORE", d=0.1, through=True, cb_d=0.05, cb_depth=0.1)
check(not f.ok and "Model kaynaklı" in f.info, f"hatalı havşa başı: {f.info[:80]}")
clear()

# ---------------------------------------------------------------- araç parçaları
from mini_cad import health, hole as hm  # noqa: E402

f = hm.new_feature(body, "SIMPLE")
check(f.hole_thread == "NONE" and abs(f.hole_d - 0.02) < 1e-9,
      f"1 m gövdede başlangıç çapı orantılı: {f.hole_d}")
f.hole_kind = "CBORE"
f.hole_thread = "M8"
hm.apply_preset(f)
check(abs(f.hole_d - 0.009) < 1e-7 and abs(f.hole_cb_d - 0.015) < 1e-7 and
      abs(f.hole_cb_depth - 0.0086) < 1e-7, "M8 havşa başlı: Ø9, yuva Ø15 × 8.6 mm (ISO 4762)")
f.hole_kind = "CSINK"
hm.apply_preset(f)
check(abs(f.hole_cs_d - 0.0172) < 1e-7, "M8 havşalı: havşa Ø17.2 mm")
f.hole_kind = "TAPPED"
hm.apply_preset(f)
check(abs(f.hole_d - 0.0068) < 1e-7, "M8 dişli: kılavuz matkabı Ø6.8 mm")
clear()
# yakalama adayları: eskiz noktası ve daire merkezi
pc = bpy.data.curves.new("Nokta", "CURVE")
pc.splines.new("BEZIER").bezier_points[0].co = (0.3, 0.2, H)
pob = bpy.data.objects.new("Nokta", pc)
sc.collection.objects.link(pob)
cc = bpy.data.curves.new("Daire", "CURVE")
sp = cc.splines.new("BEZIER")
sp.bezier_points.add(3)
for k, bp in enumerate(sp.bezier_points):
    a = k * math.pi / 2
    bp.co = (0.7 + 0.05 * math.cos(a), 0.3 + 0.05 * math.sin(a), H)
sp.use_cyclic_u = True
cob = bpy.data.objects.new("Daire", cc)
sc.collection.objects.link(cob)
cands = hm.snap_candidates(C)
kinds = sorted(k for _p, k in cands)
check(kinds == ["Daire merkezi", "Nokta"] and any(abs(p[0] - 0.7) < 1e-6 for p, k in cands
                                                 if k == "Daire merkezi"),
      f"yakalama adayları: {kinds}")

# model denetimi: kenara çok yakın / yanı delen delik → içeri kaydır
KEY = "body:" + body.name
f = hole([((0.97, 0.3, H), (0, 0, -1))], kind="SIMPLE", d=0.1, through=True)
health.run(KEY, notify=False)
w = [x for x in health.FINDINGS[KEY] if ":wall" in x["id"]]
check(w and "yan yüzeyi deliyor" in w[0]["msg"], f"yanı delen delik: {w and w[0]['msg'][:90]}")
if w:
    lab, fn, _i = w[0]["fixes"][0]
    health.apply_fix(KEY, fn, lab)
x = (body.matrix_world @ __import__("mathutils").Vector(tuple(f.hole_pts[0].co))).x
w = [x_ for x_ in health.FINDINGS[KEY] if ":wall" in x_["id"]]
check(x <= L - 0.05 - 0.025 + 1e-4 and x > 0.85 and not w,
      f"'{lab}': delik x={x:.4f} (et = yarıçapın yarısı), uyarı kalktı")
clear()
f = hole(TOP, kind="CBORE", d=0.1, through=True, cb_d=0.05, cb_depth=0.1)
health.run(KEY, notify=False)
e = [x for x in health.FINDINGS[KEY] if "hole:" in x["id"] and ":fail" in x["id"]]
check(e and any("türet" in fx[0] for fx in e[0]["fixes"]), f"hatalı delik önerisi: {e and [fx[0] for fx in e[0]['fixes']]}")
if e:
    fx = next(fx for fx in e[0]["fixes"] if "türet" in fx[0])
    health.apply_fix(KEY, fx[1], fx[0])
check(f.ok, f"havşa ölçüleri türetildi, delik açıldı: {f.info[:50]}")

if PNG:                                   # Delik penceresi (gerçek veriyle)
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from pil_painter import PILPainter
    from mini_cad import blendcad, ribbon, ribbon_actions as ra, ribbon_formspecs as fs_
    f.hole_thread = "M8"
    hm.apply_preset(f)
    h2 = f.hole_pts.add()
    h2.co, h2.nrm = (0.25, 0.3, H), (0, 0, -1)
    core.rebuild(body)
    ra.form_state["hole_uid"] = f.uid
    rb = ribbon.Ribbon(1.0)
    blendcad._setup_forms(rb)
    rb.tab = "HOLE"
    p = PILPainter(1300, 980)
    rb.layout(p, 1300, 980, 44, 300, 52)
    rb._anchor_x = rb._rect("btn", "HOLE")[0]
    t_, ic, spec, w_ = fs_.FORMS["HOLE"]
    rb.open_form("HOLE", t_, ic, spec, w_)
    p.viewport()
    p.headers(52)
    rb.draw(p, 1300, 980, 44, 300, 0.0, 52)
    p.save(PNG)

print("SONUÇ:", "tamam" if not fails else f"{len(fails)} hata")
sys.exit(1 if fails else 0)
