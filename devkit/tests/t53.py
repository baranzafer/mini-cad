# v0.19.0 (Aşama 4): Ölçü aracı, Yatay / Dikey, Eş merkezli, Yarıçap / Çap, Pürüzsüz (G2),
# Simetrik (çizgiye göre), nokta-doğru uzaklığı; ölçü değeri düzenleme
exec(open("t42.py").read().split("def tang():")[0])
ctx.region = region
ca = importlib.import_module("mini_cad.constraints_arcs")

def check(cond, msg):
    print(("  tamam  " if cond else "  HATA   ") + msg)
    if not cond:
        raise SystemExit(1)

def reset():
    cu.splines.clear(); curve.cad.constraints.clear(); cmod._last_pos.clear()
    op.sketch.clear(); op.sk_points.clear(); op._hist_reset(); op.temp = op.temp_pick = None
    ctx.scene.minicad_auto_constraints = False
    op._set_plane("XY"); op._set_tool(ctx, "LINE"); op.dirty = True

def co(si, i):
    return np.asarray(cu.splines[si].bezier_points[i].co, dtype=float)

def line(a, b):
    op._set_tool(ctx, "LINE"); click(a); click(b); key("RET")

def finish():
    key("RET", ctrl=True); op.dirty = True

def ctool(k):
    op._set_tool(ctx, "C_" + k); op.dirty = True

def last():
    return curve.cad.constraints[-1]

print("A) Ölçü: doğruya tık + Enter → uzunluk; değer yaz")
reset(); line((0, 0), (2, 0)); finish()
ctool("DIM")
click((1, 0))
check(len(op.c_refs) == 1 and op.c_refs[0][0] == "seg", "doğru seçildi")
key("RET")
c = last()
check(c.kind == "DISTANCE" and abs(c.length - 2) < 1e-9 and op.dim_edit is not None, "uzunluk ölçüsü 2, değer düzenleme açık")
typ("3"); key("RET")
L = np.linalg.norm(co(0, 1) - co(0, 0))
check(abs(L - 3) < 1e-6 and op.dim_edit is None, f"değer 3 uygulandı: boy {L:.6f}")
print("   mevcut ölçüye tık: düzenle")
cmod._glyph_boxes.clear(); cmod._glyph_boxes.append((690, 690, 720, 710, "Tel", 0))
op.modal(ctx, NS(type="LEFTMOUSE", value="PRESS", mouse_x=700, mouse_y=700, unicode="", shift=False, ctrl=False, alt=False))
check(op.dim_edit == ("Tel", 0), "ölçü değerine tıklayınca düzenleme")
typ("1.5"); key("RET")
check(abs(np.linalg.norm(co(0, 1) - co(0, 0)) - 1.5) < 1e-6, "1.5 uygulandı")
cmod._glyph_boxes.clear()
key("ESC")

print("B) Ölçü: iki doğru → açı; paralel → uzaklık; iki nokta → mesafe; nokta + doğru")
reset(); line((0, 0), (2, 0)); line((0, 1), (2, 2)); finish()
ctool("DIM"); click((1, 0)); click((1, 1.5))
c = last()
check(c.kind == "ANGLE" and abs(math.degrees(c.angle) - math.degrees(math.atan2(1, 2))) < 1e-6, f"açı {math.degrees(c.angle):.3f}°")
typ("45"); key("RET")
d1, d2 = co(0, 1) - co(0, 0), co(1, 1) - co(1, 0)
ang = math.degrees(math.acos(np.dot(d1, d2) / np.linalg.norm(d1) / np.linalg.norm(d2)))
check(abs(ang - 45) < 1e-4, f"45° uygulandı: {ang:.5f}")
reset(); line((0, 0), (2, 0)); line((0, 1), (2, 1)); finish()
ctool("DIM"); click((1, 0)); click((1, 1))
c = last()
check(c.kind == "LINEDIST" and abs(c.length - 1) < 1e-9, "paralel doğrular: uzaklık 1")
typ("2"); key("RET")
d = (co(0, 1) - co(0, 0)) / np.linalg.norm(co(0, 1) - co(0, 0))
dists = [abs(float(np.cross(co(1, i) - co(0, 0), d)[2])) for i in (0, 1)]
check(np.allclose(dists, 2, atol=1e-6), f"uzaklık 2, doğrular paralel kaldı: {np.round(dists, 6)}")
reset(); line((0, 0), (1, 0)); line((3, 3), (4, 3)); finish()
ctool("DIM"); click((0, 0)); click((3, 3))
c = last()
check(c.kind == "DISTANCE" and len(c.refs) == 2 and all(r.point for r in c.refs), "iki nokta: mesafe")
op.modal(ctx, ev("RIGHTMOUSE", (3, 3)))
check(op.dim_edit is None, "sağ tık: ölçülen değer kaldı")
click((3.5, 3)); click((0, 0))
check(last().kind == "PTLINE", "doğru + nokta (sıra fark etmez): uzaklık")
key("ESC")

