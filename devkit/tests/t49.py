# v0.17.0 (Aşama 2): Düzenle / Desen — Taşı, Kopyala, Döndür, Ölçekle, Esnet,
# Dikdörtgen desen, Dairesel desen, Ayna (seçim: tık / kutu)
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
    op.xsel, op.xnodes = set(), set()
    ctx.scene.minicad_auto_constraints = True
    op._set_plane("XY"); op._set_tool(ctx, "LINE"); op.dirty = True

def rect(a, b):
    op._set_tool(ctx, "RECT"); click(a); click(b); op._set_tool(ctx, "LINE")

def line(a, b):
    op._set_tool(ctx, "LINE"); click(a); click(b); key("RET")

def corners(st):
    return sorted(tuple(np.round(sg["p"][0][:2], 6)) for sg in st["segs"])

def tool(t):
    op._set_tool(ctx, t); op.dirty = True

def drag(a, b):
    move(a); op.modal(ctx, ev("LEFTMOUSE", a)); move(b); op.modal(ctx, ev("LEFTMOUSE", b, val="RELEASE"))

print("A) Taşı: tıkla seç → Enter → temel (uç yakalama) → hedef")
reset(); rect((0, 0), (2, 1))
tool("MOVE")
check(op.xf["step"] == "SEL", "seçim adımı")
click((1, 0))
check(op.xsel == {0}, "dikdörtgen seçildi")
key("RET")
check(op.xf["step"] == "BASE", "Enter: temel nokta adımı")
move((0.05, 0.03))
check(op.snap_kind == "Uç" and np.allclose(op.cursor, (0, 0, 0)), f"temel uca yapışır: {op.snap_kind}")
click((0.05, 0.03))
check(op.xf["step"] == "TGT" and np.allclose(op.xf["base"], 0), "temel (0,0)")
move((3, 2))
check(len(op.xprev) == 1, "önizleme")
click((3, 2))
check(corners(op.sketch[0]) == [(3.0, 2.0), (3.0, 3.0), (5.0, 2.0), (5.0, 3.0)], f"taşındı: {corners(op.sketch[0])}")
check(op.xf["step"] == "BASE" and op.xsel == {0}, "seçim korundu, temel adımına dönüldü")
key("Z", ctrl=True)
check(corners(op.sketch[0])[0] == (0.0, 0.0), "Ctrl+Z: geri alındı")

print("B) Kopyala: yazılan uzunluk")
reset(); rect((0, 0), (2, 1))
tool("COPY"); click((1, 0)); key("RET"); click((0, 0))
move((1, 0)); typ("5"); key("RET")
check(len(op.sketch) == 2 and corners(op.sketch[1])[0] == (5.0, 0.0), f"kopya +5: {corners(op.sketch[1])}")
check(corners(op.sketch[0])[0] == (0.0, 0.0), "asıl yerinde")

print("C) Döndür: merkez → 90 yaz; C ile kopya")
reset(); line((1, 0), (2, 0))
tool("ROTATE"); click((1.5, 0)); key("RET"); click((0, 0))
typ("90"); key("RET")
seg = op.sketch[0]["segs"][0]["p"]
check(np.allclose(seg[0], (0, 1, 0)) and np.allclose(seg[3], (0, 2, 0)), f"90° döndü: {np.round(seg[0], 4)} {np.round(seg[3], 4)}")
click((0, 0)); key("C")
check(op.xf["copy"], "C: kopya açık")
typ("90"); key("RET")
check(len(op.sketch) == 2 and np.allclose(op.sketch[1]["segs"][0]["p"][0], (-1, 0, 0)), "kopya döndürüldü, asıl kaldı")
click((0, 0)); move((-1, 0.0001))
check(abs(abs(op.xf["info"]["ang"]) - 90.0) < 0.5, f"fareyle açı (seçimin ortasına göre): {op.xf['info'].get('ang')}")
key("ESC")

print("D) Ölçekle: 2 yaz")
reset(); rect((0, 0), (2, 1))
tool("SCALE"); click((1, 0)); key("RET"); click((0, 0)); typ("2"); key("RET")
check(corners(op.sketch[0]) == [(0.0, 0.0), (0.0, 2.0), (4.0, 0.0), (4.0, 2.0)], f"2 kat: {corners(op.sketch[0])}")

print("E) Esnet: sağ kenar noktaları kutuyla (soldan sağa)")
reset(); rect((0, 0), (2, 1))
tool("STRETCH")
drag((1.5, -0.5), (2.5, 1.5))
check(op.xnodes == {(0, 1), (0, 2)}, f"kutudaki noktalar: {op.xnodes}")
key("RET"); click((2, 0)); click((3, 0))
check(corners(op.sketch[0]) == [(0.0, 0.0), (0.0, 1.0), (3.0, 0.0), (3.0, 1.0)], f"esnetildi: {corners(op.sketch[0])}")

