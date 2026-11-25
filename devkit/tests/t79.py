# v0.33.0: delik hesapları (holemath, bpy / OCC'siz)
import sys, types, importlib, math
pkg = types.ModuleType("mini_cad"); pkg.__path__ = ["/home/claude/mini_cad"]; sys.modules["mini_cad"] = pkg
hm = importlib.import_module("mini_cad.holemath")
fails = 0
def check(ok, msg):
    global fails
    print(("  ok  " if ok else "  HATA ") + msg)
    if not ok: fails += 1
pi = math.pi
r = 0.05
def V(p, through=None): return hm.volume_below(hm.profile(p, through))
check(abs(V({"kind": "SIMPLE", "d": 0.1, "through": True}, 0.4) - pi * r * r * 0.4) < 1e-12, "düz tümüyle geçen (Pappus)")
tip = r / math.tan(math.radians(59))
check(abs(V({"kind": "SIMPLE", "d": 0.1, "depth": 0.2, "tip_angle": 118}) - (pi * r * r * 0.2 + pi * r * r * tip / 3)) < 1e-12, "kör + 118° uç = silindir + koni")
check(abs(V({"kind": "SIMPLE", "d": 0.1, "depth": 0.2, "tip_angle": 0}) - pi * r * r * 0.2) < 1e-12, "düz dip")
check(abs(V({"kind": "CBORE", "d": 0.1, "through": True, "cb_d": 0.2, "cb_depth": 0.1}, 0.4) - pi * (0.01 * 0.1 + r * r * 0.3)) < 1e-12, "havşa başlı")
hc = 0.05
check(abs(V({"kind": "CSINK", "d": 0.1, "through": True, "cs_d": 0.2, "cs_angle": 90}, 0.4) - (pi * hc / 3 * (0.01 + 0.1 * r + r * r) + pi * r * r * (0.4 - hc))) < 1e-12, "havşalı 90° (kesik koni + silindir)")
prof = hm.profile({"kind": "SIMPLE", "d": 0.1, "through": True}, 0.4)
check(prof[0][1] < 0 and prof[0][0] == 0 and prof[-1][0] == 0, "profil eksende başlar / biter, yüzeyin üstüne taşar (çakışık yüz yok)")
for bad, why in (({"kind": "CBORE", "d": 0.1, "through": True, "cb_d": 0.05, "cb_depth": 0.1}, "yuva < delik"),
                 ({"kind": "CSINK", "d": 0.1, "through": False, "depth": 0.01, "cs_d": 0.3, "cs_angle": 90}, "havşa delikten uzun"),
                 ({"kind": "SIMPLE", "d": 0.0, "through": True}, "sıfır çap")):
    try:
        hm.profile(bad, 0.4); check(False, f"hata beklenirdi: {why}")
    except ValueError:
        check(True, f"geçersiz değer reddedildi: {why}")
p = hm.preset("TAPPED", "M10")
check(abs(p["d"] - 0.0085) < 1e-12 and abs(p["pitch"] - 0.0015) < 1e-12, "M10: matkap 8.5, adım 1.5")
p = hm.preset("CBORE", "M6", scale_length=0.001)
check(abs(p["d"] - 6.6) < 1e-9 and abs(p["cb_d"] - 11.0) < 1e-9, "birim ölçeği mm sahnede: M6 geçme Ø6.6, yuva Ø11")
check(set(hm.SIZES) == set(hm.CLEARANCE) == set(hm.CBORE) == set(hm.CSINK), "bütün tablolarda aynı ölçüler")
check(all(hm.ISO_COARSE[k][2] < hm.ISO_COARSE[k][0] < hm.CLEARANCE[k] < hm.CBORE[k][0] for k in hm.SIZES), "matkap < anma < geçme < yuva çapı")
t = hm.describe({"kind": "CBORE", "d": 9, "cb_d": 15, "cb_depth": 8.6, "through": True, "thread": "M8"})
check(t == "M8 Kademeli Ø9 · yuva Ø15×8.6 · tümüyle geçen", f"açıklama: {t}")
print("SONUÇ:", "tamam" if not fails else f"{fails} hata")
sys.exit(1 if fails else 0)
