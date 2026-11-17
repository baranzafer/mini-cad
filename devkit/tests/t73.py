# v0.29.0: BlendCAD araç pencereleri (ribbon_forms) — sahte veriyle etkileşim
import sys, types, importlib, math
for n in ("gpu", "blf", "gpu_extras", "gpu_extras.batch"):
    sys.modules[n] = types.ModuleType(n)
sys.modules["gpu_extras.batch"].batch_for_shader = None
pkg = types.ModuleType("mini_cad"); pkg.__path__ = ["/home/claude/mini_cad"]; sys.modules["mini_cad"] = pkg
F = importlib.import_module("mini_cad.ribbon_forms")
ribbon = importlib.import_module("mini_cad.ribbon")
Meta = F.Meta

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

class Obj:
    def __init__(s, name): s.name = name

class Data:
    __meta__ = {
        "size": Meta("FLOAT", "Ölçü", min=0.0, max=10.0, soft_min=0.0, soft_max=1.0, step=1,
                     precision=3, unit="LENGTH"),
        "count": Meta.int(1, 16, "Adet"),
        "on": Meta.bool("Açık"),
        "kind": Meta.enum([("A", "Bir", ""), ("B", "İki", ""), ("C", "Üç", "")], "Tür"),
        "angle": Meta("FLOAT", "Açı", unit="ROTATION"),
        "tool": Meta("POINTER", "Araç"),
    }
    def __init__(s):
        s.size, s.count, s.on, s.kind, s.angle, s.tool = 0.2, 3, False, "A", 0.0, None

d = Data()
rows = [Data() for _ in range(9)]
commits, msgs, clicks = [], [], []
state = {"act": 0}

def spec(ui, ctx):
    ui.prop(d, "on", "Uygula", style="check")
    with ui.enabled(d.on):
        ui.section("Yeni")
        ui.prop(d, "size")
        with ui.row():
            ui.prop(d, "count")
            ui.prop(d, "angle")
    ui.prop(d, "kind", "", style="seg")
    ui.prop(d, "kind", "Tür")
    ui.prop(d, "tool", "Araç", style="object", choices=lambda: [(Obj("Küp"), "Küp"), (Obj("Silindir"), "Silindir")])
    ui.button("Ekle", lambda: clicks.append("ekle"), primary=True, key="B")
    ui.button("Kapalı", lambda: clicks.append("kapalı"), enabled=False)
    def cells(u, it, i):
        u.prop(it, "on", "", style="check", weight=0.2)
        u.label(f"Satır {i}", weight=1)
    ui.list("L", rows, state["act"], lambda j: state.__setitem__("act", j), cells, rows=4)
    ui.label("Uzun bir açıklama metni pencerenin genişliğine göre satırlara bölünmeli ki "
             "kesilmesin ve okunabilsin.", "info")

h = F.FormHost(1.0, on_commit=commits.append, on_message=msgs.append)
check(h.open("T", "Deneme", "FILLET3D", spec, 100.0), "pencere açıldı")
p = P()
h.draw(p, 700, 1600, 900)
check(h.box is not None and h.box[3] == 700 and h.box[0] == 100.0, f"şeridin altında, düğme hizasında {h.box}")
check("Deneme" in p.texts and "Ekle" in p.texts, "başlık ve düğme çizildi")

def el(kind, name=None, text=None):
    for e in h.els:
        if e["kind"] == kind and (name is None or e.get("name") == name) and (text is None or e.get("text") == text):
            return e
    raise KeyError((kind, name, text))
