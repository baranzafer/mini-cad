# v0.21.0: eksikler 2. parti — ayna simetri kısıtı, yuvarlamada eşit yarıçap, ilişkisel
# dikdörtgen / dairesel desen, ilişkisel yansıtma, taslağa al (Edit Sketch), metin
exec(open("t42.py").read().split("def tang():")[0])
ctx.region = region
ca = importlib.import_module("mini_cad.constraints_arcs")
links = importlib.import_module("mini_cad.links")
corem = importlib.import_module("mini_cad.core")

def check(cond, msg):
    print(("  tamam  " if cond else "  HATA   ") + msg)
    if not cond:
        raise SystemExit(1)

Splines.remove = lambda s, sp: s.pop(next(i for i, x in enumerate(s) if x is sp))
def _bp():
    return BP(co=Vec((0, 0, 0)), handle_left=Vec((0, 0, 0)), handle_right=Vec((0, 0, 0)), handle_left_type="FREE", handle_right_type="FREE")
BPList.add = lambda s, n: s.extend(_bp() for _ in range(n))
def _new(s, t):
    sp = Spline(type="BEZIER", bezier_points=BPList([_bp()]), use_cyclic_u=False, points=[])
    s.append(sp); return sp
Splines.new = _new
def link_factory():
    return NS(kind="RPAT", enabled=True, src="", src_obj=None, dst="", n1=3, n2=1, s1=1.0, s2=1.0,
              dir1=(0, 0, 0), dir2=(0, 0, 0), center=(0, 0, 0), axis=(0, 0, 1), angle=2 * math.pi,
              plane_o=(0, 0, 0), plane_n=(0, 0, 1), info="")
curve.cad.links = Coll(link_factory)
ctx.scene.objects = Objs({"Tel": curve})
for o in (curve,):
    o.cad.features, o.cad.bevels = [], []

def reset(auto=False):
    cu.splines.clear(); curve.cad.constraints.clear(); curve.cad.links.clear(); cmod._last_pos.clear()
    op.sketch.clear(); op.sk_points.clear(); op.sk_cons, op.sk_pats = [], {}
    op._hist_reset(); op.temp = op.temp_pick = None; op.coord_mode = False
    ctx.scene.minicad_auto_constraints = auto
    op._set_plane("XY"); op._set_tool(ctx, "LINE"); op.dirty = True

def co(si, i):
    return np.asarray(cu.splines[si].bezier_points[i].co, dtype=float)

def line(a, b):
    op._set_tool(ctx, "LINE"); click(a); click(b); key("RET")

def finish():
    key("RET", ctrl=True); op.dirty = True

def cons():
    return list(curve.cad.constraints)

print("A) Ayna: ayna çizgisi bir doğruysa simetri kısıtları (Bitir'de)")
reset()
line((0, -1), (0, 3)); line((1, 0), (2, 1))
op._set_tool(ctx, "MIRROR"); click((1.5, 0.5)); key("RET"); click((0, -1)); click((0, 3))
check(len(op.sketch) == 3 and len(op.sk_cons) == 2, f"aynalandı, {len(op.sk_cons)} simetri bekliyor")
finish()
ks = [c.kind for c in cons()]
check(ks.count("SYMLINE") == 2 and all(c.ok for c in cons()), f"Bitir: simetri kısıtları {ks}")
reset()
line((1, 0), (2, 1))
op._set_tool(ctx, "MIRROR"); click((1.5, 0.5)); key("RET"); click((0, -1)); click((0, 3))
check(len(op.sk_cons) == 0, "ayna noktaları doğru değilse kısıt yok (yalnız kopya)")

print("B) Köşe yuvarla: aynı yarıçaplılar eşit bağlanır")
reset()
op._set_tool(ctx, "RECT"); click((0, 0)); click((4, 2))
op._set_tool(ctx, "FILLET2D"); op.dirty = True; typ("0.5")
click((4, 0)); click((4, 2)); click((0, 2))
check(len(op.sk_cons) == 2 and all(c["kind"] == "EQUAL" for c in op.sk_cons), "iki EŞİT bekliyor (ilkine bağlı)")
finish()
eqs = [c for c in cons() if c.kind == "EQUAL"]
check(len(eqs) == 2 and all(c.ok for c in eqs), "Bitir: yaylar arası eşit yarıçap kısıtları")

print("C) İlişkisel dikdörtgen desen")
reset()
line((0, 0), (0, 1))
op._set_tool(ctx, "RPAT"); click((0, 0.5)); key("RET"); click((0, 0))
move((1, 0)); typ("3"); click((1, 0))
op.modal(ctx, ev("RIGHTMOUSE", (1, 0)))
check(len(op.sketch) == 3 and op.sk_pats, "3 adet, desen etiketli")
line((5, 5), (6, 5))                                    # desenden sonra çizilen
finish()
check(len(curve.cad.links) == 1, f"Bitir: ilişki kaydı ({len(curve.cad.links)})")
lk = curve.cad.links[0]
check(lk.kind == "RPAT" and lk.n1 == 3 and abs(lk.s1 - 1) < 1e-9 and lk.src == "0" and lk.dst == "1,2", f"kayıt: {lk.src} → {lk.dst}, n {lk.n1}, aralık {lk.s1}")
cmod.add("FIX", [("pt", curve, 3, 0)], solve=False)
fix = cons()[-1]
lk.n1 = 4; links.update_all(ctx.scene)
check(len(cu.splines) == 5 and np.allclose(co(4, 0), (3, 0, 0)), f"adet 4: yeni kopya x=3 ({len(cu.splines)} spline)")
lk.s1 = 2.0; links.update_all(ctx.scene)
check(np.allclose(co(1, 0), (2, 0, 0)) and np.allclose(co(4, 0), (6, 0, 0)), "aralık 2: kopyalar yeniden konumlandı")
cu.splines[0].bezier_points[1].co = Vec((0, 1.5, 0)); links.update_all(ctx.scene)
check(np.allclose(co(2, 1), (4, 1.5, 0)), "kaynak değişti: kopyalar izledi")
check(links.update_all(ctx.scene) == 0, "değişiklik yoksa yazılmaz")
lk.n1 = 2; links.update_all(ctx.scene)
check(len(cu.splines) == 3 and lk.dst == "1", f"adet 2: fazlalar silindi ({len(cu.splines)}), dst {lk.dst}")
check(fix.refs[0].spline == 2 and np.allclose(co(2, 0), (5, 5, 0)), "sonraki spline'a bağlı kısıt yeniden eşlendi")