print("F) Kutu: pencere (soldan sağa) / kesişen (sağdan sola)")
reset(); rect((0, 0), (2, 1)); line((3, 0), (5, 0))
tool("MOVE")
drag((-0.5, -0.5), (4, 1.5))
check(op.xsel == {0}, f"pencere: yalnız tamamen içindeki: {op.xsel}")
click((6, 3))
check(op.xsel == set(), "boşluğa tık: seçim temizlendi")
drag((4, 1.5), (1.5, -0.5))
check(op.xsel == {0, 1}, f"kesişen: değenler: {op.xsel}")

print("G) Dikdörtgen desen: adet 4, aralık 1.5; 2. yön atlanır")
reset(); rect((0, 0), (1, 1))
tool("RPAT"); click((0.5, 0)); key("RET"); click((0, 0))
move((1, 0)); typ("4"); key("TAB"); typ("1.5")
check(len(op.xprev) == 3, f"önizleme 3 kopya: {len(op.xprev)}")
click((1, 0))
check(op.xf["step"] == "DIR2", "2. yön adımı")
op.modal(ctx, ev("RIGHTMOUSE", (1, 0)))
xs = sorted(corners(st)[0][0] for st in op.sketch)
check(xs == [0.0, 1.5, 3.0, 4.5], f"1. yönde 4 adet: {xs}")
print("   2 yönlü:")
reset(); rect((0, 0), (1, 1))
tool("RPAT"); click((0.5, 0)); key("RET"); click((0, 0))
move((2, 0)); typ("2"); click((2, 0))
move((0, 3)); typ("2"); click((0, 3))
check(len(op.sketch) == 4, f"2×2 = 4: {len(op.sketch)}")

print("H) Dairesel desen: 4 adet")
reset(); line((1, 0), (2, 0))
tool("CPAT"); click((1.5, 0)); key("RET"); click((0, 0))
typ("4"); key("RET")
ends = sorted(tuple(np.round(st["segs"][0]["p"][0][:2], 6)) for st in op.sketch)
check(ends == [(-1.0, 0.0), (0.0, -1.0), (0.0, 1.0), (1.0, 0.0)], f"4 kopya, 90°: {ends}")

print("I) Ayna: y ekseni")
reset(); line((1, 0), (2, 1))
tool("MIRROR"); click((1.5, 0.5)); key("RET"); click((0, -1)); click((0, 1))
check(len(op.sketch) == 2 and np.allclose(op.sketch[1]["segs"][0]["p"][3], (-2, 1, 0)), f"aynalandı: {np.round(op.sketch[1]['segs'][0]['p'][3], 4)}")
check(np.allclose(op.sketch[0]["segs"][0]["p"][3], (2, 1, 0)), "asıl yerinde")

print("J) Araç değişince seçim: düzenle araçları arasında korunur, çizimde temizlenir")
op._set_tool(ctx, "MOVE"); op.xsel = {0}; op._set_tool(ctx, "ROTATE")
check(op.xsel == {0} and op.xf["step"] == "BASE", "Taşı → Döndür: seçim korundu, temel adımı")
op._set_tool(ctx, "LINE")
check(op.xsel == set() and op.xf is None, "Doğru: seçim temizlendi")

print("K) Bitir ve çizim (stub)")
key("RET", ctrl=True)
check(len(cu.splines) == 2, f"yazıldı: {len(cu.splines)} spline")
calls = []
dx = importlib.import_module("mini_cad.draw_xform")
for nm in ("_text", "_poly", "_marker", "_dashed"):
    setattr(dx, nm, (lambda nm: lambda *a, **k: calls.append(nm) or (10, 10))(nm))
op._draw_rows = lambda *a: calls.append("rows")
reset(); rect((0, 0), (2, 1))
for t in ("MOVE", "ROTATE", "SCALE", "RPAT", "CPAT", "MIRROR", "STRETCH"):
    op._set_tool(ctx, t); op.xsel = {0}; op.xnodes = {(0, 1)} if t == "STRETCH" else set()
    op.xf["step"] = "BASE"; click((0, 0)); move((1.3, 0.7)); calls.clear()
    op._draw_modify3d(region); op._draw_modify2d(region)
    check("rows" in calls and "_poly" in calls, f"{t}: önizleme ve ölçü kutusu")
    op._set_tool(ctx, "LINE")
print("t49 bitti")
