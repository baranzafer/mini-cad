# v0.23.0: Çizimi Düzenle — kaydedilmiş (Bitir'lenmiş) bir çizimin tamamını yeniden taslağa alma
# (Outliner / sağ tık menüsü, panel, Taslağa al aracında Shift+tık)
exec(open("t56.py").read().split('print("A)')[0])

print("A) Bütün çizim taslağa alınır, sıra ve referanslar korunur")
reset()
op._set_tool(ctx, "RECT"); click((0, 0)); click((2, 1)); finish()
op._set_tool(ctx, "POINT"); click((5, 5)); finish()
line((3, 0), (4, 0)); finish()
check(len(cu.splines) == 3 and len(cu.splines[1].bezier_points) == 1, "dikdörtgen, nokta, doğru kaydedildi")
cmod.add("DISTANCE", [("seg", curve, 0, 0)], solve=False)
cmod.add("DISTANCE", [("seg", curve, 2, 0)], solve=False)
c_rect, c_line = cons()
op._set_plane("XZ")                                     # düzenleme düzlemi çizimden alınmalı
n = op._edit_load_all(ctx, "Tel")
check(n == 2 and len(op.sketch) == 2 and all(st.get("edit_src") for st in op.sketch), f"2 çizgi taslakta ({n})")
check(len(cu.splines) == 1 and len(cu.splines[0].bezier_points) == 1, "objede yalnızca nokta kaldı")
check(c_rect.refs[0].spline < -1000 and c_line.refs[0].spline < -1000, "referanslar geçici işarette")
check(op.edit_obj == "Tel", "düzenlenen çizim hatırlandı")
check(op.plane_mode == "LOCK" and op.locked is not None and op.locked.name == "XY" and op.phase == "DRAW", "çizim düzlemi XY'ye kilitlendi")
line((3, 2), (4, 3))                                    # düzenlerken yeni çizgi
ctx.scene.minicad_draw_target = "NEW"                   # hedef yeni eğri olsa da düzenlenen çizime yazılır
made = []
op._new_curve = lambda context: made.append(1) or curve
finish()
ctx.scene.minicad_draw_target = "ACTIVE"
check(not made, "yeni eğri oluşturulmadı")
check(len(cu.splines) == 4, f"Bitir: 4 spline ({len(cu.splines)})")
check(c_rect.refs[0].spline == 1 and c_line.refs[0].spline == 2, f"sıra korundu: {c_rect.refs[0].spline}, {c_line.refs[0].spline}")
check(np.allclose(co(1, 0), (0, 0, 0)) and np.allclose(co(2, 0), (3, 0, 0)) and np.allclose(co(3, 0), (3, 2, 0)), "konumlar doğru")
check(op.edit_obj is None and not op.sketch, "düzenleme Bitir'le bitti")
cmod.solve_all(ctx.scene, force=True)
check(c_rect.ok and c_line.ok, "kısıtlar geçerli")

print("B) Yalnızca düzenlenen çizgiler: Bitir geri alma adımı yazar, Ctrl+Z koruması")
reset()
line((0, 0), (2, 0)); finish()
op._edit_load_all(ctx, "Tel")
check(len(cu.splines) == 0 and len(op.sketch) == 1, "çizgi taslakta")
u0 = len(undo)
key("Z", ctrl=True)
check(len(op.sketch) == 1 and len(undo) == u0, "Ctrl+Z Blender'a gitmedi (çizgiler çiftlenmez)")
op._set_tool(ctx, "MOVE"); click((1, 0)); key("RET"); click((0, 0)); click((0, 1))
key("Z", ctrl=True)
check(np.allclose(op.sketch[0]["segs"][0]["p"][0], (0, 0, 0)), "taslak geçmişi yine çalışır (taşıma geri alındı)")
c0 = op.created
finish()
check(len(cu.splines) == 1 and len(undo) == u0 + 1 and op.created == c0 + 1, "geri yazıldı, geri alma adımı var")
check(not op.hist, "Bitir'den sonra taslak geçmişi temiz")

