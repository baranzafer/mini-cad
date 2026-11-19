"""GERÇEK Blender + OCC: uzun hesap koruması (v0.35.0).

Kullanım: python bpy_longcalc_check.py <mini_cad'in üst klasörü> [çıktı.png]

1) Süre sınırı (Blender içinde hesap): kutu + delik + ekstrüzyon + fillet; sınır çok küçük
   → ilk işlemden sonra durur: kısmi gövde (yalnız delik), kalanlar "Bekliyor", soru
   (Devam et / Her zaman tamamı / Yavaş işlemi kapat / Böyle bırak), Öneriler'de bulgu.
   Devam et → tam hacim. Her zaman tamamı → gövde ayarı. Yavaş işlemi kapat.
2) Arka plan süreci: uzun iş (test_sleep) → senkron çağrı 0.5 sn'de döner (Blender
   donmaz), ilerleme okunur, Durdur süreci kapatır, sonraki iş yeni süreçte çalışır;
   bekleme sınırını aşan işin sonucu sonradan gelir; önceki iş sürerken yeniden hesap
   "Sırada" olur ve iş bitince zamanlayıcıyla hesaplanır.
3) Bildirim merkezi: düğmeli soru çizilir, düğmeye basınca işlev çalışır, soru kalkar.
"""
import math
import sys
import time

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
eng = next(m for n, m in sys.modules.items()
           if isinstance(getattr(m, "_final", None), dict) and hasattr(m, "_bool_new"))
geo = next(m for n, m in sys.modules.items() if n.endswith(".geometry") and hasattr(m, "apply_extrude"))
from mini_cad import extrude, health, hole, jobs, notify  # noqa: E402

prefs = C.preferences.addons["mini_cad"].preferences


def vol():
    return geo.volume(eng._final[body.name]["shape"]) if body.name in eng._final else None


def shown_vol():
    """Görünen (yazılan) mesh hacmi — kısmi sonuçta _final güncellenmez."""
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(body.data)
    v = bm.calc_volume()
    bm.free()
    return abs(v)


asks = []
core.ASK_HOOKS.append(lambda k, lv, t, a: asks.append((k, lv, t, a)))

# ---- 1) süre sınırı
h1 = hole.new_feature(body, "SIMPLE")
h1.hole_thread, h1.hole_d, h1.hole_through = "NONE", 0.1, True
pt = h1.hole_pts.add()
pt.co, pt.nrm = (0.3, 0.3, H), (0, 0, -1)
ex = extrude.new_feature(body, "LINEAR")
ep = ex.ext_pts.add()
ep.co, ep.nrm = (L, 0.3, 0.2), (1, 0, 0)
ex.ext_dist = 0.2
h2 = hole.new_feature(body, "SIMPLE")
h2.hole_thread, h2.hole_d, h2.hole_through = "NONE", 0.1, True
pt = h2.hole_pts.add()
pt.co, pt.nrm = (0.7, 0.3, H), (0, 0, -1)
r = 0.05
V_hole = math.pi * r * r * H
V_full = 0.24 - 2 * V_hole + 0.6 * 0.4 * 0.2

prefs.calc_budget = 0.0
core.rebuild(body)
check(abs(vol() - V_full) < 1e-6, f"sınırsız: tam hacim {vol():.6f} ({V_full:.6f})")

prefs.calc_budget = 1e-6                # her şey sınırı aşar: yalnız ilk işlem
asks.clear()
core._final_sig.pop(body.name, None)
core.forget_cache(body.name)
core.rebuild(body)
p = core.PARTIAL.get(body.name)
check(p is not None and p["done"] == 1 and p["total"] == 3, f"kısmi: {p and (p['done'], p['total'])}")
check(body.cad.status.startswith("Kısmi"), f"durum: {body.cad.status[:90]}")
check(h1.ok and "Bekliyor" not in h1.info and "Bekliyor" in ex.info and "Bekliyor" in h2.info,
      f"ilk işlem yapıldı, kalanlar bekliyor ({ex.info[:30]})")
sv = shown_vol()
check(abs(sv - (0.24 - V_hole)) < 2e-3, f"görünen gövde yalnız ilk delikli: {sv:.4f} ({0.24 - V_hole:.4f})")
q = [a for a in asks if a[0] == "calc:" + body.name and a[1]]
labels = [x[0] for x in q[-1][3]] if q else []
check(labels[:2] == ["Devam et", "Her zaman tamamı"] and "Böyle bırak" in labels,
      f"soru: {labels}")
check("Tamamı hesaplansın mı?" in (q[-1][2] if q else ""), f"soru metni: {(q[-1][2] if q else '')[:120]}")
fs = [f for k, n, ff in health.all_findings() if k == "calc:" + body.name for f in ff]
check(fs and fs[0]["fixes"][0][0].startswith("Tamamla"), "Öneriler'de de soruluyor")
check(body.name not in eng._final or abs(vol() - V_full) < 1e-6,
      "kısmi şekil 'son tam şekil' sayılmadı (denetim / önizleme tabanı olmaz)")

# bildirim merkezindeki düğme: Devam et
from pil_painter import PILPainter  # noqa: E402
nc = notify.CENTER
nc.items, nc.asks = [], {}
k, lv, t, acts = q[-1]
nc.ask(k, lv, t, acts, 0.0)
pp = PILPainter(900, 600)
pp.viewport()
nc.draw(pp, 1.0, 10, 10, 440, 0.0)
if PNG:
    pp.save(PNG)
