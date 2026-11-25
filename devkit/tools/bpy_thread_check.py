"""GERÇEK Blender + OCC: dişli delik ve vida / somun (v0.36.0).

Kullanım: python bpy_thread_check.py <mini_cad'in üst klasörü> [çıktı klasörü (PNG)]

Sahne mm (scale_length 0.001), kutu 40 × 30 × 12 mm.
- Modellenmiş M6 dişli delik: kör ve geçen; çıkan hacim matkaptan büyük, diş tepe çapı
  kadar değil (analitik aralık); dişin içindeki nokta boş (diş gerçekten açıldı).
- Sol el, 2 ağızlı, trapez / kare / yuvarlak / testere / Whitworth / özel (eğri) profil.
- Geçme: boşluk büyüyünce delik büyür, vida küçülür (hacimler monoton).
- Delikten uyumlu vida: diş, boy, yer; delik değişince bağlı vida da değişir.
- Kademeli geçme deliğine imbus vida + somun (çıkış yüzünde); havşaya havşa başlı vida.
- Bağımsız vida (başsız saplama, altıgen baş, mercimek, yarık / yıldız yuva) ve somun.
- Eski (v0.33) dişli delik göçü: kozmetik kalır (görünüş değişmez).
- İsteğe bağlı: Delik (dişli) ve Vida pencerelerinin PNG'leri.
"""
import math
import os
import sys

OUT = sys.argv[2] if len(sys.argv) > 2 else None
ROOT = sys.argv[1]
sys.path.insert(0, ROOT)
import bpy  # noqa: E402
import addon_utils  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

fails = []


def check(ok, msg):
    print(("  ok  " if ok else "  HATA ") + msg)
    if not ok:
        fails.append(msg)


def _raise(e):
    raise e


addon_utils.enable("mini_cad", default_set=True, handle_error=_raise)
from mini_cad import core, hole as HL, thread as TH, threadmath as tm, ui  # noqa: E402

C = bpy.context
sc = C.scene
sc.unit_settings.scale_length = 0.001          # 1 birim = 1 mm
C.preferences.addons["mini_cad"].preferences.background = False
L, W, H = 40.0, 30.0, 12.0
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
body.cad.lin_defl = 0.05
body.cad.ang_defl = math.radians(10)
core.rebuild(body)
check("Kapalı katı" in body.cad.status, f"kutu: {body.cad.status}")

eng = next(m for n, m in sys.modules.items()
           if isinstance(getattr(m, "_final", None), dict) and hasattr(m, "_bool_new"))
geo = next(m for n, m in sys.modules.items() if n.endswith(".geometry") and
           hasattr(m, "make_part"))


def vol(ob=body):
    return geo.volume(eng._final[ob.name]["shape"])


def inside(ob, q):
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.TopAbs import TopAbs_IN
    from OCP.gp import gp_Pnt
    return BRepClass3d_SolidClassifier(eng._final[ob.name]["shape"], gp_Pnt(*q),
                                       1e-7).State() == TopAbs_IN


V0 = vol()
check(abs(V0 - L * W * H) < 1e-3 * V0, f"kutu hacmi {V0:.1f}")
pi = math.pi


def clear():
    while len(body.cad.features):
        body.cad.features.remove(0)
    core.forget_cache(body.name)
    core.rebuild(body)


def tapped(pts, family="ISO_M", size="M6", through=False, depth=10.0, fit="NOMINAL",
           **thr):
    f = HL.new_feature(body, "TAPPED")
    TH.init_thread(f.thr, family, size, modeled=True, fit=fit)
    for k, v in thr.items():
        setattr(f.thr, k, v)
    f.hole_through = through
    f.hole_depth = depth
    f.hole_tip = 118.0
    for co, n in pts:
        h = f.hole_pts.add()
        h.co, h.nrm = co, n
    HL.apply_preset(f)
    core.rebuild(body)
    return f


TOP = [((20.0, 15.0, H), (0, 0, -1))]

