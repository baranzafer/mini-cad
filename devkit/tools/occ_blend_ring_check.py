"""Halka biçimli teğet birleşim (v0.23.1) GERÇEK OCC ile ölçülür. OCP 7.9 gerekir:
    python3 -m venv /tmp/occ && /tmp/occ/bin/pip install "cadquery-ocp-novtk>=7.9.3,<8" numpy
    /tmp/occ/bin/python devkit/tools/occ_blend_ring_check.py <eklenti klasörü>
Model (kullanıcı raporu): z=0'da yuvarlatılmış dikdörtgen, z=H'de daire; 8 yama (4 kenar +
4 köşe), hiçbiri düzlemsel değil → hepsi kaynaşır. v0.23.0'da Teğet seçilince OCC dolgu aracı
çöküyordu (segfault: Dolgu yüzü ortak kenarı kopyalar, kenarın komşu yüzde pcurve'ü yok),
çökmese de kurma sırasına göre 35°'ye varan kırılma kalıyordu. Şimdi: ortak teğet şeridi.
v0.24.0: Teğet 4 kenarlı yamada Hermite-Coons sınır yüzeyi (teğet ağırlığı); Coons düzeltmesi.
Ölçülen: komşu yamaların ortak kenarında normaller arası açı (kırılma); yamanın Coons sınır
yüzeyine göre dışa taşması (balon etkisi, yama boyunun %'si); dört biçim; kurma sıraları;
önizleme; teğet ağırlığı 0.5 / 1 / 2."""
import math, os, sys, tempfile, time
import numpy as np
_src = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/mini_cad")
_pkg = tempfile.mkdtemp(); os.makedirs(os.path.join(_pkg, "mc")); open(os.path.join(_pkg, "mc", "__init__.py"), "w").close()
for _f in ("geometry.py", "errors.py"): os.symlink(os.path.join(_src, _f), os.path.join(_pkg, "mc", _f))
sys.path.insert(0, _pkg)
from mc import geometry as g
from OCP.BRep import BRep_Tool
from OCP.ShapeAnalysis import ShapeAnalysis_Surface
from OCP.GeomLProp import GeomLProp_SLProps
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_REVERSED
SHAPE = globals().get('SHAPE', (2.0, 1.3, 0.45, 0.2, 0.2, 1.0, 1.0))
AX, AY, RF, CX, CY, RC, H = SHAPE
def P(*a): return tuple(float(x) for x in a)
def line(a, b): a, b = np.array(a, float), np.array(b, float); return {"p": [P(*a), P(*(a+(b-a)/3)), P(*(a+2*(b-a)/3)), P(*b)]}
def arcseg(c, r, t0, t1, z):
    k = 4/3*math.tan((t1-t0)/4)*r
    p0 = np.array([c[0]+r*math.cos(t0), c[1]+r*math.sin(t0), z]); p1 = np.array([c[0]+r*math.cos(t1), c[1]+r*math.sin(t1), z])
    d0 = np.array([-math.sin(t0), math.cos(t0), 0]); d1 = np.array([-math.sin(t1), math.cos(t1), 0])
    return {"p": [P(*p0), P(*(p0+d0*k)), P(*(p1-d1*k)), P(*p1)]}
# taban düğümleri (saat yönü tersine): her köşe yayının iki ucu
corn = [(AX-RF, AY-RF, 0.0), (-(AX-RF), AY-RF, math.pi/2), (-(AX-RF), -(AY-RF), math.pi), (AX-RF, -(AY-RF), 1.5*math.pi)]
base = []   # [(segment, düğüm0, düğüm1)]
nodes = []
for cx, cy, t in corn:
    a = arcseg((cx, cy), RF, t, t+math.pi/2, 0.0)
    nodes.append(np.array(a["p"][0])); nodes.append(np.array(a["p"][3]))
segs_bottom = []
for k, (cx, cy, t) in enumerate(corn):
    segs_bottom.append(arcseg((cx, cy), RF, t, t+math.pi/2, 0.0))            # köşe yayı: nodes[2k] -> nodes[2k+1]
    segs_bottom.append(line(nodes[2*k+1], nodes[(2*k+2) % 8]))                # kenar
ang = [math.atan2(n[1]-CY, n[0]-CX) for n in nodes]
top_pts = [np.array([CX+RC*math.cos(a), CY+RC*math.sin(a), H]) for a in ang]
def toparc(i, j):
    a0, a1 = ang[i], ang[j]
    if a1 <= a0: a1 += 2*math.pi
    return arcseg((CX, CY), RC, a0, a1, H)
