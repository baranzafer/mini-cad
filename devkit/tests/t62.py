# v0.25.3: çizim araçlarında klavyeden ölçü girişi — yaylar (3 noktalı, merkezli, teğet) ve
# diğer araçların denetimi (doğru, daire, dikdörtgen, CV / noktalardan geçen spline, kalem)
exec(open("t42.py").read().split("def tang():")[0])
ctx.region = region
import math

def check(cond, msg):
    print(("  tamam  " if cond else "  HATA   ") + msg)
    if not cond:
        raise SystemExit(1)

def reset(tool):
    op.sketch.clear(); op.segs = []; op.start = None; op.stage = []; op._hist_reset()
    op.typed, op.field = ["", ""], 0
    ctx.scene.minicad_auto_constraints = False
    op._set_plane("XY"); op._set_tool(ctx, tool); op.dirty = True

def typ2(t):
    for ch in t:
        op.modal(ctx, ev("ONE", None, uni=ch))

def P(x): return np.asarray(x, dtype=float)[:2]

def arc_pts(segs, n=9):
    out = []
    for sg in segs:
        p = [np.asarray(q, float) for q in sg["p"]]
        for t in np.linspace(0, 1, n):
            m = 1 - t
            out.append(m**3 * p[0] + 3*m*m*t * p[1] + 3*m*t*t * p[2] + t**3 * p[3])
    return np.array(out)

print("A) 3 noktalı yay: bitiş noktası (uzunluk), eğrilik (yarıçap)")
reset("ARC3")
click((0, 0)); move((1, 0))
check(op._fields() == ("Uzunluk", "Açı"), f"1. adım alanları: {op._fields()}")
typ2("2"); key("RET")
check(len(op.stage) == 1 and np.allclose(P(op.stage[0]), (2, 0)), f"bitiş noktası uzunluk 2: {P(op.stage[0])}")
check(op.typed == ["", ""], "yazılan sıfırlandı (sonraki adım ayrı)")
move((1, 0.3))
check(op._fields() == ("Yarıçap", "Yay açısı"), f"2. adım alanları: {op._fields()}")
typ2("1.25"); move((1, 0.3))
check(abs(op.arc_info["radius"] - 1.25) < 1e-9, f"önizleme yarıçapı 1.25: {op.arc_info['radius']}")
key("RET")
A = arc_pts(op.segs)
check(np.allclose(A[0][:2], (0, 0)) and np.allclose(A[-1][:2], (2, 0)), "yay uçları (0,0)–(2,0)")
check(abs(A[:, 1].max() - 0.5) < 1e-6, f"imleç yanında, yükseklik 0.5 (R 1.25): {A[:, 1].max():.6f}")
check(np.allclose(np.linalg.norm(A[:, :2] - (1, -0.75), axis=1), 1.25, atol=2e-3), "noktalar R 1.25 çemberinde")

print("B) 3 noktalı yay: yay açısı (180°, 270° büyük yay), imlecin öbür yanında")
for deg, h in (("180", 1.0), ("270", 2.0 / (2 * math.sin(math.radians(135))) * (1 - math.cos(math.radians(135))))):
    reset("ARC3")
    click((0, 0)); click((2, 0)); move((1, -0.3))
    key("TAB"); typ2(deg); move((1, -0.3)); key("RET")
    A = arc_pts(op.segs)
    check(abs(-A[:, 1].min() - h) < 2e-3 and A[:, 1].max() < 1e-9, f"{deg}°: aşağı doğru derinlik {h:.4f} ({-A[:, 1].min():.4f})")

print("C) Merkezli yay: merkez, başlangıç (yarıçap / açı merkeze göre), bitiş (yay açısı)")
reset("CARC")
click((0, 0))
check(op.stage and np.allclose(P(op.stage[0]), (0, 0)), "ilk tık: merkez")
move((1, 0.2))
check(op._fields() == ("Yarıçap", "Açı"), f"başlangıç adımı alanları: {op._fields()}")
typ2("1.5"); key("TAB"); typ2("0"); key("RET")
check(op.start is not None and np.allclose(P(op.start), (1.5, 0)), f"başlangıç merkezden 1.5, 0°: {P(op.start) if op.start is not None else None}")
move((0.3, 1.0))
check(op._fields() == ("Yay açısı", None), f"bitiş adımı: {op._fields()}")
typ2("90"); move((0.3, 1.0)); key("RET")
A = arc_pts(op.segs)
check(np.allclose(np.linalg.norm(A[:, :2], axis=1), 1.5, atol=2e-3), "yay merkez (0,0), R 1.5")
check(np.allclose(A[-1][:2], (0, 1.5), atol=1e-6), f"90°, imlecin yanında bitiş (0, 1.5): {A[-1][:2]}")
reset("CARC")
click((0, 0)); click((1.5, 0)); move((0.3, 1.0)); typ2("200"); move((0.3, 1.0)); key("RET")
A = arc_pts(op.segs)
ang = math.degrees(math.atan2(A[-1][1], A[-1][0])) % 360
check(abs(ang - 200) < 1e-3 and A[:, 1].max() > 1.4, f"200° (büyük yay), yukarıdan dolanır: bitiş açısı {ang:.2f}")
reset("LINE")
click((-1, 0)); click((0, 0)); op._set_tool(ctx, "CARC")
move((0.2, 1.0))
check(op._fields() == ("Yarıçap", "Açı"), "zincirden: merkez adımı (önceki uçtan uzaklık / açı)")
typ2("1"); key("TAB"); typ2("90"); key("RET")
check(np.allclose(P(op.stage[0]), (0, 1)), f"merkez (0, 1): {P(op.stage[0])}")
move((1.2, 1.0)); typ2("90"); move((1.2, 1.0)); key("RET")
A = arc_pts(op.segs[-1:])
check(np.allclose(A[-1][:2], (1, 1), atol=1e-6), f"zincirde 90° yay bitişi (1, 1): {A[-1][:2]}")

