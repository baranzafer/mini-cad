# v0.15.4: geçici zeminde eski çizime yapışınca zeminde kalma; seçim sırasında taslak görünür
exec(open("t42.py").read().split("def tang():")[0])
ctx.region = region

def check(cond, msg):
    print(("  tamam  " if cond else "  HATA   ") + msg)
    if not cond:
        raise SystemExit(1)

def reset():
    cu.splines.clear(); curve.cad.constraints.clear(); cmod._last_pos.clear()
    op.sketch.clear(); op._hist_reset(); op.temp = op.temp_pick = None
    ctx.scene.minicad_auto_constraints = True
    op._set_plane("XY"); op._set_tool(ctx, "LINE"); op.dirty = True

def to_temp(h):
    key("U"); key("Z"); typ(h); key("RET")
    check(op.temp is not None and abs(op.locked.o[2] - float(h)) < 1e-12, f"geçici zemin z={h}")

print("A) Eski çizimin ucuna yapışınca çizgi YENİ zeminde başlar ve sürer:")
reset()
click((0, 0)); click((2, 0)); key("RET")             # z=0 taslak doğrusu
to_temp("0.5")
move((2, 0))
check(op.snap_kind == "Uç" and abs(op.cursor[2] - 0.5) < 1e-12, f"imleç zeminde: {np.round(op.cursor, 3)}")
check(op.snap_src is not None and abs(op.snap_src[2]) < 1e-12, "asıl nokta (z=0) hiza için saklandı")
click((2, 0))
check(abs(op.start[2] - 0.5) < 1e-12 and abs(op.plane.o[2] - 0.5) < 1e-12, "başlangıç ve düzlem z=0.5")
click((2, 2))
check(abs(op.segs[-1]["p"][3][2] - 0.5) < 1e-12, "ikinci nokta z=0.5")
click((0, 0))                                         # yine eski uca yapış
check(abs(op.segs[-1]["p"][3][2] - 0.5) < 1e-12, "eski uca yapışan ara nokta da z=0.5")
check(abs(op.plane.o[2] - 0.5) < 1e-12, "düzlem eski yüksekliğe kaymadı")
key("RET")
zs = [float(q[2]) for sg in op.sketch[-1]["segs"] for q in sg["p"]]
check(max(abs(z - 0.5) for z in zs) < 1e-12, "bütün çizgi z=0.5")

print("B) Teğet yay eski çizginin ucundan: teğet zemine izdüşer, yay zeminde")
reset()
click((0, 0)); click((2, 0)); key("RET")
to_temp("0.5")
op._set_tool(ctx, "TARC"); op.dirty = True
click((2, 0))
check(op.start_tan is not None and op.start_tan[1][0] == "@proj" and np.allclose(op.start_tan[0], (1, 0, 0)),
      f"teğet (+X, zeminde): {op.start_tan and np.round(op.start_tan[0], 3)}")
move((3, 1))
check(op.arc_info is not None and "radius" in op.arc_info, "önizleme teğet yay")
click((3, 1)); key("RET")
zs = [float(q[2]) for sg in op.sketch[-1]["segs"] for q in sg["p"]]
check(max(abs(z - 0.5) for z in zs) < 1e-12, "yay z=0.5")
key("RET", ctrl=True)
kinds = [c.kind for c in curve.cad.constraints]
print("   kısıtlar:", kinds)
check(all(c.ok for c in curve.cad.constraints), "yazılan kısıtlar sağlanıyor (farklı yükseklikler bağlanmadı)")
zmin = min(float(np.asarray(b.co)[2]) for sp in cu.splines[1:] for b in sp.bezier_points)
check(abs(zmin - 0.5) < 1e-12, "kaydedilen yeni eğriler z=0.5")

print("C) Kaydedilmiş eğri ucuna yapışınca da zeminde kalır; U ile normale dönünce normal akış")
op._set_tool(ctx, "LINE"); op.dirty = True
move((0, 0))
check(op.snap_kind == "Uç" and abs(op.cursor[2] - 0.5) < 1e-12, "eğri ucu zemine izdüştü")
key("U")
op.dirty = True
move((0, 0))
check(op.snap_src is None and abs(op.cursor[2]) < 1e-12, "normal düzlemde eski davranış (nokta kendisi)")
reset()
op.plane_mode = "AUTO"
click((0, 0)); click((1, 0)); key("RET")
op.sketch[0]["segs"][0]["p"] = tuple(np.array(q) + np.array([0, 0, 0.3]) for q in op.sketch[0]["segs"][0]["p"])
op.dirty = True
move((1, 0))
check(abs(op.cursor[2] - 0.3) < 1e-12 and op.snap_src is None, "geçici zemin yokken 3D nokta yüksekliği korunur")
op._set_plane("XY")

print("D) Geçici zemin seçilirken taslak çizilir, noktalar yakalanır")
reset()
click((0, 0)); click((1.0, 1.0)); key("RET")
drawn = []
op._draw_sketch3d = lambda r: drawn.append("3d"); op._draw_sketch2d = lambda r: drawn.append("2d")
op._draw_plane_pick = lambda r: None; op._draw_offset3d = lambda r: None; op._draw_offset2d = lambda r: None
op.palette.draw = lambda *a: None
sys.modules["gpu"].state = NS(blend_set=lambda *a: None, depth_test_set=lambda *a: None)
dr = importlib.import_module("mini_cad.draw_render")
for nm in ("_text", "_rect", "_dashed", "_poly", "_marker"):
    setattr(dr, nm, lambda *a, **k: (10, 10))
key("U")
check(op.phase == "PLANE", "yön seçimi")
op._draw3d(); op._draw2d()
check("3d" in drawn and "2d" in drawn, f"taslak yön seçiminde çiziliyor: {drawn}")
move((1.0, 1.0))
check(op.plane_snap is not None and op.plane_snap[1] == "Uç", f"yön seçerken noktaya yapışır: {op.plane_snap and op.plane_snap[1]}")
key("Z"); drawn.clear(); op._draw3d(); op._draw2d()
check("3d" in drawn and "2d" in drawn, "taslak yükseklik seçiminde de çiziliyor")
key("ESC"); key("ESC")
check(op.phase == "DRAW" and op.temp is None, "iptal")

print("E) Yön seçerken noktaya tık: o noktadan geçen zemin (tek adım)")
op.sketch[0]["segs"][0]["p"] = tuple(np.array(q) + np.array([0, 0, 0.7]) for q in op.sketch[0]["segs"][0]["p"])
op.dirty = True
key("U"); click((1.0, 1.0))
check(op.phase == "DRAW" and op.temp is not None and abs(op.locked.o[2] - 0.7) < 1e-12,
      f"zemin noktanın yüksekliğinde: {op.temp and op.temp['label']}")
check(np.allclose(op.temp["grid_o"], (1, 1, 0.7)), "ızgara kökeni o nokta")
key("U")

print("F) Normal düzlem seçiminde (Shift+Q) iki aşama korunur, nokta tek adımı yok")
key("Q", shift=True)
check(op.phase == "PLANE" and op.temp_pick is None, "Shift+Q: düzlem seçimi")
move((1.0, 1.0))
check(op.plane_snap is None, "normal seçimde nokta tek adımı kapalı")
op.modal(ctx, ev("RIGHTMOUSE", (1.0, 1.0)))
check(op.phase == "DRAW", "sağ tık: otomatik")
print("t45 bitti")
