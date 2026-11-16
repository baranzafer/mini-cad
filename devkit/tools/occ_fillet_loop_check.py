"""Kapak çevresi kenar döngüsüne fillet (v0.25.13) — GERÇEK OCC. OCP 7.9 gerekir:
    /tmp/occ/bin/python devkit/tools/occ_fillet_loop_check.py <eklenti klasörü>
Model (kullanıcı raporu, kayıttaki uç / orta noktalardan uydurma): y=0'da 10 noktalı kapalı
"kemik" profil, y=-4.204'te dikeyde ters dönmüş ikinci profil, aralarında 4 doğru ray, 4 yan
Coons yüzü, y=0'da 8 ve 9 numaralı çizgilerle üçe bölünmüş düz kapak, öbür uç açık (10 serbest
kenar). Fillet y=0 döngüsüne (10 kenar, teğet sürekli: OCC tek kontur yapar).
  1) Pürüzsüz profil: 0.01–0.2 arası her ölçü uygulanmalı (bölünmüş ve tek kapak).
  2) Bir noktanın tutamaçları neredeyse sıfır (sivri): OCC çözemez; hata mesajı yeri ve
     daralan yarıçapı söylemeli.
"""
import json, os, sys, tempfile
import numpy as np
SRC = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/mini_cad")
pkg = tempfile.mkdtemp(); os.makedirs(os.path.join(pkg, "mc")); open(os.path.join(pkg, "mc", "__init__.py"), "w").close()
for f in ("geometry.py", "errors.py"):
    os.symlink(os.path.join(SRC, f), os.path.join(pkg, "mc", f))
sys.path.insert(0, pkg)
from mc import geometry as g
D = json.loads('''{"S0": [[[-2.15184, 0.0, 2.68396], [-2.01164, 0.0, 2.76087], [-1.64904, 0.0, 2.93629], [-1.194, 0.0, 3.071]], [[-1.194, 0.0, 3.071], [-0.43001, 0.0, 3.29717], [0.41635, 0.0, 3.29911], [1.181, 0.0, 3.075]], [[1.181, 0.0, 3.075], [1.63853, 0.0, 2.9409], [2.00736, 0.0, 2.76282], [2.1525, 0.0, 2.68282]], [[2.1525, 0.0, 2.68282], [2.68456, 0.0, 2.38957], [2.77332, 0.0, 1.87608], [2.52178, 0.0, 1.57587]], [[2.52178, 0.0, 1.57587], [2.33329, 0.0, 1.35091], [1.98576, 0.0, 1.28423], [1.58935, 0.0, 1.49033]], [[1.58935, 0.0, 1.49033], [1.44443, 0.0, 1.56568], [1.29595, 0.0, 1.66507], [1.064, 0.0, 1.756]], [[1.064, 0.0, 1.756], [0.35422, 0.0, 2.03424], [-0.54948, 0.0, 2.01935], [-1.244, 0.0, 1.681]], [[-1.244, 0.0, 1.681], [-1.39512, 0.0, 1.60738], [-1.50842, 0.0, 1.5338], [-1.61826, 0.0, 1.47769]], [[-1.61826, 0.0, 1.47769], [-1.98399, 0.0, 1.29088], [-2.32701, 0.0, 1.3488], [-2.51787, 0.0, 1.57395]], [[-2.51787, 0.0, 1.57395], [-2.77284, 0.0, 1.87472], [-2.68597, 0.0, 2.39096], [-2.15184, 0.0, 2.68396]]], "S1": [[[-2.15313, -4.204, 1.37189], [-2.00737, -4.204, 1.28904], [-1.66665, -4.204, 1.12399], [-1.244, -4.204, 0.9916]], [[-1.244, -4.204, 0.9916], [-0.50517, -4.204, 0.76017], [0.31772, -4.204, 0.73928], [1.064, -4.204, 0.9406]], [[1.064, -4.204, 0.9406], [1.54288, -4.204, 1.06978], [1.9627, -4.204, 1.26177], [2.1453, -4.204, 1.36424]], [[2.1453, -4.204, 1.36424], [2.63788, -4.204, 1.64066], [2.71271, -4.204, 2.11934], [2.47734, -4.204, 2.39507]], [[2.47734, -4.204, 2.39507], [2.30341, -4.204, 2.59882], [1.98576, -4.204, 2.66128], [1.62669, -4.204, 2.47419]], [[1.62669, -4.204, 2.47419], [1.50073, -4.204, 2.40855], [1.37105, -4.204, 2.3211], [1.181, -4.204, 2.236]], [[1.181, -4.204, 2.236], [0.46311, -4.204, 1.91455], [-0.47737, -4.204, 1.91629], [-1.194, -4.204, 2.242]], [[-1.194, -4.204, 2.242], [-1.37926, -4.204, 2.3262], [-1.50584, -4.204, 2.41157], [-1.62838, -4.204, 2.47543]], [[-1.62838, -4.204, 2.47543], [-1.98298, -4.204, 2.66022], [-2.30516, -4.204, 2.60079], [-2.48083, -4.204, 2.39074]], [[-2.48083, -4.204, 2.39074], [-2.71167, -4.204, 2.1147], [-2.63398, -4.204, 1.6452], [-2.15313, -4.204, 1.37189]]]}''')
S0 = [[tuple(p) for p in sg] for sg in D["S0"]]
S1 = [[tuple(p) for p in sg] for sg in D["S1"]]

