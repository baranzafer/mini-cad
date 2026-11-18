"""GERÇEK Blender + OCC: model denetimi bulguları ve düzeltmeleri (v0.32.0).

Kullanım: python bpy_health_check.py <mini_cad'in üst klasörü>

Kutu (1 × 0.6 × 0.4) üzerinde senaryolar:
  F1 fillet çok büyük (0.45 > yükseklik): başarısız → "en büyük ölçüyü bul" → "ölçüyü X yap" → olur
  F2 fillet büyük ama olmuş (0.19, komşu kenar 0.4): uyarı → önerilen ölçü
  B1 boolean aracının yüzü gövdenin üst yüzüyle aynı düzlemde: uyarı → aracı kaydır → uyarı kalkar
  B2 boolean etkisiz (araç uzakta): uyarı
  W1 tel kafes ucu kutu köşesine 2 mm uzak: uyarı → uçları kaynat
  W2 tel kafes ucu kenarın ortasında (nokta yok): uyarı → böl ve kaynat
  W3 sıfır boy parça: uyarı → fazla noktayı kaldır (biçim ve yüzey korunur)
  O1 gövdeden yüzey silinince açık kabuk: serbest kenarlar işaretli
"""
import sys

PNG = sys.argv[-1] if sys.argv[-1].endswith(".png") else None
ROOT = sys.argv[-2] if PNG else sys.argv[-1]
sys.path.insert(0, ROOT)
import bpy  # noqa: E402
import addon_utils  # noqa: E402
import numpy as np  # noqa: E402

fails = []


def check(ok, msg):
    print(("  ok  " if ok else "  HATA ") + msg)
    if not ok:
        fails.append(msg)


def _raise(e):
    raise e


addon_utils.enable("mini_cad", default_set=True, handle_error=_raise)
from mini_cad import core, health, ui  # noqa: E402

C = bpy.context
sc = C.scene
C.preferences.addons["mini_cad"].preferences.background = False

L, W, H = 1.0, 0.6, 0.4
P = [(0, 0, 0), (L, 0, 0), (L, W, 0), (0, W, 0), (0, 0, H), (L, 0, H), (L, W, H), (0, W, H)]
EDGES = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5),
         (2, 6), (3, 7)]
FACES = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 9, 4, 8), (2, 11, 6, 10), (1, 10, 5, 9),
         (3, 8, 7, 11)]


def curve(name, lines):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    for pts in lines:
        sp = cu.splines.new("BEZIER")
        sp.bezier_points.add(len(pts) - 1)
        for bp, co in zip(sp.bezier_points, pts):
            bp.co = co
            bp.handle_left_type = bp.handle_right_type = "VECTOR"
    ob = bpy.data.objects.new(name, cu)
    sc.collection.objects.link(ob)
    return ob


wire = curve("Tel", [(P[a], P[b]) for a, b in EDGES])
ui.apply_surface(C, "segs", [(wire, i, 0) for i in FACES[0]], new_body=True)
body = sc.minicad_target
for fc in FACES[1:]:
    ui.apply_surface(C, "segs", [(wire, i, 0) for i in fc])
core.rebuild(body)
check("Kapalı katı" in body.cad.status, f"kutu: {body.cad.status}")
KEY = "body:" + body.name


def find(prefix):
    return [f for f in health.FINDINGS.get(KEY, []) if prefix in f["id"]]


def fix(f, label_part=""):
    for label, fn, _ic in f["fixes"]:
        if label_part in label:
            health.apply_fix(KEY, fn, label)
            return label
    raise KeyError(label_part)


health.run(KEY, notify=False)
check(not health.FINDINGS[KEY], f"temiz kutu: bulgu yok ({[f['msg'][:60] for f in health.FINDINGS[KEY]]})")

print("F1) fillet çok büyük")
ok, msg = ui.add_feature(C, [(wire, 4, 0)])
f = body.cad.features[-1]
f.size = 0.45
core.rebuild(body)
health.run(KEY, notify=False)
fs = find("fillet:")
check(fs and fs[0]["level"] == "error", f"başarısız fillet bulgusu: {fs and fs[0]['msg'][:110]}")
lab = fix(fs[0], "") if fs else ""
print("      uygulandı:", lab)
fs = find("fillet:")
if fs and fs[0]["level"] == "error":
    lab = fix(fs[0], "Ölçüyü")
    print("      uygulandı:", lab)
check(f.ok and f.size < 0.45, f"fillet artık uygulanıyor: ölçü {f.size:.4f} ({f.info[:60]})")

print("F2) fillet büyük ama olmuş: komşu kenara göre")
f.size = 0.19
core.rebuild(body)
health.run(KEY, notify=False)
fs = find(":big")
check(fs and fs[0]["level"] == "warn", f"uyarı: {fs and fs[0]['msg'][:110]}")
if fs:
    fix(fs[0], "Ölçü")
check(f.ok and abs(f.size - 0.16) < 1e-6 and not find(":big"), f"önerilen ölçü 0.16: {f.size:.4f}")
body.cad.features.remove(len(body.cad.features) - 1)
core.rebuild(body)