def c(e): r = e["rect"]; return ((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)

# devre dışı alan (on=False)
e = el("prop", "size")
check(e["enabled"] is False, "Uygula kapalıyken alan devre dışı")
h.press(*c(e)); check(h.drag is None, "devre dışı alan tepki vermez")
h.press(*c(el("prop", "on"))); check(d.on is True and commits, "onay kutusu: açıldı + geri alma adımı")
h.build()

# sayı alanı: oklar
e = el("prop", "size"); x0, y0, x1, y1 = e["rect"]
h.press(x1 - 4, (y0 + y1) / 2); check(abs(d.size - 0.21) < 1e-9 or d.size > 0.2, f"sağ ok: arttı ({d.size})")
v = d.size; h.press(x0 + 4, (y0 + y1) / 2); check(d.size < v, "sol ok: azaldı")
# sürükle
v = d.size; mx, my = c(el("prop", "size"))
h.press(mx, my); check(h.capturing(), "sürükleme başladı (klavye / fare pencerede)")
h.move(mx + 60, my); n0 = len(commits)
check(d.size > v, f"sürükleyince arttı ({v} → {d.size})")
h.release(mx + 60, my); check(not h.capturing() and len(commits) == n0 + 1, "bırakınca tek geri alma adımı")
# tıkla-yaz
h.press(mx, my); h.release(mx, my)
check(h.edit is not None and h.edit["fresh"], "tıklayınca yazma modu (tamamı seçili)")
for ch in "0.35": h.key("X", ch)
check(h.edit["text"] == "0.35", "yazılan metin")
h.key("RET"); check(abs(d.size - 0.35) < 1e-12 and h.edit is None, "Enter: uygulandı")
# sınır
h.press(mx, my); h.release(mx, my); [h.key("X", ch) for ch in "99"]; h.key("RET")
check(d.size == 10.0, "üst sınıra kısıldı")
# geçersiz
h.press(mx, my); h.release(mx, my); [h.key("X", ch) for ch in "abc"]; h.key("RET")
check(d.size == 10.0 and msgs and "Geçersiz" in msgs[-1], "geçersiz değer: değişmez + ileti")
# Tab sonraki alana
h.press(mx, my); h.release(mx, my); h.key("TAB")
check(h.edit is not None and "count" in h.edit["id"], "Tab: sonraki sayı alanı")
h.key("BACK_SPACE"); [h.key("X", ch) for ch in "7"]; h.key("RET")
check(d.count == 7, "tamsayı yazıldı")
# Esc iptal
h.press(*c(el("prop", "count"))); h.release(*c(el("prop", "count")))
h.key("X", "9"); h.key("ESC"); check(d.count == 7 and h.edit is None, "Esc: iptal")
# açı (derece)
h.build(); ea = el("prop", "angle")
h.press(*c(ea)); h.release(*c(ea)); [h.key("X", ch) for ch in "90"]; h.key("RET")
check(abs(d.angle - math.pi / 2) < 1e-9, "açı derece yazılır, radyan saklanır")
check(F.default_fmt(Data.__meta__["angle"], d.angle) == "90.0°", "açı derece gösterilir")

# bölmeli seçim
h.build(); seg = [e for e in h.els if e["kind"] == "seg"]
check(len(seg) == 3, "3 bölme")
h.press(*c(seg[2])); check(d.kind == "C", "bölmeye tık: C")
# açılır liste
h.build(); dd = el("prop", "kind", "Tür")
h.press(*c(dd)); check(h.drop is not None and len(h.drop["rows"]) == 3, "açılır liste açıldı")
r, val, nm = h.drop["rows"][1]
h.press((r[0] + r[2]) / 2, (r[1] + r[3]) / 2); check(d.kind == "B" and h.drop is None, "listeden seçildi")
# obje seçimi
h.build(); ob = el("prop", "tool")
h.press(*c(ob)); check(len(h.drop["rows"]) == 3 and h.drop["rows"][0][2] == "— yok —", "obje listesi (+ yok)")
r, val, nm = h.drop["rows"][2]; h.press((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
check(d.tool is not None and d.tool.name == "Silindir", "obje seçildi")
h.build(); h.press(*c(el("prop", "tool"))); h.key("ESC"); check(h.drop is None, "Esc: liste kapandı")
# düğmeler
h.build()
h.press(*c(el("button", text="Ekle"))); check(clicks == ["ekle"], "düğme çalıştı")
h.press(*c(el("button", text="Kapalı"))); check(clicks == ["ekle"], "devre dışı düğme çalışmaz")
# liste
h.build()
rws = [e for e in h.els if e["kind"] == "listrow"]
check(len(rws) == 4, "listede 4 satır görünür (9 öğe)")
h.press(*c(rws[2])); check(state["act"] == 2, "satır seçildi")
cb = [e for e in h.els if e.get("inrow") and e["kind"] == "prop"][1]
h.press(*c(cb)); check(rows[1].on is True and state["act"] == 2, "satırdaki onay kutusu satırı seçmeden değişir")
lb = el("listbox"); h.wheel(*c(lb), 1); h.build()
rws = [e for e in h.els if e["kind"] == "listrow"]
check(rws[0]["index"] == 1, "tekerlek: liste kaydı")
# uzun yazı satırlara bölünür
labels = [e for e in h.els if e["kind"] == "label" and e["tone"] == "info"]
check(len(labels) >= 2, f"uzun bilgi yazısı {len(labels)} satır")
# kapat
h.press(*c(el("close"))); check(not h.is_open(), "X ile kapandı")
# aynı pencere tekrar: aç / kapa
h.open("T", "Deneme", "FILLET3D", spec, 100.0); check(not h.open("T", "Deneme", "FILLET3D", spec, 100.0) and not h.is_open(), "aynı düğme pencereyi kapatır")

# kısa bölgede kaydırma
h.open("T", "Deneme", "FILLET3D", spec, 100.0)
h.draw(p, 300, 1600, 320)
check(h.scroll_max > 0, "alçak görünüm: pencere kaydırılabilir")
vis = [e for e in h.els if h._visible(e)]
check(all(e["rect"][1] >= h.box[1] - 0.5 for e in vis), "görünmeyen öğeler çizilmez")
h.wheel(*c(el("head")), 1)
check(h.scroll > 0, "tekerlek: pencere kaydı")

# şerit ile birlikte: pencere şeridin altında, olaylar şeride değil pencereye
rb = ribbon.Ribbon(1.0)
p2 = P(); rb.layout(p2, 1600, 900)
x0, y0, x1, y1 = rb._rect("btn", "LINE")
rb.press((x0 + x1) / 2, (y0 + y1) / 2, 0.0)
rb.open_form("T", "Deneme", "FILLET3D", spec, 280)
rb.draw(p2, 1600, 900)
fb = rb.forms.box
check(abs(fb[0] - x0) < 1 and fb[3] <= rb.box[1], "pencere tıklanan düğmenin altında")
check(rb.contains(fb[0] + 20, fb[1] + 10), "şerit + pencere olayları tüketir")
e = [e for e in rb.forms.els if e["kind"] == "button" and e["text"] == "Ekle"][0]
n = len(clicks); rb.press(*c(e), 1.0); check(len(clicks) == n + 1, "şerit üzerinden pencere düğmesi")
ef = [e for e in rb.forms.els if e["kind"] == "prop" and e["name"] == "size"][0]
rb.press(*c(ef), 2.0); check(rb.capturing(), "şerit: sürükleme yakalaması")
rb.release(*c(ef)); check(rb.forms.edit is not None, "şerit: yazma modu")
check(rb.key("X", "1") and rb.key("RET"), "şerit klavyeyi pencereye verir")
check(d.size == 1.0, "değer yazıldı")

print("SONUÇ:", "tamam" if not fails else f"{fails} hata")
sys.exit(1 if fails else 0)
