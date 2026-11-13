# v0.25.0: Yüzeyi Böl — döngü kesimi (halka), bıçak, kenara nokta ekleme ve referans eşleme,
# kesimin gerçek yüzeye izdüşümü, modal araç
exec(open("t42.py").read().split("def tang():")[0])
ctx.region = region
import math
split = importlib.import_module("mini_cad.split")
sm = importlib.import_module("mini_cad.surfmath")

def check(cond, msg):
    print(("  tamam  " if cond else "  HATA   ") + msg)
    if not cond:
        raise SystemExit(1)

class Coll(list):
    def __init__(s, factory=None, *a): super().__init__(*a); s.f = factory
    def add(s):
        x = s.f(); s.append(x); return x
    def remove(s, i): del s[i]
    def clear(s): del s[:]
def segref(): return NS(obj=None, spline=0, seg=0)
def bevref(): return NS(obj=None, spline=0, seg=0, kind="FILLET", size=0.002)
def patchf(): return NS(name="Yüzey", segs=Coll(segref), curves=Coll(), method="AUTO", enabled=True,
                        blend="BODY", own_weight=False, tangent_weight=1.0, info="", ok=True)
def cref(): return NS(obj=None, spline=0, index=0, point=False)
def consf(): return NS(kind="AXIS", refs=Coll(cref), enabled=True, info="", ok=True)

def mk_spline(pts, cyclic=False, curve=None):
    """pts: [(co, hl, hr)] ya da düz noktalar (VECTOR)."""
    bl = BPList()
    for p in pts:
        if len(p) == 3 and not isinstance(p[0], (int, float)):
            co, hl, hr = p; tl = tr = "ALIGNED"
        else:
            co = hl = hr = p; tl = tr = "VECTOR"
        bl.append(BP(co=Vec(co), handle_left=Vec(hl), handle_right=Vec(hr), handle_left_type=tl, handle_right_type=tr))
    sp = Spline(type="BEZIER", bezier_points=bl, use_cyclic_u=cyclic, points=[])
    if all(b.handle_left_type == "VECTOR" for b in bl):       # VECTOR tutamaçları 1/3'te
        n = len(bl)
        for i, b in enumerate(bl):
            nx = bl[(i + 1) % n].co if (cyclic or i < n - 1) else None
            pv = bl[i - 1].co if (cyclic or i > 0) else None
            b.handle_right = b.co + (nx - b.co) / 3 if nx is not None else b.co
            b.handle_left = b.co + (pv - b.co) / 3 if pv is not None else b.co
    return sp

Splines.new = lambda s, t: (s.append(Spline(type="BEZIER", bezier_points=BPList([BP(co=None, handle_left=None, handle_right=None, handle_left_type="", handle_right_type="")]), use_cyclic_u=False, points=[])), s[-1])[1]
BPList.add = lambda s, n: s.extend(BP(co=None, handle_left=None, handle_right=None, handle_left_type="", handle_right_type="") for _ in range(n))

def setup(splines):
    cu.splines.clear()
    for sp in splines: cu.splines.append(sp)
    curve.cad.constraints = Coll(consf); curve.cad.links = Coll(); curve.cad.patches = []; curve.cad.features = []
    body = NS(name="CAD", type="MESH", cad=NS(is_cad=True, patches=Coll(patchf), features=[], bevels=Coll(bevref), constraints=[], links=[],
              join_tol=1e-3, active_patch=0), matrix_world=I4, data=None)
    bpy.data.objects = Objs({"Tel": curve, "CAD": body})
    ctx.active_object = body; ctx.scene.minicad_target = body; ctx.scene.objects = Objs({"Tel": curve, "CAD": body}); ctx.mode = "OBJECT"
    return body

def add_patch(body, refs, name):
    p = body.cad.patches.add(); p.name = name
    for si, k in refs:
        r = p.segs.add(); r.obj, r.spline, r.seg = curve, si, k
    return p

def keys(p): return sorted((r.spline, r.seg) for r in p.segs)

def plane_mesh(x0, x1, y0, y1, n=8):
    V, T = [], []
    for i in range(n + 1):
        for j in range(n + 1): V.append((x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * j / n, 0.0))
    for i in range(n):
        for j in range(n):
            a = i * (n + 1) + j; T += [(a, a + n + 1, a + n + 2), (a, a + n + 2, a + 1)]
    return sm.Mesh(V, T)

print("A) İki kare yüzey: ortak kenardan döngü kesimi iki yüzeyi halka olarak keser")
body = setup([mk_spline([(0,0,0),(2,0,0),(4,0,0)]), mk_spline([(0,2,0),(2,2,0),(4,2,0)]),
              mk_spline([(0,0,0),(0,2,0)]), mk_spline([(2,0,0),(2,2,0)]), mk_spline([(4,0,0),(4,2,0)])])
