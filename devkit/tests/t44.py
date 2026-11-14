# v0.15.3: taslak çizgisinin ucundan teğet yay, sürüklerken ölçü yardımcısı, geçici zemin (U)
exec(open("t42.py").read().split("def tang():")[0])

def check(cond, msg):
    print(("  tamam  " if cond else "  HATA   ") + msg)
    if not cond:
        raise SystemExit(1)

def reset():
    cu.splines.clear(); curve.cad.constraints.clear(); cmod._last_pos.clear()
    op.sketch.clear(); op._hist_reset()
    ctx.scene.minicad_auto_constraints = True
    op._set_tool(ctx, "LINE"); op.dirty = True

print("A) Teğet yay, TASLAKTAKİ (henüz Bitir'lenmemiş) doğrunun ucundan:")
reset()
click((-1, -2)); click((-1, 0)); key("RET")          # taslağa eklendi, eğriye yazılmadı
check(len(op.sketch) == 1 and len(cu.splines) == 0, "doğru taslakta")
op._set_tool(ctx, "TARC"); op.dirty = True
click((-1, 0))
check(op.start_tan is not None and op.start_tan[1][0] == "@sketch", f"başlangıç teğeti: {op.start_tan and np.round(op.start_tan[0], 3)}")
check(np.allclose(op.start_tan[0], (0, 1, 0)), "teğet doğrunun devamı (+Y)")
move((1, 0))
check(op.preview and op.preview[0]["kind"] != "line" and op.arc_info and "radius" in op.arc_info,
      f"önizleme teğet yay, R={op.arc_info and round(op.arc_info['radius'], 3)}")
check(abs(op.arc_info["radius"] - 1.0) < 1e-6, "yarıçap 1 (3 noktalı yay gibi değil)")
click((1, 0)); key("RET"); key("RET", ctrl=True)
kinds = [c.kind for c in curve.cad.constraints]
print("   kısıtlar:", kinds)
check("TANGENT" in kinds, "Bitir'de TEĞET kısıtı yazıldı")
a = cu.splines[1].bezier_points[0]; l = cu.splines[0].bezier_points
t_arc = np.asarray(a.handle_right) - np.asarray(a.co); dd = np.asarray(l[1].co) - np.asarray(l[0].co)
dev = float(np.linalg.norm(np.cross(t_arc / np.linalg.norm(t_arc), dd / np.linalg.norm(dd))))
check(dev < 1e-6, f"yazılan yay doğruya teğet (sapma {dev:.2e})")

print("B) Teğet yay, taslak doğrusunun BAŞLANGIÇ ucundan (ters yön):")
reset()
click((0, 0)); click((2, 0)); key("RET")
op._set_tool(ctx, "TARC"); op.dirty = True
click((0, 0))
check(op.start_tan is not None and np.allclose(op.start_tan[0], (-1, 0, 0)), "teğet dışarı doğru (-X)")
op._undo_last(ctx); op._set_tool(ctx, "LINE")

print("C) Boşlukta teğet yay hâlâ 3 noktalı yay gibi:")
reset()
op._set_tool(ctx, "TARC"); click((3, -3))
check(op.start_tan is None, "teğet yok")
op._undo_last(ctx)

print("D) Taslak noktası sürüklerken ölçü: yazılan uzunluk + açı")
reset()
click((0, 0)); click((1, 0)); key("RET")
p0 = to_px((1, 0))
op.modal(ctx, ev("MOUSEMOVE", (1, 0))); op.modal(ctx, ev("LEFTMOUSE", (1, 0)))
check(op.sk_drag is not None and op.sk_drag["key"][0] == "pt", "sürükleme başladı")
move((1.5, 0.3))
check(op._dim_anchor() is not None and np.allclose(op._dim_anchor(), (0, 0, 0)), "ölçü noktası: komşu nokta (0,0)")
typ("2"); key("TAB"); typ("90")
check(op.typed == ["2", "90"], f"yazılan: {op.typed}")
end = op.sketch[0]["segs"][0]["p"][3]
check(np.allclose(end, (0, 2, 0), atol=1e-9), f"nokta (0,2)'ye kilitlendi: {np.round(end, 4)}")
op.modal(ctx, ev("LEFTMOUSE", (1.5, 0.3), val="RELEASE"))
end = op.sketch[0]["segs"][0]["p"][3]
check(op.sk_drag is None and np.allclose(end, (0, 2, 0), atol=1e-9), "bırakınca yazılan değer kaldı")
check(op.typed == ["", ""], "yazılan sıfırlandı")

