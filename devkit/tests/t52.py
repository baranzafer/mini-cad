# v0.18.0 (Aşama 3): Oluştur araçları modal — dikdörtgen çeşitleri (R döngüsü), çokgen,
# kanallar, yay kanal, elips, teğet daire (O döngüsü), nokta, geometri yansıt
exec(open("t42.py").read().split("def tang():")[0])
ctx.region = region
sm = importlib.import_module("mini_cad.sketchmath")

def check(cond, msg):
    print(("  tamam  " if cond else "  HATA   ") + msg)
    if not cond:
        raise SystemExit(1)

def reset():
    cu.splines.clear(); curve.cad.constraints.clear(); cmod._last_pos.clear()
    op.sketch.clear(); op.sk_points.clear(); op._hist_reset(); op.temp = op.temp_pick = None
    ctx.scene.minicad_auto_constraints = True
    op._set_plane("XY"); op._set_tool(ctx, "LINE"); op.dirty = True

def corners(st):
    return sorted(tuple(np.round(sg["p"][0][:2], 6)) for sg in st["segs"])

def bbox(st):
    P = np.vstack([dm.sample(sg, 17) for sg in st["segs"]])
    return np.round(P.min(axis=0)[:2], 3).tolist(), np.round(P.max(axis=0)[:2], 3).tolist()

print("A) R döngüsü")
reset()
seq = []
for _ in range(5):
    key("R"); seq.append(op.tool)
check(seq == ["RECT", "RECT3", "RECTC", "RECT3C", "RECT"], f"R: {seq}")
seq = []
for _ in range(4):
    key("O"); seq.append(op.tool)
check(seq == ["CIRCLE", "CIRCT", "ELLIPSE", "CIRCLE"], f"O: {seq}")

print("B) Dikdörtgen 3 nokta / merkezden (yazarak) / 3 nokta merkezden")
reset(); op._set_tool(ctx, "RECT3")
click((0, 0)); click((2, 0)); click((2, 1))
st = op.sketch[-1]
check(st["cyclic"] and corners(st) == [(0, 0), (0, 1), (2, 0), (2, 1)], f"3 nokta: {corners(st)}")
check([a for sg in st["segs"] for a in sg.get("auto", ())] == [("AXIS", 0), ("AXIS", 1), ("AXIS", 0), ("AXIS", 1)], "eksene hizalı: yatay / dikey oto kısıt")
op._set_tool(ctx, "RECT3"); click((0, 0)); move((1, 1)); typ("2"); key("TAB"); typ("90")
check(np.allclose(op.cursor, (0, 2, 0)), "2. tıkta uzunluk / açı yazılır")
click((1, 1)); click((1, 2))
check(len(op.sketch) == 2, "döndürülmüş 3 nokta")
reset(); op._set_tool(ctx, "RECTC")
click((0, 0)); move((1, 1)); typ("4"); key("TAB"); typ("2"); key("RET")
check(corners(op.sketch[-1]) == [(-2, -1), (-2, 1), (2, -1), (2, 1)], f"merkezden 4×2: {corners(op.sketch[-1])}")
op._set_tool(ctx, "RECT3C"); click((5, 0)); click((6, 0)); click((7, 0.5))
check(corners(op.sketch[-1]) == [(4, -0.5), (4, 0.5), (6, -0.5), (6, 0.5)], f"3 nokta merkezden: {corners(op.sketch[-1])}")

print("C) Çokgen: kenar sayısı yazılır, D: iç / dış")
reset(); op._set_tool(ctx, "POLYGON")
click((0, 0)); move((1, 0)); key("TAB"); typ("5"); key("RET")
st = op.sketch[-1]
check(len(st["segs"]) == 5 and np.allclose(st["segs"][0]["p"][0], (1, 0, 0)), f"5 kenar, köşe imleçte: {len(st['segs'])}")
check(op.poly_n == 5, "kenar sayısı hatırlandı")
key("D"); click((4, 0)); click((5, 0))
mids = [0.5 * (np.asarray(s["p"][0]) + np.asarray(s["p"][3])) for s in op.sketch[-1]["segs"]]
check(not op.poly_inner and any(np.allclose(m, (5, 0, 0)) for m in mids), "dış teğet: kenar ortası imleçte")

print("D) Kanallar ve yay kanal")
reset(); op._set_tool(ctx, "SLOTCC")
click((0, 0)); click((4, 0)); move((4, 1)); typ("2"); key("RET")
check(bbox(op.sketch[-1]) == ([-1.0, -1.0], [5.0, 1.0]), f"merkezden merkeze, genişlik 2: {bbox(op.sketch[-1])}")
op._set_tool(ctx, "SLOTO"); click((0, 3)); click((6, 3)); click((5, 3.5))
check(bbox(op.sketch[-1]) == ([0.0, 2.5], [6.0, 3.5]), f"toplam boy: {bbox(op.sketch[-1])}")
op._set_tool(ctx, "SLOTC"); click((0, 6)); click((2, 6)); click((2, 6.5))
check(bbox(op.sketch[-1]) == ([-2.5, 5.5], [2.5, 6.5]), f"merkez noktalı: {bbox(op.sketch[-1])}")
op._set_tool(ctx, "ARCSLOT"); click((3, -3)); click((-3, -3)); click((0, 0)); move((0, 0.5)); typ("1"); key("RET")
P = np.vstack([dm.sample(sg, 17) for sg in op.sketch[-1]["segs"]])
R = np.linalg.norm(P[:, :2] - np.array([0, -3]), axis=1)
check(op.sketch[-1]["cyclic"] and R.min() > 2.49 and R.max() < 3.51, f"yay kanal R 2.5..3.5: {R.min():.3f}..{R.max():.3f}")

