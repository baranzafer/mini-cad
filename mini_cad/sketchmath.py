"""Taslak düzenleme matematiği (bpy'siz, başsız test edilebilir): bezier bölme, varlıklar,
kesişimler, Kırp / Uzat / Böl / Ötele / 2D Köşe yuvarla / 2D Pah.

Taslak çizgisi (stroke): {"segs": [seg], "cyclic", "node_ids", "start_tan"}
Segment (seg): {"kind": "line" | "arc" | "curve", "p": (4 nokta), "grp", "auto", ...}

Varlık (entity): bir çizginin aynı nesneye ait ardışık segmentleri (Inventor'daki tek doğru,
tek yay, tek spline). Aynı "grp" değerini taşıyan segmentler ya da aynı çembere ait gruplanmamış
yay segmentleri (daire) tek varlıktır. Varlık parametresi u ∈ [0, n]: segment sırası + t.

Bütün işlemler yeni çizgi listesi döndürür; girdiyi değiştirmez.
"""

import copy
import itertools
import math

import numpy as np

from . import drawmath as dm

_GRP = itertools.count(10 ** 6)          # eklenen parçalar için benzersiz grup numarası


def new_grp():
    return next(_GRP)


# ================================================================ bezier temelleri

def _P(seg):
    return [np.asarray(q, dtype=np.float64) for q in seg["p"]]


def bez_point(P, t):
    u = 1.0 - t
    return u ** 3 * P[0] + 3 * u * u * t * P[1] + 3 * u * t * t * P[2] + t ** 3 * P[3]


def bez_deriv(P, t):
    u = 1.0 - t
    return 3 * (u * u * (P[1] - P[0]) + 2 * u * t * (P[2] - P[1]) + t * t * (P[3] - P[2]))


def bez_split(P, t):
    """De Casteljau: t'de iki kübik bezier (sol, sağ)."""
    a = [P[i] + (P[i + 1] - P[i]) * t for i in range(3)]
    b = [a[i] + (a[i + 1] - a[i]) * t for i in range(2)]
    c = b[0] + (b[1] - b[0]) * t
    return [P[0], a[0], b[0], c], [c, b[1], a[2], P[3]]


def bez_sub(P, t0, t1):
    """[t0, t1] aralığındaki parça (aynı eğri, yeniden parametrelenmiş)."""
    if t0 <= 1e-12 and t1 >= 1 - 1e-12:
        return list(P)
    left = bez_split(P, t1)[0] if t1 < 1 - 1e-12 else list(P)
    if t0 <= 1e-12:
        return left
    return bez_split(left, t0 / t1)[1]


def seg_point(seg, t):
    return bez_point(_P(seg), t)


def seg_tangent(seg, t):
    d = bez_deriv(_P(seg), t)
    n = float(np.linalg.norm(d))
    if n < 1e-12:
        P = _P(seg)
        d = P[3] - P[0]
        n = float(np.linalg.norm(d))
    return d / n if n > 1e-15 else None


def seg_sub(seg, t0, t1):
    """Segmentin [t0, t1] parçası. Doğru düz kalır; yazılan uzunluk kısıtı düşer."""
    out = {k: v for k, v in seg.items() if k not in ("p", "auto", "tan_start")}
    P = _P(seg)
    if seg["kind"] == "line":
        a, b = bez_point(P, t0), bez_point(P, t1)
        out["p"] = dm.line_seg(a, b)["p"]
        out["auto"] = [a_ for a_ in seg.get("auto", ()) if a_[0] != "DIST"]
    else:
        out["p"] = tuple(bez_sub(P, t0, t1))
        out["auto"] = []
    out["_mod"] = True
    return out


def sample(seg, n=33):
    if seg["kind"] == "line":
        P = _P(seg)
        return np.array([P[0], P[3]]), np.array([0.0, 1.0])
    t = np.linspace(0.0, 1.0, n)
    return dm.sample(seg, n), t


def seg_length(seg, n=65):
    S, _ = sample(seg, n)
    return float(np.linalg.norm(np.diff(S, axis=0), axis=1).sum())


def reverse_seg(seg):
    out = dict(seg)
    out["p"] = tuple(reversed(seg["p"]))
    out.pop("tan_start", None)
    return out


def fit_plane(points):
    """Noktalar bir düzlemdeyse (merkez, normal), değilse / doğrusalsa None."""
    P = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    c = P.mean(axis=0)
    size = float(np.linalg.norm(P.max(axis=0) - P.min(axis=0)))
    if size < 1e-12:
        return None
    _, sv, vt = np.linalg.svd(P - c)
    if sv[1] < 1e-9 * size:
        return None
    n = vt[2]
    if float(np.abs((P - c) @ n).max()) > 1e-6 * (1.0 + size):
        return None
    return c, n


def stroke_points(st):
    return [q for sg in st["segs"] for q in _P(sg)]


def sketch_scale(sketch, extra=()):
    pts = [q for st in sketch for q in stroke_points(st)]
    for poly in extra:
        pts += list(np.asarray(poly).reshape(-1, 3))
    if not pts:
        return 1.0
    P = np.array(pts)
    return max(float(np.linalg.norm(P.max(axis=0) - P.min(axis=0))), 1e-6)


# ================================================================ varlıklar

def _same_circle(a, b):
    ca, cb = dm.arc_of_bezier(_P(a)), dm.arc_of_bezier(_P(b))
    if ca is None or cb is None:
        return False
    tol = 1e-6 * (1.0 + ca[1])
    if np.linalg.norm(ca[0] - cb[0]) > tol or abs(ca[1] - cb[1]) > tol:
        return False
    ta, tb = dm.end_tangent(a), dm.start_tangent(b)
    return ta is not None and tb is not None and float(np.dot(ta, tb)) > math.cos(
        math.radians(0.5))


def _same_entity(a, b):
    if a.get("grp") is not None or b.get("grp") is not None:
        return a.get("grp") == b.get("grp") and a["kind"] == b["kind"]
    return a["kind"] == "arc" and b["kind"] == "arc" and _same_circle(a, b)


def entities(st):
    """[(i0, i1)] ardışık segment aralıkları."""
    segs = st["segs"]
    out, i = [], 0
    while i < len(segs):
        j = i + 1
        while j < len(segs) and _same_entity(segs[j - 1], segs[j]):
            j += 1
        out.append((i, j))
        i = j
    return out


def entity_of(st, seg_index):
    for i0, i1 in entities(st):
        if i0 <= seg_index < i1:
            return i0, i1
    return None


def closed_entity(st, i0, i1):
    return st["cyclic"] and i0 == 0 and i1 == len(st["segs"])


def ent_point(st, i0, i1, u):
    n = i1 - i0
    u = min(max(u, 0.0), n)
    j = min(int(u), n - 1)
    return seg_point(st["segs"][i0 + j], u - j)