print("E) Tutamaç sürüklerken ölçü: tutamaç boyu yazılır")
reset()
op._set_tool(ctx, "ARC3"); click((0, 0)); click((2, 0)); click((1, 1)); key("RET")
st = op.sketch[0]; sg = st["segs"][0]
h = sg["p"][1]; node = sg["p"][0]
op.modal(ctx, ev("MOUSEMOVE", tuple(h[:2]))); op.modal(ctx, ev("LEFTMOUSE", tuple(h[:2])))
check(op.sk_drag is not None and op.sk_drag["key"][0] == "h", f"tutamaç sürükleniyor: {op.sk_drag and op.sk_drag['key']}")
move((float(h[0]) - 0.05, float(h[1]) + 0.2))
typ("0.5")
h2 = op.sketch[0]["segs"][0]["p"][1]
L = float(np.linalg.norm(np.asarray(h2) - np.asarray(node)))
check(abs(L - 0.5) < 1e-9, f"tutamaç boyu 0.5: {L:.6f}")
key("RET")
check(op.sk_drag is None, "Enter ile uygulandı")
op._set_tool(ctx, "LINE")

print("F) Geçici zemin (U): yön + yükseklik, U ile geri dönüş")
reset()
op.plane_mode = "XY"; op.locked = None
click((0, 0)); click((1, 0))                 # süren çizgi
key("G")
check(op.phase == "PLANE" and op.temp_pick is not None, "U: geçici zemin seçimi (1/2)")
check(len(op.sketch) == 1 and not op.segs, "süren çizgi taslağa eklendi")
key("Z")
check(op.phase == "OFFSET" and op.off["name"] == "XY", "Z: XY, yükseklik adımı (2/2)")
typ("0.5"); key("RET")
check(op.phase == "DRAW" and op.temp is not None and op.plane_mode == "LOCK", f"geçici zemin açık: {op.temp and op.temp['label']}")
click((0, 1)); click((1, 1)); key("RET")
z = op.sketch[-1]["segs"][0]["p"][0][2]
check(abs(z - 0.5) < 1e-9, f"yeni çizgi geçici zeminde z={z}")
click((2, 1)); click((3, 1)); key("RET")
z = op.sketch[-1]["segs"][0]["p"][3][2]
check(abs(z - 0.5) < 1e-9, "sonraki çizgi de geçici zeminde")
key("G")
check(op.temp is None and op.plane_mode == "XY" and op.locked is None, "U: asıl düzleme dönüldü")
click((0, 3)); click((1, 3)); key("RET")
z = op.sketch[-1]["segs"][0]["p"][0][2]
check(abs(z) < 1e-9, f"normal akış: z={z}")

print("G) Geçici zemin: sağ tık = yön aynı, sadece yükseklik; ana düzleme göre fark")
key("G"); op.modal(ctx, ev("RIGHTMOUSE", (0, 0)))
check(op.phase == "OFFSET" and op.off["name"] == "XY", "mevcut yön (XY) ile yükseklik adımı")
check(op._main_height(op.off["base"]) == 0.0, "ana düzlem yüksekliği 0")
typ("-0.25"); key("RET")
check(op.temp is not None and abs(op.locked.o[2] + 0.25) < 1e-9, "z = -0.25")
key("G", shift=True)
check(op.phase == "PLANE" and op.temp_pick["saved"][0] == "XY", "Shift+G: başka geçici zemin, asıl düzlem korunur")
key("ESC")
check(op.phase == "DRAW" and op.temp is not None, "Esc: seçim iptal, geçici zemin sürüyor")
key("X", shift=True)
check(op.temp is None and op.plane_mode == "YZ", "Shift+X ile açık düzlem seçimi geçici zemini bitirir")
op._set_plane("XY")

