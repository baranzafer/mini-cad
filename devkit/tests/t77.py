# v0.31.0: yüzey sınırı teşhisi ve onarım önerileri (loopfix, bpy'siz)
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

def solve(segs, n=12):
    """Önerilen onarımları sırayla uygula (kullanıcı 'Hepsini düzelt' dedi)."""
    kinds = []
    for _ in range(n):
        iss = lf.diagnose(segs, TOL)
        fx = [i for i in iss if i["fix"]]
        if not fx:
            return segs, kinds, iss
        kinds.append(fx[0]["kind"])
        segs = lf.apply_fix(segs, fx[0]["fix"])
    return segs, kinds, lf.diagnose(segs, TOL)

def closed(segs):
    nodes, of = lf._cluster([(r, P) for r, P in segs], TOL)
    deg = {}
    for k in of.values():
        deg[k] = deg.get(k, 0) + 1
    return all(v == 2 for v in deg.values())

sq = [("alt", L((0, 0), (1, 0))), ("sağ", L((1, 0), (1, 1))), ("üst", L((1, 1), (0, 1))), ("sol", L((0, 1), (0, 0)))]
check(lf.diagnose(sq, TOL) == [], "kusursuz kare: sorun yok")

print("A) Taşan çizgi: sol kenar alttan taşmış, alt kenarın ucu onun ORTASINA değiyor")
segs = sq[:3] + [("sol", L((0, 1), (0, -0.4)))]
iss = lf.diagnose(segs, TOL)
check(iss and iss[0]["kind"] == "TJUNC" and iss[0]["fix"]["ref"] == "sol", f"T-birleşim: {iss and iss[0]['msg']}")
check(abs(iss[0]["fix"]["t"] - 1 / 1.4) < 1e-4 and np.allclose(iss[0]["fix"]["to"], (0, 0, 0), atol=1e-6), "bölme noktası (0,0)")
segs2, kinds, rest = solve(segs)
check(kinds == ["TJUNC", "EXTRA"] and closed(segs2) and len(segs2) == 4, f"böl + taşan parçayı çıkar → kapalı 4 kenar ({kinds})")

print("B) Uçlar değmiyor: 3 mm boşluk")
segs = sq[:2] + [("üst", L((1, 1), (0.003, 1)))] + [sq[3]]
iss = lf.diagnose(segs, TOL)
check(iss and iss[0]["kind"] == "GAP" and "3.00 mm" in iss[0]["msg"], f"boşluk: {iss and iss[0]['msg']}")
segs2, kinds, _ = solve(segs)
check(kinds == ["GAP"] and closed(segs2), "uçlar birleşti → kapalı")
far = sq[:2] + [("üst", L((1, 1), (0.2, 1)))] + [sq[3]]
check(not [i for i in lf.diagnose(far, TOL) if i["kind"] == "GAP"], "20 cm açıklık 'yakın' sayılmaz (niyet değil)")

print("C) Üst üste binen kenar (aynı kenar iki kez çizilmiş)")
segs = sq + [("alt2", L((1, 0), (0, 0.0004)))]
iss = lf.diagnose(segs, TOL)
check(iss and iss[0]["kind"] == "DUP" and iss[0]["fix"]["ref"] == "alt2", f"çift kenar: {iss and iss[0]['msg']}")
segs2, kinds, _ = solve(segs)
check(closed(segs2) and len(segs2) == 4, "biri çıkarıldı → kapalı")

print("D) Çok kısa kırık parça (köşede 0.3 mm)")
segs = [("alt", L((0, 0), (1, 0))), ("kırık", L((1, 0), (1.0003, 0))), ("sağ", L((1.0003, 0), (1, 1))), sq[2], sq[3]]
segs2, kinds, _ = solve(segs)
check(kinds[0] == "TINY" and closed(segs2) and len(segs2) == 4, f"kısa parça çıkarıldı, köşe kaynadı ({kinds})")

print("E) Köşesi olmayan kenara snap: çizgi ucu kenarın ortasında, kenar bölünmemiş (iki yüzey)")
# büyük dikdörtgenin alt kenarı tek parça; orta dikme alt kenarın ortasına snap olmuş
segs = [("alt", L((0, 0), (2, 0))), ("dikme", L((1, 0), (1, 1))), ("üst", L((1, 1), (0, 1))), ("sol", L((0, 1), (0, 0)))]
segs2, kinds, _ = solve(segs)
check(kinds[0] == "TJUNC" and "EXTRA" in kinds and closed(segs2) and len(segs2) == 4, f"alt kenar bölündü, sağ yarısı çıktı ({kinds})")

print("F) Dal: köşede 3 kenar (onarım önerisi yok, yalnız bilgi)")
segs = sq + [("çapraz", L((0, 0), (1, 1)))]
iss = lf.diagnose(segs, TOL)
check(any(i["kind"] == "BRANCH" and i["fix"] is None for i in iss), "dal bildirildi")
print("G) Plan: 'Hepsini düzelt' adımlarının hepsi önceden listelenir")
segs = [("alt", L((0, 0), (1, 0))), ("sağ", L((1, 0), (1, 1))), ("üst", L((1, 1), (0.003, 1))),
        ("sol", L((0, 1), (0, -0.3)))]
pl = lf.plan(segs, TOL)
check([i["kind"] for i in pl] == ["TJUNC", "GAP", "EXTRA"], f"3 adım: {[i['kind'] for i in pl]}")
check(lf.diagnose(segs, TOL)[0]["kind"] == "TJUNC", "plan veriyi değiştirmez (benzetim)")
print("SONUÇ:", "tamam" if not fails else f"{fails} hata")
sys.exit(1 if fails else 0)
