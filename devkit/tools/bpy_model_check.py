"""GERÇEK Blender (bpy modülü) + GERÇEK OCC ile BlendCAD araç pencerelerini basit bir modelde dener.

Kullanım (Blender 5.x bpy + cadquery-ocp-novtk 7.9 kurulu bir Python ile):
    python bpy_model_check.py <mini_cad klasörünün üst klasörü> <png çıktı klasörü>

Model: 12 tel kafes kenarından 6 yüzlü kapalı kutu (1 × 0.6 × 0.4 m). Her araç penceresi
(Gövde, Yüzeyler, Fillet, Boolean, Simetri, İşlem sırası, Ayarlar, Kısıtlar, Çekirdek,
Mesh → tel kafes, Kenar seçimi, Profil süpürme) gerçek veriyle kurulur, PNG'ye çizilir ve
pencerenin kendi denetimleriyle (tık, sürükle, yaz, liste) işlem yapılır; sonuç gövdenin
yeniden hesabıyla doğrulanır. Kalıcı (modal) araçlar arka planda çalışmadığı için kenar
seçimi yerine seçimi alan işlev doğrudan çağrılır (B / P'nin yaptığı).
"""
import os
import sys

ROOT, OUT = sys.argv[-2], sys.argv[-1]
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.makedirs(OUT, exist_ok=True)

import bpy  # noqa: E402
import addon_utils  # noqa: E402

from pil_painter import PILPainter  # noqa: E402

fails = []


def check(ok, msg):
    print(("  ok  " if ok else "  HATA ") + msg)
    if not ok:
        fails.append(msg)


def _raise(e):
    raise e


addon_utils.enable("mini_cad", default_set=True, handle_error=_raise)
from mini_cad import (blendcad, core, kernel, ribbon, ribbon_actions as ra,  # noqa: E402
                      ribbon_formspecs as fs, ui)

C = bpy.context
sc = C.scene
C.preferences.addons["mini_cad"].preferences.background = False     # Blender içinde hesap
check(kernel.kernel_available(), "OCC çekirdeği hazır")

# ---------------------------------------------------------------- model: kutu tel kafesi
L, W, H = 1.0, 0.6, 0.4
P = [(0, 0, 0), (L, 0, 0), (L, W, 0), (0, W, 0), (0, 0, H), (L, 0, H), (L, W, H), (0, W, H)]
EDGES = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5),
         (2, 6), (3, 7)]
cu = bpy.data.curves.new("TelKafes", "CURVE")
cu.dimensions = "3D"
for a, b in EDGES:
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(1)
    for bp, co in zip(sp.bezier_points, (P[a], P[b])):
        bp.co = co
        bp.handle_left_type = bp.handle_right_type = "VECTOR"
wire = bpy.data.objects.new("TelKafes", cu)
sc.collection.objects.link(wire)
FACES = [(0, 1, 2, 3), (4, 5, 6, 7), (0, 9, 4, 8), (2, 11, 6, 10), (1, 10, 5, 9),
         (3, 8, 7, 11)]
ok, msg = ui.apply_surface(C, "segs", [(wire, i, 0) for i in FACES[0]], new_body=True)
check(ok, f"ilk yüzey + yeni gövde: {msg}")
body = sc.minicad_target
for fc in FACES[1:]:
    ok, msg = ui.apply_surface(C, "segs", [(wire, i, 0) for i in fc])
    check(ok, f"yüzey: {msg}")
core.rebuild(body)
check("Kapalı katı" in body.cad.status, f"kutu kapalı katı: {body.cad.status}")
C.view_layer.objects.active = body


# ---------------------------------------------------------------- pencere yardımcıları

