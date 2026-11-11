# v0.16.0 (Aşama 1): Değiştir araçları — Kırp / Uzat / Böl / Ötele / Köşe yuvarla / Pah
exec(open("t42.py").read().split("def tang():")[0])
ctx.region = region
sm = importlib.import_module("mini_cad.sketchmath")

def check(cond, msg):
    print(("  tamam  " if cond else "  HATA   ") + msg)
    if not cond:
        raise SystemExit(1)

def reset():
    cu.splines.clear(); curve.cad.constraints.clear(); cmod._last_pos.clear()
    op.sketch.clear(); op._hist_reset(); op.temp = op.temp_pick = None
    ctx.scene.minicad_auto_constraints = True
    op._set_plane("XY"); op._set_tool(ctx, "LINE"); op.dirty = True

def rect_and_line():
    reset()
    op._set_tool(ctx, "RECT"); click((0, 0)); click((4, 2))
    op._set_tool(ctx, "LINE"); click((2, -1)); click((2, 3)); key("RET")
    check(len(op.sketch) == 2, "dikdörtgen + dikey doğru taslakta")

def nodes(st):
    return [tuple(np.round(sg["p"][0], 4)) for sg in st["segs"]] + \
        ([] if st["cyclic"] else [tuple(np.round(st["segs"][-1]["p"][3], 4))])

print("A) Kırp (B): dikdörtgenin sol alt kenar parçası")
rect_and_line()
key("B")
check(op.tool == "TRIM", "B: Kırp aracı")
move((1, 0))
check(op.mod is not None and op.mod["kind"] == "TRIM" and len(op.mod["prev"]) == 1, "önizleme: kırpılacak parça")
pv = op.mod["prev"][0]["p"]
check(np.allclose(pv[0], (0, 0, 0)) and np.allclose(pv[3], (2, 0, 0)), "parça (0,0)-(2,0)")
click((1, 0))
rect = op.sketch[0]
check(not rect["cyclic"] and nodes(rect)[0] == (2.0, 0.0, 0.0), f"kırpıldı, çizgi açıldı: {nodes(rect)}")
key("Z", ctrl=True)
check(op.sketch[0]["cyclic"], "Ctrl+Z: taslakta geri alındı")
key("Z", ctrl=True, shift=True)
check(not op.sketch[0]["cyclic"], "Ctrl+Shift+Z: yinelendi")

print("B) Kırp: kesişimsiz nesne tamamen silinir; sürükleyerek çoklu")
op.sketch.append({"segs": [dm.line_seg(np.array([5., 0, 0]), np.array([6., 0, 0]))], "cyclic": False, "node_ids": {}, "start_tan": None})
op.dirty = True
n0 = len(op.sketch)
click((5.5, 0))
check(len(op.sketch) == n0 - 1, "kesişimsiz doğru silindi")
rect_and_line()
key("B")
move((2, -0.5)); op.modal(ctx, ev("LEFTMOUSE", (2, -0.5)))          # alttaki taşan kısım
move((2, 2.5))                                                        # sürükle: üstteki taşan
op.modal(ctx, ev("LEFTMOUSE", (2, 2.5), val="RELEASE"))
ln = op.sketch[1]["segs"]
ys = sorted([round(float(ln[0]["p"][0][1]), 6), round(float(ln[-1]["p"][3][1]), 6)])
check(ys == [0.0, 2.0], f"sürükleyerek iki taşan parça kırpıldı: y {ys}")
move((3.0, 3.0))
check(op.mod is None and not op.mod_drag, "bırakınca sürükleme bitti")

print("C) Uzat (Shift ile Kırp ⇄ Uzat): kısa doğru sınıra uzar")
reset()
op._set_tool(ctx, "RECT"); click((0, 0)); click((4, 2))
op._set_tool(ctx, "LINE"); click((1, 1)); click((2, 1)); key("RET")
op._set_tool(ctx, "EXTEND"); op.dirty = True
move((1.9, 1))
check(op.mod and op.mod["kind"] == "EXTEND" and op.mod["ok"] and np.allclose(op.mod["tip"], (4, 1, 0)), "önizleme: uç (4,1)")
click((1.9, 1))
check(np.allclose(op.sketch[1]["segs"][-1]["p"][3], (4, 1, 0)), "sağa uzatıldı")
op._set_tool(ctx, "TRIM")
op.modal(ctx, ev("MOUSEMOVE", (1.1, 1), shift=True))
check(op.mod and op.mod["kind"] == "EXTEND", "Kırp'ta Shift: Uzat")
op.modal(ctx, ev("LEFTMOUSE", (1.1, 1), shift=True)); op.modal(ctx, ev("LEFTMOUSE", (1.1, 1), val="RELEASE"))
check(np.allclose(op.sketch[1]["segs"][0]["p"][0], (0, 1, 0)), "baş uç sola uzatıldı")

print("D) Böl")
rect_and_line()
op._set_tool(ctx, "SPLIT"); op.dirty = True
move((2, 0.3))
check(op.mod and op.mod["ok"] and np.allclose(op.mod["pts"][0], (2, 0, 0)), "en yakın kesişim (2,0)")
click((2, 0.3))
check(len(sm.entities(op.sketch[1])) == 2 and len(op.sketch[1]["segs"]) == 2, "doğru iki nesneye bölündü, çizgi bütün")

