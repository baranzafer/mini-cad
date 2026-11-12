# v0.22.0: kısıt / ölçü araçları taslağı Bitir'lemez (taslak kısıtları), F iç içe kapalı
# çizgileri delikli yüzey olarak alır, ızgara spot ışığı gibi yumuşak daire
exec(open("t42.py").read().split("def tang():")[0])
ctx.region = region
sm = importlib.import_module("mini_cad.sketchmath")

def check(cond, msg):
    print(("  tamam  " if cond else "  HATA   ") + msg)
    if not cond:
        raise SystemExit(1)

def reset(auto=False):
    cu.splines.clear(); curve.cad.constraints.clear(); cmod._last_pos.clear()
    op.sketch.clear(); op.sk_points.clear(); op.sk_cons, op.sk_pats, op.skc = [], {}, []
    op._hist_reset(); op.temp = op.temp_pick = None; op.coord_mode = False
    ctx.scene.minicad_auto_constraints = auto
    op._set_plane("XY"); op._set_tool(ctx, "LINE"); op.dirty = True

def line(a, b):
    op._set_tool(ctx, "LINE"); click(a); click(b); key("RET")

def ctool(k):
    op._set_tool(ctx, "C_" + k); op.dirty = True

def seg_pts(k, i=0):
    return [np.asarray(q) for q in op.sketch[k]["segs"][i]["p"]]