class Shot:
    """Şerit + açık pencere: kur, PNG'ye çiz, öğe bul, tıkla."""

    def __init__(self, tab, button, fid):
        self.rb = ribbon.Ribbon(1.0)
        blendcad._setup_forms(self.rb)
        self.rb.state_fn, self.rb.active_fn = ra.state, ra.active
        self.rb.tab = tab
        self.w, self.h = 1500, 900
        self.p = PILPainter(self.w, self.h)
        self.rb.layout(self.p, self.w, self.h, 44, 300, 52)
        r = self.rb._rect("btn", button)
        self.rb._anchor_x = r[0]
        title, icon, spec, width = fs.FORMS[fid]
        self.rb.open_form(fid, title, icon, spec, width)
        self.draw()

    def draw(self):
        self.p = PILPainter(self.w, self.h)
        self.p.viewport()
        self.p.headers(52)
        self.rb.draw(self.p, self.w, self.h, 44, 300, 0.0, 52)
        return self

    def save(self, name):
        self.draw()
        x0, y0, x1, y1 = self.rb.forms.box
        img = self.p.img
        s = 2
        crop = (0, 0, int(max(x1 + 40, self.rb.box[2] + 20) * s),
                int((self.h - y0 + 30) * s))
        img.crop(crop).save(os.path.join(OUT, name))

    def el(self, kind, text=None, name=None, pred=None):
        self.rb.forms.build()
        for e in self.rb.forms.els:
            if e["kind"] == kind and (text is None or e.get("text") == text) and \
                    (name is None or e.get("name") == name) and (pred is None or pred(e)):
                return e
        raise KeyError((kind, text, name))

    def click(self, e, dx=0.0):
        r = e["rect"]
        mx, my = (r[0] + r[2]) / 2 + dx, (r[1] + r[3]) / 2
        self.rb.press(mx, my, 0.0)
        self.rb.release(mx, my)
        self.draw()

    def type_into(self, e, text):
        r = e["rect"]
        mx, my = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
        self.rb.press(mx, my, 0.0)
        self.rb.release(mx, my)
        for ch in text:
            self.rb.key("X", ch)
        self.rb.key("RET")
        self.draw()

    def pick_drop(self, e, label):
        self.click(e)
        for r, val, nm in self.rb.forms.drop["rows"]:
            if nm == label:
                self.rb.press((r[0] + r[2]) / 2, (r[1] + r[3]) / 2, 0.0)
                self.draw()
                return True
        return False


def rebuild_ok(what):
    core.rebuild(body)
    check(body.cad.status.startswith(("Tamam", "Önizleme")) or "Kapalı katı" in body.cad.status,
          f"{what}: gövde yeniden hesaplandı ({body.cad.status})")


# ---------------------------------------------------------------- Gövde
s = Shot("SOLID", "BODY", "BODY")
s.save("f01_govde.png")
check(any(e["kind"] == "label" and "yüzey" in e.get("text", "") for e in s.rb.forms.els),
      "Gövde penceresi: özet satırı")

# ---------------------------------------------------------------- Yüzeyler
s = Shot("SURFACE", "SURF_LIST", "SURF_LIST")
rows = [e for e in s.rb.forms.els if e["kind"] == "listrow"]
check(len(rows) == 5, f"Yüzeyler: 6 yüzeyden 5 satır görünür ({len(rows)})")
s.click(rows[2])
check(body.cad.active_patch == 2, "Yüzeyler: satır seçimi")
s.pick_drop(s.el("prop", name="surface_blend"), "Teğet (G1)")
check(body.cad.surface_blend == "TANGENT", "Yüzeyler: birleşim Teğet")
s.save("f02_yuzeyler.png")
s.pick_drop(s.el("prop", name="surface_blend"), "Keskin (G0)")
rebuild_ok("Keskin birleşim")

# ---------------------------------------------------------------- Fillet
ok, msg = ui.add_feature(C, [(wire, 4, 0)])            # Kenar seçiminde B'nin yaptığı
check(ok, f"fillet eklendi: {msg}")
s = Shot("SOLID", "FILLET", "FILLET_R")
fe = s.el("prop", name="size")
s.type_into(fe, "0.05")
f = body.cad.features[body.cad.active_bevel]
check(abs(f.size - 0.05) < 1e-9, f"Fillet: ölçü pencereden yazıldı ({f.size})")
rebuild_ok("fillet 0.05")
s.click(s.el("seg", text="Pah"))
check(f.kind == "CHAMFER", "Fillet: tür Pah (bölmeli seçim)")
rebuild_ok("pah")
s.click(s.el("seg", text="Fillet"))
v = body.cad.default_bevel
db = s.el("prop", name="default_bevel")
s.click(db, dx=(db["rect"][2] - db["rect"][0]) / 2 - 4)  # sağ ok (alanın sağ ucu)
s.save("f03_fillet.png")
check(body.cad.default_bevel > v, f"Fillet: yeni ölçü alanının sağ oku arttırdı ({v} → {body.cad.default_bevel})")