print("E) Elips")
reset(); op._set_tool(ctx, "ELLIPSE"); click((0, 0)); click((2, 0)); click((0.5, 1))
check(bbox(op.sketch[-1]) == ([-2.0, -1.0], [2.0, 1.0]), f"elips 2×1: {bbox(op.sketch[-1])}")
check(len(sm.entities(op.sketch[-1])) == 1, "elips tek nesne")

print("F) Teğet daire: üç doğru")
reset()
for a, b in (((0, 0), (3, 0)), ((0, 0), (0, 4)), ((3, 0), (0, 4))):
    click(a); click(b); key("RET")
op._set_tool(ctx, "CIRCT"); op.dirty = True
click((1.5, 0)); click((0, 2))
check(len(op.ct_lines) == 2, "iki doğru seçildi")
key("BACK_SPACE")
check(len(op.ct_lines) == 1, "Backspace: son seçim geri")
click((0, 2)); move((1.5, 2.0))
check(op.pk and op.pk.get("circle") is not None, "önizleme (3. doğru üzerinde)")
click((1.5, 2.0))
check(len(op.ct_lines) == 3 and len(op.sketch) == 3, "üç doğru seçildi, daire henüz yok")
move((5, 5))
cc = op.pk["circle"][0]
check(not np.allclose(cc, (1, 1, 0)), f"imleç dışarıda: dış teğet daire önizlemesi {np.round(cc, 3)}")
move((1.1, 0.9)); click((1.1, 0.9))
c = dm.arc_of_bezier(op.sketch[-1]["segs"][0]["p"])
check(len(op.sketch) == 4 and np.allclose(c[0], (1, 1, 0)) and abs(c[1] - 1) < 1e-9, "imleç içeride: iç teğet daire merkez (1,1), R 1")

print("G) Nokta: yakalanır, geri alınır, Bitir'de yazılır")
reset(); op._set_tool(ctx, "POINT")
click((5, 5))
check(len(op.sk_points) == 1 and np.allclose(op.sk_points[0], (5, 5, 0)), "nokta eklendi")
op._set_tool(ctx, "LINE"); op.dirty = True; move((5.05, 5.03))
check(op.snap_kind == "Nokta" and np.allclose(op.cursor, (5, 5, 0)), "çizerken noktaya yapışır")
key("Z", ctrl=True)
check(len(op.sk_points) == 0, "Ctrl+Z: nokta geri alındı")
key("Z", ctrl=True, shift=True)
check(len(op.sk_points) == 1, "Ctrl+Shift+Z: yinelendi")
key("RET", ctrl=True)
check(len(cu.splines) == 1 and len(cu.splines[0].bezier_points) == 1 and op.sk_points == [], "Bitir: tek noktalı spline")
op.dirty = True; move((5.05, 5.03))
check(op.snap_kind == "Nokta", "kaydedilen noktaya da yapışır")

print("H) Geometri yansıt: z=2'deki eğri z=0 düzlemine")
reset()
op.sketch.append({"segs": [dm.line_seg(np.array([0., 0, 2]), np.array([2., 0, 2]))], "cyclic": False, "node_ids": {}, "start_tan": None})
key("RET", ctrl=True)
op._set_tool(ctx, "PROJECT"); op.dirty = True
check(op.tool == "PROJECT", "Yansıt aracı")
move((1, 0)); op._update(ctx, *to_px((1, 0)))
check(op.pk and op.pk.get("segs"), "kenar bulundu, önizleme")
click((1, 0))
seg = op.sketch[-1]["segs"][0]
check(seg["kind"] == "line" and abs(seg["p"][0][2]) < 1e-12 and np.allclose(seg["p"][3], (2, 0, 0)), "izdüşüm z=0")

print("I) Bitir: şekiller eğriye yazılır")
reset(); op._set_tool(ctx, "SLOTCC"); click((0, 0)); click((2, 0)); click((2, 0.5))
op._set_tool(ctx, "POLYGON"); click((5, 0)); click((6, 0))
key("RET", ctrl=True)
check(len(cu.splines) == 2 and cu.splines[0].use_cyclic_u, f"yazıldı: {len(cu.splines)} spline")
check(all(c.ok for c in curve.cad.constraints), "kısıtlar tutarlı")

print("J) Çizim (stub)")
calls = []
ds = importlib.import_module("mini_cad.draw_shapes")
for nm in ("_text", "_poly", "_marker"):
    setattr(ds, nm, (lambda nm: lambda *a, **k: calls.append(nm) or (10, 10))(nm))
op._draw_rows = lambda *a: calls.append("rows")
reset(); op._set_tool(ctx, "POLYGON"); click((0, 0)); move((1, 0))
check(op.shape_rows and op.shape_rows[0][0] == "Yarıçap", "ölçü satırları")
op.sk_points.append(np.array([1., 1, 0])); calls.clear(); op._draw_points2d(region)
check(calls.count("_poly") == 2, "nokta çizildi")
op._set_tool(ctx, "CIRCT"); calls.clear(); op._pk_draw2d(region); op._pk_draw3d(region)
check("_text" in calls, "teğet daire etiketi")
print("t52 bitti")
