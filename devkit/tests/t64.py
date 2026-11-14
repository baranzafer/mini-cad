# v0.25.5: taslakta Teğet / Pürüzsüz — anında ve biçimi bozmadan (Inventor gibi)
exec(open("t58.py").read().split('print("A)')[0])
import math

def arc_info(k):
    segs = [np.array([np.asarray(q, float) for q in sg["p"]]) for sg in op.sketch[k]["segs"]]
    arcs = [dm.arc_of_bezier(P) for P in segs]
    return segs, arcs

def tang_angle(a, b):
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    return math.degrees(math.acos(min(1.0, abs(float(np.dot(a, b))))))

def ctool_click(kind, pa, pb):
    ctool(kind); click(pa); click(pb)

print("A) Kullanıcı senaryosu: doğru + ucundan 3 noktalı yay → Teğet")
reset()
line((-4, 1), (1, 4))
op._set_tool(ctx, "ARC3"); click((1, 4)); click((5, 4)); click((3.5981, 4.7984)); key("RET")
check(len(op.sketch) == 2, "doğru ve yay taslakta")
L0 = seg_pts(0)
segs0, arcs0 = arc_info(1)
check(all(a is not None for a in arcs0), f"yay ({len(segs0)} parça)")
before = tang_angle(L0[3] - L0[0], segs0[0][1] - segs0[0][0])
ctool_click("TANGENT", (-1.5, 2.5), (3.6, 4.79))
check(len(op.skc) == 1 and op.skc[0]["ok"], f"teğet uygulandı ({op.skc[0]['info']})")
L1 = seg_pts(0)
check(all(np.allclose(p, q) for p, q in zip(L0, L1)), "doğru hiç değişmedi")
segs1, arcs1 = arc_info(1)
check(len(segs1) == len(segs0), "yayın parça sayısı aynı (kısıt referansları kaymaz)")
check(np.allclose(segs1[0][0], (1, 4, 0)) and np.allclose(segs1[-1][3], (5, 4, 0)), "yayın iki ucu yerinde")
check(all(a is not None for a in arcs1) and all(np.linalg.norm(a[0] - arcs1[0][0]) < 1e-6 and abs(a[1] - arcs1[0][1]) < 1e-6 for a in arcs1),
      f"hâlâ gerçek bir çember yayı (R {arcs1[0][1]:.4f})")
after = tang_angle(L1[3] - L1[0], segs1[0][1] - segs1[0][0])
check(before > 5 and after < 1e-4, f"ortak uçta kırılma {before:.1f}° → {after:.2e}°")
v = segs1[0][1] - segs1[0][0]
check(float(np.dot(v, L1[3] - L1[0])) > 0, "yay doğrunun devamı yönünde çıkıyor (geri dönmüyor)")

print("B) Sürüklemeden sonra teğetlik korunur")
st = op.sketch[1]
sm._move_node(st["segs"], len(st["segs"]), np.array([6.0, 3.0, 0.0]), False)
op._sk_solve()
segs2, arcs2 = arc_info(1)
check(np.allclose(segs2[-1][3], (6, 3, 0)) and all(a is not None for a in arcs2), "yay yeni uca uzandı, hâlâ yay")
check(tang_angle(L1[3] - L1[0], segs2[0][1] - segs2[0][0]) < 1e-4 and all(np.allclose(p, q) for p, q in zip(L1, seg_pts(0))), "teğet ve doğru korundu")

print("C) Pürüzsüz doğru–yay: G2 olamaz, açıklama + teğet")
reset()
line((-4, 1), (1, 4))
op._set_tool(ctx, "ARC3"); click((1, 4)); click((5, 4)); click((3.5981, 4.7984)); key("RET")
ctool_click("SMOOTH", (-1.5, 2.5), (3.6, 4.79))
check(not op.skc[0]["ok"] and "G2" in op.skc[0]["info"], f"açıklama: {op.skc[0]['info'][:50]}")
segs3, _ = arc_info(1)
check(tang_angle(np.array([5.0, 3.0, 0]), segs3[0][1] - segs3[0][0]) < 1e-4, "teğet yine de uygulandı")

