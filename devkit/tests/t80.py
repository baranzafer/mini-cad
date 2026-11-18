# v0.34.0: birleşim noktasını eğriler üzerinde kaydırma (slide.py, bpy'siz)
import sys, types, importlib, math
import numpy as np
pkg = types.ModuleType("mini_cad"); pkg.__path__ = ["/home/claude/mini_cad"]; sys.modules["mini_cad"] = pkg
sl = importlib.import_module("mini_cad.slide")
sm = importlib.import_module("mini_cad.sketchmath")
fails = 0
def check(ok, msg):
    global fails
    print(("  ok  " if ok else "  HATA ") + msg)
    if not ok: fails += 1
L = sl._line_bez
A, B, C = np.array([0., 0, 0]), np.array([1., 0, 0]), np.array([2., 0, 0])
# 1) iki doğrudan oluşan düz zincirin orta düğümü: ileri kaydır → iki doğru, aynı doğrultu
segs, lines, new = sl.slide_chain([L(A, B), L(B, C)], [True, True], 1, False, "f", 0.5)
check(np.allclose(new, [1.5, 0, 0]) and np.allclose(segs[0][3], new) and np.allclose(segs[1][0], new)
      and np.allclose(segs[0][0], A) and np.allclose(segs[1][3], C), "doğru zincir: düğüm 1.5'e kaydı, uçlar yerinde")
check(all(sl._is_straight(s) for s in segs), "doğrular düz kaldı")
# 2) çeyrek daire yayı (2 parça) üzerinde kaydırma: şekil (yarıçap) korunur
def arc(c, r, a0, a1):
    k = 4 / 3 * math.tan((a1 - a0) / 4)
    p0 = c + r * np.array([math.cos(a0), math.sin(a0), 0]); p3 = c + r * np.array([math.cos(a1), math.sin(a1), 0])
    t0 = np.array([-math.sin(a0), math.cos(a0), 0]); t1 = np.array([-math.sin(a1), math.cos(a1), 0])
    return np.array([p0, p0 + t0 * r * k, p3 - t1 * r * k, p3])
O = np.zeros(3)
s1, s2 = arc(O, 1, 0, math.pi / 4), arc(O, 1, math.pi / 4, math.pi / 2)
segs, lines, new = sl.slide_chain([s1, s2], [False, False], 1, False, "f", 0.5)
rad = [np.linalg.norm(sm.bez_point(P, t)) for P in segs for t in np.linspace(0, 1, 21)]
check(abs(np.linalg.norm(new) - 1) < 1e-4 and max(abs(r - 1) for r in rad) < 2e-3,
      f"yay üzerinde kaydırma: yarıçap korunur (sapma {max(abs(r - 1) for r in rad):.1e})")
ang = math.degrees(math.atan2(new[1], new[0]))
check(55 < ang < 80, f"düğüm yay boyunca ilerledi ({ang:.1f}°)")
# geri yönde
segs, lines, new = sl.slide_chain([s1, s2], [False, False], 1, False, "b", 0.5)
ang = math.degrees(math.atan2(new[1], new[0]))
check(10 < ang < 35 and abs(np.linalg.norm(new) - 1) < 1e-4, f"geri kaydırma ({ang:.1f}°)")
# 3) uç uzatma (doğru) ve kısaltma
segs, lines, new = sl.slide_chain([L(A, B)], [True], 1, False, "x", 0.5)
check(np.allclose(new, [1.5, 0, 0]) and np.allclose(segs[0][3], new), "uçtan teğet boyunca uzatma")
segs, lines, new = sl.slide_chain([L(A, B)], [True], 1, False, "b", 0.4)
check(np.allclose(new, [0.4, 0, 0]), "uçtan geri kısaltma")
# 4) Slider: + birleşimi — yatay doğru zinciri düğümü ile dikey doğrunun ucu aynı noktada
H = ([L(A, B), L(B, C)], [True, True], False)
V = ([L(B, B + [0, 1, 0])], [True], False)
s = sl.Slider([H, V], [(0, 1), (1, 0)])
kinds = sorted(b.kind for b, _ in s.branches)
check(kinds == ["b", "f", "f", "x"], f"dallar: {kinds}")
bi = next(i for i, (b, _) in enumerate(s.branches) if b.kind == "f" and b.owner == 0)
out, new = s.apply(bi, 0.5)
check(np.allclose(new, [1.5, 0, 0]) and np.allclose(out[1][0][0][0], new) and np.allclose(out[1][0][0][3], [1, 1, 0]),
      "yatay boyunca kaydı; dikey doğrunun ucu birlikte geldi, öbür ucu yerinde")
# dikey doğru boyunca kaydırma: yatay zincir düğümü dikeyde yukarı taşınır (bağlı)
bi = next(i for i, (b, _) in enumerate(s.branches) if b.owner == 1 and b.kind == "f")
out, new = s.apply(bi, 0.3)
check(np.allclose(new, [1, 0.3, 0]) and np.allclose(out[0][0][0][3], new) and np.allclose(out[0][0][1][0], new),
      "dikey boyunca kaydı; yatay zincirin düğümü izledi")
# 5) T birleşimi: geçen eğri yalnız yol
s = sl.Slider([V], [(0, 0)], passing=[(L(A, C), 0.5)])
bi = next(i for i, (b, _) in enumerate(s.branches) if b.kind == "p")
out, new = s.apply(bi, 0.8)
check(np.allclose(new, [1.6, 0, 0]) and np.allclose(out[0][0][0][0], new), "T birleşimi: geçen eğri boyunca kaydı")
# 6) yakalama: yol üzerindeki nokta
s = sl.Slider([H], [(0, 1)])
s.add_snap_points([[1.25, 0, 0], [5, 5, 5]], ["Orta", "Uç"], 1e-4)
check(len(s.snaps) == 1 and s.snaps[0][2] == "Orta", "yol üzerindeki yakalama noktası bulundu, dıştaki alınmadı")
s.add_crossings([np.array([[1.7, -1, 0], [1.7, 1, 0]])], 1e-3)
cr = [x for x in s.snaps if x[2] == "Kesişim"]
check(len(cr) == 1 and abs(s.branches[cr[0][0]][0].point(cr[0][1])[0] - 1.7) < 0.02, "öbür eğriyle kesişim yakalaması")
b = s.branches[0][0]
par, p = b.at(0.25)
check(abs(np.linalg.norm(p - b.path[0]) - 0.25) < 1e-6, "yay uzunluğuyla konum (ölçü yazma)")
# 7) uydurma: düz olmayan iki parçanın birleşimi teğetleri korur
Pj, isl = sl.join(s1, s2)
check(not isl and abs(np.linalg.norm(sm.bez_point(Pj, 0.5)) - 1) < 5e-3, "birleştirilen yay hâlâ yay")
print("BAŞARISIZ:", fails) if fails else print("TAMAM")
sys.exit(1 if fails else 0)
