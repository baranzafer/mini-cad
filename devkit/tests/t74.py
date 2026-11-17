# v0.30.0: Sil aracı — taslak nesnesinin / noktasının tamamı (Kırp'tan farklı: kesişime bakmaz)
exec(open("t47.py").read().split('print("A) Kırp')[0])

print("A) Sil: kesişen dikey doğrunun TAMAMI silinir (Kırp yalnız parçayı silerdi)")
rect_and_line()
op._set_tool(ctx, "DELETE")
check(op.tool == "DELETE", "Sil aracı seçildi")
move((2, 2.5))
check(op.mod is not None and op.mod["kind"] == "DELETE", "önizleme: silinecek nesne")
check(len(op.mod["prev"]) == 1 and np.allclose(op.mod["prev"][0]["p"][0], (2, -1, 0)), "önizleme doğrunun tamamı")
click((2, 2.5))
check(len(op.sketch) == 1 and op.sketch[0]["cyclic"], f"doğru silindi, dikdörtgen sağlam ({len(op.sketch)})")
key("Z", ctrl=True)
check(len(op.sketch) == 2, "Ctrl+Z: geri geldi")

print("B) Sil: dikdörtgenin bir kenarı (kesişimden bağımsız tam kenar)")
op._set_tool(ctx, "DELETE"); op.dirty = True
move((1, 0))
check(op.mod and op.mod["kind"] == "DELETE", "alt kenar vurgulandı")
pv = op.mod["prev"][0]["p"]
check(np.allclose(pv[0], (0, 0, 0)) and np.allclose(pv[3], (4, 0, 0)), "kenarın tamamı (0,0)-(4,0), kesişimde bölünmez")
click((1, 0))
check(not op.sketch[0]["cyclic"] and len(op.sketch[0]["segs"]) == 3, "dikdörtgen açıldı: 3 kenar kaldı")

print("C) Sil: sürükleyerek çoklu")
reset()
for y in (0, 1, 2):
    op._set_tool(ctx, "LINE"); click((0, y)); click((3, y)); key("RET")
check(len(op.sketch) == 3, "3 yatay doğru")
op._set_tool(ctx, "DELETE"); op.dirty = True
move((1, 0)); op.modal(ctx, ev("LEFTMOUSE", (1, 0)))
move((1, 1)); move((1, 2))
op.modal(ctx, ev("LEFTMOUSE", (1, 2), val="RELEASE"))
check(len(op.sketch) == 0, f"sürükleyerek üçü de silindi ({len(op.sketch)})")

print("D) Sil: taslak noktası")
reset()
op._set_tool(ctx, "POINT"); click((1, 1)); click((2, 2))
check(len(op.sk_points) == 2, "2 nokta")
op._set_tool(ctx, "DELETE"); op.dirty = True
move((2, 2))
check(op.mod and op.mod["kind"] == "DELPT", "nokta vurgulandı")
click((2, 2))
check(len(op.sk_points) == 1 and np.allclose(op.sk_points[0][:2], (1, 1)), "nokta silindi")
move((5, 5))
check(op.mod is None, "boşlukta vurgu yok")
print("SONUÇ: tamam")
