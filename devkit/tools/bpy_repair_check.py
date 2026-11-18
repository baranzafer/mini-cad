"""GERÇEK Blender + OCC: kusurlu yüzey sınırlarında teşhis ve kullanıcı onaylı onarım (v0.31.0).

Kullanım: python bpy_repair_check.py <mini_cad'in üst klasörü>

Senaryolar (çizimde sık olanlar):
  A) taşan çizgi: sol kenar alttan taşıyor, alt kenarın ucu onun ortasına snap olmuş
  B) köşesi olmayan kenara snap: dikme, tek parça alt kenarın ortasında (bölünmemiş)
  C) uçlar 3 mm değmiyor
  D) aynı kenar iki kez çizilmiş
  E) mevcut gövdeye eklerken T-birleşim (komşu yüzeyle tamamlama yolu)
Her birinde: yüzey önce oluşmaz → öneri listesi → "Hepsini düzelt ve yüzeyi oluştur" →
yüzey oluşur, kapalı / geçerli; eğri biçimi korunur, bölünen eğriye bağlı diğer yüzeyler
bozulmaz.
"""
import sys

ROOT = sys.argv[-1] if not sys.argv[-1].endswith(".png") else sys.argv[-2]
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
from mini_cad import core, repair, ui  # noqa: E402

C = bpy.context
sc = C.scene
C.preferences.addons["mini_cad"].preferences.background = False


def curve(name, lines):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    for a, b in lines:
        sp = cu.splines.new("BEZIER")
        sp.bezier_points.add(1)
        for bp, co in zip(sp.bezier_points, (a, b)):
            bp.co = co
            bp.handle_left_type = bp.handle_right_type = "VECTOR"
    ob = bpy.data.objects.new(name, cu)
    sc.collection.objects.link(ob)
    return ob


def run(title, ob, kinds_expected, new_body=True, refs=None):
    print(title)
    refs = refs or [(ob, i, 0) for i in range(len(ob.data.splines))]
    n_obj = len(bpy.data.objects)
    ok, msg = ui.apply_surface(C, "segs", refs, new_body=new_body)
    check(not ok, f"önce oluşmadı: {msg[:110]}")
    d = repair.PENDING["data"]
    kinds = [i["kind"] for i in d["issues"]] if d else []
    check(d is not None and kinds and kinds[0] in kinds_expected, f"teşhis: {kinds}")
    if d:
        for i in d["issues"]:
            print("      ·", i["msg"])
    repair.fix(None)
    check(repair.PENDING["data"] is None, "onarım sonrası bekleyen sorun yok (yüzey oluştu)")
    body = sc.minicad_target
    return body, n_obj


Z = 0.0
# A) taşan çizgi
A = curve("A_Tasan", [((0, 0, Z), (1, 0, Z)), ((1, 0, Z), (1, 1, Z)), ((1, 1, Z), (0, 1, Z)),
                      ((0, 1, Z), (0, -0.4, Z))])
body, _ = run("A) taşan çizgi (T-birleşim + fazla parça)", A, {"TJUNC"})
check(body is not None and body.cad.patches[-1].ok, f"yüzey: {body and body.cad.status}")
sp = A.data.splines[3]
check(len(sp.bezier_points) == 3 and abs(sp.bezier_points[1].co.y) < 1e-6,
      "sol kenar (0,0)'da bölündü, biçim aynı (taşan kısım eğride duruyor)")
pt = body.cad.patches[-1]
check(len(pt.segs) == 4, f"yüzey 4 segmentle kuruldu ({len(pt.segs)})")

# B) köşesi olmayan kenara snap
B = curve("B_Orta", [((3, 0, Z), (5, 0, Z)), ((4, 0, Z), (4, 1, Z)), ((4, 1, Z), (3, 1, Z)),
                     ((3, 1, Z), (3, 0, Z))])
body, _ = run("B) dikme tek parça kenarın ortasında", B, {"TJUNC"})
check(body is not None and body.cad.patches[-1].ok, f"yüzey: {body and body.cad.status}")
check(len(B.data.splines[0].bezier_points) == 3, "alt kenar dikmenin dibinde bölündü")

# C) 3 mm boşluk
Cc = curve("C_Bosluk", [((6, 0, Z), (7, 0, Z)), ((7, 0, Z), (7, 1, Z)), ((7, 1, Z), (6.003, 1, Z)),
                        ((6, 1, Z), (6, 0, Z))])