print("H) Geçici zemin seçilirken Esc aracı kapatmaz")
key("G"); key("ESC")
check(op.phase == "DRAW" and op.temp is None and draw._STATE["active"] is op, "araç açık")

print("I) Yükseklik yakalaması: ana düzlem ve ızgara kökeni")
op.temp_pick = {"saved": ("LOCK", dm.Plane.axis("XY", (0, 0, 0.75)))}
base = dm.Plane.axis("XY", (0, 0, 0))
check(abs(op._main_height(base) - 0.75) < 1e-12, "ana düzlem yüksekliği 0.75")
op.temp_pick = None
op.temp = {"saved": ("XY", None), "plane": base, "label": "x", "grid_o": np.array([0.3, 0.3, 0.0])}
check(np.allclose(op._grid_origin(), (0.3, 0.3, 0)), "ızgara kökeni yakalanan noktaya taşındı")
op.temp = None
check(np.allclose(op._grid_origin(), 0), "normalde ızgara kökeni dünya kökeni")

print("J) Yükseklik bir noktadan alınınca: nokta yüksekliği + ızgara kökeni; çizim fonksiyonları")
calls = []
dr = importlib.import_module("mini_cad.draw_render"); dpl = importlib.import_module("mini_cad.draw_plane")
de = importlib.import_module("mini_cad.draw_edit")
for mod in (dr, dpl, de):
    for nm in ("_text", "_rect", "_dashed", "_poly", "_marker"):
        if hasattr(mod, nm):
            setattr(mod, nm, (lambda nm: lambda *a, **k: calls.append((nm, a)) or (10, 10))(nm))
reset(); op._set_plane("XY")
click((0, 0)); click((1, 0)); key("RET")
op.sketch[0]["segs"][0]["p"] = tuple(np.array(q) + np.array([0, 0, 0.4]) for q in op.sketch[0]["segs"][0]["p"])
op.dirty = True
key("G"); key("Z")
move((1, 0))
check(op.off["kind"] == "Uç yüksekliği" and abs(op.off["t"] - 0.4) < 1e-9, f"nokta yüksekliği: {op.off['kind']} {op.off['t']}")
calls.clear(); op._draw_offset2d(region)
txt = [a[2] for n, a in calls if n == "_text"]
check(any("Yükseklik" in t for t in txt) and any("Fark" in t for t in txt), f"ölçü kutusu: {txt}")
check(any(n == "_marker" for n, _ in calls), "yakalanan nokta işaretlendi")
op.modal(ctx, ev("LEFTMOUSE", (1, 0)))
check(op.temp is not None and np.allclose(op.temp["grid_o"], (1, 0, 0.4)), f"ızgara kökeni: {op.temp['grid_o']}")
calls.clear()
op.modal(ctx, ev("MOUSEMOVE", (1, 0))); op.modal(ctx, ev("LEFTMOUSE", (1, 0)))
move((1.4, 0.6))
check(op.sk_drag is not None and op.sk_drag["moved"], "taslak noktası sürükleniyor")
calls.clear(); op._draw_drag_input(region, op._px(op.cursor))
txt = [a[2] for n, a in calls if n == "_text"]
check(any("Uzunluk" in t for t in txt) and any("Açı" in t for t in txt), f"sürükleme ölçü kutusu: {txt}")
op.modal(ctx, ev("LEFTMOUSE", (1.4, 0.6), val="RELEASE"))
key("G")
check(op.temp is None and np.allclose(op._grid_origin(), 0), "U: geri dönüldü")
print("t44 bitti")
