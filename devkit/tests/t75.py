# v0.30.0: bildirim merkezi — sol alt, önem gruplu, 45 sn, çarpı
import sys, types, importlib
for n in ("gpu", "blf", "gpu_extras", "gpu_extras.batch"):
    sys.modules[n] = types.ModuleType(n)
sys.modules["gpu_extras.batch"].batch_for_shader = None
pkg = types.ModuleType("mini_cad"); pkg.__path__ = ["/home/claude/mini_cad"]; sys.modules["mini_cad"] = pkg
N = importlib.import_module("mini_cad.notify")
ribbon = importlib.import_module("mini_cad.ribbon")
fails = 0
def check(ok, msg):
    global fails
    print(("  ok  " if ok else "  HATA ") + msg)
    if not ok: fails += 1
class P:
    def __init__(s): s.texts = []
    def measure(s, t, size, bold=False): return (0.6 * size * len(t), size)
    def text(s, x, y, t, *a, **k): s.texts.append(t)
    def __getattr__(s, n): return lambda *a, **k: None

check(N.level_of("Hata: x") == "error" and N.level_of("Geçersiz değer: a") == "warn" and
      N.level_of("“Delik” yeni özellik olarak planlandı (yakında)") == "hint" and
      N.level_of("Kısıtlar çözüldü") == "info", "metinden önem derecesi")
c = N.Center()
c.push("info", "Kısıtlar çözüldü", 0.0)
c.push("error", "Hata: boolean", 1.0)
c.push("warn", "Geçersiz değer: abc", 2.0)
c.push("info", "Kısıtlar çözüldü", 3.0)
check(len(c.items) == 3, "aynı ileti çoğalmaz")
p = P(); c.draw(p, 1.0, 50, 10, 420, 3.0)
x0, y0, x1, y1 = c.box
check(x0 == 50 and y0 == 10, "sol altta (araç çubuğunun sağında)")
heads = [t for t in p.texts if t.isupper()]
check(heads[:3] == ["HATALAR (1)", "UYARILAR (1)", "BILGI (1)"] or heads[0].startswith("HATALAR"),
      f"önem sırasıyla gruplar: {heads}")
check(c.expire(46.0) and sorted(it["text"] for it in c.items) == ["Geçersiz değer: abc", "Kısıtlar çözüldü"], "45 sn dolan (hata, t=1) kalktı; diğerleri kalır")
check(c.expire(48.5) and not c.items, "yenilenen de 45 sn sonra kalkar")
c.push("info", "a", 10.0); c.expire(54.0)
check(len(c.items) == 1, "45 sn dolmadan kalır")
# süren durum
c = N.Center()
c.sync("body", [("error", "G · Yüzey 2: kurulamadı")], 0.0)
c.sync("body", [("error", "G · Yüzey 2: kurulamadı")], 30.0)
check(c.items[0]["t0"] == 0.0, "durum değişmedikçe zamanı yenilenmez")
c.sync("body", [], 31.0)
check(not c.items, "durum düzelince hemen kalkar")
c.sync("body", [("error", "E1")], 32.0)
c.push("info", "bilgi", 32.0)
p = P(); c.draw(p, 1.0, 0, 0, 420, 32.0)
r = c.close_rect
check(c.press((r[0] + r[2]) / 2, (r[1] + r[3]) / 2) and not c.visible(), "çarpı hepsini kapatır")
c.sync("body", [("error", "E1")], 33.0)
check(not c.visible(), "kapatılan durum değişmeden geri gelmez")
c.sync("body", [("error", "E1"), ("error", "E2")], 34.0)
check(len(c.visible()) == 2, "durum değişince yeniden görünür")
# uzun metin satırlara bölünür, grupta en fazla 4 ileti
c = N.Center()
for i in range(7):
    c.push("warn", f"Uyarı {i}: " + "uzun açıklama " * 8, float(i))
p = P(); c.draw(p, 1.0, 0, 0, 300, 7.0)
check(any(t.startswith("… 3 ileti daha") for t in p.texts), "grupta 4 ileti + '… 3 daha'")
# şerit: ileti bildirim merkezine gider, şerit altı balon çizilmez
rb = ribbon.Ribbon(1.0)
got = []
rb.notify = got.append
rb.on_action = lambda k, it: "Kısıtlar çözüldü"
rb.layout(P(), 1600, 900)
x0, y0, x1, y1 = rb._rect("btn", "LINE")
rb.press((x0 + x1) / 2, (y0 + y1) / 2, 0.0)
check(got == ["Kısıtlar çözüldü"], "şerit iletisi bildirim merkezine")
calls = []
rb._draw_toast = lambda *a: calls.append(1)
rb.draw(P(), 1600, 900, now=0.5)
check(not calls, "şerit altı balon çizilmez")
print("SONUÇ:", "tamam" if not fails else f"{fails} hata")
sys.exit(1 if fails else 0)