def ent_sub(segs, i0, i1, a, b):
    """Varlığın [a, b] (0..n) parçasının segmentleri."""
    out = []
    for j in range(i0, i1):
        lo, hi = j - i0, j - i0 + 1
        s0, s1 = max(a, lo), min(b, hi)
        if s1 - s0 <= 1e-9:
            continue
        if s0 <= lo + 1e-12 and s1 >= hi - 1e-12:
            out.append(dict(segs[j]))
        else:
            out.append(seg_sub(segs[j], s0 - lo, s1 - lo))
    return out


# ================================================================ kesişimler

def _seg_seg_closest(A0, A1, B0, B1):
    """Doğru parçası çiftleri (vektörel): (uzaklık, s, t)."""
    d1, d2, r = A1 - A0, B1 - B0, A0 - B0
    a = np.einsum("...i,...i", d1, d1)
    e = np.einsum("...i,...i", d2, d2)
    f = np.einsum("...i,...i", d2, r)
    c = np.einsum("...i,...i", d1, r)
    b = np.einsum("...i,...i", d1, d2)
    den = a * e - b * b
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.where(den > 1e-18, np.clip((b * f - c * e) / den, 0.0, 1.0), 0.0)
        t = np.where(e > 1e-18, (b * s + f) / e, 0.0)
        t = np.clip(t, 0.0, 1.0)
        s = np.where(a > 1e-18, np.clip((b * t - c) / a, 0.0, 1.0), 0.0)
    pa = A0 + d1 * s[..., None]
    pb = B0 + d2 * t[..., None]
    return np.linalg.norm(pa - pb, axis=-1), s, t


def _poly_hits(SA, tA, SB, tol):
    """İki çoklu çizginin kesişim adayları: [(A parametresi, B üzerindeki segment, s)]."""
    A0, A1 = SA[:-1][:, None, :], SA[1:][:, None, :]
    B0, B1 = SB[:-1][None, :, :], SB[1:][None, :, :]
    d, s, t = _seg_seg_closest(A0, A1, B0, B1)
    out = []
    for i, j in zip(*np.where(d <= tol)):
        out.append((float(tA[i] + (tA[i + 1] - tA[i]) * s[i, j]), int(j), float(t[i, j])))
    return out


def _refine(PA, sa, PB, tb, it=12):
    """İki bezier arasında en yakın nokta çifti (Gauss-Newton). (s, t, uzaklık)"""
    s, t = sa, tb
    for _ in range(it):
        r = bez_point(PA, s) - bez_point(PB, t)
        J = np.stack([bez_deriv(PA, s), -bez_deriv(PB, t)], axis=1)
        try:
            step = np.linalg.lstsq(J, -r, rcond=None)[0]
        except np.linalg.LinAlgError:
            break
        s = float(np.clip(s + step[0], 0.0, 1.0))
        t = float(np.clip(t + step[1], 0.0, 1.0))
        if abs(step[0]) + abs(step[1]) < 1e-13:
            break
    return s, t, float(np.linalg.norm(bez_point(PA, s) - bez_point(PB, t)))


def _refine_poly(PA, sa, B0, B1, it=12):
    """Bezier ile doğru parçası arasında en yakın nokta (Newton). (s, uzaklık)"""
    s = sa
    d = B1 - B0
    dd = float(np.dot(d, d))
    for _ in range(it):
        p = bez_point(PA, s)
        w = float(np.clip(np.dot(p - B0, d) / dd, 0.0, 1.0)) if dd > 1e-24 else 0.0
        r = p - (B0 + d * w)
        if dd > 1e-24:
            r = r - d * float(np.dot(r, d)) / dd
        g = bez_deriv(PA, s)
        if dd > 1e-24:
            g = g - d * float(np.dot(g, d)) / dd
        gg = float(np.dot(g, g))
        if gg < 1e-24:
            break
        step = -float(np.dot(r, g)) / gg
        s = float(np.clip(s + step, 0.0, 1.0))
        if abs(step) < 1e-13:
            break
    p = bez_point(PA, s)
    w = float(np.clip(np.dot(p - B0, d) / dd, 0.0, 1.0)) if dd > 1e-24 else 0.0
    return s, float(np.linalg.norm(p - (B0 + d * w)))


def entity_cuts(sketch, k, i0, i1, extra=(), scale=None):
    """Varlığın başka geometriyle (taslak + dış çoklu çizgiler) kesiştiği iç parametreler."""
    st = sketch[k]
    segs = st["segs"]
    n = i1 - i0
    if scale is None:
        scale = sketch_scale(sketch, extra)
    tol_d = 3e-3 * scale
    tol_f = 2e-4 * scale      # "Yakın" yakalaması eğrinin kirişine düşebilir: hafif gevşek
    others = []
    for kk, st2 in enumerate(sketch):
        m = len(st2["segs"])
        for jj, sg in enumerate(st2["segs"]):
            if kk == k and i0 <= jj < i1:
                continue
            others.append(("seg", sg))
    own = [(j, segs[j]) for j in range(i0, i1)]
    cuts = []
    for j, sg in own:
        SA, tA = sample(sg)
        PA = _P(sg)
        for kind, ob in others:
            SB, tB = sample(ob)
            PB = _P(ob)
            for sa, jb, sb in _poly_hits(SA, tA, SB, tol_d):
                tb = float(tB[jb] + (tB[jb + 1] - tB[jb]) * sb)
                s, _t, dist = _refine(PA, sa, PB, tb)
                if dist <= tol_f:
                    cuts.append((j - i0) + s)
        for poly in extra:
            SB = np.asarray(poly, dtype=np.float64)
            if len(SB) < 2:
                continue
            for sa, jb, sb in _poly_hits(SA, tA, SB, tol_d):
                s, dist = _refine_poly(PA, sa, SB[jb], SB[jb + 1])
                if dist <= tol_f:
                    cuts.append((j - i0) + s)
        # varlığın kendisiyle (komşu olmayan segmentler) kesişimi
        for j2, sg2 in own:
            if abs(j2 - j) <= 1 or (closed_entity(st, i0, i1) and abs(j2 - j) == n - 1):
                continue
            SB, tB = sample(sg2)
            for sa, jb, sb in _poly_hits(SA, tA, SB, tol_d):
                tb = float(tB[jb] + (tB[jb + 1] - tB[jb]) * sb)
                s, _t, dist = _refine(PA, sa, _P(sg2), tb)
                if dist <= tol_f:
                    cuts.append((j - i0) + s)
    eps = 1e-6
    if closed_entity(st, i0, i1):          # kapalı varlıkta başlangıç (u=0 ≡ n) da kesişimdir
        cuts = sorted((0.0 if c >= n - eps or c <= eps else c) for c in cuts)
    else:
        cuts = sorted(c for c in cuts if eps < c < n - eps)
    out = []
    for c in cuts:
        if not out or c - out[-1] > 1e-6:
            out.append(c)
    return out