print("D) Teğet yay: yarıçap ve yay açısı")
reset("LINE")
click((0, 0)); click((1, 0))
op._set_tool(ctx, "TARC"); move((1.5, 0.5))
check(op._fields() == ("Yarıçap", "Yay açısı"), f"teğet yay alanları: {op._fields()}")
typ2("0.5"); key("TAB"); typ2("90"); move((1.5, 0.5)); key("RET")
A = arc_pts(op.segs[-1:])
check(np.allclose(A[-1][:2], (1.5, 0.5), atol=1e-6), f"R 0.5, 90°: bitiş (1.5, 0.5): {A[-1][:2]}")
check(np.allclose(np.linalg.norm(A[:, :2] - (1, 0.5), axis=1), 0.5, atol=2e-3), "merkez (1, 0.5)")
sg0 = op.segs[-1]["p"]; t0 = (np.asarray(sg0[1], float) - np.asarray(sg0[0], float))[:2]
check(abs(t0[1]) < 1e-3 * np.linalg.norm(t0) and t0[0] > 0, "doğruya teğet başlıyor")
reset("LINE")
click((0, 0)); click((1, 0))
op._set_tool(ctx, "TARC"); move((1.3, -0.8)); typ2("0.4"); move((1.3, -0.8)); key("RET")
A = arc_pts(op.segs[-1:])
check(np.allclose(np.linalg.norm(A[:, :2] - (1, -0.4), axis=1), 0.4, atol=2e-3), "yalnız yarıçap: imlecin yanında (aşağı) R 0.4")

print("E) Diğer araçlar: doğru, daire, dikdörtgen, CV, noktalardan geçen spline, kalem")
reset("LINE"); click((0, 0)); move((1, 1)); typ2("2"); key("TAB"); typ2("30"); key("RET")
e = P(op.segs[-1]["p"][3])
check(np.allclose(e, (2 * math.cos(math.radians(30)), 1.0), atol=1e-6), f"doğru 2 / 30°: {e}")
reset("CIRCLE"); click((0, 0)); move((1, 0)); typ2("1.5"); key("RET")
pts = arc_pts(op.sketch[-1]["segs"]) if op.sketch else arc_pts(op.segs)
check(np.allclose(np.linalg.norm(pts[:, :2], axis=1), 1.5, atol=2e-3), "daire yarıçap 1.5")
reset("RECT"); click((0, 0)); move((1, 1)); typ2("2"); key("TAB"); typ2("0.5"); key("RET")
pts = np.array([P(sg["p"][0]) for sg in (op.sketch[-1]["segs"] if op.sketch else op.segs)])
check(np.allclose(pts.max(axis=0), (2, 0.5)), f"dikdörtgen 2 × 0.5: {pts.max(axis=0)}")
for tool in ("CV", "FIT"):
    reset(tool); click((0, 0)); move((1, 0)); typ2("2"); key("RET")
    check(len(op.stage) == 1 and np.allclose(P(op.stage[0]), (2, 0)), f"{tool}: sonraki nokta uzunluk 2 ({P(op.stage[0]) if op.stage else None})")
reset("PEN"); click((0, 0)); move((1, 0)); typ2("2"); key("RET")
e = P(op.segs[-1]["p"][3]) if op.segs else None
check(e is not None and np.allclose(e, (2, 0)), f"kalem: nokta uzunluk 2 ({e})")
print("F) Yeni eğri: gizli koleksiyon / yerel görünüm (Outliner'da var, görünümde yok sorunu)")
linked = []
class C_(NS): pass
def coll(name, hidden=False):
    c = C_(name=name, hide_viewport=hidden); c.objects = NS(link=lambda o, c=c: linked.append((c.name, o.name))); return c
scene_coll, act = coll("Scene Collection"), coll("Gizli")
lc_act = NS(collection=act, exclude=False, hide_viewport=True, children=[])
ctx.view_layer = NS(layer_collection=NS(collection=scene_coll, exclude=False, hide_viewport=False, children=[lc_act]))
ctx.scene.collection = scene_coll; ctx.collection = act
bpy.data.curves = NS(new=lambda n, t: NS(splines=Splines([]), dimensions="2D", update_tag=lambda: None))
lv = []
bpy.data.objects.new = lambda n, cu_: NS(name=n, data=cu_, local_view_set=lambda sp, v: lv.append(v))
op.area.spaces.active.local_view = None
o = op._new_curve(ctx)
check(linked[-1] == ("Scene Collection", "CAD_TelKafes") and not lv, f"etkin koleksiyon gizli: sahne koleksiyonuna ({linked[-1]})")
lc_act.hide_viewport = False
op.area.spaces.active.local_view = object()
o = op._new_curve(ctx)
check(linked[-1] == ("Gizli", "CAD_TelKafes") and lv == [True], "görünür etkin koleksiyon + yerel görünüm: oraya ve yerel görünüme")
op.area.spaces.active.local_view = None
print("t62 bitti")