P0 = add_patch(body, [(0,0),(1,0),(2,0),(3,0)], "Yüzey")
P1 = add_patch(body, [(0,1),(1,1),(3,0),(4,0)], "Yüzey.1")
c_axis = curve.cad.constraints.add(); c_axis.kind = "AXIS"; r = c_axis.refs.add(); r.obj, r.spline, r.index = curve, 3, 0
c_len = curve.cad.constraints.add(); c_len.kind = "DISTANCE"; r = c_len.refs.add(); r.obj, r.spline, r.index = curve, 3, 0
c_pt = curve.cad.constraints.add(); c_pt.kind = "FIX"; r = c_pt.refs.add(); r.obj, r.spline, r.index, r.point = curve, 3, 1, True
feat = NS(segs=Coll(segref)); r = feat.segs.add(); r.obj, r.spline, r.seg = curve, 3, 0; body.cad.features.append(feat)
geoms = split.body_geoms(body, 1e-3)
check(all(g.ok and g.nsides == 4 for g in geoms), "iki yüzey de 4 kenarlı")
mesh = plane_mesh(0, 4, 0, 2)
cuts = split.ring_cuts(geoms, ("Tel", 3, 0), 0.5, mesh)
check(len(cuts) == 2, f"halka iki yüzeyden geçti ({len(cuts)} kesim)")
ys = [round(float(p[1]), 6) for c in cuts for p in c["pts"]]
check(all(abs(y - 1.0) < 1e-6 for y in ys), "kesimler y = 1 doğrusu")
n, ins, off = split.apply_cuts(body, cuts, 1e-3)
check(n == 2 and ins == 3 and off == 1, f"2 yüzey bölündü, 3 kenar noktası, 1 kısıt kapandı ({n}, {ins}, {off})")
check(len(body.cad.patches) == 4, "4 yüzey")
check([len(sp.bezier_points) for sp in cu.splines[2:5]] == [3, 3, 3] and len(cu.splines) == 7, "dikey kenarlara nokta, 2 kesim spline'ı")
check(np.allclose(cu.splines[3].bezier_points[1].co, (2, 1, 0)), "ortak kenarın ortasında yeni nokta")
check(all(cu.splines[3].bezier_points[i].handle_left_type == "VECTOR" for i in range(3)), "düz kenar düz kaldı (VECTOR)")
geoms = split.body_geoms(body, 1e-3)
check(all(g.ok and g.nsides == 4 for g in geoms), "bölünen 4 yüzey de kapalı döngü, 4 kenarlı")
areas = sorted(round(float(np.ptp(np.array(g.verts)[:, 0]) * np.ptp(np.array(g.verts)[:, 1])), 6) for g in geoms)
check(areas == [2.0, 2.0, 2.0, 2.0], f"her biri 2×1 ({areas})")
check(c_axis.enabled and not c_len.enabled and "bölündü" in c_len.info, "eksen kısıtı korundu, uzunluk kısıtı devre dışı")
check(c_pt.refs[0].index == 2, "nokta kısıtı kaydı (1 → 2)")
check(sorted((r.spline, r.seg) for r in feat.segs) == [(3, 0), (3, 1)], "fillet iki yarıyı da aldı")
check(keys(body.cad.patches[0]) != keys(body.cad.patches[2]) and body.cad.patches[2].name == "Yüzey.2", "yeni yüzey ayarları ve adı")

print("B) Bıçak: köşeden karşı kenarın ortasına (üçgen + dörtgen)")
body = setup([mk_spline([(0,0,0),(2,0,0),(2,2,0),(0,2,0)], cyclic=True)])
add_patch(body, [(0,0),(0,1),(0,2),(0,3)], "Kare")
geoms = split.body_geoms(body, 1e-3)
cut, err = split.knife_cut(geoms, np.array([0.0, 0, 0]), np.array([2.0, 1, 0]), plane_mesh(0, 2, 0, 2), tol=1e-3)
check(cut is not None, f"kesim planlandı {err}")
cut2, err2 = split.knife_cut(geoms, np.array([0.5, 0, 0]), np.array([1.5, 0, 0]), None, tol=1e-3)
check(cut2 is None and "farklı kenar" in err2, "aynı kenardaki iki nokta reddedilir")
n, ins, off = split.apply_cuts(body, [cut], 1e-3)
geoms = split.body_geoms(body, 1e-3)
check(n == 1 and ins == 1 and len(cu.splines[0].bezier_points) == 5, "kapalı spline'a nokta eklendi (köşede eklenmedi)")
check(sorted(g.nsides for g in geoms) == [3, 4], f"üçgen + dörtgen ({[g.nsides for g in geoms]})")