print("E) Ötele: dikdörtgen dışa, yazılan 0.5")
reset()
op._set_tool(ctx, "RECT"); click((0, 0)); click((4, 2))
op._set_tool(ctx, "OFFSET"); op.dirty = True
click((2, 0))
check(op.off_sel is not None and len(op.off_sel["segs"]) == 4, "döngü seçildi")
move((2, -1.0))
check(op.mod and op.mod["kind"] == "OFFSET" and abs(abs(op.mod["d"]) - 1.0) < 1e-6, f"fareyle mesafe {op.mod and round(op.mod['d'], 4)}")
typ("0.5"); key("RET")
new = op.sketch[-1]
xs = sorted(round(float(sg["p"][0][0]), 6) for sg in new["segs"])
check(len(op.sketch) == 2 and new["cyclic"] and xs == [-0.5, -0.5, 4.5, 4.5], f"dışa 0.5 ötelendi: {xs}")
check(op.off_sel is None, "seçim bırakıldı")
click((2, 0)); op.modal(ctx, ev("RIGHTMOUSE", (2, 0))); op.modal(ctx, ev("RIGHTMOUSE", (2, 0), val="RELEASE"))
check(op.off_sel is None and op.tool == "OFFSET", "sağ tık: seçim bırakılır, araç kalır")

print("F) Köşe yuvarla: yarıçap yaz, köşeye tıkla; aynı yarıçapla devam")
reset()
op._set_tool(ctx, "RECT"); click((0, 0)); click((4, 2))
op._set_tool(ctx, "FILLET2D"); op.dirty = True
typ("0.5")
move((4, 0))
check(op.mod and op.mod["kind"] == "CORNER" and op.mod["res"] is not None and np.allclose(op.mod["res"]["center"], (3.5, 0.5, 0)), "önizleme merkez (3.5,0.5)")
click((4, 0))
st = op.sketch[0]
check(len(st["segs"]) == 5 and len(sm.corners(st)) == 3, f"yuvarlandı: {len(st['segs'])} segment")
check(abs(op.fillet_r - 0.5) < 1e-12 and op.typed == ["", ""], "yarıçap hatırlandı")
click((4, 2))
check(len(sm.corners(op.sketch[0])) == 2, "ikinci köşe aynı yarıçapla")
typ("5"); move((0, 0))
check(op.mod and op.mod["res"] is None, f"büyük yarıçap reddedilir: {op.mod and op.mod['why']}")
op.typed = ["", ""]

print("G) Pah: 0.5 × 0.25")
op._set_tool(ctx, "CHAMFER2D"); op.dirty = True
typ("0.5"); key("TAB"); typ("0.25")
click((0, 0))
segs = op.sketch[0]["segs"]
pts = [tuple(np.round(sg["p"][0], 4)) for sg in segs]
# kapalı dikdörtgenin 0. köşesi: önceki kenar (sol, aşağı iner) 0.5, sonraki (alt) 0.25
check(any(np.allclose(p, (0, 0.5, 0)) for p in pts) and any(np.allclose(p, (0.25, 0, 0)) for p in pts), f"pah uçları: {pts}")

print("H) Ayrı iki doğrunun buluşan uçları: köşe yuvarla birleştirir")
reset()
click((0, 0)); click((2, 0)); key("RET")
click((2, 0)); click((2, 2)); key("RET")
op._set_tool(ctx, "FILLET2D"); op.dirty = True; typ("0.5")
click((2, 0))
check(len(op.sketch) == 1 and len(op.sketch[0]["segs"]) == 3, "tek çizgi: doğru-yay-doğru")

print("I) Bitir: değiştirilmiş taslak eğriye yazılır, kısıtlar tutarlı")
key("RET", ctrl=True)
check(len(cu.splines) == 1 and len(cu.splines[0].bezier_points) == 4, f"yazıldı: {len(cu.splines[0].bezier_points)} nokta")
check(all(c.ok for c in curve.cad.constraints), f"kısıtlar sağlanıyor: {[(c.kind, c.ok) for c in curve.cad.constraints]}")

print("J) Çizim fonksiyonları (stub)")
calls = []
dmod = importlib.import_module("mini_cad.draw_modify")
for nm in ("_text", "_poly", "_marker", "_dashed"):
    setattr(dmod, nm, (lambda nm: lambda *a, **k: calls.append(nm) or (10, 10))(nm))
op._draw_rows = lambda *a: calls.append("rows")
rect_and_line()
for tool, p in (("TRIM", (1, 0)), ("EXTEND", (2, 2.9)), ("SPLIT", (2, 0.3)), ("FILLET2D", (4, 0)), ("CHAMFER2D", (4, 0))):
    op._set_tool(ctx, tool); op.dirty = True; move(p); calls.clear()
    op._draw_modify3d(region); op._draw_modify2d(region)
    check(len(calls) > 0, f"{tool}: çizildi ({len(calls)} çağrı)")
op._set_tool(ctx, "OFFSET"); click((2, 0)); move((2, -1)); calls.clear()
op._draw_modify3d(region); op._draw_modify2d(region)
check("rows" in calls, "OFFSET: ölçü kutusu")
print("t47 bitti")
