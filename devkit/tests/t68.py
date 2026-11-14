# v0.25.12: iki kapalı eğri arasına bağlantı çizgisi — uçlar eğriye yapışır (tam eğri üstü),
# Bitir'de eğriye nokta eklenip çakışık kısıtıyla bağlanır; eksen (X/Y/Z) ve düzlem
# (Shift+X/Y/Z) kilidi hiç bozulmaz: kilitliyken eğrinin kilitle kesiştiği nokta yakalanır
exec(open("t59.py").read().split('print("A) Bütün')[0])
sfm = importlib.import_module("mini_cad.surfmath")

def add_loop(pts):
    """Doğrudan objeye kapalı çokgen spline (düz kenarlar, tutamaçlar 1/3'te)."""
    sp = Spline(type="BEZIER", use_cyclic_u=True, points=[], bezier_points=BPList())
    n = len(pts)
    for i, p in enumerate(pts):
        p, nx, pv = Vec(p), Vec(pts[(i + 1) % n]), Vec(pts[i - 1])
        sp.bezier_points.append(BP(co=p, handle_left=Vec(p + (pv - p) / 3), handle_right=Vec(p + (nx - p) / 3),
                                   handle_left_type="VECTOR", handle_right_type="VECTOR"))
    cu.splines.append(sp)
    return len(cu.splines) - 1

def coin():
    return [c for c in curve.cad.constraints if c.kind == "COINCIDENT"]

def on_spline(si, q):
    sp = cu.splines[si]
    return any(np.allclose(np.asarray(b.co, float), q, atol=1e-6) for b in sp.bezier_points)

print("A) 2B: X eksen kilidiyle iki kare arası doğru, iki uç da eğriye bağlanır")
reset()
a = add_loop([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)])
b = add_loop([(5, 0, 0), (7, 0, 0), (7, 3, 0), (5, 3, 0)])
op.dirty = True
op._set_tool(ctx, "LINE")
move((2.03, 1.3))
check(op.snap_kind == "Yakın" and np.allclose(op.cursor, (2, 1.3, 0)), f"başlangıç eğrinin tam üstünde: {op.snap_kind} {op.cursor}")
click((2.03, 1.3))
key("X")
move((3.5, 1.9))
check(abs(op.cursor[1] - 1.3) < 1e-9, "X kilidi: imleç eksende")
move((5.08, 1.45))
check(op.snap_kind == "Eğri" and np.allclose(op.cursor, (5, 1.3, 0), atol=1e-9), f"eksen ∩ eğri: {op.snap_kind} {op.cursor}")
move((4.95, 0.1))                                       # karenin köşesi yakın: kilit bozulmaz
check(abs(op.cursor[1] - 1.3) < 1e-9, f"köşe yakınında da eksende: {op.cursor}")
move((5.08, 1.45)); click((5.08, 1.45))
key("RET")
check(op.sketch[-1].get("attach") and len(op.sketch[-1]["attach"]) == 2, "iki uç eğriye yapışık işaretli")
check(op.axis_lock == 0, "eksen kilidi kapatana kadar açık kalır")
key("X")
finish()
check(len(cu.splines[a].bezier_points) == 5 and len(cu.splines[b].bezier_points) == 5, "iki kareye de nokta eklendi")
check(on_spline(a, (2, 1.3, 0)) and on_spline(b, (5, 1.3, 0)), "noktalar kesişimde")
ln = len(cu.splines) - 1
cs = coin()
check(len(cs) == 2 and all(c.ok for c in cs), f"2 çakışık kısıt: {[(c.kind, c.ok) for c in curve.cad.constraints]}")
check({(r.spline, r.index) for c in cs for r in c.refs} >= {(a, 2), (b, 4), (ln, 0), (ln, 1)}, "kısıtlar doğru noktalarda")
sq = cu.splines[a]
check(np.allclose(sq.bezier_points[1].co, (2, 0, 0)) and np.allclose(sq.bezier_points[3].co, (2, 2, 0)), "kare biçimi değişmedi")

print("B) Düzlem kilidi (Shift+Z): dik duran eğri düzlemi kestiği yerden yakalanır")
reset()
a = add_loop([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)])
b = add_loop([(5, 1.3, -1), (7, 1.3, -1), (7, 1.3, 1), (5, 1.3, 1)])      # XZ'de duran kare
op.dirty = True
check(op.plane_mode == "XY", "XY düzlem kilidi (Shift+Z)")
op._set_tool(ctx, "LINE")
click((2.03, 1.5))
move((5.05, 1.33))
check(op.snap_kind == "Eğri" and np.allclose(op.cursor, (5, 1.3, 0), atol=1e-9), f"düzlem ∩ eğri (köşe yerine): {op.snap_kind} {op.cursor}")
move((6.0, 1.33))
check(abs(op.cursor[2]) < 1e-9, f"üst kenar yakınında z=0'da kalır: {op.cursor}")
move((5.05, 1.33)); click((5.05, 1.33)); key("RET")
finish()
check(len(cu.splines[b].bezier_points) == 5 and on_spline(b, (5, 1.3, 0)), "dik kareye z=0'da nokta eklendi")
check(len(coin()) == 2 and all(c.ok for c in coin()), "iki uç bağlı")