print("D) İlişkisel dairesel desen")
reset()
line((1, 0), (2, 0))
op._set_tool(ctx, "CPAT"); click((1.5, 0)); key("RET"); click((0, 0)); typ("4"); key("RET")
finish()
lk = curve.cad.links[0]
check(lk.kind == "CPAT" and lk.n1 == 4 and len(cu.splines) == 4, "4 adet, ilişki")
lk.angle = math.radians(90); links.update_all(ctx.scene)
P = sorted(tuple(np.round(co(i, 0)[:2], 4)) for i in range(4))
check(np.allclose(P, sorted([(1, 0), (math.cos(math.pi / 6), math.sin(math.pi / 6)), (math.cos(math.pi / 3), math.sin(math.pi / 3)), (0, 1)]), atol=1e-4), f"90° içine 4 adet: {P}")

print("E) İlişkisel yansıtma")
reset()
op.sketch.append({"segs": [dm.line_seg(np.array([0., 0, 2]), np.array([2., 0, 2]))], "cyclic": False, "node_ids": {}, "start_tan": None})
finish()
op._set_tool(ctx, "PROJECT"); op.dirty = True; move((1, 0)); click((1, 0))
check(op.sketch[-1].get("proj") is not None, "yansıtılan çizgi kaynağını biliyor")
finish()
lk = curve.cad.links[0]
check(lk.kind == "PROJ" and lk.src == "0:0" and lk.dst == "1", f"ilişki: {lk.src} → {lk.dst}")
cu.splines[0].bezier_points[1].co = Vec((3, 1, 2)); links.update_all(ctx.scene)
check(np.allclose(co(1, 1), (3, 1, 0)) and abs(co(1, 0)[2]) < 1e-12, f"kaynak değişti: izdüşüm izledi {co(1, 1)}")

print("F) Taslağa al (Edit Sketch)")
reset()
op._set_tool(ctx, "RECT"); click((0, 0)); click((2, 1)); finish()
line((5, 0), (6, 0)); finish()
cmod.add("DISTANCE", [("seg", curve, 0, 0)], solve=False)
cmod.add("DISTANCE", [("seg", curve, 1, 0)], solve=False)
c_rect, c_line = cons()
op._set_tool(ctx, "EDITSK"); op.dirty = True
move((1, 0)); click((1, 0))
check(len(cu.splines) == 1 and len(op.sketch) == 1 and op.sketch[0].get("edit_src"), "dikdörtgen taslağa alındı, spline objeden çıktı")
check(c_line.refs[0].spline == 0 and c_rect.refs[0].spline < -1000, "referanslar: sonraki kaydı, kendisininki işaretli")
op._set_tool(ctx, "MOVE"); click((1, 0)); key("RET"); click((0, 0)); click((0, 3))
check(op.sketch[0].get("edit_src"), "taşınınca da kaynağı korunur")
finish()
check(len(cu.splines) == 2 and c_rect.refs[0].spline == 1 and c_line.refs[0].spline == 0, f"Bitir: geri yazıldı, referans {c_rect.refs[0].spline}")
check(np.allclose(co(1, 0), (0, 3, 0)), "yeni konumda")
cmod.solve_all(ctx.scene, force=True)
check(c_rect.ok and c_line.ok, "kısıtlar geçerli")

print("G) Metin")
reset()
op._font_splines = lambda context, text, size: [([((0, 0), (0, 0), (0, 0)), ((size, 0), (size, 0), (size, 0)), ((size, size), (size, size), (size, size))], True) for _ in text]
op._set_tool(ctx, "TEXT"); click((1, 1))
check(op.txt is not None, "yazı başladı")
for ch in "AB":
    op.modal(ctx, NS(type=ch, value="PRESS", mouse_x=0, mouse_y=0, unicode=ch, shift=False, ctrl=False, alt=False))
check(op.txt["text"] == "AB" and op.tool == "TEXT", "harfler araç kısayolu olmadan metne gitti")
key("TAB"); typ("0.5"); key("RET")
check(op.txt is None and len(op.sketch) == 2, f"2 harf çizgisi taslakta ({len(op.sketch)})")
P = np.array([sg["p"][0] for sg in op.sketch[0]["segs"]])
check(np.allclose(P[:, :2].max(axis=0), (1.5, 1.5)), f"yükseklik 0.5, konum (1,1): {P[:, :2].max(axis=0)}")
op._set_tool(ctx, "TEXT"); click((3, 3)); typ("1"); key("ESC")
check(op.txt is None and len(op.sketch) == 2 and op.tool == "TEXT", "Esc: metin iptal, araç açık")
print("t56 bitti")
