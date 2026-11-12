# v0.20.0: eksikler (1. parti) — referans ölçü, merkez mesafesi, yaylarda eşit yarıçap,
# otomatik ölçü, ölçü çizgileri, ayrı iki doğruda köşe, X / Y hassas giriş, merkez noktalı yay
# kanal, düzenle araçlarında noktalar
exec(open("t42.py").read().split("def tang():")[0])
ctx.region = region
ca = importlib.import_module("mini_cad.constraints_arcs")
cg = importlib.import_module("mini_cad.constraints_glyphs")
sm = importlib.import_module("mini_cad.sketchmath")

def check(cond, msg):
    print(("  tamam  " if cond else "  HATA   ") + msg)
    if not cond:
        raise SystemExit(1)

def reset(auto=False):
    cu.splines.clear(); curve.cad.constraints.clear(); cmod._last_pos.clear()
    op.sketch.clear(); op.sk_points.clear(); op._hist_reset(); op.temp = op.temp_pick = None
    op.coord_mode = False
    ctx.scene.minicad_auto_constraints = auto
    op._set_plane("XY"); op._set_tool(ctx, "LINE"); op.dirty = True

def co(si, i):
    return np.asarray(cu.splines[si].bezier_points[i].co, dtype=float)

def line(a, b):
    op._set_tool(ctx, "LINE"); click(a); click(b); key("RET")

def finish():
    key("RET", ctrl=True); op.dirty = True

def ctool(k):
    op._set_tool(ctx, "C_" + k); op.dirty = True

def drag(a, b):
    move(a); op.modal(ctx, ev("LEFTMOUSE", a)); move(b); op.modal(ctx, ev("LEFTMOUSE", b, val="RELEASE"))

def cons():
    return list(curve.cad.constraints)

def for_cons(c):            # stub kısıt nesnesine yeni alanlar
    if not hasattr(c, "driven"):
        c.driven = False

_orig_add = cmod.add
def add_(*a, **k):
    c = _orig_add(*a, **k)
    if c is not None:
        for_cons(c)
    return c
cmod.add = add_

print("A) Referans ölçü: çelişen ölçü referans olur, geometri bozulmaz, değeri ölçülür")
reset(); line((0, 0), (2, 0)); finish()
ctool("DIM"); click((1, 0)); key("RET"); typ("3"); key("RET")
c1 = cons()[0]
check(abs(np.linalg.norm(co(0, 1) - co(0, 0)) - 3) < 1e-6, "1. ölçü 3 uygulandı")
p0 = (co(0, 0).copy(), co(0, 1).copy())
click((1.5, 0)); key("RET")
c2 = cons()[-1]
check(len(cons()) == 2, "ikinci ölçü eklendi")
op.dim_edit = None; op.typed = ["", ""]
c2.length = 5.0; c2.driven = False
cmod.solve_all(ctx.scene, force=True, dry=True)
check(not c2.ok and np.allclose(co(0, 0), p0[0]) and np.allclose(co(0, 1), p0[1]), "kuru çözüm: çelişki görüldü, geometri değişmedi")
c2.driven = True; c2.length = 7.0
cmod.solve_all(ctx.scene, force=True)
check(c2.ok and abs(c2.length - 3) < 1e-6, f"referans ölçü geometriden ölçüldü: {c2.length}")
c1.length = 4.0; cmod.solve_all(ctx.scene, force=True)
check(abs(c2.length - 4) < 1e-6, "sürücü ölçü değişince referans güncellendi")
check(cg.dim_text(c2).startswith("(") and cg.dim_text(c1)[0] != "(", f"referans parantezli: {cg.dim_text(c2)}")
key("ESC")

print("B) Merkez mesafesi: daire–daire, daire–nokta, daire–doğru")
reset()
op._set_tool(ctx, "CIRCLE"); click((0, 0)); click((1, 0)); click((4, 0)); click((4.5, 0)); finish()
ctool("DIM"); click((0, 1)); click((4, 0.5))
c = cons()[-1]
check(c.kind == "CENTERDIST" and abs(c.length - 4) < 1e-6, f"daire–daire: {c.length:.6f}")
typ("6"); key("RET")
g0, g1 = ca.arc_group(curve, 0, 0), ca.arc_group(curve, 1, 0)
check(abs(np.linalg.norm(g0["c"] - g1["c"]) - 6) < 1e-5 and abs(g0["R"] - 1) < 1e-4 and abs(g1["R"] - 0.5) < 1e-4, "merkezler 6, yarıçaplar korundu")
reset()
op._set_tool(ctx, "CIRCLE"); click((0, 0)); click((1, 0)); line((3, 3), (4, 3)); finish()
ctool("DIM"); click((0, 1)); click((3, 3))
c = cons()[-1]
check(c.kind == "CENTERDIST" and abs(c.length - math.hypot(3, 3)) < 1e-6, "daire–nokta")
op.modal(ctx, ev("RIGHTMOUSE", (0, 0)))
click((0, -1)); click((3.5, 3));
c = cons()[-1]
check(c.kind == "CENTERDIST" and abs(c.length - 3) < 1e-6, f"daire–doğru (merkezden doğruya): {c.length:.6f}")
key("ESC")