# ---- 1) M6 kör, modellenmiş
f = tapped(TOP)
rem = V0 - vol()
sp = TH.spec(f.thr)
r_root, R = tm.radii(sp)
d = f.hole_d
L_t = 10.0 - 0.6 * f.thr.P
v_drill = pi * (d / 2) ** 2 * 10.0 + pi * (d / 2) ** 2 * (d / 2 / math.tan(math.radians(59))) / 3
v_major = pi * R * R * 10.0
check(f.ok and v_drill * 1.05 < rem < v_major, f"M6 kör dişli: çıkan {rem:.1f} (matkap "
      f"{v_drill:.1f} < · < tepe çapı {v_major:.1f}) · {f.info[:60]}")
poly, t_d, _h = tm.tooth_region(sp, 0.0, 1.0)
probe_r = r_root + 0.5 * (t_d + max(q[1] for q in poly))
hits = sum(inside(body, (20 + probe_r * math.cos(a), 15 + probe_r * math.sin(a), H - 5.0))
           for a in [k * 2 * pi / 24 for k in range(24)])
check(5 <= hits <= 19, f"diş halkasında malzeme ve boşluk birlikte (24 noktadan {hits} dolu)")
check(not inside(body, (20.0, 15.0, H - 3.0)), "eksen boş (matkap)")
check(inside(body, (20.0 + R + 0.3, 15.0, H - 3.0)), "tepe çapının dışı dolu")
V_m6 = rem

# ---- 1b) ağız pahlı dişli delik (giriş havşası)
fm = tapped([((8.0, 8.0, H), (0, 0, -1))], through=True)
fm.hole_mouth_d = 7.2
core.rebuild(body)
check(fm.ok and "modellenmiş" in fm.info and not inside(body, (8.0 + 3.45, 8.0, H - 0.1)),
      f"ağız pahlı geçen dişli delik: {fm.info[:50]}")
body.cad.features.remove(len(body.cad.features) - 1)
core.forget_cache(body.name)
core.rebuild(body)

# ---- 2) delikten uyumlu vida
scr, msg = TH.create_for_hole(C, body, f, 0, "SCREW")
check(scr is not None and "Kapalı katı" in scr.cad.status, f"uyumlu vida: {msg}")
check(abs(TH.mm(scr.cad.part.length) - 8.0) < 1e-6, f"vida boyu kör deliğe göre: "
      f"{TH.mm(scr.cad.part.length):g} mm")
o = scr.matrix_world.translation
z = scr.matrix_world.col[2].xyz
check((o - Vector((20, 15, H))).length < 1e-6 and z.dot(Vector((0, 0, 1))) > 0.999,
      f"vida deliğe yerleşti: başlangıç {tuple(round(x, 3) for x in o)}, eksen +Z")
vs = vol(scr)
hd = tm.head_dims("SOCKET", 6.0)
v_head = pi * (hd["dk"] / 2) ** 2 * hd["k"]
check(v_head * 0.8 < vs < v_head + pi * 9 * 8.0, f"vida hacmi {vs:.1f} (baş ≈ {v_head:.1f})")
# vida deliğin içinde: vidanın diş içi noktası, deliğin boşluğunda
check(inside(scr, (20.0, 15.0, H - 3.0)) and not inside(body, (20.0, 15.0, H - 3.0)),
      "vida çekirdeği deliğin boşluğunda")

# ---- 3) geçme: FDM boşluk → delik büyür, bağlı vida küçülür
f.thr.fit = "FDM"
TH.apply_fit(f.thr)
HL.apply_preset(f)
core.rebuild(body)
core.rebuild(scr)
rem2, vs2 = V0 - vol(), vol(scr)
check(rem2 > V_m6 and vs2 < vs, f"FDM boşluk {TH.mm(f.thr.clearance):.2f} mm: delik "
      f"{V_m6:.1f}→{rem2:.1f}, vida {vs:.1f}→{vs2:.1f}")
f.thr.swell = TH.u(0.1)
core.rebuild(body)
core.rebuild(scr)
check(V0 - vol() > rem2 and vol(scr) < vs2, "baskı genleşmesi: delik büyür, vida küçülür")