# ================================================================ çizgi yardımcıları

def _stroke(segs, cyclic=False):
    return {"segs": segs, "cyclic": cyclic, "node_ids": {}, "start_tan": None}


def _tag(st):
    """İşlem öncesi: segmentlere eski sıralarını yaz (kısıt referansları için)."""
    st = copy.deepcopy(st)
    for i, sg in enumerate(st["segs"]):
        sg["_oid"] = i
    return st


def _carry(old, new_strokes):
    """Eski çizginin üst verisini yeni çizgilere konumla / sırayla taşır; geçici alanları siler."""
    nodes = []
    segs = old["segs"]
    n = len(segs)
    for k, pid in (old.get("node_ids") or {}).items():
        k = k % (n if old["cyclic"] else n + 1) if n else 0
        pos = _P(segs[k])[0] if k < n else _P(segs[-1])[3]
        nodes.append((pos, pid))
    p_first = _P(segs[0])[0] if segs else None
    for st in new_strokes:
        ss = st["segs"]
        m = len(ss)
        pts = [_P(ss[j])[0] for j in range(m)] + ([] if st["cyclic"] else [_P(ss[-1])[3]])
        ids = {}
        for pos, pid in nodes:
            for j, q in enumerate(pts):
                if np.linalg.norm(q - pos) <= 1e-9 * (1.0 + float(np.abs(pos).max())):
                    ids[j] = pid
                    break
        st["node_ids"] = ids
        if old.get("start_tan") is not None and ss and ss[0].get("_oid") == 0 and \
                not ss[0].get("_mod") and np.linalg.norm(_P(ss[0])[0] - p_first) < 1e-12:
            st["start_tan"] = old["start_tan"]
        omap = {sg.get("_oid"): j for j, sg in enumerate(ss) if sg.get("_oid") is not None and
                not sg.get("_mod")}
        for sg in ss:
            autos = []
            for a in sg.get("auto", ()):
                if a[0] == "REF" and a[2][0] == "chain":
                    j = omap.get(a[2][1])
                    if j is None:
                        continue
                    autos.append(("REF", a[1], ("chain", j)))
                else:
                    autos.append(a)
            sg["auto"] = autos
    if old.get("edit_src") and len(new_strokes) == 1:
        new_strokes[0]["edit_src"] = old["edit_src"]   # taslağa alınmış eğri geri yazılsın
    for st in new_strokes:
        for sg in st["segs"]:
            sg.pop("_oid", None)
            sg.pop("_mod", None)
    return new_strokes


def fix_sketch_refs(sketch):
    """Taslak çizgisinin ucundan başlayan teğet yay referanslarını ("@sketch", çizgi,
    segment, uç) yeni sıraya göre konumdan yeniden bulur; bulunamazsa düşürür."""
    for k, st in enumerate(sketch):
        tan = st.get("start_tan")
        if tan is None or tan[1][0] != "@sketch" or not st["segs"]:
            continue
        p = _P(st["segs"][0])[0]
        found = None
        for k2 in range(len(sketch) - 1, -1, -1):
            if k2 == k:
                continue
            s2 = sketch[k2]
            if s2["cyclic"] or not s2["segs"]:
                continue
            for j, end in ((len(s2["segs"]) - 1, 3), (0, 0)):
                sg = s2["segs"][j]
                if np.linalg.norm(_P(sg)[end] - p) > 1e-9 * (1.0 + float(np.abs(p).max())):
                    continue
                t = dm.end_tangent(sg) if end == 3 else dm.start_tangent(sg)
                if t is None:
                    continue
                t = t if end == 3 else -t
                if float(np.dot(t, tan[0])) > math.cos(math.radians(1.0)):
                    found = (t, ("@sketch", k2, j, end))
                    break
            if found:
                break
        st["start_tan"] = found
    return sketch


def replace(sketch, k, new_strokes):
    """k. çizgiyi yenileriyle değiştirir (yeni liste)."""
    out = [copy.deepcopy(s) for s in sketch[:k]] + list(new_strokes) + \
        [copy.deepcopy(s) for s in sketch[k + 1:]]
    return fix_sketch_refs(out)


def reverse_stroke(st):
    out = dict(st)
    out["segs"] = [reverse_seg(sg) for sg in reversed(st["segs"])]
    out["start_tan"] = None
    return out


# ================================================================ Kırp

def trim(sketch, k, i0, i1, u, cuts):
    """İmlecin (u) bulunduğu, en yakın iki kesişim arasındaki parçayı siler. Kesişim yoksa
    varlığın tamamı silinir (Inventor gibi). Yeni taslak listesi."""
    st = _tag(sketch[k])
    segs = st["segs"]
    n = i1 - i0
    closed = closed_entity(st, i0, i1)
    inner = [c for c in cuts if (-1e-9 <= c if closed else 1e-7 < c) and c < n - 1e-7]
    if closed:
        if len(inner) < 2:
            return replace(sketch, k, [])
        lo = [c for c in inner if c < u]
        hi = [c for c in inner if c > u]
        if lo and hi:              # [a, b] silinir: [b, n] + [0, a] kalır
            a, b = lo[-1], hi[0]
            keep = ent_sub(segs, i0, i1, b, n) + ent_sub(segs, i0, i1, 0, a)
        else:                      # silinen aralık başlangıçtan (u=0) geçiyor
            keep = ent_sub(segs, i0, i1, inner[0], inner[-1])
        return replace(sketch, k, _carry(st, [_stroke(keep)]))
    a = max([c for c in inner if c < u], default=0.0)
    b = min([c for c in inner if c > u], default=float(n))
    left = segs[:i0] + ent_sub(segs, i0, i1, 0.0, a)
    right = ent_sub(segs, i0, i1, b, float(n)) + segs[i1:]
    if st["cyclic"]:
        res = [_stroke(right + left)] if right + left else []
    else:
        res = [_stroke(s) for s in (left, right) if s]
    return replace(sketch, k, _carry(st, res))


def trim_span(st, i0, i1, u, cuts):
    """Kırpılacak aralığın (a, b) parametreleri — önizleme için. Kapalı varlıkta sarmalı."""
    n = i1 - i0
    closed = closed_entity(st, i0, i1)
    inner = [c for c in cuts if (-1e-9 <= c if closed else 1e-7 < c) and c < n - 1e-7]
    if closed:
        if len(inner) < 2:
            return [(0.0, float(n))]
        lo = [c for c in inner if c < u]
        hi = [c for c in inner if c > u]
        if lo and hi:
            return [(lo[-1], hi[0])]
        a, b = inner[-1], inner[0]
        return [(a, float(n)), (0.0, b)]
    return [(max([c for c in inner if c < u], default=0.0),
             min([c for c in inner if c > u], default=float(n)))]


# ================================================================ Böl

