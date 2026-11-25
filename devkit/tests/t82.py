# v0.36.0: diş hesapları (threadmath, bpy / OCC'siz)
import sys, types, importlib, math
pkg = types.ModuleType("mini_cad"); pkg.__path__ = ["/home/claude/mini_cad"]; sys.modules["mini_cad"] = pkg
tm = importlib.import_module("mini_cad.threadmath")
hm = importlib.import_module("mini_cad.holemath")
fails = 0
def check(ok, msg):
    global fails
    print(("  ok  " if ok else "  HATA ") + msg)
    if not ok: fails += 1

def spec(fam, size, **kw):
    st = tm.standard(fam, size)
    d = {"D": st["D"], "P": st["P"], "profile": st["profile"], "angle": st["a1"] + st["a2"],
         "angle2": st["a1"], "depth": st["depth"], "crest": st["crest"], "rc": st["rc"], "rr": st["rr"]}
    d.update(kw)
    return tm.spec_from(d)

# standartlar
st = tm.standard("ISO_M", "M6")
check(st["D"] == 6.0 and st["P"] == 1.0 and abs(st["depth"] - 0.5413) < 1e-3 and st["tap"] == 5.0, "M6: Ø6 × 1, h 0.541, matkap 5")
check(abs(tm.standard("UNC", "1/4-20")["P"] - 1.27) < 1e-9, "1/4-20 UNC adım 1.27 mm")
check(abs(tm.standard("BSP", "G1/2")["D"] - 20.955) < 1e-9, "G1/2 boru dişi Ø20.955")
check(tm.standard("TR", "Tr20×4")["profile"] == "TRAP" and tm.standard("BUTT", "S20×4")["a1"] == 3.0, "trapez / testere profili")
check(all(len(tm.sizes(f)) > 5 for f, *_ in tm.FAMILIES if f != "CUSTOM"), "her standartta ölçüler")
check(tm.find_size("ISO_M", 8.0, 1.25) == "M8", "çap + adımdan ölçü adı")

# profil: her standartta, her ofsette çokgen adımdan dar (helis turları değmez)
bad = []
for f, *_r in tm.FAMILIES:
    if f == "CUSTOM":
        continue
    for size in tm.sizes(f):
        sp = spec(f, size)
        P = sp["P"]
        for c in (0.0, 0.1, 0.2):
            dh, ds = tm.fit_offsets(c * P, 0.5)
            if tm.check_regions(sp, dh, ds):
                bad.append((size, c))
check(not bad, f"bütün standart ölçülerde profil adıma sığar (boşluk 0 / 0.1P / 0.2P) {bad[:3]}")
big = spec("BSW", "1/4 BSW"); P_ = big["P"]
check(bool(tm.check_regions(big, *tm.fit_offsets(0.5 * P_, 0.5))), "aşırı boşluk reddedilir (hata metni)")
sp = spec("ISO_M", "M6")
base = tm.outline(sp)
check(base[0] == (0.0, 0.0) and abs(base[-1][0] - 1.0) < 1e-12 and abs(max(q[1] for q in base) - sp["depth"]) < 1e-12, "dış profil dipten dibe, tepe = diş yüksekliği")
w_crest = [q for q in base if abs(q[1] - sp["depth"]) < 1e-12]
check(abs(w_crest[-1][0] - w_crest[0][0] - 0.125) < 1e-9, "ISO tepe düzlüğü P/8")
up = tm.offset(base, 0.05); dn = tm.offset(base, -0.05)
check(max(q[1] for q in up) > max(q[1] for q in base) > max(q[1] for q in dn), "ofset: + büyütür, − küçültür")
a0 = tm.area_centroid(tm.tooth_region(sp, 0.0)[0])[0]
a1 = tm.area_centroid(tm.tooth_region(sp, 0.1)[0])[0]
check(a1 > a0, "delik payı diş oluğunu büyütür")
g0 = tm.area_centroid(tm.groove_region(sp, 0.0)[0])[0]
g1 = tm.area_centroid(tm.groove_region(sp, -0.1)[0])[0]
check(g1 > g0, "vida payı vidadaki oluğu büyütür (vida küçülür)")
# sivri tepede aşırı küçültme: ilmek temizlenir
sharp = spec("ISO_M", "M6", crest=0.0)
o = tm.offset(tm.outline(sharp), -0.2)
check(all(o[i][0] <= o[i + 1][0] + 1e-9 for i in range(len(o) - 1)), "sivri tepede küçültme: kendini kesmeyen profil")
# yuvarlak profil
rd = spec("RD", "Rd20×1/8\"")
check(len(tm.outline(rd)) > 10 and not tm.check_regions(rd, 0, 0), "yuvarlak diş: yaylarla")
# özel profil (eğri noktaları)
cs = tm.spec_from({"D": 10, "P": 2, "profile": "CUSTOM", "depth": 1.0,
                   "custom": [(math.cos(a), math.sin(a)) for a in [math.pi - k * math.pi / 8 for k in range(9)]]})