check(len(nc.btns) == len(acts), f"düğmeler çizildi: {len(nc.btns)}")
r0 = nc.btns[0][0]
nc.press((r0[0] + r0[2]) / 2, (r0[1] + r0[3]) / 2)   # "Devam et"
check(k not in nc.asks, "karar verilince soru kalktı")
check(body.name in core._unlimited_once and body.name not in core.PARTIAL, "Devam et: sınırsız sıraya girdi")
core.rebuild(body)                        # (Blender'da zamanlayıcı yapar)
check(abs(vol() - V_full) < 1e-6 and not core.PARTIAL.get(body.name),
      f"tamamlandı: {vol():.6f} · {body.cad.status[:40]}")
core.rebuild(body)
check(body.name not in core.PARTIAL, "değişmeyen gövde önbellekten anında: sınıra takılmaz")
core.forget_cache(body.name)
core.rebuild(body)
check(body.name in core.PARTIAL, "bir sonraki gerçek hesapta sınır yine geçerli (tek seferlik)")
core.continue_full(body.name, always=True)
check(body.cad.full_calc, "Her zaman tamamı: gövde ayarı açıldı")
core.rebuild(body)
check(body.name not in core.PARTIAL and abs(vol() - V_full) < 1e-6, "full_calc: sınırsız")
body.cad.full_calc = False
core.forget_cache(body.name)
core.rebuild(body)
p = core.PARTIAL.get(body.name)
msg = core.disable_features(body.name, p["slow"]["uids"]) if p and p["slow"] else ""
check(msg.startswith("Kapatıldı") and sum(1 for f in body.cad.features if not f.enabled) == 1,
      f"yavaş işlemi kapat: {msg}")
for f in body.cad.features:
    f.enabled = True
prefs.calc_budget = 8.0
core.rebuild(body)
check(abs(vol() - V_full) < 1e-6 and not core.PARTIAL.get(body.name), "8 sn sınırda tam hesap")

# ---- 2) arka plan süreci
prefs.background = True
c = jobs.client()
c.stop()
c.want_process = True
c.ensure()
t0 = time.time()
while c.mode == "starting" and time.time() - t0 < 60:
    c.poll()
    time.sleep(0.05)
check(c.mode == "process", f"arka plan süreci: {c.describe()}")
if c.mode == "process":
    t0 = time.time()
    late = {}
    res = c.call("test_sleep", {"steps": 12, "dt": 0.25}, wait_limit=0.5,
                 on_late=lambda r: late.setdefault("r", r), tag="Uzun")
    dt = time.time() - t0
    check(res.get("pending") and dt < 1.5, f"senkron çağrı bekleme sınırında döndü ({dt:.2f} sn)")
    time.sleep(0.8)
    c.poll()
    rr = core.running()
    check(rr is not None and rr["name"] == "Uzun" and rr["progress"].startswith("bekleme"),
          f"süren iş ve ilerleme: {rr}")
    n = core.cancel_running()
    check(n == "Uzun" and c.mode == "off" and core.running() is None, f"Durdur: {n}, mod {c.mode}")
    res = c.call("ping", {}, wait_limit=30)
    check(res.get("ok") and c.mode == "process", "durdurduktan sonra yeni süreçte hesap")
    late = {}
    res = c.call("test_sleep", {"steps": 4, "dt": 0.25}, wait_limit=0.2,
                 on_late=lambda r: late.setdefault("r", r), tag="Geç")
    t0 = time.time()
    while "r" not in late and time.time() - t0 < 10:
        c.poll()
        time.sleep(0.05)
    check(res.get("pending") and late.get("r", {}).get("slept") == 4, "geç gelen sonuç sonradan işlendi")
    # önceki iş sürerken yeniden hesap: Sırada → zamanlayıcı
    c.submit("test_sleep", {"steps": 14, "dt": 0.25}, lambda r: None, tag="Önceki")
    old_sync = core.SYNC_WAIT
    core.SYNC_WAIT = 0.5
    t0 = time.time()
    ok = core.rebuild(body)
    dt = time.time() - t0
    core.SYNC_WAIT = old_sync
    check(not ok and body.cad.status.startswith("Sırada") and dt < 1.5,
          f"önceki iş sürerken: '{body.cad.status[:40]}' ({dt:.2f} sn)")
    t0 = time.time()
    while time.time() - t0 < 60:
        core._tick()
        if body.cad.status.startswith("Tamam") and not c.busy():
            break
        time.sleep(0.05)
    check(body.cad.status.startswith("Tamam"), f"sonra arka planda hesaplandı: {body.cad.status[:50]}")
    # durdurulan gövde değişene kadar bekler
    c.submit("test_sleep", {"steps": 20, "dt": 0.25}, lambda r: None, tag=body.name)
    time.sleep(0.3)
    core.cancel_running()
    check(body.name in core.HELD and "durduruldu" in body.cad.status, "gövde durduruldu, bekletiliyor")
    core.schedule(body)
    check(core._next_job() is None, "bekletilen gövde kendiliğinden yeniden hesaplanmaz")
    ex.ext_dist = 0.25                   # kullanıcı bir şey değiştirdi
    core.schedule(body)
    nj = core._next_job()
    check(nj is not None and body.name not in core.HELD, "değişiklik yapınca yeniden hesaplanır")
    c.stop()
prefs.background = False

print("SONUÇ:", "tamam" if not fails else f"{len(fails)} hata")
sys.exit(1 if fails else 0)