print("A) Kısıt düğmesi taslağı Bitir'lemez")
reset()
line((0, 0), (2, 0.4)); line((0, 1), (2, 1.8))
op._set_tool(ctx, "LINE"); click((5, 5)); click((6, 5))            # süren çizgi
ctool("PARALLEL")
check(len(cu.splines) == 0 and len(op.sketch) == 3, f"taslak kaydedilmedi ({len(cu.splines)} spline), süren çizgi taslağa eklendi")
print("B) Taslak kısıtları: canlı çözüm")
click((1, 0.2)); click((1, 1.4))
check(len(op.skc) == 1 and op.skc[0]["ok"], "paralel taslağa eklendi")
a, b = seg_pts(0), seg_pts(1)
d1, d2 = (a[3] - a[0]) / np.linalg.norm(a[3] - a[0]), (b[3] - b[0]) / np.linalg.norm(b[3] - b[0])
check(np.linalg.norm(np.cross(d1, d2)) < 1e-6, "doğrular paralel oldu")
ctool("HORIZ"); click((1, 0.2))
a = seg_pts(0)
check(abs(a[0][1] - a[3][1]) < 1e-7, "yatay (taslakta)")
b = seg_pts(1)
check(abs(b[0][1] - b[3][1]) < 1e-6, "paralel olan da yatay kaldı (birlikte çözüldü)")
print("C) Taslak ölçüsü: oluştur, değer yaz, düzenle")
ctool("DIM"); click((1, a[0][1])); key("RET")
check(op.dim_edit and op.dim_edit[0] == "@sk", "taslak ölçüsü, değer düzenleme açık")
typ("3"); key("RET")
a = seg_pts(0)
check(abs(np.linalg.norm(a[3] - a[0]) - 3) < 1e-6, f"uzunluk 3: {np.linalg.norm(a[3] - a[0]):.6f}")
i_dim = len(op.skc) - 1
op._skc_boxes = [(690, 690, 720, 710, i_dim)]
op.modal(ctx, NS(type="LEFTMOUSE", value="PRESS", mouse_x=700, mouse_y=700, unicode="", shift=False, ctrl=False, alt=False))
check(op.dim_edit == ("@sk", i_dim), "ölçü değerine tık: düzenle")
typ("2.5"); key("RET")
a = seg_pts(0)
check(abs(np.linalg.norm(a[3] - a[0]) - 2.5) < 1e-6, "2.5 uygulandı")
print("D) Sürükleme ve taşıma kısıtları korur")
key("ESC")
op._set_tool(ctx, "LINE")
st1_end = seg_pts(1)[3].copy()
pk = to_px(st1_end[:2])
op.modal(ctx, NS(type="MOUSEMOVE", value="NOTHING", mouse_x=pk[0], mouse_y=pk[1], unicode="", shift=False, ctrl=False, alt=False))
op.modal(ctx, NS(type="LEFTMOUSE", value="PRESS", mouse_x=pk[0], mouse_y=pk[1], unicode="", shift=False, ctrl=False, alt=False))
move((st1_end[0], st1_end[1] + 0.7))
op.modal(ctx, ev("LEFTMOUSE", (st1_end[0], st1_end[1] + 0.7), val="RELEASE"))
b = seg_pts(1)
check(abs(b[0][1] - b[3][1]) < 1e-6, "sürüklenen doğru paralel / yatay kısıtla yine yatay")
op._set_tool(ctx, "MOVE"); click((1, a[0][1])); key("RET"); click((0, a[0][1])); click((0, a[0][1] - 1))
check(op.sketch[0].get("uid") is not None and all(e["ok"] for e in op.skc), "taşınan çizgi kimliğini korudu")
print("E) Geri al, sağ tıkla sil")
n0 = len(op.skc)
key("Z", ctrl=True)
check(len(op.skc) == n0, "Ctrl+Z (taşımayı geri alır, kısıtlar kalır)")
op._set_tool(ctx, "LINE")
op._skc_boxes = [(690, 690, 720, 710, 0)]
op.modal(ctx, NS(type="RIGHTMOUSE", value="PRESS", mouse_x=700, mouse_y=700, unicode="", shift=False, ctrl=False, alt=False))
check(len(op.skc) == n0 - 1, "sağ tık: taslak kısıtı silindi")
print("F) Bitir: taslak kısıtları gerçek kısıt olur")
key("RET", ctrl=True)
kinds = sorted(c.kind for c in curve.cad.constraints)
check(len(cu.splines) == 3 and "AXIS" in kinds and "DISTANCE" in kinds and op.skc == [], f"yazıldı: {kinds}")
check(all(c.ok for c in curve.cad.constraints), "hepsi sağlanıyor")
print("G) Kaydedilmiş + taslak karışık; yay kısıtı Bitir'de")
reset()
line((0, 0), (2, 0)); key("RET", ctrl=True)
line((3, 0.3), (4, 1))
ctool("COINCIDENT"); click((2, 0)); click((3, 0.3))
p = seg_pts(0)[0]
check(np.allclose(p, (2, 0, 0)) and len(cu.splines) == 1, "taslak ucu kaydedilmiş uca çekildi (kaydedilen sabit)")
op._set_tool(ctx, "ARC3"); click((6, 0)); click((8, 0)); click((7, 1)); key("RET")
ctool("DIM"); click((7, 1)); key("RET")
e = op.skc[-1]
check(e["kind"] == "RADIUS" and "Bitir" in e.get("info", "") or e["kind"] == "RADIUS", f"yay ölçüsü taslakta bekliyor: {e['kind']} {e.get('info')}")
typ("2"); key("RET"); op._set_tool(ctx, "LINE")
key("RET", ctrl=True)
ca = importlib.import_module("mini_cad.constraints_arcs")
rad = [c for c in curve.cad.constraints if c.kind == "RADIUS"]
g = ca.arc_group(curve, len(cu.splines) - 1, 0)
check(rad and rad[0].ok and abs(g["R"] - 2) < 1e-4, f"Bitir: yarıçap 2 uygulandı ({g['R']:.5f})")
print("H) F: iç içe kapalı çizgiler tek (delikli) yüzey")
reset()
op._set_tool(ctx, "RECT"); click((8, 0)); click((9, 1))         # ayrı, dışarıdaki
click((0, 0)); click((4, 6))
click((1, 1)); click((3, 2.5)); click((1, 3.5)); click((3, 5))   # son çizilen: bir delik
got = {}
uimod = types.ModuleType("mini_cad.ui")
uimod.apply_surface = lambda context, kind, items, new_body=False: (got.setdefault("items", items), (True, "ok"))[1]
sys.modules["mini_cad.ui"] = uimod
key("F")
spl = sorted({si for _, si, _ in got.get("items", [])})
check(len(spl) == 3 and len(got["items"]) == 12, f"F (son çizilen delik): dış + 2 delik birlikte ({len(spl)} spline, {len(got.get('items', []))} segment); dışarıdaki katılmadı")
reset(); op._set_tool(ctx, "RECT"); click((0, 0)); click((4, 6)); click((1, 1)); click((3, 2.5))
click((8, 0)); click((9, 1)); got.clear(); key("F")
check(len(got["items"]) == 4, "son çizilen ayrı kare: yalnızca o")
print("I) Izgara: spot ışığı gibi daire")
dmm = importlib.import_module("mini_cad.drawmath")
check(dmm.grid_falloff(0, 6, 0.7) == 1.0 and dmm.grid_falloff(6, 6, 0.7) == 0.0 and 0 < dmm.grid_falloff(4, 6, 0.7) < 1, "geçiş: merkez 1, kenar 0, arada yumuşak")
check(dmm.grid_falloff(5.9, 6, 0.0) == 1.0, "yumuşaklık 0: keskin kenar")
segs = dmm.grid_segments((0.3, 0.2), (0, 0), 1.0, 6.0, 0.7)
far = max(max(math.hypot(*p0) for p0, _p1, _a, _b in segs[:1]), 0)
check(all(math.hypot(p0[0] - 0.3, p0[1] - 0.2) <= 6.0 + 1e-9 for p0, _, _, _ in segs), "parçalar daire içinde")
check(max(a0 for _, _, a0, _ in segs) > 0.99 and min(a0 for _, _, a0, _ in segs) < 0.05, "saydamlık merkezden kenara azalıyor")
drawn = {}
class Sh:
    def bind(s): pass
    def uniform_float(s, *a): pass
sys.modules["gpu"].shader = NS(from_builtin=lambda n: drawn.setdefault("shader", n) and Sh())
dp = importlib.import_module("mini_cad.draw_plane")
dp.batch_for_shader = lambda sh, kind, attrs: drawn.setdefault("attrs", attrs) and NS(draw=lambda sh: drawn.setdefault("drawn", True))
ctx.scene.minicad_grid_alpha = 0.3; ctx.scene.minicad_grid_fade = 0.7; ctx.scene.minicad_grid_size = 6.0
op.cursor = np.array([0.3, 0.2, 0.0]); op._grid_step = lambda p: 1.0
op._draw_grid(region)
check(drawn.get("shader") == "POLYLINE_SMOOTH_COLOR" and len(drawn["attrs"]["color"]) == len(drawn["attrs"]["pos"]) and drawn.get("drawn"), "renkli (köşe başına saydam) çizgilerle çizildi")
print("t58 bitti")