print("C) Yaylarda Eşit: yarıçaplar eşitlenir")
reset()
op._set_tool(ctx, "CIRCLE"); click((0, 0)); click((1, 0)); click((4, 0)); click((4.5, 0)); finish()
ctool("EQUAL"); click((0, 1)); click((4, 0.5))
g0, g1 = ca.arc_group(curve, 0, 0), ca.arc_group(curve, 1, 0)
check(cons()[-1].ok and abs(g0["R"] - g1["R"]) < 1e-5 and g0["closed"] and g1["closed"], f"R {g0['R']:.5f} = {g1['R']:.5f}")
check(cmod.satisfied(cons()[-1]), "satisfied: eşit yarıçap")

print("D) Otomatik ölçü")
reset()
op._set_tool(ctx, "RECT"); click((0, 0)); click((2, 1)); finish()
ctool("AUTODIM"); click((1, 0))
check(len(cons()) == 4 and all(c.kind == "DISTANCE" for c in cons()), f"dikdörtgen: 4 uzunluk ({[c.kind for c in cons()]})")
click((1, 0))
check(len(cons()) == 4, "ikinci kez: eklenecek yok")
reset()
op._set_tool(ctx, "CIRCLE"); click((0, 0)); click((1, 0)); finish()
ctool("AUTODIM"); click((0, 1))
check(len(cons()) == 1 and cons()[0].kind == "RADIUS" and cons()[0].axis == 1, "daire: çap")

print("E) Ölçü çizgileri (ekran yerleşimi)")
reset(); line((0, 0), (2, 0)); finish()
ctool("DIM"); click((1, 0)); key("RET"); key("ESC")
to_px2 = lambda p: (float(p[0]) * 50 + 500, float(p[1]) * 50 + 500)
geo = cg.dim_geometry(cons()[0])
lay = cg.dim_layout(geo, to_px2, 1.0)
check(geo[0] == "lin" and lay is not None and lay[0][1] > 500 and len(lay[1]) >= 6, f"doğrusal: yazı ölçü çizgisinin üstünde {np.round(lay[0], 1)}")
reset(); op._set_tool(ctx, "CIRCLE"); click((0, 0)); click((1, 0)); finish()
ctool("DIM"); click((0, 1)); key("RET"); key("ESC")
geo = cg.dim_geometry(cons()[0])
lay = cg.dim_layout(geo, to_px2, 1.0)
check(geo[0] == "rad" and geo[3] and len(lay[1]) >= 10, "çap: merkezden iki yana oklu çizgi")
reset(); line((0, 0), (2, 0)); line((0, 0.5), (2, 2)); finish()
ctool("DIM"); click((1, 0)); click((1, 1.25)); key("ESC")
geo = cg.dim_geometry(cons()[-1])
check(geo[0] == "ang" and cg.dim_layout(geo, to_px2, 1.0) is not None, "açı: yay")

print("F) Ayrı iki doğruda köşe yuvarla / pah")
reset()
line((0, 0), (2, 0)); line((3, 1), (3, 3))
op._set_tool(ctx, "FILLET2D"); op.dirty = True; typ("0.5")
move((1, 0))
check(op.mod and op.mod["kind"] == "LINEPICK", "köşe yok: doğru seçimi")
click((1, 0)); move((3, 2))
check(op.mod and op.mod["kind"] == "CORNER" and op.mod["res"] is not None, "ikinci doğru: önizleme")
click((3, 2))
st = op.sketch[-1]
c = dm.arc_of_bezier([np.asarray(q) for q in st["segs"][1]["p"]])
check(len(op.sketch) == 1 and len(st["segs"]) == 3 and np.allclose(c[0], (2.5, 0.5, 0)), f"uzatılıp yuvarlandı: merkez {np.round(c[0], 4)}")
reset()
line((0, 0), (4, 0)); line((2, -1), (2, 2))
op._set_tool(ctx, "CHAMFER2D"); op.dirty = True; typ("0.5")
click((1, 0)); click((2, 1.5))
st = op.sketch[-1]
P = [tuple(np.round(sg["p"][0], 4)) for sg in st["segs"]] + [tuple(np.round(st["segs"][-1]["p"][3], 4))]
check(len(op.sketch) == 1 and P[0][:2] == (0, 0) and P[-1][:2] == (2, 2) and (1.5, 0.0) in [q[:2] for q in P], f"kesişen: tıklanan parçalar kaldı, pah: {P}")