# ---- 4) sol el + 2 ağız: vida da sol / 2 ağız
f.thr.hand = "LEFT"
f.thr.starts = 2
core.rebuild(body)
core.rebuild(scr)
check(f.ok and "Kapalı katı" in scr.cad.status and "LEFT" in repr(TH.primitive(scr)["spec"]),
      f"sol el 2 ağızlı: delik {f.info[:40]} · vida {scr.cad.status[:40]}")
bpy.data.objects.remove(scr)
clear()

# ---- 5) profiller (geçen delik)
for fam, size in (("TR", "Tr10×2"), ("SQ", "Kare 10×2"), ("RD", "Rd10×1/8\""),
                  ("BUTT", "S10×2"), ("BSW", "1/4 BSW"), ("UNC", "1/4-20"),
                  ("ISO_MF", "M8×1"), ("BSP", "G1/8"), ("ACME", "1/4 ACME")):
    f = tapped(TOP, fam, size, through=True)
    rem = V0 - vol()
    sp = TH.spec(f.thr)
    r_root, R = tm.radii(sp)
    check(f.ok and pi * (f.hole_d / 2) ** 2 * H * 1.02 < rem < pi * R * R * H,
          f"{size}: geçen dişli delik, çıkan {rem:.1f} · {f.info[:45]}")
    clear()

# ---- 6) özel profil: eğriden (yarım daire benzeri)
pc = bpy.data.curves.new("Profil", "CURVE")
spl = pc.splines.new("POLY")
pts = [(math.cos(a), math.sin(a)) for a in [pi - k * pi / 8 for k in range(9)]]
spl.points.add(len(pts) - 1)
for p_, (x, y) in zip(spl.points, pts):
    p_.co = (x, y, 0, 1)
prof_ob = bpy.data.objects.new("Profil", pc)
sc.collection.objects.link(prof_ob)
f = tapped(TOP, "ISO_M", "M8", through=True)
f.thr.profile = "CUSTOM"
f.thr.family = "CUSTOM"
f.thr.custom_obj = prof_ob
f.thr.depth = TH.u(0.6)
HL.apply_preset(f)
core.rebuild(body)
check(f.ok and "modellenmiş" in f.info, f"özel profil (eğri): {f.info[:60]}")
clear()

# ---- 7) eski (v0.33) dişli delik: kozmetik kalır
f = HL.new_feature(body, "SIMPLE")
f.hole_kind = "TAPPED"
f.hole_thread = "M6"
f.hole_d = 5.0
f.hole_through = True
h = f.hole_pts.add()
h.co, h.nrm = TOP[0]
core.rebuild(body)
check(f.thr.inited and not f.thr.modeled and abs((V0 - vol()) - pi * 2.5 ** 2 * H) < 0.5,
      f"eski dişli delik göçü: kozmetik, Ø5 matkap ({V0 - vol():.1f})")
clear()

# ---- 8) kademeli geçme deliği + imbus vida + somun; havşa + havşa başlı vida
g = HL.new_feature(body, "CBORE")
g.hole_thread = "M5"
g.hole_through = True
HL.apply_preset(g)
h = g.hole_pts.add()
h.co, h.nrm = (10.0, 15.0, H), (0, 0, -1)
core.rebuild(body)
check(g.ok, f"M5 kademeli: {g.info[:50]}")
s2, msg = TH.create_for_hole(C, body, g, 0, "SCREW")
check(s2 is not None and s2.cad.part.head == "SOCKET" and "Kapalı katı" in s2.cad.status,
      f"kademeliye imbus vida: {msg}")
o = s2.matrix_world.translation
check(abs(o.z - (H - g.hole_cb_depth)) < 1e-4, f"vida başı yuva dibinde: z={o.z:.3f}")
n2, msg = TH.create_for_hole(C, body, g, 0, "NUT")
o = n2.matrix_world.translation
check(n2 is not None and "Kapalı katı" in n2.cad.status and abs(o.z) < 1e-3 and
      n2.matrix_world.col[2].xyz.z < -0.999, f"somun çıkış yüzünde: {msg} z={o.z:.4f}")
