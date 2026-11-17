# v0.30.0: sağ tık menüsü — taslak nesnesi / noktası (gerçek çizim aracı, stub görünüm)
exec(open("t47.py").read().split('print("A) Kırp')[0])
rib = importlib.import_module("mini_cad.ribbon")
rs = importlib.import_module("mini_cad.ribbon_state")
rc = importlib.import_module("mini_cad.ribbon_ctx")
rb = rib.Ribbon(1.0)
rs.STATE.update(running=True, ribbon=rb, area=None)

class P:
    def measure(s, t, size, bold=False): return (0.6 * size * len(t), size)
    def __getattr__(s, n): return lambda *a, **k: None

def rmb(p):
    move(p)
    return op.modal(ctx, ev("RIGHTMOUSE", p))

def choose(text):
    rb.menu.layout(P(), 2000, 2000)
    for r, it in rb.menu.rows:
        if it.get("text") == text:
            rb.menu.press((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
            return True
    raise KeyError(text)

print("A) Üzerine gelme: taslak nesnesi vurgulanır")
reset()
op._set_tool(ctx, "LINE"); click((0, 0)); click((3, 1)); key("RET")
op._set_tool(ctx, "LINE"); click((0, 3)); click((3, 3)); key("RET")
move((1.5, 0.5))
check(op.ctx_hover is not None and op.ctx_hover["what"] == "seg" and op.ctx_hover["k"] == 0, "eğik doğru vurgulandı")
move((5, 5))
check(op.ctx_hover is None, "boşlukta vurgu yok")

print("B) Sağ tık → mini menü, Sil")
r = rmb((1.5, 3))
check(r == {"RUNNING_MODAL"} and rb.menu.is_open() and rb.menu.title == "Taslak nesnesi", "menü açıldı")
texts = [it.get("text") for it in rb.menu.items if it.get("text")]
check(all(t in texts for t in ("Sil", "Kırp (bu parça)", "Böl", "Taşı", "Yatay", "Ölçü")), f"öğeler: {texts}")
check(rs.over_ribbon(ev("LEFTMOUSE", (9, 9))), "menü açıkken fare menünün (çizim aracı olayı bırakır)")
choose("Sil")
check(not rb.menu.is_open() and len(op.sketch) == 1, f"üst doğru silindi ({len(op.sketch)})")
check(op.tool == "DELETE", "araç Sil'de kaldı (Inventor gibi devam)")

print("C) Sağ tık → Yatay kısıtı")
op._set_tool(ctx, "LINE")
rmb((1.5, 0.5)); choose("Yatay")
st = op.sketch[0]
y0, y1 = float(st["segs"][0]["p"][0][1]), float(st["segs"][-1]["p"][3][1])
check(abs(y0 - y1) < 1e-6, f"doğru yatay oldu (y {y0:.4f}, {y1:.4f})")

print("D) Sağ tık → Taşı: nesne seçili, temel nokta bekleniyor")
op._set_tool(ctx, "LINE")
mid = tuple(np.round((st["segs"][0]["p"][0][:2] + st["segs"][-1]["p"][3][:2]) / 2, 4))
rmb(mid); choose("Taşı")
check(op.tool == "MOVE" and op.xf is not None and op.xf["step"] == "BASE" and 0 in op.xsel, f"Taşı: seçim {op.xsel}, adım {op.xf and op.xf['step']}")

print("E) Nokta menüsü")
op._set_tool(ctx, "POINT"); click((5, 5)); click((6, 6))
rmb((6, 6))
check(rb.menu.title == "Taslak noktası", "nokta menüsü")
choose("Noktayı sil")
check(len(op.sk_points) == 1, "nokta silindi")

print("F) Çizgi çizerken sağ tık eskisi gibi çizgiyi bitirir (menü açılmaz)")
op._set_tool(ctx, "LINE"); click((0, -2)); click((2, -2))
n = len(op.sketch)
rmb((2, -2))
check(not rb.menu.is_open() and len(op.sketch) == n + 1, "sağ tık: çizgi taslağa eklendi")

print("G) Şerit kapalıyken sağ tık menüsü yok (eski davranış)")
rs.STATE["running"] = False
op._set_tool(ctx, "LINE"); move((1, -2))
r = rmb((1, -2))
check(not rb.menu.is_open(), "menü açılmadı")
print("SONUÇ: tamam")