print("G) Hassas giriş (Shift+Tab): X / Y, sonra ΔX / ΔY")
reset()
key("TAB", shift=True)
check(op.coord_mode, "koordinat girişi açık")
move((0.3, 0.3)); typ("1"); key("TAB"); typ("2"); key("RET")
check(op.start is not None and np.allclose(op.start, (1, 2, 0)), f"ilk nokta X=1, Y=2: {op.start}")
typ("3"); key("TAB"); typ("-0.5"); key("RET")
check(np.allclose(op.segs[-1]["p"][3], (4, 1.5, 0)), f"ΔX=3, ΔY=-0.5: {op.segs[-1]['p'][3]}")
key("RET"); key("TAB", shift=True)
check(not op.coord_mode, "uzunluk / açıya dönüldü")
reset(); op._set_tool(ctx, "RECT"); click((0, 0)); click((1, 1))
op._set_tool(ctx, "MOVE"); click((0.5, 0)); key("RET"); click((0, 0))
key("TAB", shift=True); typ("2"); key("TAB"); typ("1"); key("RET")
xs = sorted(round(float(sg["p"][0][0]), 6) for sg in op.sketch[0]["segs"])
ys = sorted(round(float(sg["p"][0][1]), 6) for sg in op.sketch[0]["segs"])
check(xs == [2, 2, 3, 3] and ys == [1, 1, 2, 2], f"Taşı ΔX=2, ΔY=1: {xs} {ys}")
op.coord_mode = False

print("H) Merkez noktalı yay kanal")
reset(); op._set_tool(ctx, "SLOTARCC")
click((0, 0)); click((3, 0)); click((0, 3)); move((0, 3.4)); typ("1"); key("RET")
Pp = np.vstack([dm.sample(sg, 17) for sg in op.sketch[-1]["segs"]])
R = np.linalg.norm(Pp[:, :2], axis=1)
check(op.sketch[-1]["cyclic"] and R.min() > 2.49 and R.max() < 3.51 and Pp[:, 0].min() > -0.6, f"çeyrek yay kanal R 2.5..3.5: {R.min():.3f}..{R.max():.3f}")

print("I) Düzenle araçlarında noktalar")
reset(); op._set_tool(ctx, "POINT"); click((5, 5))
op._set_tool(ctx, "RECT"); click((0, 0)); click((1, 1))
op._set_tool(ctx, "MOVE"); click((5, 5))
check(op.xpts == {0}, "noktaya tık: nokta seçildi")
key("RET"); click((5, 5)); click((6, 4))
check(np.allclose(op.sk_points[0], (6, 4, 0)) and len(op.sk_points) == 1, f"nokta taşındı: {op.sk_points[0]}")
op._set_tool(ctx, "COPY"); op.xf["step"] = "SEL"; op.xsel, op.xpts = set(), set()
drag((-1, -1), (7, 6))
check(op.xsel == {0} and op.xpts == {0}, f"kutu: çizgi ve nokta {op.xsel} {op.xpts}")
key("RET"); click((0, 0)); click((0, -3))
check(len(op.sketch) == 2 and len(op.sk_points) == 2 and np.allclose(op.sk_points[1], (6, 1, 0)), "kopyada nokta da kopyalandı")
op._set_tool(ctx, "CPAT"); op.xf["step"] = "SEL"; op.xsel, op.xpts = set(), {0}
key("RET"); click((0, 0)); typ("4"); key("RET")
check(len(op.sk_points) == 5, f"dairesel desen: 3 nokta kopyası ({len(op.sk_points)})")

print("J) Kısıt simgeleri / ölçü çizgileri çizimi (gpu stub)")
reset(); line((0, 0), (2, 0)); op._set_tool(ctx, "CIRCLE"); click((5, 0)); click((6, 0)); finish()
ctool("DIM"); click((1, 0)); key("RET"); key("ESC")
ctool("DIM"); click((5, 1)); key("RET"); key("ESC")
pal = importlib.import_module("mini_cad.palette")
drawn = []
pal.rect = lambda *a: drawn.append("rect"); pal.text = lambda *a, **k: drawn.append("text")
pal._lines = lambda seg, *a: drawn.append(("lines", len(seg))); pal.draw_icon = lambda *a: drawn.append("icon")
sys.modules["gpu"].state = NS(blend_set=lambda *a: None)
ctx.region_data = NS(); ctx.preferences.system.ui_scale = 1.0
printed = []
import builtins
_p = builtins.print
builtins.print = lambda *a, **k: printed.append(a)
cmod._glyph_boxes.clear(); cmod._draw_glyphs()
builtins.print = _p
check(not printed, f"hata yok: {printed}")
check(len(cmod._glyph_boxes) == 2 and sum(1 for d in drawn if isinstance(d, tuple)) == 2, f"iki ölçü: kutu {len(cmod._glyph_boxes)}, çizgi {[d for d in drawn if isinstance(d, tuple)]}")
print("t55 bitti")
