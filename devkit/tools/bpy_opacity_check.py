"""GERÇEK Blender: gövde saydamlığı (v0.34.0).

Kullanım: python bpy_hole_check.py <mini_cad'in üst klasörü> [çıktı.png]

Kutu gövdede opaklık, yeniden hesaplamada korunma, çizerken saydam kipi.
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
from mini_cad import opacity  # noqa: E402
body.cad.opacity = 0.3
sl = body.material_slots
check(len(sl) == 1 and sl[0].link == "OBJECT" and sl[0].material is not None and
      abs(sl[0].material.diffuse_color[3] - 0.3) < 1e-6, "opaklık 0.3: obje bağlantılı saydam malzeme")
check(abs(body.color[3] - 0.3) < 1e-6, "nesne rengi alfası 0.3")
core.rebuild(body)
check(body.material_slots[0].link == "OBJECT" and abs(body.material_slots[0].material.diffuse_color[3] - 0.3) < 1e-6,
      "yeniden hesaplamadan sonra saydam kaldı")
body.cad.opacity = 1.0
check(body.material_slots[0].link == "DATA" and body.material_slots[0].material is None,
      "opak: eski (veri) bağlantısına döndü")
sc.minicad_draw_ghost = True
opacity.apply_all(True)
check(abs(body.material_slots[0].material.diffuse_color[3] - 0.35) < 1e-6, "çizerken saydam: 0.35")
opacity.apply_all(False)
check(body.material_slots[0].link == "DATA", "çizim bitince opak")
# kullanıcının kendi malzemesi korunur
m = bpy.data.materials.new("Kirmizi"); m.diffuse_color = (1, 0, 0, 1)
body.data.materials[0] = m
body.cad.opacity = 0.5
check(body.material_slots[0].link == "OBJECT", "kendi malzemesi olan gövde de saydamlaşır")
body.cad.opacity = 1.0
check(body.data.materials[0] == m and body.material_slots[0].material == m, "kullanıcı malzemesi korundu")
print("SONUÇ:", "tamam" if not fails else f"{len(fails)} hata")
sys.exit(1 if fails else 0)