print("C) Düzlem tanıma")
pts = lambda P: [(0, [{"kind": "line", "p": tuple(np.array(p, float) for p in P)}], False)]
check(op._edit_plane(pts([(0, 0, 1), (1, 0, 1), (1, 0, 1), (1, 1, 1)])).name == "XY", "XY")
check(op._edit_plane(pts([(0, 2, 0), (1, 2, 0), (1, 2, 0), (1, 2, 1)])).name == "XZ", "XZ")
pl = op._edit_plane(pts([(0, 0, 0), (1, 0, 1), (1, 0, 1), (1, 1, 1)]))
check(pl is not None and pl.name == "FACE" and abs(abs(pl.n @ np.array([-1, 0, 1]) / 2 ** 0.5) - 1) < 1e-9, "eğik düzlem")
check(op._edit_plane(pts([(0, 0, 0), (1, 0, 0), (1, 1, 0), (1, 1, 1)])) is None, "düzlemsel değil: kilit yok")
check(op._edit_plane(pts([(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)])) is None, "tek doğru: kilit yok")

print("D) Taslağa al aracında Shift+tık: bütün çizim")
reset()
line((0, 0), (2, 0)); finish(); line((0, 3), (2, 3)); finish()
op._set_tool(ctx, "EDITSK"); op.dirty = True
move((1, 0)); op.modal(ctx, ev("LEFTMOUSE", (1, 0), shift=True)); op.modal(ctx, ev("LEFTMOUSE", (1, 0), val="RELEASE"))
check(len(cu.splines) == 0 and len(op.sketch) == 2, "iki çizgi birden taslakta")
finish()
check(len(cu.splines) == 2 and np.allclose(co(0, 0), (0, 0, 0)) and np.allclose(co(1, 0), (0, 3, 0)), "aynı sırayla geri yazıldı")

print("E) Çizimi Düzenle komutu (Outliner / panel)")
reset()
line((0, 0), (2, 0)); finish()
E = draw.MINICAD_OT_edit_sketch
check(E.poll(ctx), "aktif eğri varken komut kullanılabilir")
check(draw.edit_target(NS(active_object=None, selected_ids=[NS(type="MESH", matrix_world=I4), curve])) is curve, "Outliner seçiminden eğri bulunur")
check(draw.edit_target(NS(active_object=None, selected_ids=[], selected_objects=[])) is None, "eğri yoksa komut kapalı")
eo = E.__new__(E); eo.report = lambda *a: print("RAPOR", a)
r = eo.execute(ctx)                                     # çizim aracı açık: taslağa eklenir
check(r == {"FINISHED"} and len(op.sketch) == 1 and len(cu.splines) == 0, "açık araçta taslağa alındı")
r = eo.execute(ctx)
check(r == {"CANCELLED"} and len(op.sketch) == 1, "ikinci kez alınmaz")
finish()
check(len(cu.splines) == 1, "geri yazıldı")

print("F) Çizim aracı edit_curve ile açılınca")
draw._STATE["active"] = None
op2 = draw.MINICAD_OT_draw.__new__(draw.MINICAD_OT_draw); op2.report = lambda *a: None
op2.edit_curve = "Tel"
op2.invoke(ctx, NS())
check(len(op2.sketch) == 1 and len(cu.splines) == 0 and op2.edit_obj == "Tel" and op2.phase == "DRAW", "açılışta çizim taslağa alındı")
calls = []
draw._STATE["active"] = None
bpy.ops.minicad = NS(draw=lambda *a, **k: calls.append(k))
ctx.temp_override = lambda **k: __import__("contextlib").nullcontext()
ctx.window = NS()
eo.execute(ctx)
check(calls == [{"edit_curve": "Tel"}], f"araç kapalıyken çizim aracı açılır: {calls}")
print("t59 bitti")