body, _ = run("C) uçlar 3 mm değmiyor", Cc, {"GAP"})
check(body is not None and body.cad.patches[-1].ok, f"yüzey: {body and body.cad.status}")
e = Cc.data.splines[2].bezier_points[1].co
s = Cc.data.splines[3].bezier_points[0].co
check((e - s).length < 1e-9, "uçlar ortak noktada")

# D) aynı kenar iki kez
D = curve("D_Cift", [((9, 0, Z), (10, 0, Z)), ((10, 0, Z), (10, 1, Z)), ((10, 1, Z), (9, 1, Z)),
                     ((9, 1, Z), (9, 0, Z)), ((10, 0, Z), (9, 0.0004, Z))])
body, _ = run("D) üst üste iki kenar", D, {"DUP"})
check(body is not None and body.cad.patches[-1].ok and len(body.cad.patches[-1].segs) == 4,
      "yüzey fazla kenar olmadan kuruldu")

# E) mevcut gövdeye eklerken: komşu kare + taşan kenar, gövde bozulmamalı
E = curve("E_Komsu", [((12, 0, Z), (13, 0, Z)), ((13, 0, Z), (13, 1, Z)), ((13, 1, Z), (12, 1, Z)),
                      ((12, 1, Z), (12, 0, Z))])
ok, msg = ui.apply_surface(C, "segs", [(E, i, 0) for i in range(4)], new_body=True)
check(ok, "komşu gövde: ilk kare")
body = sc.minicad_target
F = curve("E_Tasan", [((13, 0, Z), (14, 0, Z)), ((14, 0, Z), (14, 1.5, Z)),
                      ((14, 1, Z), (13, 1, Z))])
refs = [(F, i, 0) for i in range(3)] + [(E, 1, 0)]
run("E) gövdeye eklenen ikinci kare: sağ kenar taşıyor", F, {"TJUNC"}, new_body=False,
    refs=refs)
check(len(body.cad.patches) == 2 and all(p.ok for p in body.cad.patches),
      f"gövde: 2 geçerli yüzey ({[p.info[:40] for p in body.cad.patches]})")
core.rebuild(body)
check(body.cad.status.startswith("Tamam"), f"gövde hesap: {body.cad.status}")

# pencere görüntüsü (gerçek veriyle): taşan çizgi + boşluk birlikte
if sys.argv[-1].endswith(".png"):
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from pil_painter import PILPainter
    from mini_cad import blendcad, ribbon, ribbon_actions as ra, ribbon_formspecs as fs
    H2 = curve("H_Gorsel", [((30, 0, Z), (31, 0, Z)), ((31, 0, Z), (31, 1, Z)),
                            ((31, 1, Z), (30.003, 1, Z)), ((30, 1, Z), (30, -0.3, Z))])
    ui.apply_surface(C, "segs", [(H2, i, 0) for i in range(4)], new_body=True)
    rb = ribbon.Ribbon(1.0)
    blendcad._setup_forms(rb)
    rb.tab = "TOOLS"
    p = PILPainter(1300, 760)
    rb.layout(p, 1300, 760, 44, 300, 52)
    rb._anchor_x = rb._rect("btn", "REPAIR")[0]
    t, ic, spec, w = fs.FORMS["REPAIR"]
    rb.open_form("REPAIR", t, ic, spec, w)
    p.viewport()
    p.headers(52)
    rb.draw(p, 1300, 760, 44, 300, 0.0, 52)
    p.save(sys.argv[-1])
    repair.cancel()

# vazgeç: hiçbir şey değişmez
G = curve("G_Vazgec", [((20, 0, Z), (21, 0, Z)), ((21, 0, Z), (21, 1, Z)), ((21, 1, Z), (20.004, 1, Z)),
                       ((20, 1, Z), (20, 0, Z))])
before = tuple(G.data.splines[2].bezier_points[1].co)
ok, msg = ui.apply_surface(C, "segs", [(G, i, 0) for i in range(4)], new_body=True)
repair.cancel()
check(repair.PENDING["data"] is None and tuple(G.data.splines[2].bezier_points[1].co) == before,
      "Vazgeç: eğriler değişmedi (sormadan düzeltme yok)")

print("SONUÇ:", "tamam" if not fails else f"{len(fails)} hata")
sys.exit(1 if fails else 0)