c = HL.new_feature(body, "CSINK")
c.hole_thread = "M4"
c.hole_through = True
HL.apply_preset(c)
h = c.hole_pts.add()
h.co, h.nrm = (30.0, 15.0, H), (0, 0, -1)
core.rebuild(body)
s3, msg = TH.create_for_hole(C, body, c, 0, "SCREW")
check(s3 is not None and s3.cad.part.head == "CSK" and "Kapalı katı" in s3.cad.status,
      f"havşaya havşa başlı vida: {msg}")

# ---- 9) bağımsız parçalar
sc.cursor.location = (60, 0, 0)
for head, drive in (("NONE", "HEXSOCKET"), ("HEX", "NONE"), ("BUTTON", "HEXSOCKET"),
                    ("CHEESE", "SLOT"), ("CSK", "CROSS")):
    ob = TH.create_free(C, "SCREW", "M5")
    ob.cad.part.head, ob.cad.part.drive = head, drive
    core.rebuild(ob)
    check("Kapalı katı" in ob.cad.status, f"bağımsız vida {head}/{drive}: {ob.cad.status[:50]}")
nut = TH.create_free(C, "NUT", "M8")
check("Kapalı katı" in nut.cad.status, f"bağımsız somun: {nut.cad.status[:50]}")
# vidaya delik (parça da bir BlendCAD gövdesi)
ob = TH.create_free(C, "SCREW", "M8")
ob.cad.part.head = "HEX"
core.rebuild(ob)
v1 = vol(ob)
hf = HL.new_feature(ob, "SIMPLE")
hf.hole_d, hf.hole_through = 2.0, True
hh = hf.hole_pts.add()
hh.co, hh.nrm = (8.0, 0.0, -10.0), (-1, 0, 0)
core.rebuild(ob)
check(hf.ok and vol(ob) < v1, f"vidaya çapraz delik (kopilya): {hf.info[:40]}")
# STEP
path = os.path.join(OUT or "/tmp", "vida.step")
from mini_cad import kernel  # noqa: E402,F401
try:
    geo.write_step(eng._final[ob.name]["shape"], path, 1.0)
    check(os.path.getsize(path) > 10000, f"STEP yazıldı ({os.path.getsize(path)} bayt)")
except Exception as e:
    check(False, f"STEP: {e}")

# ---- 10) pencereler
if OUT:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from pil_painter import PILPainter
    from mini_cad import blendcad, ribbon, ribbon_actions as ra, ribbon_formspecs as fs_
    clear()
    f = tapped(TOP, "ISO_M", "M6", fit="FDM")
    ra.form_state["hole_uid"] = f.uid
    ra.form_state["thr_adv_hole"] = [True]
    sc.minicad_target = body
    for fid, name, tab in (("HOLE", "pencere_delik.png", "HOLE"),
                           ("BOLT", "pencere_vida.png", "HOLE")):
        if fid == "BOLT":
            scr, _m = TH.create_for_hole(C, body, f, 0, "SCREW")
            ra.form_state["part"] = scr.name
            C.view_layer.objects.active = scr
        rb = ribbon.Ribbon(1.0)
        blendcad._setup_forms(rb)
        rb.tab = tab
        p = PILPainter(1300, 1500)
        rb.layout(p, 1300, 1500, 44, 300, 52)
        rb._anchor_x = rb._rect("btn", "HOLE")[0]
        t_, ic, spec, w_ = fs_.FORMS[fid]
        rb.open_form(fid, t_, ic, spec, w_)
        p.viewport()
        p.headers(52)
        rb.draw(p, 1300, 1500, 44, 300, 0.0, 52)
        p.save(os.path.join(OUT, name))
    print("PNG:", OUT)

print("SONUÇ:", "tamam" if not fails else f"{len(fails)} hata")
sys.exit(1 if fails else 0)