co = tm.outline(cs)
check(co[0] == (0.0, 0.0) and co[-1][0] == 2.0 and abs(max(q[1] for q in co) - 1.0) < 1e-9, "özel profil adıma ve yüksekliğe ölçeklenir")
# asimetrik (testere) dişi adıma sığar
bt = spec("BUTT", "S20×4")
ol = tm.outline(bt)
check(0 < min(q[0] for q in ol[1:-1]) and max(q[0] for q in ol[1:-1]) < 4.0, "testere dişi adımın içinde")
# matkap: modellenmiş delikte iç çapa yakın
d = tm.minor_drill(spec("ISO_M", "M8"), 0.0, 1.0)
check(6.6 < d < 6.9, f"M8 modellenmiş matkap Ø{d:.3f}")
check(tm.minor_drill(spec("ISO_M", "M8"), 0.0, 0.75) > d, "kavrama azalınca matkap büyür")
# geçme
check(tm.fit_offsets(0.2, 0.5) == (0.1, -0.1) and tm.fit_offsets(0.2, 1.0, 0.05) == (0.25, -0.05), "boşluk paylaşımı ve baskı genleşmesi")
check(abs(tm.fit_clearance("ISO", 1.0) - 0.0065) < 1e-12 and tm.fit_clearance("FDM", 1) == 0.25 and tm.fit_clearance("CUSTOM", 1) is None, "geçme ön ayarları")
# Pappus hacmi
sq = [(0, 0), (1, 0), (1, 1), (0, 1)]
check(abs(tm.thread_volume_per_turn(sq, 2.0) - 2 * math.pi * 2.5) < 1e-12, "tur başına hacim (Pappus)")
# baş / somun / boy
check(tm.head_dims("SOCKET", 6.0)["dk"] == 10.0 and tm.nut_dims(8.0)["s"] == 13.0, "ISO 4762 / 4032 tabloları")
check(tm.head_dims("SOCKET", 7.3)["dk"] > 7.3, "tablo dışı çapta orantılı baş")
check(tm.std_length(11.0) == 10 and tm.std_length(16.0) == 16, "standart boy")
check(tm.cbore_dims("SOCKET", 8.0, hm.CBORE) == (15.0, 8.6) and tm.cbore_dims("HEX", 8.0, hm.CBORE)[0] > 15.0, "kademeli yuva: imbus tablo, altıgende lokma payı")
check(tm.csink_dims("INCH82", 6.35, hm.CSINK)[1] == 82.0, "inç havşa 82°")
# delik profili: ağız pahı ve havşa üstü pay
pr = hm.profile({"kind": "TAPPED", "d": 5.0, "through": True, "mouth_d": 6.6}, 20)
check(any(abs(r - 2.5) < 1e-12 and abs(s - 0.8) < 1e-9 for r, s in pr), "dişli delikte ağız pahı (90°)")
pr = hm.profile({"kind": "CSINK", "d": 6.6, "through": True, "cs_d": 13.0, "cs_angle": 90, "cs_head": 1.0}, 20)
check(any(abs(r - 6.5) < 1e-12 and abs(s - 1.0) < 1e-12 for r, s in pr), "havşa üstü silindirik pay")
print("SONUÇ:", "tamam" if not fails else f"{fails} hata")
sys.exit(1 if fails else 0)