rise = [line(nodes[i], top_pts[i]) for i in range(8)]
patches = []
TRI = globals().get("TRI", False)   # kenar yamaları: düz üçgen + eğri üçgen (kullanıcı modeli)
for k in range(8):   # segment k: nodes[k] -> nodes[k+1]
    if TRI and k % 2 == 1:
        i, j = k, (k+1) % 8
        bsg = segs_bottom[k]; t = toparc(i, j); t = {"p": list(reversed(t["p"]))}
        diag = line(nodes[j], top_pts[i])
        r0 = {"p": list(reversed(rise[i]["p"]))}
        ch1 = [bsg, diag, r0]
        ch2 = [rise[j], t, {"p": list(reversed(diag["p"]))}]
        patches.append({"idx": len(patches), "name": "düz" + str(k//2), "chain": ch1, "sides": [[x] for x in ch1], "method": "AUTO"})
        patches.append({"idx": len(patches), "name": "eğri" + str(k//2), "chain": ch2, "sides": [[x] for x in ch2], "method": "AUTO"})
        continue
    i, j = k, (k+1) % 8
    b = segs_bottom[k]
    t = toparc(i, j); t = {"p": list(reversed(t["p"]))}
    r1 = rise[j]; r0 = {"p": list(reversed(rise[i]["p"]))}
    ch = [b, r1, t, r0]
    patches.append({"idx": len(patches), "name": ("köşe" if k % 2 == 0 else "kenar") + str(k//2), "chain": ch, "sides": [[s] for s in ch], "method": "AUTO"})
def normal_at(face, p):
    surf = BRep_Tool.Surface_s(face)
    uv = ShapeAnalysis_Surface(surf).ValueOfUV(gp_Pnt(*p), 1e-7)
    pr = GeomLProp_SLProps(surf, uv.X(), uv.Y(), 1, 1e-9)
    if not pr.IsNormalDefined(): return None
    n = pr.Normal(); n = np.array([n.X(), n.Y(), n.Z()])
    return -n if face.Orientation() == TopAbs_REVERSED else n
def kink(built):
    worst = 0.0
    for k in range(8):
        fa, fb = built[k], built[(k+1) % 8]; a, c = nodes[(k+1) % 8], top_pts[(k+1) % 8]
        for s in np.linspace(0.2, 0.8, 13):
            q = a*(1-s)+c*s; na, nb = normal_at(fa, q), normal_at(fb, q)
            if na is None or nb is None: continue
            worst = max(worst, math.degrees(math.acos(min(1, abs(float(np.dot(na, nb))/np.linalg.norm(na)/np.linalg.norm(nb))))))
    return worst
def run(blend, preview=False, order_fn=None, weight=1.0):
    for p in patches: p["blend"] = blend; p["weight"] = weight
    b = g.Builder(); built, info = {}, {}
    t0 = time.perf_counter()
    order = (order_fn or g.blend_order)(patches) if blend != "SHARP" else patches
    if blend != "SHARP" and hasattr(g, "blend_prepare"): g.blend_prepare(b, order)
    for p in order:
        try:
            f, lab = b.face(p["chain"], p["sides"], p["method"], preview, **({"blend": blend, "weight": weight} if blend != "SHARP" else {}))
        except Exception as e:
            print("   HATA", p["name"], e); return
        built[p["idx"]], info[p["name"]] = f, lab
    ms = (time.perf_counter()-t0)*1000
    shape, sinfo = g.assemble([built[k] for k in range(len(patches))], [], 1e-6, False)
    print(f"[{blend}{' önizleme' if preview else ''}] {ms:.0f} ms · {sinfo} · kullanılabilir={all(g.face_usable(f) for f in built.values())} · kırılma {kink(built):.2f}°")
    return built

def per_edge(built):
    out = []
    for k in range(8):
        fa, fb = built[k], built[(k+1) % 8]; a, c = nodes[(k+1) % 8], top_pts[(k+1) % 8]
        w = 0.0
        for s in np.linspace(0.2, 0.8, 7):
            q = a*(1-s)+c*s; na, nb = normal_at(fa, q), normal_at(fb, q)
            if na is None or nb is None: continue
            w = max(w, math.degrees(math.acos(min(1, abs(float(np.dot(na, nb))/np.linalg.norm(na)/np.linalg.norm(nb))))))
        out.append(round(w, 2))
    return out

from OCP.GeomAPI import GeomAPI_ProjectPointOnSurf

def bulge(built):
    """Her yamanın Coons sınır yüzeyine göre en büyük dışa (+) / içe (−) sapması, yama boyunun %'si."""
    out = []
    for p in patches:
        cs = [g._bspline_from_side(s) for s in p["sides"]]
        S = g._GeomFill_BSplineCurves(cs[0], cs[1], cs[2], cs[3], g._GeomFill_CoonsStyle).Surface()
        u0, u1, v0, v1 = S.Bounds(); surf = BRep_Tool.Surface_s(built[p["idx"]]); worst = 0.0
        for a in np.linspace(0.1, 0.9, 9):
            for b in np.linspace(0.1, 0.9, 9):
                q = S.Value(u0 + (u1-u0)*a, v0 + (v1-v0)*b)
                pr = GeomAPI_ProjectPointOnSurf(q, surf)
                if pr.NbPoints() == 0: continue
                r = pr.NearestPoint()
                d = np.array([r.X()-q.X(), r.Y()-q.Y(), r.Z()-q.Z()])
                rad = np.array([q.X()-CX, q.Y()-CY, 0.0]); rad /= np.linalg.norm(rad)
                sv = float(np.dot(d, rad))
                if abs(sv) > abs(worst): worst = sv
        P = np.array([q for s in p["chain"] for q in s["p"]])
        out.append(100 * worst / float(np.ptp(P, axis=0).max()))
    return out

if __name__ == "__main__":
    import sys as _s
    ok = True
    for shp in ((2.0, 1.3, 0.45, 0.2, 0.2, 1.0, 1.0), (1.0, 1.0, 0.3, 0.0, 0.0, 0.7, 1.5),
                (3.0, 1.0, 0.5, -0.8, 0.3, 0.6, 0.6), (1.5, 1.5, 0.7, 0.5, -0.4, 1.2, 0.8)):
        ns = {"__name__": "ring", "SHAPE": shp}
        exec(compile(open(__file__).read().split("if __name__ ==")[0], __file__, "exec"), ns)
        print("Biçim", shp)
        sharp = max(ns["per_edge"](ns["run"]("SHARP")))
        worst = 0.0
        for st in range(0, 8, 3):
            rot = lambda ps, s=st: sorted(ps, key=lambda p: (p["idx"] - s) % 8)
            b = ns["run"]("TANGENT", order_fn=rot)
            e = ns["per_edge"](b); worst = max(worst, max(e))
            print(f"   kurma sırası {st}'den: kenarlarda kırılma {e}")
        pv = max(ns["per_edge"](ns["run"]("TANGENT", True)))
        bl1 = ns["bulge"](b)
        free = ns["run"]("TANGENT_FREE"); blf = ns["bulge"](free)
        print(f"   keskin {sharp:.2f}° → teğet en kötü {worst:.2f}° (önizleme {pv:.2f}°)")
        print(f"   Coons'a göre taşma: teğet %{min(bl1):+.1f}..{max(bl1):+.1f} · serbest dolgu %{min(blf):+.1f}..{max(blf):+.1f}")
        prev = None
        for w in (0.5, 1.0, 2.0):
            bw = ns["run"]("TANGENT", weight=w); kw = max(ns["per_edge"](bw)); m = float(np.mean(ns["bulge"](bw)))
            print(f"   teğet ağırlığı {w}: kırılma {kw:.2f}° · ortalama taşma %{m:+.1f}")
            ok &= kw < 1.0 and (prev is None or m > prev)
            prev = m
        ok &= worst < 1.0 and pv < 3.0 and worst < sharp + 1e-9 and max(abs(x) for x in bl1) < 2.0
    print("Üçgenli model (kenarlar: düzlemsel üçgen + üstü yay olan eğri üçgen)")
    ns = {"__name__": "ring", "TRI": True}
    exec(compile(open(__file__).read().split("if __name__ ==")[0], __file__, "exec"), ns)
    ps = ns["patches"]; own = {}
    for p in ps:
        for sg in p["chain"]: own.setdefault(g._ekey(sg["p"]), []).append(p["idx"])
    shared = [(k, v) for k, v in own.items() if len(v) == 2]
    def tri_kink(built):
        w = 0.0
        for k, (a_, c_) in shared:
            Pc = g._np(g._cubic(g._np(list(k))))
            for sv in np.linspace(0.2, 0.8, 7):
                q = g._bez(Pc, sv); na, nb = ns["normal_at"](built[a_], q), ns["normal_at"](built[c_], q)
                if na is None or nb is None: continue
                w = max(w, math.degrees(math.acos(min(1, abs(float(np.dot(na, nb)) / np.linalg.norm(na) / np.linalg.norm(nb))))))
        return w
    for bl, w in (("SHARP", 1.0), ("TANGENT", 1.0), ("TANGENT", 0.5), ("TANGENT", 2.0)):
        kk = tri_kink(ns["run"](bl, weight=w))
        print(f"   {bl} ağırlık {w}: kenar ortalarında (%20-80) en büyük kırılma {kk:.2f}°")
        if bl == "TANGENT":
            ok &= kk < 1.5
    assert ok, "halka teğet birleşim beklenen sınırda değil"
    print("SONUÇ: halka teğet birleşim çalışıyor")