def split(sketch, k, i0, i1, u, cuts=()):
    """Varlığı böler: açık varlık u'da ikiye ayrılır (çizgi bütün kalır, ikinci parça yeni
    nesne olur). Kapalı varlık (daire) imleci çevreleyen iki kesişimde yay parçalarına
    ayrılır. Yeni taslak ya da None."""
    st = _tag(sketch[k])
    segs = st["segs"]
    n = i1 - i0
    if closed_entity(st, i0, i1):
        inner = [c for c in cuts if -1e-9 <= c < n - 1e-7]
        if len(inner) < 2:
            return None
        lo = [c for c in inner if c < u]
        hi = [c for c in inner if c > u]
        if lo and hi:
            a, b = lo[-1], hi[0]
            piece = ent_sub(segs, i0, i1, a, b)
            rest = ent_sub(segs, i0, i1, b, n) + ent_sub(segs, i0, i1, 0, a)
        else:
            piece = ent_sub(segs, i0, i1, inner[-1], n) + ent_sub(segs, i0, i1, 0, inner[0])
            rest = ent_sub(segs, i0, i1, inner[0], inner[-1])
        g1, g2 = new_grp(), new_grp()
        for sg in piece:
            sg["grp"] = g1
        for sg in rest:
            sg["grp"] = g2
        return replace(sketch, k, _carry(st, [_stroke(piece + rest, True)]))
    if not (1e-7 < u < n - 1e-7):
        return None
    first = ent_sub(segs, i0, i1, 0.0, u)
    second = ent_sub(segs, i0, i1, u, float(n))
    g = new_grp()
    for sg in second:
        sg["grp"] = g
    out = segs[:i0] + first + second + segs[i1:]
    return replace(sketch, k, _carry(st, [_stroke(out, st["cyclic"])]))


# ================================================================ Uzat

def _ray_hit(e, d, bounds, tol, lmax):
    """Işının (e + λd) sınırlarla ilk kesişimi λ. Taslak eğrilerinde gerçek eğriyle inceltilir."""
    best = None
    for S, P in bounds:
        if len(S) < 2:
            continue
        A0 = np.broadcast_to(e, S[:-1].shape)
        A1 = np.broadcast_to(e + d * lmax, S[:-1].shape)
        dist, s, t = _seg_seg_closest(A0, A1, S[:-1], S[1:])
        for i in np.where(dist <= tol)[0]:
            lam = float(s[i]) * lmax
            if P is not None and len(S) > 2:      # eğri sınır: eğri üzerinde incelt
                tb = (i + float(t[i])) / (len(S) - 1)
                sb, dd = _refine_poly(P, tb, e, e + d * lmax)
                q = bez_point(P, sb)
                if dd <= 1e-6 * (1.0 + lmax):
                    lam = float(np.dot(q - e, d))
            if lam > 1e-7 * (1.0 + lmax) and (best is None or lam < best):
                best = lam
    return best


def _boundaries(sketch, k, i0, i1, extra):
    """[(çoklu çizgi, bezier noktaları ya da None)]"""
    out = []
    for kk, st in enumerate(sketch):
        for jj, sg in enumerate(st["segs"]):
            if kk == k and i0 <= jj < i1:
                continue
            out.append((sample(sg, 65)[0], _P(sg)))
    return out + [(np.asarray(p, dtype=np.float64), None) for p in extra]


def extend_preview(sketch, k, end, extra=(), scale=None):
    """Açık çizginin ucunu (end: 0 başlangıç, 1 son) en yakın sınıra uzatma.
    (yeni segmentler, uç noktası) ya da (None, sebep)."""
    st = sketch[k]
    if st["cyclic"] or not st["segs"]:
        return None, "Kapalı çizgi uzatılamaz"
    if scale is None:
        scale = sketch_scale(sketch, extra)
    work = st if end == 1 else reverse_stroke(st)
    segs = work["segs"]
    ent = entities(work)[-1]
    i0, i1 = ent
    last = segs[-1]
    polys = _boundaries([work if kk == k else s for kk, s in enumerate(sketch)], k, i0, i1, extra)
    tol = 1e-6 * (1.0 + scale)
    lmax = 50.0 * scale
    P = _P(last)
    if last["kind"] == "line":
        e = P[3]
        d = dm.unit(P[3] - P[0])
        if d is None:
            return None, "Sıfır boylu doğru"
        lam = _ray_hit(e, d, polys, tol, lmax)
        if lam is None:
            return None, "Uzatılacak sınır yok"
        new = dict(last)
        new["p"] = dm.line_seg(P[0], e + d * lam)["p"]
        new["auto"] = [a for a in last.get("auto", ()) if a[0] != "DIST"]
        new["_mod"] = True
        return {"segs": segs[:-1] + [new], "tip": e + d * lam, "reversed": end == 0}, ""
    if last["kind"] == "arc":
        arc = dm.arc_of_bezier(P)
        if arc is None:
            return None, "Yay tanınmadı"
        c, R, _n = arc
        e = P[3]
        t = dm.end_tangent(last)
        e1 = (e - c) / R
        e2 = t - e1 * float(np.dot(t, e1))
        e2 = dm.unit(e2)
        if e2 is None:
            return None, "Yay tanınmadı"
        used = sum(abs(_arc_angle(s)) for s in segs[i0:i1])
        rest = 2 * math.pi - used - 1e-6
        if rest <= 1e-6:
            return None, "Yay zaten tam çember"
        ang = np.linspace(0.0, rest, 721)
        path = c + R * (np.cos(ang)[:, None] * e1 + np.sin(ang)[:, None] * e2)
        best = None
        for S, _Pb in polys:
            if len(S) < 2:
                continue
            for sa, jb, sb in _poly_hits(path, ang, S, 3e-3 * scale):
                if sa > 1e-6 and (best is None or sa < best):
                    # açıyı sınır doğru parçasıyla kesiştirerek incelt
                    B0, B1 = S[jb], S[jb + 1]
                    lo_, hi_ = max(sa - 0.02, 1e-7), min(sa + 0.02, rest)
                    for _ in range(60):
                        m1 = lo_ + (hi_ - lo_) / 3
                        m2 = hi_ - (hi_ - lo_) / 3

                        def dist(a_):
                            p = c + R * (math.cos(a_) * e1 + math.sin(a_) * e2)
                            d_ = B1 - B0
                            w = float(np.clip(np.dot(p - B0, d_) / max(np.dot(d_, d_), 1e-30),
                                              0, 1))
                            return float(np.linalg.norm(p - (B0 + d_ * w)))
                        if dist(m1) < dist(m2):
                            hi_ = m2
                        else:
                            lo_ = m1
                    a_ = 0.5 * (lo_ + hi_)
                    p = c + R * (math.cos(a_) * e1 + math.sin(a_) * e2)
                    d_ = B1 - B0
                    w = float(np.clip(np.dot(p - B0, d_) / max(np.dot(d_, d_), 1e-30), 0, 1))
                    if float(np.linalg.norm(p - (B0 + d_ * w))) <= 1e-3 * scale:
                        best = a_
        if best is None:
            return None, "Uzatılacak sınır yok"
        add = dm._arc_from_basis(c, R, e1, e2, best, p_start=e)
        for sg in add:
            sg["grp"] = last.get("grp")
            sg["_mod"] = True
        tip = add[-1]["p"][3]
        return {"segs": segs + add, "tip": tip, "reversed": end == 0}, ""
    return None, "Spline uzatılamaz (doğru ve yay uzatılır)"