print("D) Doğru + serbest eğri: doğru ve eğrinin biçimi korunur, yalnızca uç tutamacı döner")
reset()
line((0, 0), (2, 0))
op._set_tool(ctx, "FIT"); click((2, 0)); click((3, 1.5)); click((5, 1)); key("RET")
c0 = [np.array([np.asarray(q, float) for q in sg["p"]]) for sg in op.sketch[1]["segs"]]
ctool_click("TANGENT", (1, 0), (3, 1.5))
c1 = [np.array([np.asarray(q, float) for q in sg["p"]]) for sg in op.sketch[1]["segs"]]
check(op.skc[0]["ok"] and all(np.allclose(p, q) for p, q in zip(seg_pts(0), [np.array(x) for x in [(0,0,0),(2/3,0,0),(4/3,0,0),(2,0,0)]])), "doğru değişmedi")
check(tang_angle(np.array([1.0, 0, 0]), c1[0][1] - c1[0][0]) < 1e-4, "eğri ortak uçta doğruya teğet")
check(abs(np.linalg.norm(c1[0][1] - c1[0][0]) - np.linalg.norm(c0[0][1] - c0[0][0])) < 1e-9, "tutamaç boyu aynı")
check(all(np.allclose(c0[i], c1[i]) for i in range(1, len(c0))) and np.allclose(c0[0][2:], c1[0][2:]), "eğrinin geri kalanı (noktalar, öbür tutamaçlar) aynı")

print("E) Yay + serbest eğri: Pürüzsüz (G2) — eğrilik eşit")
reset()
op._set_tool(ctx, "ARC3"); click((0, 0)); click((2, 0)); click((1, 1)); key("RET")
op._set_tool(ctx, "FIT"); click((2, 0)); click((3, -1)); click((5, -0.5)); key("RET")
ctool_click("SMOOTH", (1, 1), (3, -1))
check(op.skc[0]["ok"], f"pürüzsüz uygulandı ({op.skc[0]['info']})")
A_ = op._skc_ent(op.skc[0]["refs"][0]); B_ = op._skc_ent(op.skc[0]["refs"][1])
ka, na = op._curvature(A_, False); kb, nb = op._curvature(B_, True)
check(abs(ka - 1.0) < 1e-6 and abs(kb - ka) < 1e-6 and float(np.dot(na, nb)) > 0.999, f"eğrilik {ka:.4f} = {kb:.4f}, aynı yönde")
check(tang_angle(A_["segs"][-1][3] - A_["segs"][-1][2], B_["segs"][0][1] - B_["segs"][0][0]) < 1e-4, "teğet")
arcsA = [dm.arc_of_bezier(P) for P in A_["segs"]]
check(all(a is not None and abs(a[1] - 1.0) < 1e-6 for a in arcsA), "yay değişmedi (R 1)")

print("F) Ortak ucu olmayan: doğru daireye teğet (doğru kendine paralel kayar)")
reset()
op._set_tool(ctx, "CIRCLE"); click((0, 0)); click((1, 0)); key("RET")
line((-2, 1.5), (2, 1.6))
L0 = seg_pts(1)
ctool_click("TANGENT", (0, 1.55), (1, 0))
L1 = seg_pts(1)
u = (L1[3] - L1[0]) / np.linalg.norm(L1[3] - L1[0])
d = abs(float(u[0] * (-L1[0][1]) - u[1] * (-L1[0][0])))
check(op.skc[0]["ok"] and abs(d - 1.0) < 1e-6, f"doğrunun merkeze uzaklığı = R ({d:.6f})")
check(np.allclose(L1[3] - L1[0], L0[3] - L0[0]), "doğrunun yönü ve boyu aynı")
_, carcs = arc_info(0)
check(all(a is not None and abs(a[1] - 1) < 1e-6 and np.allclose(a[0], 0) for a in carcs), "daire değişmedi")

print("G) Bitir: kaydedilen geometri taslaktaki gibi kalır, teğet kısıtı yazılır")
reset()
line((-4, 1), (1, 4))
op._set_tool(ctx, "ARC3"); click((1, 4)); click((5, 4)); click((3.5981, 4.7984)); key("RET")
ctool_click("TANGENT", (-1.5, 2.5), (3.6, 4.79))
P_line, P_arc = seg_pts(0), [np.array([np.asarray(q, float) for q in sg["p"]]) for sg in op.sketch[1]["segs"]]
key("RET", ctrl=True)
ks = [c.kind for c in curve.cad.constraints]
check("TANGENT" in ks, f"Bitir: teğet kısıtı ({ks})")
sp_arc = cu.splines[1]
P_saved = np.array([np.asarray(b.co, float) for b in sp_arc.bezier_points])
check(np.allclose(P_saved[0], (1, 4, 0)) and np.allclose(P_saved[-1], (5, 4, 0)), "yay uçları yerinde")
h = np.asarray(sp_arc.bezier_points[0].handle_right, float) - P_saved[0]
check(tang_angle(np.array([5.0, 3.0, 0]), h) < 1e-4, "kaydedilen yay doğruya teğet")
check(np.allclose(np.asarray(cu.splines[0].bezier_points[0].co, float), (-4, 1, 0)), "doğru yerinde")
print("t64 bitti")