print("C) Kilitsiz, eğri üstüne iki uç (Yakın) ve çok parçalı çizgi")
reset()
a = add_loop([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)])
b = add_loop([(5, 0, 0), (7, 0, 0), (7, 3, 0), (5, 3, 0)])
op.dirty = True
op._set_tool(ctx, "LINE")
click((0.7, 1.98)); click((3, 4)); click((5.6, 2.98)); key("RET")
finish()
check(len(cu.splines[a].bezier_points) == 5 and len(cu.splines[b].bezier_points) == 5, "iki uca da nokta eklendi")
check(on_spline(a, (0.7, 2, 0)) and on_spline(b, (5.6, 3, 0)), "noktalar eğri üstünde")
check(len(coin()) == 2, "2 çakışık kısıt")

print("D) Taslaktaki (Bitir'lenmemiş) kareye bağlanma, uç taşınırsa bağlanmaz")
reset()
op._set_tool(ctx, "RECT"); click((0, 0)); click((2, 2))
op._set_tool(ctx, "LINE"); op.dirty = True
click((2.02, 0.7)); click((4, 0.7)); key("RET")
check(op.sketch[-1].get("attach"), "taslaktaki kareye yapıştı")
finish()
rect_si = 0
check(len(cu.splines[rect_si].bezier_points) == 5 and len(coin()) >= 1, f"Bitir'de taslaktan yazılan kareye nokta eklendi ({len(cu.splines[rect_si].bezier_points)})")
reset()
a = add_loop([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)])
op.dirty = True
op._set_tool(ctx, "LINE"); click((2.02, 0.7)); click((4, 0.7)); key("RET")
op.sketch[-1]["segs"][0]["p"] = [np.array(v, float) for v in [(2.5, 0.7, 0), (3, 0.7, 0), (3.5, 0.7, 0), (4, 0.7, 0)]]
finish()
check(len(cu.splines[a].bezier_points) == 4 and not coin(), "uç eğriden ayrıldıysa eğriye dokunulmaz")

print("F) Eğri (daire) hedef: eksen kilidinde kesişim bezier'in tam üstünde")
reset()
a = add_loop([(0, 0, 0), (2, 0, 0), (2, 2, 0), (0, 2, 0)])
op.dirty = True
op._set_tool(ctx, "CIRCLE"); click((5, 1)); click((6, 1))
finish()
ci = len(cu.splines) - 1
n0 = len(cu.splines[ci].bezier_points)
op._set_tool(ctx, "LINE"); op.dirty = True
click((2.03, 1.3)); key("X")
x = 5 - (1 - 0.09) ** 0.5
move((x + 0.05, 1.4))
segs = [sfm.cubic(corem._spline_segment(curve, ci, cu.splines[ci], k, I4)["p"]) for k in range(n0)]
dmin = min(sfm.closest_t(P_, op.cursor)[1] for P_ in segs)
check(op.snap_kind == "Eğri" and abs(op.cursor[1] - 1.3) < 1e-9 and dmin < 1e-9, f"daire ∩ X ekseni: {op.cursor}, sapma {dmin:.1e}")
click((x + 0.05, 1.4)); key("RET"); key("X")
finish()
check(len(cu.splines[ci].bezier_points) == n0 + 1 and len(coin()) == 2, f"daireye nokta eklendi ({n0} → {len(cu.splines[ci].bezier_points)})")
segs2 = [sfm.cubic(corem._spline_segment(curve, ci, cu.splines[ci], k, I4)["p"]) for k in range(n0 + 1)]
dev = max(min(sfm.closest_t(P0, sfm.bez(P_, t))[1] for P0 in segs) for P_ in segs2 for t in np.linspace(0, 1, 7))
check(dev < 1e-9, f"daire biçimi değişmedi (sapma {dev:.1e})")

print("E) surfmath kesişimleri")
P = np.array([[0, 0, 0], [1, 2, 0], [3, 2, 0], [4, 0, 0.]])
check(len(sfm.bez_plane_hits(P, [2, 0, 0], [1, 0, 0])) == 1, "düzlem: tek kesişim (örnek noktada)")
check(sfm.bez_plane_hits(P, [0, 0, 0], [0, 0, 1]) == [], "düzlemdeki eğri: kesişim sayılmaz")
hs = [sfm.bez(P, t) for t in sfm.bez_line_hits(P, [0, 1, 0], [1, 0, 0], 1e-9)]
check(len(hs) == 2 and all(abs(h[1] - 1) < 1e-9 for h in hs), "doğru: iki kesişim")
check(sfm.bez_line_hits(P, [0, 1, 1], [1, 0, 0], 1e-9) == [], "kesişmeyen doğru")
check(np.allclose(sfm.bez(P, sfm.bez_ray_closest(P, [2, 1.5, 5], [0, 0, -1])), (2, 1.5, 0)), "ışına en yakın")
print("t68 bitti")