def _arc_angle(seg):
    arc = dm.arc_of_bezier(_P(seg))
    if arc is None:
        return 0.0
    c, R, _ = arc
    P = _P(seg)
    a, b = (P[0] - c) / R, (P[3] - c) / R
    m = (bez_point(P, 0.5) - c) / R
    ang = math.acos(max(-1.0, min(1.0, float(np.dot(a, b)))))
    if float(np.dot(m, a + b)) < 0:
        ang = 2 * math.pi - ang
    return ang


def extend(sketch, k, end, extra=(), scale=None):
    """Açık çizginin ucunu en yakın sınıra uzatır. (yeni taslak, "") ya da (None, sebep)."""
    st = _tag(sketch[k])
    sk2 = list(sketch)
    sk2[k] = st
    res, why = extend_preview(sk2, k, end, extra, scale)
    if res is None:
        return None, why
    new = _stroke([dict(sg) for sg in res["segs"]])
    if res["reversed"]:
        new = reverse_stroke(new)
    return replace(sketch, k, _carry(st, [new])), ""


# ================================================================ Ötele (offset)

def _fit_offset_curve(P, d, nrm_fn):
    """Spline segmenti için öteleme: uçlar ve uç teğetleri korunarak kübik uydurma."""
    t = np.linspace(0.0, 1.0, 17)
    Q = []
    for ti in t:
        Q.append(bez_point(P, ti) + nrm_fn(bez_deriv(P, ti)) * d)
    Q = np.array(Q)
    q0, q3 = Q[0], Q[-1]
    t0 = dm.unit(P[1] - P[0]) if np.linalg.norm(P[1] - P[0]) > 1e-12 else dm.unit(P[3] - P[0])
    t1 = dm.unit(P[3] - P[2]) if np.linalg.norm(P[3] - P[2]) > 1e-12 else dm.unit(P[3] - P[0])
    u = 1 - t
    b0, b1, b2, b3 = u ** 3, 3 * u * u * t, 3 * u * t * t, t ** 3
    base = np.outer(b0 + b1, q0) + np.outer(b2 + b3, q3)
    A = np.stack([(b1[:, None] * t0).ravel(), (-b2[:, None] * t1).ravel()], axis=1)
    rhs = (Q - base).ravel()
    try:
        al, be = np.linalg.lstsq(A, rhs, rcond=None)[0]
    except np.linalg.LinAlgError:
        al = be = float(np.linalg.norm(q3 - q0)) / 3
    return (q0, q0 + t0 * al, q3 - t1 * be, q3)


def _line_isect(p, d, q, e, n):
    """Düzlemde iki doğrunun kesişimi (p + a d = q + b e)."""
    w = np.cross(d, e)
    den = float(np.dot(w, n))
    if abs(den) < 1e-12:
        return None
    a = float(np.dot(np.cross(q - p, e), n)) / den
    return p + d * a


def offset(st, d, normal):
    """Çizginin tamamını düzlemde d kadar öteler (d > 0: n × teğet yönü). Yeni çizgi
    ya da (None, sebep)."""
    n = dm.unit(normal)
    segs = st["segs"]

    def nrm(tangent):
        v = np.cross(n, tangent)
        L = float(np.linalg.norm(v))
        return v / L if L > 1e-15 else v

    egrp = {}
    for e0, e1 in entities(st):
        g = new_grp()
        for i in range(e0, e1):
            egrp[i] = g
    out = []
    for si, sg in enumerate(segs):
        P = _P(sg)
        if sg["kind"] == "line":
            t = dm.unit(P[3] - P[0])
            if t is None:
                continue
            off = nrm(t) * d
            new = {"kind": "line", "p": dm.line_seg(P[0] + off, P[3] + off)["p"]}
        elif sg["kind"] == "arc" and dm.arc_of_bezier(P) is not None:
            c, R, _ = dm.arc_of_bezier(P)
            sgn = float(np.dot(nrm(bez_deriv(P, 0.5)), (bez_point(P, 0.5) - c) / R))
            R2 = R + math.copysign(1.0, sgn) * d
            if R2 <= 1e-9 * (1.0 + R):
                return None, "Öteleme yayın yarıçapından büyük"
            new = {"kind": "arc", "p": tuple(c + (q - c) * (R2 / R) for q in P)}
        else:
            new = {"kind": sg["kind"], "p": _fit_offset_curve(P, d, nrm)}
        new["grp"] = egrp[si]
        out.append(new)
    if not out:
        return None, "Ötelenecek parça yok"
    # birleşimler
    m = len(out)
    joints = range(m) if st["cyclic"] else range(1, m)
    for j in joints:
        A, B = out[j - 1], out[j]
        a_end, b_start = np.asarray(A["p"][3]), np.asarray(B["p"][0])
        if np.linalg.norm(a_end - b_start) <= 1e-9 * (1.0 + float(np.abs(a_end).max())):
            continue
        ta, tb = dm.end_tangent(A), dm.start_tangent(B)
        smooth = ta is not None and tb is not None and float(np.dot(ta, tb)) > math.cos(
            math.radians(1.0))
        if smooth:
            mid = 0.5 * (a_end + b_start)
            _set_end(A, 3, mid)
            _set_end(B, 0, mid)
            continue
        X = _line_isect(a_end, ta, b_start, tb, n) if ta is not None and tb is not None \
            else None
        if X is None:
            continue
        ahead_a = float(np.dot(X - a_end, ta))
        ahead_b = float(np.dot(b_start - X, tb))
        if A["kind"] == "line" and B["kind"] == "line":
            _set_end(A, 3, X)
            _set_end(B, 0, X)
        elif ahead_a >= 0 and ahead_b >= 0:     # boşluk: teğet uzantılarıyla kapat
            if A["kind"] == "line":
                _set_end(A, 3, X)
            else:
                A["_ext_after"] = X
            if B["kind"] == "line":
                _set_end(B, 0, X)
            else:
                B["_ext_before"] = X
        else:                                   # örtüşme: iki parçayı kesişimde kırp
            hit = _overlap_cut(A, B)
            if hit is not None:
                sa, tb_, q = hit
                A["p"] = tuple(bez_sub(_P(A), 0.0, sa)) if A["kind"] != "line" else \
                    dm.line_seg(_P(A)[0], q)["p"]
                B["p"] = tuple(bez_sub(_P(B), tb_, 1.0)) if B["kind"] != "line" else \
                    dm.line_seg(q, _P(B)[3])["p"]
            else:
                mid = 0.5 * (a_end + b_start)
                _set_end(A, 3, mid)
                _set_end(B, 0, mid)
    final = []
    for sg in out:
        if "_ext_before" in sg:
            X = sg.pop("_ext_before")
            final.append(dict(dm.line_seg(X, sg["p"][0]), grp=new_grp()))
        final.append(sg)
        if "_ext_after" in sg:
            X = sg.pop("_ext_after")
            final.append(dict(dm.line_seg(sg["p"][3], X), grp=new_grp()))
    return _stroke(final, st["cyclic"]), ""