def L(a, b):
    a, b = np.array(a, float), np.array(b, float)
    return [tuple(a + (b - a) * t) for t in (0, 1 / 3, 2 / 3, 1)]

def rev(s):
    return list(reversed(s))

def build(S0, split_caps):
    P0, P1 = (lambda i: S0[i][0]), (lambda i: S1[i][0])
    R2, R3, R4, R5 = L(P0(2), P1(6)), L(P0(1), P1(7)), L(P0(6), P1(2)), L(P0(7), P1(1))
    bld = g.Builder(); fs = []
    P = lambda s: {"p": s}
    def add(sides):
        fs.append(bld.face([c for s in sides for c in s], sides, "AUTO", False)[0])
    add([[P(R4)], [P(S1[k]) for k in (2, 3, 4, 5)], [P(rev(R2))], [P(S0[k]) for k in (2, 3, 4, 5)]])
    add([[P(S0[1])], [P(R2)], [P(S1[6])], [P(rev(R3))]])
    add([[P(S1[k]) for k in (7, 8, 9, 0)], [P(rev(R5))], [P(S0[k]) for k in (7, 8, 9, 0)], [P(R3)]])
    add([[P(S1[1])], [P(rev(R4))], [P(S0[6])], [P(R5)]])
    if split_caps:
        l9, l8 = L(P0(1), P0(7)), L(P0(2), P0(6))
        caps = ([P(rev(l9))] + [P(S0[k]) for k in (7, 8, 9, 0)], [P(S0[1]), P(l8), P(S0[6]), P(l9)],
                [P(S0[k]) for k in (2, 3, 4, 5)] + [P(rev(l8))])
    else:
        caps = ([P(S0[k]) for k in range(10)],)
    for ch in caps:
        fs.append(bld.face(ch, [[c] for c in ch], "AUTO", False)[0])
    return g.assemble(fs, [], 1e-3, True)

def samples(seg, n=64):
    Pp = np.array(seg, float); t = np.linspace(0, 1, n)[:, None]
    return (1-t)**3*Pp[0] + 3*(1-t)**2*t*Pp[1] + 3*(1-t)*t*t*Pp[2] + t**3*Pp[3]

def fillet(S0, shape, r):
    out, res = g.apply_features(shape, [{"kind": "FILLET", "size": r,
                                          "polys": [samples(s) for s in S0]}], [], 1e-3)
    return out, res[0]

ok = True
for split in (True, False):
    shape, info = build(S0, split)
    for r in (0.01, 0.05, 0.1, 0.2):
        out, (fok, msg) = fillet(S0, shape, r)
        print(f"[{'bölünmüş' if split else 'tek'} kapak] r={r}: {fok} {msg} · yüz "
              f"{len(g._shape_faces(shape))} → {len(g._shape_faces(out))}")
        ok &= fok and len(g._shape_faces(out)) > len(g._shape_faces(shape))
assert ok, "pürüzsüz profilde fillet uygulanmalı"
# 2) Aynı rapora daha sıkı uydurulmuş profil: P3 ve P0'da tutamaçlar neredeyse sıfır (sivri)
S0b = [[tuple(p) for p in sg] for sg in json.loads('''[[[-2.037016, 0.0, 2.744636], [-2.082418, 0.0, 2.723487], [-1.61311, 0.0, 2.943964], [-1.194, 0.0, 3.071]], [[-1.194, 0.0, 3.071], [-0.453381, 0.0, 3.295489], [0.439727, 0.0, 3.297576], [1.181, 0.0, 3.075]], [[1.181, 0.0, 3.075], [1.604439, 0.0, 2.947857], [2.07813, 0.0, 2.725519], [2.032731, 0.0, 2.74665]], [[2.032731, 0.0, 2.74665], [2.713865, 0.0, 2.429615], [2.793324, 0.0, 1.831339], [2.49521, 0.0, 1.534295]], [[2.49521, 0.0, 1.534295], [2.318442, 0.0, 1.358161], [2.006122, 0.0, 1.284714], [1.594428, 0.0, 1.495605]], [[1.594428, 0.0, 1.495605], [1.446039, 0.0, 1.571618], [1.29718, 0.0, 1.667253], [1.064, 0.0, 1.756]], [[1.064, 0.0, 1.756], [0.339268, 0.0, 2.03183], [-0.534505, 0.0, 2.01781], [-1.244, 0.0, 1.681]], [[-1.244, 0.0, 1.681], [-1.394129, 0.0, 1.609731], [-1.511553, 0.0, 1.537171], [-1.623306, 0.0, 1.481304]], [[-1.623306, 0.0, 1.481304], [-2.002716, 0.0, 1.29163], [-2.312937, 0.0, 1.355577], [-2.493194, 0.0, 1.535178]], [[-2.493194, 0.0, 1.535178], [-2.791467, 0.0, 1.832364], [-2.714746, 0.0, 2.42895], [-2.037016, 0.0, 2.744636]]]''')]
shape, info = build(S0b, True)
out, (fok, msg) = fillet(S0b, shape, 0.1)
print("[sivri nokta] r=0.1:", fok, msg)
assert not fok and "daralıyor" in msg and "tutamaç" in msg, "hata mesajı yeri söylemeli"
print("SONUÇ: kapak döngüsü fillet'i çalışıyor, sivri noktada yer gösteriliyor")