print("C) Yarıçap / çap (ölçü aracıyla ve Yarıçap kısıtıyla)")
reset()
op._set_tool(ctx, "ARC3"); click((1, 0)); click((-1, 0)); click((0, 1)); key("RET")
finish()
g = ca.arc_group(curve, 0, 0)
check(g is not None and abs(g["R"] - 1) < 1e-6 and len(g["segs"]) == 2, f"yay grubu: R {g and round(g['R'], 6)}, {g and len(g['segs'])} parça")
ctool("DIM"); click((0, 1)); key("RET")
c = last()
check(c.kind == "RADIUS" and c.axis == 0 and abs(c.length - 1) < 1e-6, "yay: yarıçap ölçüsü")
typ("2"); key("RET")
g = ca.arc_group(curve, 0, 0)
check(g is not None and abs(g["R"] - 2) < 1e-4 and c.ok, f"yarıçap 2: {g and g['R']:.6f}")
reset()
op._set_tool(ctx, "CIRCLE"); click((0, 0)); click((1, 0)); finish()
ctool("DIM"); click((0, 1)); key("RET")
c = last()
check(c.kind == "RADIUS" and c.axis == 1, "daire: çap gösterilir")
typ("4"); key("RET")
g = ca.arc_group(curve, 0, 0)
check(g["closed"] and abs(g["R"] - 2) < 1e-4 and np.allclose(g["c"], 0, atol=1e-5), f"çap 4 → R 2, merkez yerinde: {g['R']:.6f}")

print("D) Eş merkezli")
reset()
op._set_tool(ctx, "CIRCLE"); click((0, 0)); click((1, 0)); click((3, 1)); click((3.5, 1)); finish()
ctool("CONCENTRIC"); click((0, 1)); click((3, 1.5))
c = last()
g0, g1 = ca.arc_group(curve, 0, 0), ca.arc_group(curve, 1, 0)
check(c.kind == "CONCENTRIC" and c.ok and np.linalg.norm(g0["c"] - g1["c"]) < 1e-5, f"merkezler çakıştı: {np.round(g0['c'], 4)} {np.round(g1['c'], 4)}")
check(abs(g0["R"] - 1) < 1e-3 and abs(g1["R"] - 0.5) < 1e-3, f"yarıçaplar korundu: {g0['R']:.4f}, {g1['R']:.4f}")

print("E) Yatay / Dikey (çizim düzlemine göre)")
reset(); line((0, 0), (2, 0.5)); line((3, 0), (3.4, 2)); finish()
ctool("HORIZ"); click((1, 0.25))
check(last().kind == "AXIS" and last().axis == 0 and abs(co(0, 1)[1] - co(0, 0)[1]) < 1e-6, "yatay")
ctool("VERT"); click((3.2, 1))
check(last().axis == 1 and abs(co(1, 1)[0] - co(1, 0)[0]) < 1e-6, "dikey")

print("F) Simetrik (çizgiye göre)")
reset(); line((-1, 1), (-1, 2)); line((0, -1), (0, 3)); line((1.5, 1.2), (2, 2)); finish()
ctool("SYMLINE")
check(op._c_want() == "pt", "önce nokta")
click((-1, 1)); click((1.5, 1.2))
check(op._c_want() == "seg", "sonra simetri doğrusu")
click((0, 0.5))
p, q = co(0, 0), co(2, 0)
a, b = co(1, 0), co(1, 1)                       # simetri doğrusu (serbest: o da hareket edebilir)
d = (b - a) / np.linalg.norm(b - a)
refl = p - 2 * ((p - a) - d * np.dot(p - a, d))
check(last().kind == "SYMLINE" and last().ok and np.allclose(refl, q, atol=1e-6), f"doğruya göre simetrik: {np.round(p, 4)} ↔ {np.round(q, 4)}")

print("G) Pürüzsüz (G2): doğru + spline (oto kısıtlar açık: uçlar çakışık, doğru yatay)")
reset(); ctx.scene.minicad_auto_constraints = True
line((0, 0), (2, 0))
op._set_tool(ctx, "FIT"); click((2, 0)); click((3, 0.8)); click((4, 0.5)); key("RET")
finish()
check(len(cu.splines) == 2, "doğru ve spline")
ctool("SMOOTH"); click((1, 0)); click((2.6, 0.5))
c = last()
sp = cu.splines[1]
Q = [np.asarray(v, dtype=float) for v in (sp.bezier_points[0].co, sp.bezier_points[0].handle_right, sp.bezier_points[1].handle_left, sp.bezier_points[1].co)]
k = ca._curv_vec(Q)
t = Q[1] - Q[0]
check(c.kind == "SMOOTH" and c.ok, f"pürüzsüz eklendi: {c.info!r}")
check(abs(t[1]) < 1e-6 * np.linalg.norm(t), "teğet: spline doğru yönünde çıkıyor")
check(np.linalg.norm(k) < 1e-6, f"eğrilik birleşimde 0 (doğruya eşit): {np.linalg.norm(k):.2e}")
check(np.allclose(co(0, 1), co(1, 0)) and abs(co(0, 1)[1] - co(0, 0)[1]) < 1e-9, "uçlar birleşik, doğru yatay kaldı")
reset(); line((0, 0), (2, 0)); line((2, 0), (3, 1)); finish()
ctool("SMOOTH"); click((1, 0)); click((2.5, 0.5))
check(not last().ok and last().info, f"iki doğru: reddedilir ({last().info})")

print("H) Simge / panel adları")
for k in ("CONCENTRIC", "RADIUS", "SMOOTH", "SYMLINE", "PTLINE"):
    check(k in cmod.NAMES and k in cmod.ICON, f"{k}: {cmod.NAMES[k]}")
pal = importlib.import_module("mini_cad.palette")
check(all(any(x[0] == k for x in pal.CONSTRAINTS) for k in ("DIM", "HORIZ", "VERT", "CONCENTRIC", "RADIUS", "SMOOTH", "SYMLINE")), "palet düğmeleri")
print("t53 bitti")
