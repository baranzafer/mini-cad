# v0.35.0: bildirim merkezinde düğmeli soru ve süren hesap satırı (bpy'siz, sahte ressam)
import sys, types, importlib
for name in ("gpu", "blf", "gpu_extras", "gpu_extras.batch"):
    sys.modules[name] = types.ModuleType(name)
sys.modules["gpu_extras.batch"].batch_for_shader = None
pkg = types.ModuleType("mini_cad"); pkg.__path__ = ["/home/claude/mini_cad"]; sys.modules["mini_cad"] = pkg
notify = importlib.import_module("mini_cad.notify")
fails = 0
def check(ok, msg):
    global fails
    print(("  ok  " if ok else "  HATA ") + msg)
    if not ok: fails += 1


class P:
    """Ölçüm + çizim çağrılarını yutan ressam."""
    def measure(self, t, size):
        return (len(t) * size * 0.6, size)
    def __getattr__(self, n):
        return lambda *a, **k: None


calls = []
c = notify.Center()
got = []
c.on_result = got.append
c.ask("calc:A", "warn", "A: hesap durdu. Tamamı hesaplansın mı?",
      [("Devam et", lambda: calls.append("devam") or "Tamamı hesaplanıyor"),
       ("Böyle bırak", lambda: calls.append("bırak"))], 0.0)
check(len(c.visible()) == 1 and c.visible()[0]["actions"], "soru görünür")
c.expire(1000.0)
check("calc:A" in c.asks, "soru süreyle kalkmaz (karar bekler)")
c.draw(P(), 1.0, 0, 0, 420, 0.0)
check(len(c.btns) == 2, f"iki düğme ({len(c.btns)})")
r = c.btns[0][0]
check(c.press((r[0] + r[2]) / 2, (r[1] + r[3]) / 2), "düğmeye basıldı")
check(calls == ["devam"] and "calc:A" not in c.asks and got == ["Tamamı hesaplanıyor"],
      "işlev çalıştı, soru kalktı, sonuç iletisi bildirime")
c.ask("calc:B", "warn", "B?", [("X", lambda: None)], 0.0)
c.ask("calc:B", None, "", [], 0.0)
check("calc:B" not in c.asks, "soru kodla kaldırılır (hesap tamamlandı)")
c.ask("slow:A", "info", "A: hesap 12 sn sürdü", [], 0.0)
check(any(it["text"].startswith("A: hesap 12") for it in c.items), "düğmesiz soru sıradan ileti")
c.set_task("A · 2/5 · Fillet 3 · 6 sn", [("Durdur", lambda: calls.append("dur"))])
c.items = []
c.draw(P(), 1.0, 0, 0, 420, 0.0)
check(c.box is not None and len(c.btns) == 1, "süren hesap satırı tek başına da çizilir (Durdur)")
r = c.btns[0][0]
c.press((r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
check(calls[-1] == "dur" and c.task is not None, "Durdur çalıştı (satırı zamanlayıcı kaldırır)")
c.ask("calc:C", "warn", "C?", [("Devam et", lambda: None)] * 6, 0.0)
c.draw(P(), 1.0, 0, 0, 260, 0.0)
rows = {round(b[0][1]) for b in c.btns}
check(len(rows) >= 2 and all(b[0][2] <= 260 for b in c.btns), "sığmayan düğmeler alt satıra iner")
c.close()
check(not c.asks and c.task is not None, "çarpı soruları kapatır, süren hesap satırı kalır")
c.set_task(None)
c.draw(P(), 1.0, 0, 0, 420, 0.0)
check(c.box is None and not c.btns, "boşken çizilmez")
print("BAŞARISIZ:", fails) if fails else print("TAMAM")
sys.exit(1 if fails else 0)