def _set_end(seg, end, X):
    P = list(_P(seg))
    if seg["kind"] == "line":
        a, b = (X, P[3]) if end == 0 else (P[0], X)
        seg["p"] = dm.line_seg(a, b)["p"]
        return
    delta = np.asarray(X) - P[end]
    P[end] = np.asarray(X, dtype=np.float64)
    P[1 if end == 0 else 2] = P[1 if end == 0 else 2] + delta
    seg["p"] = tuple(P)


def _overlap_cut(A, B):
    SA, tA = sample(A, 65)
    SB, tB = sample(B, 65)
    scale = float(np.linalg.norm(SA.max(axis=0) - SA.min(axis=0))) + \
        float(np.linalg.norm(SB.max(axis=0) - SB.min(axis=0))) + 1e-9
    hits = _poly_hits(SA, tA, SB, 1e-6 * scale)
    if not hits:
        return None
    sa, jb, sb = max(hits, key=lambda h: h[0])
    tb = float(tB[jb] + (tB[jb + 1] - tB[jb]) * sb)
    s, t, _ = _refine(_P(A), sa, _P(B), tb)
    return s, t, bez_point(_P(A), s)


def offset_distance(st, p, normal):
    """İmleç p'nin çizgiye işaretli uzaklığı (offset ile aynı yön kuralı) ve en yakın nokta."""
    n = dm.unit(normal)
    best = None
    for sg in st["segs"]:
        t = np.linspace(0.0, 1.0, 129)
        S = dm.sample(sg, 129)
        d = np.linalg.norm(S - p, axis=1)
        i = int(np.argmin(d))
        if best is None or d[i] < best[0]:
            best = (float(d[i]), sg, float(t[i]), S[i])
    if best is None:
        return 0.0, None
    _, sg, t, q = best
    tan = seg_tangent(sg, t)
    if tan is None:
        return 0.0, q
    side = float(np.dot(np.cross(n, tan), p - q))
    dist = float(np.linalg.norm((p - q) - n * float(np.dot(p - q, n))))
    return math.copysign(dist, side if side != 0 else 1.0), q


# ================================================================ köşe (fillet / pah)

def corners(st, ang_deg=1.0):
    """Teğet olmayan iç birleşimler: [düğüm sırası]. Kapalı çizgide 0. düğüm de dahil."""
    segs = st["segs"]
    n = len(segs)
    out = []
    rng = range(n) if st["cyclic"] else range(1, n)
    for j in rng:
        a, b = segs[j - 1], segs[j]
        ta, tb = dm.end_tangent(a), dm.start_tangent(b)
        if ta is None or tb is None:
            continue
        if float(np.dot(ta, tb)) < math.cos(math.radians(ang_deg)):
            out.append(j)
    return out


def node_pos(st, j):
    segs = st["segs"]
    return _P(segs[j % len(segs)])[0] if j < len(segs) or st["cyclic"] else _P(segs[-1])[3]


def _arc_len_param(seg, dist, from_end):
    """Segment üzerinde uçtan (from_end: son uç) yay boyu 'dist' olan parametre (None: sığmaz)."""
    S, t = sample(seg, 129) if seg["kind"] != "line" else (None, None)
    if seg["kind"] == "line":
        L = seg_length(seg)
        if dist >= L - 1e-12:
            return None
        return 1.0 - dist / L if from_end else dist / L
    if from_end:
        S, t = S[::-1], t[::-1]
    cum = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(S, axis=0), axis=1))])
    if dist >= cum[-1] - 1e-12:
        return None
    i = int(np.searchsorted(cum, dist)) - 1
    i = max(0, min(i, len(cum) - 2))
    w = (dist - cum[i]) / max(cum[i + 1] - cum[i], 1e-30)
    return float(t[i] + (t[i + 1] - t[i]) * w)


def fillet_at(st, j, r):
    """j. düğümdeki köşeyi r yarıçaplı, iki parçaya teğet yayla yuvarlar.
    (yeni segment listesi: [A', yay..., B'] , önceki / sonraki segment sırası) ya da
    (None, sebep)."""
    segs = st["segs"]
    n = len(segs)
    ia, ib = (j - 1) % n, j % n
    A, B = segs[ia], segs[ib]
    PA, PB = _P(A), _P(B)
    pl = fit_plane(PA + PB)
    if pl is None:
        return None, "Köşedeki iki parça aynı düzlemde değil"
    nrm_ = pl[1]
    ta, tb = dm.end_tangent(A), dm.start_tangent(B)
    cosang = float(np.clip(np.dot(-ta, tb), -1.0, 1.0))
    theta = math.acos(cosang)                   # iç açı
    if theta < math.radians(0.5) or theta > math.radians(179.5):
        return None, "Köşe yuvarlanamaz (parçalar teğet ya da geri dönüyor)"

    def side_n(P, t):
        v = np.cross(nrm_, bez_deriv(P, t))
        L = float(np.linalg.norm(v))
        return v / L if L > 1e-15 else v

    sa_ = 1.0 if float(np.dot(side_n(PA, 1.0), tb)) > 0 else -1.0
    sb_ = 1.0 if float(np.dot(side_n(PB, 0.0), -ta)) > 0 else -1.0
    dl = r / math.tan(theta / 2.0)
    LA, LB = seg_length(A), seg_length(B)
    if dl >= LA - 1e-12 or dl >= LB - 1e-12:
        return None, "Yarıçap bu köşe için çok büyük"
    s, t = 1.0 - dl / LA, dl / LB
    for _ in range(40):
        F = (bez_point(PA, s) + side_n(PA, s) * r * sa_) - (bez_point(PB, t) + side_n(PB, t) * r * sb_)
        h = 1e-6
        dFs = ((bez_point(PA, s + h) + side_n(PA, s + h) * r * sa_) -
               (bez_point(PA, s - h) + side_n(PA, s - h) * r * sa_)) / (2 * h)
        dFt = -((bez_point(PB, t + h) + side_n(PB, t + h) * r * sb_) -
                (bez_point(PB, t - h) + side_n(PB, t - h) * r * sb_)) / (2 * h)
        J = np.stack([dFs, dFt], axis=1)
        step = np.linalg.lstsq(J, -F, rcond=None)[0]
        s, t = s + float(step[0]), t + float(step[1])
        if abs(step[0]) + abs(step[1]) < 1e-12:
            break
    if not (0.0 < s < 1.0 and 0.0 < t < 1.0):
        return None, "Yarıçap bu köşe için çok büyük"
    C = bez_point(PA, s) + side_n(PA, s) * r * sa_
    TA, TB = bez_point(PA, s), bez_point(PB, t)
    if abs(float(np.linalg.norm(TB - C)) - r) > 1e-5 * (1.0 + r):
        return None, "Yuvarlama yayı bulunamadı"
    arc = dm.center_arc(C, TA, TB, nrm_)
    if arc is None or float(np.dot(dm.start_tangent(arc["segs"][0]), seg_tangent(A, s))) < \
            math.cos(math.radians(2.0)):
        return None, "Yuvarlama yayı bulunamadı"
    g = new_grp()
    mids = []
    for sg in arc["segs"]:
        sg["grp"] = g
        sg["_mod"] = True
        mids.append(sg)
    return {"a": seg_sub(A, 0.0, s), "mids": mids, "b": seg_sub(B, t, 1.0), "ia": ia,
            "ib": ib, "center": C, "radius": r}, ""