print("C) Yarım silindir: kesim gerçek yüzeyin üzerinde")
K = 0.5522847498
def arc(x):   # (x, 1, 0) → (x, -1, 0) üstten yarım daire, iki çeyrek
    return mk_spline([((x, 1, 0), (x, 1, -K), (x, 1, K)), ((x, 0, 1), (x, K, 1), (x, -K, 1)), ((x, -1, 0), (x, -1, K), (x, -1, -K))])
body = setup([arc(0.0), arc(2.0), mk_spline([(0,1,0),(2,1,0)]), mk_spline([(0,-1,0),(2,-1,0)])])
add_patch(body, [(0,0),(0,1),(1,0),(1,1),(2,0),(3,0)], "Silindir")
N = 48; V = []; T = []
for i in range(N + 1):
    a = math.pi * i / N
    for x in (0.0, 2.0): V.append((x, math.cos(a), math.sin(a)))
for i in range(N):
    q = 2 * i; T += [(q, q + 1, q + 3), (q, q + 3, q + 2)]
cyl = sm.Mesh(V, T)
geoms = split.body_geoms(body, 1e-3)
check(geoms[0].nsides == 4, "4 kenarlı (iki yay, iki doğru)")
cuts = split.ring_cuts(geoms, ("Tel", 2, 0), 0.5, cyl)
R = [abs(math.hypot(float(p[1]), float(p[2])) - 1.0) for p in cuts[0]["pts"]]
check(len(cuts) == 1 and max(R) < 2e-3, f"kesim silindirin üzerinde (sapma {max(R):.4f})")
n, ins, off = split.apply_cuts(body, cuts, 1e-3)
sp = cu.splines[-1]
segs = [np.array([tuple(sp.bezier_points[i].co), tuple(sp.bezier_points[i].handle_right), tuple(sp.bezier_points[i + 1].handle_left), tuple(sp.bezier_points[i + 1].co)]) for i in range(len(sp.bezier_points) - 1)]
S = np.vstack([[sm.bez(P, t) for t in np.linspace(0, 1, 9)] for P in segs])
dev = float(np.max(np.abs(np.hypot(S[:, 1], S[:, 2]) - 1.0)))
check(dev < 3e-3 and np.allclose(S[:, 0], 1.0, atol=1e-6), f"yazılan kesim eğrisi x=1 yarım çemberi ({len(segs)} segment, sapma {dev:.4f})")
pa = cu.splines[0].bezier_points
check(len(pa) == 3 and np.allclose(pa[1].co, (0, 0, 1)), "yaylar bölünmedi (kesim yayları köşeden kesti)")
check(len(cu.splines[2].bezier_points) == 3 and np.allclose(cu.splines[2].bezier_points[1].co, (1, 1, 0)), "doğrulara orta nokta")
geoms = split.body_geoms(body, 1e-3)
check(len(geoms) == 2 and all(g.ok and g.nsides == 4 for g in geoms), "iki çeyrek silindir yüzey")

print("D) Kenarı bölünemeyen spline (ilişki) reddedilir, hiçbir şey değişmez")
body = setup([mk_spline([(0,0,0),(2,0,0),(2,2,0),(0,2,0)], cyclic=True)])
add_patch(body, [(0,0),(0,1),(0,2),(0,3)], "Kare")
curve.cad.links = [NS(kind="RPAT", src="0", dst="")]
geoms = split.body_geoms(body, 1e-3)
cuts = split.ring_cuts(geoms, ("Tel", 0, 0), 0.5, None)
try:
    split.apply_cuts(body, cuts, 1e-3); ok = False
except split.CadError as e:
    ok = "ilişki" in str(e)
check(ok and len(cu.splines) == 1 and len(cu.splines[0].bezier_points) == 4 and len(body.cad.patches) == 1, "ilişkili spline: hata, değişiklik yok")
curve.cad.links = Coll()

print("E) Modal araç: kenara gel, tekerlek, tık")
body = setup([mk_spline([(0,0,0),(2,0,0),(4,0,0)]), mk_spline([(0,2,0),(2,2,0),(4,2,0)]),
              mk_spline([(0,0,0),(0,2,0)]), mk_spline([(2,0,0),(2,2,0)]), mk_spline([(4,0,0),(4,2,0)])])
