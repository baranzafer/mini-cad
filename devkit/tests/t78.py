# v0.32.0: tel kafes taraması (loopfix.scan) — döngü aramadan gizli uyuşmazlıklar
import sys, types, importlib
import numpy as np
pkg = types.ModuleType("mini_cad"); pkg.__path__ = ["/home/claude/mini_cad"]; sys.modules["mini_cad"] = pkg
lf = importlib.import_module("mini_cad.loopfix")
fails = 0
def check(ok, msg):
    global fails
    print(("  ok  " if ok else "  HATA ") + msg)
    if not ok: fails += 1
def L(a, b):
    a, b = np.array(a + (0,), float), np.array(b + (0,), float)
    return np.array([a, a + (b - a) / 3, a + 2 * (b - a) / 3, b])
TOL = 0.001
sq = [("alt", L((0, 0), (1, 0))), ("sağ", L((1, 0), (1, 1))), ("üst", L((1, 1), (0, 1))), ("sol", L((0, 1), (0, 0)))]
check(lf.scan(sq, TOL) == [], "temiz kare: bulgu yok")
# açık uçlar (yarım çizim) tek başına sorun değil
check(lf.scan([("a", L((0, 0), (1, 0))), ("b", L((3, 0), (4, 0)))], TOL) == [], "uzak açık uçlar: bulgu yok")
iss = lf.scan(sq + [("ek", L((2, 0), (1.002, 0)))], TOL)
check([i["kind"] for i in iss] == ["GAP"] and len(iss[0]["fix"]["ends"]) == 1 and np.allclose(iss[0]["fix"]["to"], (1, 0, 0)),
      "kapalı köşeye 2 mm uzak uç: yalnız serbest uç köşeye taşınır")
iss = lf.scan(sq + [("dikme", L((0.5, -1), (0.5, 0)))], TOL)
check([i["kind"] for i in iss] == ["TJUNC"] and iss[0]["fix"]["ref"] == "alt", "kenar ortasına değen uç: T-birleşim")
iss = lf.scan(sq + [("çift", L((1, 0), (0, 0)))], TOL)
check([i["kind"] for i in iss] == ["DUP"], "üst üste kenar")
iss = lf.scan(sq + [("sıfır", L((1, 1), (1, 1)))], TOL)
check(["TINY"] == [i["kind"] for i in iss], "sıfır boy parça yalnız TINY (çift sayılmaz)")
# hepsi birlikte: erken dönmez
iss = lf.scan(sq + [("ek", L((2, 0), (1.002, 0))), ("dikme", L((0.5, -1), (0.5, 0))), ("çift", L((1, 0), (0, 0)))], TOL)
check(sorted(i["kind"] for i in iss) == ["DUP", "GAP", "TJUNC"], f"birden çok bulgu birlikte: {sorted(i['kind'] for i in iss)}")
print("SONUÇ:", "tamam" if not fails else f"{fails} hata")
sys.exit(1 if fails else 0)