def chamfer_at(st, j, d1, d2=None):
    """j. düğümde pah: önceki parçada d1, sonrakinde d2 (yoksa d1) yay boyu."""
    d2 = d1 if d2 is None else d2
    segs = st["segs"]
    n = len(segs)
    ia, ib = (j - 1) % n, j % n
    A, B = segs[ia], segs[ib]
    s = _arc_len_param(A, d1, True)
    t = _arc_len_param(B, d2, False)
    if s is None or t is None:
        return None, "Pah mesafesi bu köşe için çok büyük"
    a, b = seg_sub(A, 0.0, s), seg_sub(B, t, 1.0)
    mid = dm.line_seg(a["p"][3], b["p"][0])
    mid["grp"] = new_grp()
    mid["_mod"] = True
    return {"a": a, "mids": [mid], "b": b, "ia": ia, "ib": ib}, ""


def apply_corner(sketch, k, j, res):
    """fillet_at / chamfer_at sonucunu çizgiye uygular (yeni taslak listesi)."""
    st = _tag(sketch[k])
    segs = st["segs"]
    n = len(segs)
    ia, ib = res["ia"], res["ib"]
    a, b = dict(res["a"]), dict(res["b"])
    a["_oid"], b["_oid"] = ia, ib
    mids = [dict(m) for m in res["mids"]]
    if st["cyclic"] and ib == 0:
        new = [b] + [dict(s) for s in segs[1:n - 1]] + [a] + mids   # kapalı: b … a, yay
        out = _stroke(new, True)
    else:
        new = segs[:ia] + [a] + mids + [b] + segs[ib + 1:]
        out = _stroke(new, st["cyclic"])
    return replace(sketch, k, _carry(st, [out]))


def join_ends(sketch, k1, e1, k2, e2):
    """İki açık çizgiyi çakışan uçlarından birleştirir: k1 çizgisinin e1 ucu (0/1),
    k2 çizgisinin e2 ucuna. (yeni taslak, birleşik çizgi sırası, köşe düğümü)."""
    s1, s2 = _tag(sketch[k1]), copy.deepcopy(sketch[k2])
    for sg in s2["segs"]:
        sg["_oid"] = None
    a = s1 if e1 == 1 else reverse_stroke(s1)
    b = s2 if e2 == 0 else reverse_stroke(s2)
    segs = [dict(s) for s in a["segs"]] + [dict(s) for s in b["segs"]]
    j = len(a["segs"])
    new = _stroke(segs, False)
    new["node_ids"] = {}
    rest = [s for i, s in enumerate(sketch) if i not in (k1, k2)]
    lo = min(k1, k2)
    _carry(s1, [new])
    out = [copy.deepcopy(s) for s in rest[:lo]] + [new] + [copy.deepcopy(s) for s in rest[lo:]]
    return fix_sketch_refs(out), lo, j


# ================================================================ dönüşümler (Aşama 2)
# Taşı / Kopyala / Döndür / Ölçekle / Ayna / Esnet / Dikdörtgen ve dairesel desen.
# Dönüşümler noktaya uygulanan fonksiyonlardır (benzerlik dönüşümleri: doğru doğru,
# yay yay kalır).

def T_move(d):
    d = np.asarray(d, dtype=np.float64)
    return lambda p: np.asarray(p, dtype=np.float64) + d


def T_rotate(c, n, ang):
    """c'den geçen n ekseni etrafında ang radyan (sağ el kuralı)."""
    c = np.asarray(c, dtype=np.float64)
    k = dm.unit(n)
    ca, sa = math.cos(ang), math.sin(ang)

    def f(p):
        v = np.asarray(p, dtype=np.float64) - c
        return c + v * ca + np.cross(k, v) * sa + k * float(np.dot(k, v)) * (1.0 - ca)
    return f


def T_scale(c, s):
    c = np.asarray(c, dtype=np.float64)
    return lambda p: c + (np.asarray(p, dtype=np.float64) - c) * s


def T_mirror(p1, p2, n):
    """Düzlem normali n olan çizim düzleminde p1-p2 doğrusuna göre ayna."""
    p1 = np.asarray(p1, dtype=np.float64)
    m = dm.unit(np.cross(np.asarray(p2, dtype=np.float64) - p1, np.asarray(n, dtype=np.float64)))
    if m is None:
        return None

    def f(p):
        p = np.asarray(p, dtype=np.float64)
        return p - 2.0 * float(np.dot(p - p1, m)) * m
    return f


def xform_stroke(st, f, copy_=False):
    """Çizginin bütün kontrol noktalarına f uygulanmış yeni çizgi. Kopyada gruplar yenilenir.
    Konumu değişen çizginin dış bağlantıları (çakışık / teğet başlangıç) düşer."""
    gmap = {}
    segs = []
    for sg in st["segs"]:
        new = {k: v for k, v in sg.items() if k not in ("p", "tan_start")}
        new["p"] = tuple(f(q) for q in sg["p"])
        new["auto"] = list(sg.get("auto", ()))   # geçersiz kalanları Bitir ayıklar (satisfied)
        if copy_:
            g = sg.get("grp")
            new["grp"] = gmap.setdefault(g, new_grp()) if g is not None else None
        segs.append(new)
    out = {"segs": segs, "cyclic": st["cyclic"], "node_ids": {}, "start_tan": None}
    if not copy_ and st.get("edit_src"):        # taslağa alınmış eğri: kaynağı korunur
        out["edit_src"] = st["edit_src"]
    return out