add_patch(body, [(0,0),(1,0),(2,0),(3,0)], "Yüzey"); add_patch(body, [(0,1),(1,1),(3,0),(4,0)], "Yüzey.1")
split.body_mesh = lambda ob: plane_mesh(0, 4, 0, 2)
core.rebuild = lambda ob, preview=False: True
ctx.window_manager = NS(modal_handler_add=lambda op: None); ctx.workspace = NS(status_text_set=lambda t: None)
so = split.MINICAD_OT_split_surface.__new__(split.MINICAD_OT_split_surface); so.report = lambda *a: print("RAPOR", a)
check(so.invoke(ctx, NS()) == {"RUNNING_MODAL"} and len(so.edges) == 7, f"araç açıldı, {len(so.edges)} kenar")
def sev(t, p=None, val="PRESS", **kw):
    x, y = to_px(p) if p is not None else so.mouse
    return NS(type=t, value=val, mouse_x=x, mouse_y=y, shift=False, ctrl=kw.get("ctrl", False), alt=False, oskey=False)
so.modal(ctx, sev("MOUSEMOVE", (1.0, 0.0)))
check(so.hover is not None and len(so.preview) == 1, f"alt kenarda: 1 kesim önizlemesi ({len(so.preview)})")
so.modal(ctx, sev("WHEELUPMOUSE", (1.0, 0.0))); so.modal(ctx, sev("MOUSEMOVE", (1.0, 0.0)))
check(so.count == 2 and len(so.preview) == 2, "tekerlek: 2 kesim")
so.modal(ctx, sev("WHEELDOWNMOUSE", (1.0, 0.0)))
for k_ in ("ZERO", "PERIOD", "THREE"): so.modal(ctx, sev(k_))
so.modal(ctx, sev("MOUSEMOVE", (1.0, 0.0)))
xs = sorted({round(float(p[0]), 6) for c in so.preview for p in c["pts"]})
check(so.typed == "0.3" and xs == [0.6], f"yazılan oran 0.3: x = 0.6 ({xs})")
check(split._parse_ratio("30") == 0.3 and split._parse_ratio("150") is None, "30 → %30; 150 geçersiz")
so.modal(ctx, sev("LEFTMOUSE", (1.0, 0.0)))
check(len(body.cad.patches) == 3 and undo[-1] == "Mini CAD: Yüzeyi Böl", "tık: bölündü, geri alma adımı")
so.modal(ctx, sev("K")); check(so.mode == "KNIFE", "K: bıçak")
so.modal(ctx, sev("MOUSEMOVE", (4.0, 0.0))); so.modal(ctx, sev("LEFTMOUSE", (4.0, 0.0)))
check(len(so.knife) == 1 and np.allclose(so.knife[0], (4, 0, 0)), "köşeye yapıştı")
so.modal(ctx, sev("MOUSEMOVE", (2.0, 1.02)))
check(len(so.preview) == 1, "ikinci noktada önizleme")
so.modal(ctx, sev("LEFTMOUSE", (2.0, 1.02)))
check(len(body.cad.patches) == 4 and not so.knife, "bıçakla bölündü")
so.modal(ctx, sev("ESC"))
check(split._STATE["active"] is None, "Esc: kapandı")
print("F) v0.25.2: çok yüzeyli bıçak — yan yana üç kare, çapraz çizgi üçünü de keser")
body = setup([mk_spline([(0,0,0),(2,0,0),(4,0,0),(6,0,0)]), mk_spline([(0,2,0),(2,2,0),(4,2,0),(6,2,0)]),
              mk_spline([(0,0,0),(0,2,0)]), mk_spline([(2,0,0),(2,2,0)]), mk_spline([(4,0,0),(4,2,0)]), mk_spline([(6,0,0),(6,2,0)])])