# ---------------------------------------------------------------- Boolean
bpy.ops.mesh.primitive_cylinder_add(radius=0.12, depth=1.0, location=(0.5, 0.3, 0.2))
cyl = C.active_object
C.view_layer.objects.active = body
s = Shot("SOLID", "BOOL", "BOOL_DIFF")
check(s.pick_drop(s.el("prop", name="minicad_bool_tool"), cyl.name),
      "Boolean: ikincil obje listeden seçildi")
check(sc.minicad_bool_tool == cyl, "Boolean: ikincil = silindir")
s.click(s.el("button", text="Boolean ekle"))
bools = [x for x in body.cad.features if x.op == "BOOLEAN"]
check(len(bools) == 1 and bools[0].ok, f"Boolean: delik açıldı ({bools[0].info if bools else '-'})")
s.save("f04_boolean.png")
rebuild_ok("boolean")


def labels():
    at = body.data.attributes.get("cad_patch")
    return None if at is None else [d.value for d in at.data]


lab = labels()
check(lab is not None and len(lab) == len(body.data.polygons), "yüz etiketleri ('cad_patch') yazıldı")
check(set(range(6)) <= set(lab) and -1 in set(lab),
      f"6 yüzey + fillet / delik yüzleri (-1) ayrıldı: {sorted(set(lab))}")
# delik açılan üst yüz hâlâ kendi yaması: etiket 1'in üçgenleri düz, z = H ve alanı
# kutu üstü − fillet şeridi (0.05) − delik (π·0.12²)
up = [poly for i, poly in enumerate(body.data.polygons) if lab[i] == 1]
flat = all(poly.normal.z > 0.9999 and abs(poly.center.z - H) < 1e-6 for poly in up)
area = sum(poly.area for poly in up)
import math  # noqa: E402
want = L * W - L * 0.05 - math.pi * 0.12 ** 2
check(flat and abs(area - want) / want < 0.02,
      f"delikli üst yüz tek yamada: düz={flat}, alan {area:.4f} ≈ {want:.4f}")
fil = {lab[i] for i, poly in enumerate(body.data.polygons)
       if 0.05 < poly.normal.z < 0.95 and poly.normal.y < -0.05}
check(fil == {-1}, f"fillet yüzü hiçbir yamaya ait değil (-1): {fil}")

# ---------------------------------------------------------------- İşlem sırası
s = Shot("SOLID", "ORDER", "ORDER")
rows = [e for e in s.rb.forms.els if e["kind"] == "listrow"]
check(len(rows) == 2, "İşlem sırası: fillet + boolean")
s.click(rows[1])
first = body.cad.features[0].name
s.click(s.el("button", text="Yukarı"))
check(body.cad.features[0].name != first, "İşlem sırası: boolean yukarı taşındı")
s.save("f05_islem_sirasi.png")
rebuild_ok("sıra değişti")

# ---------------------------------------------------------------- Simetri
s = Shot("SURFACE", "SYM_BODY", "SYM_BODY")
s.click(s.el("prop", name="mirror_x"))
check(body.cad.mirror_x, "Simetri: X açıldı")
s.save("f06_simetri.png")
s.click(s.el("prop", name="mirror_x"))

# ---------------------------------------------------------------- Ayarlar / Kısıtlar / Çekirdek
s = Shot("TOOLS", "SETTINGS", "SETTINGS")
s.save("f07_ayarlar.png")
g = body.cad.ghost_bevel
s.click(s.el("prop", name="ghost_bevel"))
check(body.cad.ghost_bevel != g, "Ayarlar: hayalet aç / kapa")
s = Shot("CONSTRAIN", "CONS_LIST", "CONS_LIST")
s.save("f08_kisitlar.png")
s.click(s.el("prop", name="minicad_show_constraints"))
check(sc.minicad_show_constraints is False, "Kısıtlar: Göster kapandı")
s = Shot("TOOLS", "KERNEL", "KERNEL")
s.save("f09_cekirdek.png")
s = Shot("SURFACE", "WIRE_MESH", "WIRE_MESH")
s.save("f10_mesh_tel_kafes.png")
s = Shot("SURFACE", "EDGE_PICK", "EDGE_PICK")
s.save("f11_kenar_secimi.png")