def apply_xform(sketch, ks, f, copy_=False):
    """ks çizgilerine f'yi uygular (copy_: kopyalar sona eklenir). Yeni taslak listesi."""
    out = [copy.deepcopy(s) for s in sketch]
    ks = [k for k in sorted(set(ks)) if 0 <= k < len(sketch)]
    if copy_:
        out += [xform_stroke(sketch[k], f, True) for k in ks]
    else:
        for k in ks:
            out[k] = xform_stroke(sketch[k], f, False)
    return fix_sketch_refs(out)


def apply_many(sketch, ks, fns):
    """Desen: her dönüşüm için seçili çizgilerin bir kopyası sona eklenir."""
    out = [copy.deepcopy(s) for s in sketch]
    ks = [k for k in sorted(set(ks)) if 0 <= k < len(sketch)]
    for f in fns:
        out += [xform_stroke(sketch[k], f, True) for k in ks]
    return fix_sketch_refs(out)


def rect_pattern(d1, n1, d2=None, n2=1):
    """Dikdörtgen desen ötelemeleri (özdeşlik hariç). d1 / d2: bir adımlık vektörler."""
    d1 = np.asarray(d1, dtype=np.float64)
    d2 = np.zeros(3) if d2 is None else np.asarray(d2, dtype=np.float64)
    fns = []
    for i in range(max(1, int(n1))):
        for j in range(max(1, int(n2))):
            if i == 0 and j == 0:
                continue
            fns.append(T_move(d1 * i + d2 * j))
    return fns


def circ_pattern(c, n, count, total_deg=360.0):
    """Dairesel desen dönmeleri (özdeşlik hariç). Tam turda eşit bölünür."""
    count = max(1, int(count))
    if count < 2:
        return []
    full = abs(abs(total_deg) - 360.0) < 1e-9
    step = math.radians(total_deg) / (count if full else count - 1)
    return [T_rotate(c, n, step * i) for i in range(1, count)]


def stroke_nodes(st):
    segs = st["segs"]
    n = len(segs)
    out = [_P(segs[j])[0] for j in range(n)]
    if not st["cyclic"] and n:
        out.append(_P(segs[-1])[3])
    return out


def _move_node(segs, j, new, cyclic):
    """j. düğümü taşır: doğrular düz kalır, eğrilerde bağlı tutamaç da kayar."""
    n = len(segs)
    touch = []
    if j < n:
        touch.append((j, 0))
    if j > 0:
        touch.append((j - 1, 3))
    elif cyclic:
        touch.append((n - 1, 3))
    for k, end in touch:
        sg = segs[k]
        P = list(_P(sg))
        delta = np.asarray(new, dtype=np.float64) - P[end]
        P[end] = np.asarray(new, dtype=np.float64)
        if sg["kind"] != "line":
            h = 1 if end == 0 else 2
            P[h] = P[h] + delta
            sg["p"] = tuple(P)
        else:
            sg["p"] = dm.line_seg(P[0], P[3])["p"]


def stretch(sketch, nodes, d):
    """Esnet: seçili düğümler (çizgi, düğüm) d kadar taşınır; bağlı parçalar esner.
    Bir çizginin bütün düğümleri seçiliyse çizgi olduğu gibi taşınır."""
    d = np.asarray(d, dtype=np.float64)
    out = [copy.deepcopy(s) for s in sketch]
    by = {}
    for k, j in nodes:
        if 0 <= k < len(out):
            by.setdefault(k, set()).add(j)
    for k, js in by.items():
        st = out[k]
        pos = stroke_nodes(st)
        if len(js) >= len(pos):
            out[k] = xform_stroke(st, T_move(d))
            continue
        for j in sorted(js):
            if 0 <= j < len(pos):
                _move_node(st["segs"], j, pos[j] + d, st["cyclic"])
        for sg in st["segs"]:
            sg["auto"] = [a for a in sg.get("auto", ()) if a[0] != "DIST"]
        st["node_ids"] = {}
        st["start_tan"] = None
    return fix_sketch_refs(out)


# ================================================================ ayrı iki doğrunun köşesi

def lines_corner(sketch, pa, pb):
    """İki ayrı çizginin doğrularını (tıklanan parçalar korunarak) kesişim noktasına uzatıp /
    kırpıp birleştirir; köşe yuvarlama / pah için. pa, pb: (çizgi, segment, tık parametresi).
    (yeni taslak, birleşik çizgi, köşe düğümü) ya da (None, sebep, None)."""
    (ka, ia, ta), (kb, ib, tb) = pa, pb
    if ka == kb:
        return None, "iki ayrı çizgi seç (aynı çizginin köşesine doğrudan tıkla)", None
    A, B = sketch[ka], sketch[kb]
    if A["cyclic"] or B["cyclic"]:
        return None, "kapalı çizgide köşeye doğrudan tıkla", None
    sa, sb = A["segs"][ia], B["segs"][ib]
    if sa["kind"] != "line" or sb["kind"] != "line":
        return None, "iki doğru seç", None
    Pa, Pb = _P(sa), _P(sb)
    pl = fit_plane(Pa + Pb)
    if pl is None:
        return None, "doğrular aynı düzlemde değil", None
    da, db = dm.unit(Pa[3] - Pa[0]), dm.unit(Pb[3] - Pb[0])
    X = _line_isect(Pa[0], da, Pb[0], db, pl[1])
    if X is None:
        return None, "doğrular paralel", None
    out = [copy.deepcopy(s) for s in sketch]
    ends = []
    for k, i, t, P in ((ka, ia, ta, Pa), (kb, ib, tb, Pb)):
        st = out[k]
        n = len(st["segs"])
        L = float(np.linalg.norm(P[3] - P[0]))
        tx = float(np.dot(X - P[0], P[3] - P[0])) / (L * L)
        if n == 1:
            end = 1 if t < tx else 0
        elif i == n - 1:
            end = 1
        elif i == 0:
            end = 0
        else:
            return None, "doğru çizginin ucunda olmalı", None
        a, b = (P[0], X) if end == 1 else (X, P[3])
        if float(np.linalg.norm(b - a)) <= 1e-9 * (1.0 + L):
            return None, "kesişim doğrunun ucunda: köşeye doğrudan tıkla", None
        sg = st["segs"][i]
        sg["p"] = dm.line_seg(a, b)["p"]
        sg["auto"] = [x for x in sg.get("auto", ()) if x[0] != "DIST"]
        if end == 1:
            st["node_ids"] = {kk: v for kk, v in st.get("node_ids", {}).items() if kk != n}
        else:
            st["node_ids"] = {kk: v for kk, v in st.get("node_ids", {}).items() if kk != 0}
            st["start_tan"] = None
        ends.append(end)
    new, k, j = join_ends(out, ka, ends[0], kb, ends[1])
    return new, k, j