add_patch(body, [(0,0),(1,0),(2,0),(3,0)], "A"); add_patch(body, [(0,1),(1,1),(3,0),(4,0)], "B"); add_patch(body, [(0,2),(1,2),(4,0),(5,0)], "C")
split.body_mesh = lambda ob: plane_mesh(0, 6, 0, 2, 12)
so = split.MINICAD_OT_split_surface.__new__(split.MINICAD_OT_split_surface); so.report = lambda *a: print("RAPOR", a)
so.invoke(ctx, NS())
so.modal(ctx, sev("K"))
so.modal(ctx, sev("MOUSEMOVE", (1.0, 0.0))); so.modal(ctx, sev("LEFTMOUSE", (1.0, 0.0)))
check(len(so.knife) == 1 and np.allclose(so.knife[0], (1, 0, 0)), "ilk nokta: A yüzeyinin alt kenarı ortası")
so.modal(ctx, sev("MOUSEMOVE", (5.0, 2.0)))
check(len(so.preview) == 3 and sorted(c["patch"] for c in so.preview) == [0, 1, 2], f"önizleme: üç yüzeyde üç parça ({len(so.preview)})")
ends = sorted(round(float(c["pts"][0][0]), 4) for c in so.preview)
check(ends == [1.0, 2.0, 4.0], f"parçalar ortak kenarlarda (x = 2, 4) birleşiyor ({ends})")
ys = sorted(round(float(p_[1]), 4) for c in so.preview for p_ in (c["pts"][0], c["pts"][-1]))
check(np.allclose(ys, [0, 0.5, 0.5, 1.5, 1.5, 2.0]), f"çizgi üzerinde: y = {ys}")
so.modal(ctx, sev("LEFTMOUSE", (5.0, 2.0)))
geoms = split.body_geoms(body, 1e-3)
check(len(body.cad.patches) == 6 and all(g.ok for g in geoms), f"6 yüzey, hepsi kapalı ({len(body.cad.patches)})")
check(len(cu.splines[3].bezier_points) == 3 and len(cu.splines[4].bezier_points) == 3, "ortak kenarlara birer nokta eklendi")
so.modal(ctx, sev("ESC")); so.modal(ctx, sev("ESC"))
print("G) Çizgi yüzeyin dışına çıkarsa kesim yok, açıklama var")
body = setup([mk_spline([(0,0,0),(2,0,0),(2,2,0),(0,2,0)], cyclic=True), mk_spline([(4,0,0),(6,0,0),(6,2,0),(4,2,0)], cyclic=True)])
add_patch(body, [(0,0),(0,1),(0,2),(0,3)], "Sol"); add_patch(body, [(1,0),(1,1),(1,2),(1,3)], "Sağ")
mm = sm.Mesh(np.vstack([plane_mesh(0, 2, 0, 2).V, plane_mesh(4, 6, 0, 2).V]), np.vstack([plane_mesh(0, 2, 0, 2).T, plane_mesh(0, 2, 0, 2).T + 81]))
split.body_mesh = lambda ob: mm
so = split.MINICAD_OT_split_surface.__new__(split.MINICAD_OT_split_surface); so.report = lambda *a: print("RAPOR", a)
so.invoke(ctx, NS()); so.modal(ctx, sev("K"))
so.modal(ctx, sev("MOUSEMOVE", (1.0, 0.0))); so.modal(ctx, sev("LEFTMOUSE", (1.0, 0.0)))
so.modal(ctx, sev("MOUSEMOVE", (5.0, 2.0)))
check(not so.preview and "dışına" in so.knife_err, f"boşluktan geçen çizgi: {so.knife_err}")
so.modal(ctx, sev("ESC")); so.modal(ctx, sev("ESC"))
print("H) Arkada kalan (gizli) kenarlar kesim noktası sayılmaz")
body = setup([mk_spline([(0,0,0),(4,0,0),(4,2,0),(0,2,0)], cyclic=True),
              mk_spline([(1,-1,-1),(3,-1,-1),(3,3,-1),(1,3,-1)], cyclic=True)])
add_patch(body, [(0,0),(0,1),(0,2),(0,3)], "Üst"); add_patch(body, [(1,0),(1,1),(1,2),(1,3)], "Alt")
top, low = plane_mesh(0, 4, 0, 2), plane_mesh(1, 3, -1, 3)
low.V[:, 2] = -1.0
mm = sm.Mesh(np.vstack([top.V, low.V]), np.vstack([top.T, low.T + len(top.V)]))
split.body_mesh = lambda ob: mm
so = split.MINICAD_OT_split_surface.__new__(split.MINICAD_OT_split_surface); so.report = lambda *a: print("RAPOR", a)
so.invoke(ctx, NS()); so.modal(ctx, sev("K")); so.modal(ctx, sev("V"))
check(so.view_proj, "V: görünüş izdüşümü (çok yüzeyli yol)")
so.modal(ctx, sev("MOUSEMOVE", (0.0, 1.0))); so.modal(ctx, sev("LEFTMOUSE", (0.0, 1.0)))
so.modal(ctx, sev("MOUSEMOVE", (4.0, 1.0)))
check(len(so.preview) == 1 and so.preview[0]["patch"] == 0, f"yalnızca üstteki yüzey, tek parça ({len(so.preview)}; alttaki kenarlar x = 1, 3 gizli)")
check(all(abs(float(p_[2])) < 1e-9 for p_ in so.preview[0]["pts"]), "kesim üst yüzeyde (z = 0)")
so.modal(ctx, sev("ESC")); so.modal(ctx, sev("ESC"))
print("t61 bitti")
