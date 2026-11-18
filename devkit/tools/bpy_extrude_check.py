"""GERÇEK Blender + OCC: ekstrüzyon (v0.34.0) — hacimler analitik değerle karşılaştırılır.

Kullanım: python bpy_extrude_check.py <mini_cad'in üst klasörü>

Kutu 1 × 0.6 × 0.4 (hacim 0.24): üst yüz doğrusal +0.1 (0.30) · kes 0.1 (0.18) ·
kalınlaştır +0.1 (düzlem yüzde doğrusalla aynı: 0.30) · iki yönlü · yönü çevir ·
yan yüz · birden çok yüz · yüz bulunamazsa hata + öneri. Açık tek yüzey (1 × 0.6 düzlem)
kalınlaştır 0.05 → 0.03; eğri açık yüzey (silindir çeyreği R=1, boy 0.5) kalınlaştır
0.05 dışa → (π/4)(1.05² − 1²)·0.5 — şekil normaller boyunca korunur.
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
geo = next(m for n, m in sys.modules.items() if n.endswith(".geometry") and hasattr(m, "apply_extrude"))
from mini_cad import extrude, health  # noqa: E402
from mathutils import Vector  # noqa: E402


def vol(b=None):
    b = b or body
    return geo.volume(eng._final[b.name]["shape"])


V0 = vol()
check(abs(V0 - 0.24) < 1e-6, f"kutu hacmi {V0:.6f}")


def ext(pts, **kw):
    f = extrude.new_feature(body, kw.pop("kind", "LINEAR"))
    for co, n in pts:
        h = f.ext_pts.add()
        h.co, h.nrm = co, n
    for k, v in kw.items():
        setattr(f, k, v)
    core.rebuild(body)
    return f


def drop(f):
    i = next(i for i, x in enumerate(body.cad.features) if x == f)
    body.cad.features.remove(i)
    core.rebuild(body)


TOP = ((0.5, 0.3, H), (0, 0, 1))
cases = [
    ("üst yüz doğrusal +0.1", [TOP], dict(ext_dist=0.1), 0.30),
    ("üst yüz kes 0.1", [TOP], dict(ext_dist=0.1, ext_op="CUT"), 0.18),
    ("üst yüz kalınlaştır +0.1", [TOP], dict(kind="THICK", ext_dist=0.1), 0.30),
    ("üst yüz iki yönlü 0.2 (yarısı içeride)", [TOP], dict(ext_dist=0.2, ext_sym=True), 0.30),
    ("yönü çevir (birleştir içe = değişmez → hata)", [TOP], dict(ext_dist=0.1, ext_flip=True), None),
    ("yan yüz (+X) doğrusal 0.2", [((L, 0.3, 0.2), (1, 0, 0))], dict(ext_dist=0.2), 0.24 + 0.6 * 0.4 * 0.2),
    ("üst + yan iki yüz 0.1", [TOP, ((L, 0.3, 0.2), (1, 0, 0))], dict(ext_dist=0.1), None),
    ("kalınlaştır kes 0.05", [TOP], dict(kind="THICK", ext_dist=0.05, ext_op="CUT"), 0.24 - 0.03),
]
for name, pts, kw, want in cases:
    f = ext(pts, **kw)
    v = vol()
    if want is None and "hata" in name:
        check(not f.ok, f"{name}: başarısız sayıldı ({f.info[:70]})")
        fs = [x for x in health.check_body(body) if x["id"].startswith("ext:")]
        check(fs and any("Yönü çevir" in t for t, _fn, _ic in fs[0]["fixes"]),
              f"  öneri: {[t for t, _f, _i in fs[0]['fixes']] if fs else '-'}")
    elif want is None:
        # üst + yan: 0.24 + üst 0.06 + yan 0.024 (köşe kesişmez: yan prizma z 0..0.4)
        check(f.ok and abs(v - (0.24 + 0.06 + 0.024)) < 1e-5, f"{name}: hacim {v:.6f} ({f.info})")
    else:
        check(f.ok and abs(v - want) < 1e-5, f"{name}: hacim {v:.6f} (beklenen {want:.4f}) · {f.info}")
    drop(f)
check(abs(vol() - 0.24) < 1e-6, "silince kutu eski haline döndü")
# yüz bulunamazsa
f = ext([((5, 5, 5), (0, 0, 1))], ext_dist=0.1)
check(not f.ok and "bulunamadı" in f.info, f"olmayan yüz: {f.info[:80]}")
fs = [x for x in health.check_body(body) if x["id"].startswith("ext:")]
check(fs and fs[0]["fixes"][0][0] == "Yüzü yeniden seç", "öneri: yüzü yeniden seç")
drop(f)
# işlem sırası / imza: mesafe değişince yeniden hesap
f = ext([TOP], ext_dist=0.1)
f.ext_dist = 0.2
core.rebuild(body)
check(abs(vol() - 0.36) < 1e-5, f"mesafe 0.2 → hacim {vol():.5f}")
drop(f)

# ---- açık yüzey gövdeleri
def open_body(name, pts_fn):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    ob = bpy.data.objects.new(name, cu)
    sc.collection.objects.link(ob)
    for seg in pts_fn():
        sp = cu.splines.new("BEZIER")
        sp.bezier_points.add(1)
        a, b = sp.bezier_points
        a.co, a.handle_right, b.handle_left, b.co = seg
        a.handle_left = a.co
        b.handle_right = b.co
        for bp in (a, b):
            bp.handle_left_type = bp.handle_right_type = "FREE"
    ui.apply_surface(C, "segs", [(ob, i, 0) for i in range(len(cu.splines))], new_body=True)
    return sc.minicad_target


def lin(a, b):
    a, b = Vector(a), Vector(b)
    return (a, a + (b - a) / 3, a + (b - a) * 2 / 3, b)


flat = open_body("Duz", lambda: [lin((0, 0, 0), (1, 0, 0)), lin((1, 0, 0), (1, 0.6, 0)),
                                 lin((1, 0.6, 0), (0, 0.6, 0)), lin((0, 0.6, 0), (0, 0, 0))])
core.rebuild(flat)
check("katı" not in flat.cad.status.lower() or "açık" in flat.cad.status.lower(), f"düz yüzey: {flat.cad.status}")
body = flat
f = ext([((0.5, 0.3, 0), (0, 0, 1))], kind="THICK", ext_dist=0.05)
check(f.ok and abs(vol(flat) - 0.03) < 1e-6, f"açık düz yüzey kalınlaştır 0.05: {vol(flat):.6f} · {f.info}")
from OCP.Bnd import Bnd_Box  # noqa: E402
from OCP.BRepBndLib import BRepBndLib  # noqa: E402


def zrange(b):
    bb = Bnd_Box()
    BRepBndLib.Add_s(eng._final[b.name]["shape"], bb)
    x0, y0, z0, x1, y1, z1 = bb.Get()
    return z0, z1


z0, z1 = zrange(flat)
check(abs(z0) < 1e-6 and abs(z1 - 0.05) < 1e-6, f"kalınlık bakılan yöne (+Z) gitti: z {z0:.3f}..{z1:.3f}")
f.ext_flip = True
core.rebuild(flat)
z0, z1 = zrange(flat)
check(abs(z0 + 0.05) < 1e-6 and abs(z1) < 1e-6, f"yönü çevir: z {z0:.3f}..{z1:.3f}")
f.ext_flip = False
f.ext_kind = "LINEAR"
core.rebuild(flat)
check(f.ok and abs(vol(flat) - 0.03) < 1e-6, f"açık düz yüzey doğrusal 0.05: {vol(flat):.6f}")
f.ext_scope = "BODY"
f.ext_pts.clear()
core.rebuild(flat)
check(f.ok and abs(vol(flat) - 0.03) < 1e-6, f"kapsam: bütün yüzey (yüz seçmeden): {vol(flat):.6f}")

# çeyrek silindir: x = cos, z = sin (R = 1), y 0..0.5
k = 4 / 3 * math.tan(math.pi / 8)


def quarter(y):
    return (Vector((1, y, 0)), Vector((1, y, k)), Vector((k, y, 1)), Vector((0, y, 1)))


cyl = open_body("Silindir", lambda: [quarter(0.0), lin((0, 0, 1), (0, 0.5, 1)),
                                     tuple(reversed(quarter(0.5))), lin((1, 0.5, 0), (1, 0, 0))])
core.rebuild(cyl)
body = cyl
c45 = math.cos(math.pi / 4)
f = ext([((c45, 0.25, c45), (c45, 0, c45))], kind="THICK", ext_dist=0.05)
want = math.pi / 4 * (1.05 ** 2 - 1.0) * 0.5
v = vol(cyl)
check(f.ok and abs(v - want) / want < 2e-3, f"çeyrek silindir kalınlaştır dışa 0.05: {v:.6f} (beklenen {want:.6f}, "
      f"bezier yay yaklaşıklığı)")
# kalınlaştırılan katının dış yüzü de silindir: ortadaki noktası R=1.05'te
sh = eng._final[cyl.name]["shape"]
from OCP.BRepExtrema import BRepExtrema_DistShapeShape  # noqa: E402
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex  # noqa: E402
from OCP.gp import gp_Pnt  # noqa: E402
q = 1.05 * c45
dd = BRepExtrema_DistShapeShape(BRepBuilderAPI_MakeVertex(gp_Pnt(q, 0.25, q)).Vertex(), sh).Value()
check(dd < 1e-3, f"şekil korundu: dış yüz R=1.05'te (uzaklık {dd:.2e})")
f.ext_kind = "LINEAR"
core.rebuild(cyl)
v2 = vol(cyl)
check(f.ok and v2 > 0 and abs(v2 - want) > 1e-4, f"aynı yüzey doğrusal (tek yön) farklı hacim: {v2:.6f}")


if PNG:                                   # Ekstrüzyon / Saydamlık pencereleri (gerçek veriyle)
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from pil_painter import PILPainter
    from mini_cad import blendcad, ribbon, ribbon_formspecs as fs_  # noqa: E402
    body = cyl
    sc.minicad_target = cyl
    cyl.cad.opacity = 0.35

    class _Ask:
        asking = True
        body_name = cyl.name

        def feature(self):
            return f

        def set_kind(self, *a):
            pass

        def finish(self, *a, **k):
            pass

    base, ext_ = os.path.splitext(PNG)
    for suffix, tab, btn, fid, ask in (("_sor", "SOLID", "EXTRUDE", "EXTRUDE", True),
                                       ("", "SOLID", "EXTRUDE", "EXTRUDE", False),
                                       ("_saydamlik", "SOLID", "OPACITY", "OPACITY", False)):
        extrude._STATE["active"] = _Ask() if ask else None
        f.ext_kind = "THICK"
        rb = ribbon.Ribbon(1.0)
        blendcad._setup_forms(rb)
        rb.tab = tab
        pp = PILPainter(1300, 980)
        rb.layout(pp, 1300, 980, 44, 300, 52)
        rb._anchor_x = rb._rect("btn", btn)[0]
        t_, ic, spec, w_ = fs_.FORMS[fid]
        rb.open_form(fid, t_, ic, spec, w_)
        pp.viewport()
        pp.headers(52)
        rb.draw(pp, 1300, 980, 44, 300, 0.0, 52)
        pp.save(base + suffix + ext_)
    extrude._STATE["active"] = None

print("SONUÇ:", "tamam" if not fails else f"{len(fails)} hata")
sys.exit(1 if fails else 0)
