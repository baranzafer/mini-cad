# v0.27.0: BlendCAD şeridi — yerleşim ve olay mantığı (bpy / gpu'suz, sahte ressamla)
import sys, types, importlib
for n in ("gpu", "blf", "gpu_extras", "gpu_extras.batch"):
    sys.modules[n] = types.ModuleType(n)
sys.modules["gpu_extras.batch"].batch_for_shader = None
pkg = types.ModuleType("mini_cad"); pkg.__path__ = ["/home/claude/mini_cad"]; sys.modules["mini_cad"] = pkg
ribbon = importlib.import_module("mini_cad.ribbon")
data = importlib.import_module("mini_cad.ribbon_data")
icons = importlib.import_module("mini_cad.ribbon_icons")

fails = 0
def check(ok, msg):
    global fails
    print(("  ok  " if ok else "  HATA ") + msg)
    if not ok: fails += 1

class P:
    """Sahte ressam: çizimleri sayar, metin genişliği = 0.6 * boyut * harf."""
    def __init__(s): s.n = 0; s.texts = []
    def measure(s, t, size, bold=False): return (0.6 * size * len(t), size)
    def text(s, x, y, t, *a, **k): s.n += 1; s.texts.append(t)
    def rect(s, *a, **k): s.n += 1
    def outline(s, *a, **k): s.n += 1
    def lines(s, seg, *a, **k):
        assert len(seg) % 2 == 0, "çizgi parçası çift sayıda nokta olmalı"
        s.n += 1
    def tri(s, *a, **k): s.n += 1
    def circle(s, *a, **k): s.n += 1

W, H = 1500, 800
def center(r, kind, ident):
    x0, y0, x1, y1 = r._rect(kind, ident)
    return (x0 + x1) / 2, (y0 + y1) / 2

# --- veri bütünlüğü
ids = []
for b in data.all_buttons():
    ids.append(b["id"]); ids += [v["id"] for v in b["variants"]]
tops = [b["id"] for b in data.all_buttons()]
check(len(tops) == len(set(tops)), "düğme kimlikleri benzersiz")
for b in data.all_buttons():
    for it in [b] + b["variants"]:
        segs = icons.icon_lines(it["icon"])
        if not segs or len(segs) % 2 or any(abs(c) > 1.3 for p_ in segs for c in p_):
            check(False, f"simge geçersiz: {it['icon']}")
check(True, f"{len(ids)} düğme / tür simgesi geçerli")
check(all(b["status"] in (data.READY, data.PLANNED) for b in data.all_buttons()), "durum alanı")
check(data.find("HOLE_CSK")["title"] == "Havşalı", "find: tür bulunur")

# --- yerleşim
p = P(); r = ribbon.Ribbon(1.0)
r.layout(p, W, H)
x0, y0, x1, y1 = r.box
check(y1 <= H and y0 > H - 120 and x0 >= 0, f"şerit üstte: {r.box}")
check(all(r._rect("tab", t[0]) for t in data.TABS), "bütün sekmeler var")
r1920 = ribbon.Ribbon(1.0); r1920.layout(p, 1920, H)
check(len([i for i in r1920.items if i[4] == "btn"]) == sum(len(b) for _g, b in r1920.groups()),
      "Eskiz (1920 px): bütün düğmeler sığdı")
r900 = ribbon.Ribbon(1.0); r900.layout(p, 900, H)
check(r900.scroll_max > 0 and r900._rect("scroll", 1) is not None, "Eskiz (900 px): kaydırma oku")
r.draw(p, W, H, now=0.0); check(p.n > 50, "çizim çağrıları yapıldı")

# --- sekme
mx, my = center(r, "tab", "HOLE")
check(r.press(mx, my, 0.0) and r.tab == "HOLE", "sekmeye tık: Delik · Vida")
r.layout(p, W, H)
check(r._rect("btn", "HOLE") is not None and r._rect("btn", "LINE") is None, "sekme düğmeleri değişti")

# --- açıklama kartı zamanlaması
mx, my = center(r, "btn", "THREAD")
r.move(mx, my, 10.0)
p2 = P(); r.draw(p2, W, H, now=10.2); check("Diş" not in p2.texts, "0.2 sn: kart yok")
p2 = P(); r.draw(p2, W, H, now=10.6); check("Diş" in p2.texts and "NASIL KULLANILIR" not in p2.texts,
                                            "0.6 sn: kısa kart")