# ---------------------------------------------------------------- Profil süpürme
prof = bpy.data.curves.new("Profil", "CURVE")
sp = prof.splines.new("POLY")
sp.points.add(2)
for pt, co in zip(sp.points, ((0, 0, 0, 1), (0.05, 0, 0, 1), (0, 0.05, 0, 1))):
    pt.co = co
sp.use_cyclic_u = True
pob = bpy.data.objects.new("Profil", prof)
sc.collection.objects.link(pob)
s = Shot("SOLID", "SWEEP", "SWEEP")
check(s.pick_drop(s.el("prop", name="minicad_sweep_profile"), "Profil"),
      "Süpürme: profil listeden seçildi")
ok, msg = ui.add_sweep(C, [(wire, 5, 0)])              # Kenar seçiminde P'nin yaptığı
check(ok, f"Süpürme eklendi: {msg}")
s.save("f12_supurme.png")

# ---------------------------------------------------------------- STEP
path = os.path.join(OUT, "kutu.step")
r = bpy.ops.minicad.export_step(filepath=path)
check(r == {"FINISHED"} and os.path.getsize(path) > 1000, f"STEP yazıldı ({os.path.getsize(path)} B)")

# ---------------------------------------------------------------- sağ tık menüleri (v0.30.0)
from mini_cad import ribbon_ctx as rc  # noqa: E402


def run(menu, text):
    title, icon, items = menu
    for it in items:
        if it.get("text") == text:
            it["fn"]()
            return True
    raise KeyError(text)


m = rc.menu_for({"kind": "PATCH", "obj": body.name, "patch": 3})
check(m is not None and "Yüzey 4" in m[0], f"yüzey menüsü: {m and m[0]}")
run(m, "Teğet (G1)")
check(body.cad.patches[3].blend == "TANGENT", "menü: yüzey birleşimi Teğet")
run(rc.menu_for({"kind": "PATCH", "obj": body.name, "patch": 3}), "Gövde ayarı")
mb = rc.menu_for({"kind": "BODYFACE", "obj": body.name})
check(mb is not None and any(it.get("text") == "Fillet / pah…" for it in mb[2]), "işlem yüzü menüsü")
# eğri sil (bağlı referanslar eşlenir)
cu2 = bpy.data.curves.new("Ek", "CURVE")
for x in (0.0, 1.0):
    sp = cu2.splines.new("POLY")
    sp.points.add(1)
    sp.points[0].co = (x, 2, 0, 1)
    sp.points[1].co = (x, 3, 0, 1)
ek = bpy.data.objects.new("Ek", cu2)
sc.collection.objects.link(ek)
run(rc.menu_for({"kind": "CURVE", "obj": "Ek", "spline": 0}), "Bu eğriyi sil")
check(len(ek.data.splines) == 1 and abs(ek.data.splines[0].points[0].co.x - 1.0) < 1e-9,
      "menü: eğri silindi, diğeri kaldı")
# yüzey sil (üstteki delikli yüz)
n0 = len(body.cad.patches)
run(rc.menu_for({"kind": "PATCH", "obj": body.name, "patch": 1}), "Yüzeyi sil")
check(len(body.cad.patches) == n0 - 1, f"menü: yüzey silindi ({n0} → {len(body.cad.patches)})")
check("Kapalı katı" not in body.cad.status and body.cad.status.startswith("Tamam"),
      f"gövde yeniden hesaplandı, artık açık kabuk: {body.cad.status}")
lab = labels()
check(lab is not None and 1 in set(lab) and max(lab) <= n0 - 2,
      f"etiketler yeni yüzey sırasına göre: {sorted(set(lab))}")

print("SONUÇ:", "tamam" if not fails else f"{len(fails)} hata")
sys.exit(1 if fails else 0)