print("B1) aracın yüzü gövde yüzüyle aynı düzlemde")
bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0.5, 0.3, H - 0.1))
cube = C.active_object
C.view_layer.objects.active = body
sc.minicad_target = body
sc.minicad_bool_tool = cube
sc.minicad_bool_type = "CUT"
bpy.ops.minicad.add_boolean()
health.run(KEY, notify=False)
fs = find(":coplanar") or find("bool:") and [x for x in find("bool:") if "fail" in x["id"]]
check(fs, f"çakışık yüz bulgusu: {fs and fs[0]['msg'][:120]}")
z0 = cube.location.z
if fs:
    fix(fs[0], "kaydır")
check(cube.location.z > z0 and not find(":coplanar"), f"araç {1000 * (cube.location.z - z0):.2f} mm dışarı kaydı, uyarı kalktı")
b = [x for x in body.cad.features if x.op == "BOOLEAN"][0]
check(b.ok, f"boolean: {b.info[:60]}")

print("B2) etkisiz boolean")
bpy.ops.mesh.primitive_cube_add(size=0.2, location=(5, 5, 5))
far = C.active_object
C.view_layer.objects.active = body
sc.minicad_bool_tool = far
bpy.ops.minicad.add_boolean()
health.run(KEY, notify=False)
fs = find(":noop") + [x for x in find("bool:") if "fail" in x["id"]]
check(fs, f"etkisiz / başarısız boolean bildirildi: {fs and fs[0]['msg'][:100]}")
body.cad.features.remove(len(body.cad.features) - 1)
core.rebuild(body)

print("W1) yakın ama değmeyen uç (2 mm)")
ek = curve("Ek", [((L + 0.5, 0, 0), (L + 0.002, 0, 0))])
fs = health.run("curve:Ek", notify=False)
g = [x for x in fs if "GAP" in x["id"]]
check(g, f"boşluk bulgusu: {g and g[0]['msg'][:100]}")
if g:
    health.apply_fix("curve:Ek", g[0]["fixes"][0][1], g[0]["fixes"][0][0])
e = ek.data.splines[0].bezier_points[1].co
check(abs(e.x - L) < 1e-9 and "Kapalı katı" in body.cad.status, f"uç köşeye kaynadı, gövde sağlam ({e.x:.6f})")

print("W2) kenarın ortasına değen uç")
ek2 = curve("Ek2", [((0.5, -0.5, 0), (0.5, 0, 0))])
fs = health.run("curve:Ek2", notify=False)
t = [x for x in fs if "TJUNC" in x["id"]]
check(t, f"T-birleşim bulgusu: {t and t[0]['msg'][:100]}")
if t:
    health.apply_fix("curve:Ek2", t[0]["fixes"][0][1], t[0]["fixes"][0][0])
core.rebuild(body)
check(len(wire.data.splines[0].bezier_points) == 3 and "Kapalı katı" in body.cad.status,
      f"alt kenar bölündü, gövde sağlam: {body.cad.status[:50]}")

print("W3) sıfır boy parça")
z = curve("Sifir", [((2, 0, 0), (2.5, 0, 0), (2.5, 0, 0), (3, 0, 0))])
fs = health.run("curve:Sifir", notify=False)
zz = [x for x in fs if "ZERO" in x["id"]]
check(zz and zz[0]["fixes"], f"sıfır boy bulgusu: {zz and zz[0]['msg'][:90]}")
if zz:
    health.apply_fix("curve:Sifir", zz[0]["fixes"][0][1], zz[0]["fixes"][0][0])
check(len(z.data.splines[-1].bezier_points) == 3, "fazla nokta kaldırıldı")

print("O1) açık kabuk")
body.cad.patches.remove(1)
core.forget_cache(body.name)
core.rebuild(body)
health.run(KEY, notify=False)
o = find("open")
check(o and len(o[0]["pts"]) > 0, f"açık kabuk: {o and o[0]['msg'][:80]} · {o and len(o[0]['pts'])} işaret")

if PNG:                                   # Öneriler penceresi (gerçek bulgularla)
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from pil_painter import PILPainter
    from mini_cad import blendcad, ribbon, ribbon_formspecs as fs_
    ui.add_feature(C, [(wire, 7, 0)])
    body.cad.features[-1].size = 0.19
    core.rebuild(body)
    curve("Ek3", [((-0.5, 0.3, H), (-0.0015, 0.3, H))])
    health.run(KEY, notify=False)
    health.run("curve:Ek3", notify=False)
    rb = ribbon.Ribbon(1.0)
    blendcad._setup_forms(rb)
    rb.tab = "TOOLS"
    p = PILPainter(1300, 900)
    rb.layout(p, 1300, 900, 44, 300, 52)
    rb._anchor_x = rb._rect("btn", "REPAIR")[0]
    t_, ic, spec, w = fs_.FORMS["REPAIR"]
    rb.open_form("REPAIR", t_, ic, spec, w)
    p.viewport()
    p.headers(52)
    rb.draw(p, 1300, 900, 44, 300, 0.0, 52)
    p.save(PNG)

print("SONUÇ:", "tamam" if not fails else f"{len(fails)} hata")
sys.exit(1 if fails else 0)