p2 = P(); r.draw(p2, W, H, now=12.0); check("NASIL KULLANILIR" in p2.texts, "2 sn: kullanım adımları")
mx2, my2 = center(r, "btn", "BOLT")
r.move(mx2, my2, 12.1)
p2 = P(); r.draw(p2, W, H, now=12.15); check("Vida oluştur" in p2.texts, "sıcak geçiş: yeni kart hemen")
check(r.tick(12.15), "kart açılırken zamanlayıcı yeniden çizer")

# --- açılır liste (tür seçimi)
r.tab = "SKETCH"; r.layout(p, W, H)
bx0, by0, bx1, by1 = r._rect("btn", "CIRCLE")
check(r.hit(bx1 - 3, by0 + 3) == ("arrow", "CIRCLE"), "sağ alt üçgen: liste oku")
r.press(bx1 - 3, by0 + 3, 20.0); r.layout(p, W, H)
check(r.fly == "CIRCLE" and len(r.fly_items) == 3, "liste açıldı (3 tür)")
fx = r.fly_items[2]
r.press((fx[0] + fx[2]) / 2, (fx[1] + fx[3]) / 2, 20.1)
check(r.fly is None and r.variant["CIRCLE"] == "ELLIPSE" and r.active == "ELLIPSE", "Elips seçildi")
check(r.current(r._btn("CIRCLE"))["icon"] == "ELLIPSE", "düğme seçilen türün simgesini gösterir")
r.press(bx1 - 3, by0 + 3, 21.0); r.layout(p, W, H)
check(r.press(5, 5, 21.1) and r.fly is None, "dışarı tık listeyi kapatır ve tüketilir")
check(not r.press(5, 5, 21.2), "dışarı tık (liste yokken) görünüme geçer")

# --- araç seçimi, bildirim, aç / kapa
acts = []
r.on_action = lambda k, it: acts.append((k, it["id"] if it else None))
r.tab = "MODIFY"; r.layout(p, W, H)
mx, my = center(r, "btn", "TRIM")
r.press(mx, my, 30.0)
check(r.active == "TRIM" and acts[-1] == ("TOOL", "TRIM") and r.toast, "Kırp seçildi + bildirim")
r.press(mx, my, 30.5); check(r.active is None, "ikinci tık seçimi kaldırır")
r.tab = "CONSTRAIN"; r.layout(p, W, H)
mx, my = center(r, "btn", "CONS_SHOW")
check("CONS_SHOW" in r.toggles, "Kısıtları göster varsayılan açık")
r.press(mx, my, 31.0); check("CONS_SHOW" not in r.toggles and acts[-1][0] == "TOGGLE", "aç / kapa")

# --- daralt / kapat
mx, my = center(r, "collapse", None)
r.press(mx, my, 40.0); r.layout(p, W, H)
check(r.collapsed and not [i for i in r.items if i[4] == "btn"], "daraltıldı: yalnız sekmeler")
mx, my = center(r, "tab", "SOLID"); r.press(mx, my, 40.5); r.layout(p, W, H)
check(not r.collapsed and r.tab == "SOLID", "sekmeye tık açar")
mx, my = center(r, "close", None); r.press(mx, my, 41.0)
check(acts[-1] == ("CLOSE", None), "kapat düğmesi CLOSE bildirir")

# --- dar görünüm: kaydırma
r2 = ribbon.Ribbon(1.0); r2.layout(p, 700, H)
check(r2.scroll_max > 0 and r2._rect("scroll", 1) is not None, "dar görünüm: kaydırma oku")
first = [i[5] for i in r2.items if i[4] == "btn"][0]
r2.wheel(*center(r2, "btn", first), 1); r2.layout(p, 700, H)
check(r2.scroll > 0 and r2._rect("scroll", -1) is not None, "tekerlek kaydırır")
check(all(i[2] <= r2.box[2] for i in r2.items if i[4] == "btn"), "taşan düğme çizilmez")

# --- başlatıcı şeridin sağında, gizmonun solunda
lx0, ly0, lx1, ly1 = ribbon.launcher_rect(W, H, 1.0, 0)
check(lx1 < W - 90 and ly1 <= H, "başlatıcı sağ üstte, gezinme gizmosunun solunda")

print("SONUÇ:", "tamam" if not fails else f"{fails} hata")
sys.exit(1 if fails else 0)
