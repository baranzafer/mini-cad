"""Çizim şekilleri (bpy'siz, başsız test edilebilir) — Inventor 2D Oluştur araçları:

  Dikdörtgen: 3 noktalı, merkezden (2 nokta), 3 noktalı merkezden
  Çokgen (iç / dış teğet), Kanal (slot): merkezden merkeze, toplam boy, merkez noktalı,
  3 noktalı yay kanal; Elips; üç doğruya teğet daire; geometri yansıtma (düzleme izdüşüm).

Bütün fonksiyonlar dünya koordinatında nokta alır ve bir çalışma düzlemi (drawmath.Plane)
kullanır. Kapalı şekiller [seg] listesi döndürür (son nokta ilk noktaya eşit).
"""

import math

import numpy as np

from . import drawmath as dm


def _a(p):
    return np.asarray(p, dtype=np.float64)


def _on(pl, p, h):
    """Düzlem koordinatından (u, v) dünya noktası, h yüksekliğinde."""
    return pl.xyz(p) + pl.n * h


def _close(segs):
    if segs:
        segs[-1]["p"] = tuple(segs[-1]["p"][:3]) + (segs[0]["p"][0],)
    return segs


def polyline_closed(pts):
    """Kapalı doğru zinciri (her doğru ayrı nesne)."""
    segs = [dm.line_seg(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
    return _close(segs)


# ================================================================ dikdörtgenler

def rect_from_corners(c0, c1, c2, c3):
    return polyline_closed([_a(c0), _a(c1), _a(c2), _a(c3)])


def rect3(p1, p2, p3, pl):
    """3 noktalı: p1-p2 bir kenar, p3 genişliği (kenara dik uzaklık) verir."""
    p1, p2, p3 = _a(p1), _a(p2), _a(p3)
    e = p2 - p1
    e = e - pl.n * float(np.dot(e, pl.n))
    L = float(np.linalg.norm(e))
    if L < 1e-12:
        return None
    eu = e / L
    w = p3 - p2
    w = w - pl.n * float(np.dot(w, pl.n))
    w = w - eu * float(np.dot(w, eu))
    if float(np.linalg.norm(w)) < 1e-12:
        return None
    return rect_from_corners(p1, p2, p2 + w, p1 + w)


def rect_center(c, q, pl):
    """İki noktalı merkezden: merkez ve bir köşe (düzlem eksenlerine hizalı)."""
    c, q = _a(c), _a(q)
    a, b = pl.uv(c), pl.uv(q)
    du, dv = b[0] - a[0], b[1] - a[1]
    if abs(du) < 1e-12 or abs(dv) < 1e-12:
        return None
    h = pl.dist(c)
    pts = [(a[0] - du, a[1] - dv), (a[0] + du, a[1] - dv), (a[0] + du, a[1] + dv),
           (a[0] - du, a[1] + dv)]
    return rect_from_corners(*[_on(pl, p, h) for p in pts])


def rect3_center(c, m, q, pl):
    """3 noktalı merkezden: merkez, bir kenar ortası (yön + yarım boy), bir köşe (yarım en)."""
    c, m, q = _a(c), _a(m), _a(q)
    e = m - c
    e = e - pl.n * float(np.dot(e, pl.n))
    if float(np.linalg.norm(e)) < 1e-12:
        return None
    eu = dm.unit(e)
    w = q - c
    w = w - pl.n * float(np.dot(w, pl.n))
    w = w - eu * float(np.dot(w, eu))
    if float(np.linalg.norm(w)) < 1e-12:
        return None
    return rect_from_corners(c - e - w, c + e - w, c + e + w, c - e + w)


# ================================================================ çokgen

def polygon(c, q, n_sides, pl, inscribed=True):
    """Merkez c, imleç q: iç teğette q bir köşe, dış teğette q bir kenar ortası."""
    c, q = _a(c), _a(q)
    n_sides = max(3, int(n_sides))
    v = q - c
    v = v - pl.n * float(np.dot(v, pl.n))
    r = float(np.linalg.norm(v))
    if r < 1e-12:
        return None
    e1 = v / r
    e2 = np.cross(pl.n, e1)
    step = 2 * math.pi / n_sides
    if inscribed:
        R, a0 = r, 0.0
    else:
        R, a0 = r / math.cos(step / 2), step / 2
    pts = [c + R * (math.cos(a0 + k * step) * e1 + math.sin(a0 + k * step) * e2)
           for k in range(n_sides)]
    return polyline_closed(pts)


# ================================================================ kanallar (slot)

def _arc(c, p0, p1, n, ccw_ref=None):
    """c merkezli, p0'dan p1'e n etrafında pozitif yönde yay segmentleri."""
    c, p0, p1 = _a(c), _a(p0), _a(p1)
    v0 = p0 - c
    R = float(np.linalg.norm(v0))
    e1 = v0 / R
    e2 = np.cross(n, e1)
    v1 = p1 - c
    t = math.atan2(float(np.dot(v1, e2)), float(np.dot(v1, e1)))
    if t <= 1e-12:
        t += 2 * math.pi
    return dm._arc_from_basis(c, R, e1, e2, t, p0, p1)


def slot_cc(c1, c2, r, pl):
    """Merkezden merkeze kanal: iki yay merkezi, yarım genişlik r."""
    c1, c2 = _a(c1), _a(c2)
    d = c2 - c1
    d = d - pl.n * float(np.dot(d, pl.n))
    L = float(np.linalg.norm(d))
    if L < 1e-12 or r < 1e-12:
        return None
    t = d / L
    nr = np.cross(pl.n, t)                     # sol taraf
    a0, a1 = c1 - nr * r, c2 - nr * r
    b1, b0 = c2 + nr * r, c1 + nr * r
    segs = [dm.line_seg(a0, a1)]
    segs += _arc(c2, a1, b1, pl.n)
    segs += [dm.line_seg(b1, b0)]
    segs += _arc(c1, b0, a0, pl.n)
    return _close(segs)


def slot_overall(e1, e2, r, pl):
    """Toplam boy kanalı: e1-e2 kanalın uçları (yay dışları)."""
    e1, e2 = _a(e1), _a(e2)
    d = e2 - e1
    d = d - pl.n * float(np.dot(d, pl.n))
    L = float(np.linalg.norm(d))
    if L <= 2 * r + 1e-12:
        return None
    t = d / L
    return slot_cc(e1 + t * r, e2 - t * r, r, pl)


def slot_center(c, c2, r, pl):
    """Merkez noktalı kanal: kanal merkezi c, bir yay merkezi c2."""
    c, c2 = _a(c), _a(c2)
    return slot_cc(2 * c - c2, c2, r, pl)


def width_of(p_a, p_b, q, pl):
    """q'nun p_a-p_b doğrusuna düzlemdeki dik uzaklığı (yarım genişlik)."""
    d = _a(p_b) - _a(p_a)
    d = d - pl.n * float(np.dot(d, pl.n))
    t = dm.unit(d)
    if t is None:
        return 0.0
    w = _a(q) - _a(p_a)
    w = w - pl.n * float(np.dot(w, pl.n))
    return float(np.linalg.norm(w - t * float(np.dot(w, t))))


def arc_slot(p0, p1, pm, r, pl):
    """3 noktalı yay kanal: merkez çizgisi p0 → p1, pm'den geçen yay; yarım genişlik r."""
    arc = dm.arc_3pt(p0, pm, p1)
    if arc is None:
        return None
    c, R = arc["center"], arc["radius"]
    if r >= R - 1e-12 or r < 1e-12:
        return None
    p0, p1 = _a(p0), _a(p1)
    n = dm.unit(np.cross(p0 - c, dm.start_tangent(arc["segs"][0])))
    u0, u1 = (p0 - c) / R, (p1 - c) / R
    o0, o1 = c + u0 * (R + r), c + u1 * (R + r)
    i0, i1 = c + u0 * (R - r), c + u1 * (R - r)
    segs = _arc(c, o0, o1, n)                  # dış yay
    segs += _arc(p1, o1, i1, n)                # uç kapak
    segs += _arc(c, i1, i0, -n)                # iç yay (geri)
    segs += _arc(p0, i0, o0, n)                # baş kapak
    return _close(segs)


# ================================================================ elips

def ellipse(c, a_end, q, pl):
    """Merkez c, 1. eksen ucu a_end, q: 2. yarı eksen (1. eksene dik uzaklık)."""
    c, a_end, q = _a(c), _a(a_end), _a(q)
    a = a_end - c
    a = a - pl.n * float(np.dot(a, pl.n))
    A = float(np.linalg.norm(a))
    if A < 1e-12:
        return None
    au = a / A
    bu = np.cross(pl.n, au)
    B = abs(float(np.dot(q - c, bu)))
    if B < 1e-12:
        return None
    k = 4.0 / 3.0 * math.tan(math.pi / 8.0)
    segs = []
    for j in range(4):
        t0, t1 = j * math.pi / 2, (j + 1) * math.pi / 2

        def P(t):
            return c + au * A * math.cos(t) + bu * B * math.sin(t)

        def T(t):
            return -au * A * math.sin(t) + bu * B * math.cos(t)
        p0, p3 = P(t0), P(t1)
        segs.append({"kind": "curve", "p": (p0, p0 + T(t0) * k, p3 - T(t1) * k, p3)})
    return _close(segs)


# ================================================================ teğet daire (3 doğru)

def tangent_circle_3lines(lines, pl, hint=None):
    """Üç doğruya teğet daire (doğruların oluşturduğu üçgenin iç teğet dairesi; hint verilirse
    ona en yakın çözüm). lines: [(a, b)] dünya noktaları. (merkez, yarıçap) ya da None."""
    L = []
    for a, b in lines:
        ua, ub = np.array(pl.uv(a)), np.array(pl.uv(b))
        d = ub - ua
        n = float(np.linalg.norm(d))
        if n < 1e-12:
            return None
        nr = np.array([-d[1], d[0]]) / n
        L.append((nr, float(np.dot(nr, ua)), ua))
    sols = []
    for s in ((1, 1, 1), (1, 1, -1), (1, -1, 1), (-1, 1, 1),
              (1, -1, -1), (-1, 1, -1), (-1, -1, 1), (-1, -1, -1)):
        M = np.array([[L[i][0][0], L[i][0][1], -s[i]] for i in range(3)])
        rhs = np.array([L[i][1] for i in range(3)])
        try:
            x = np.linalg.solve(M, rhs)
        except np.linalg.LinAlgError:
            continue
        if x[2] > 1e-12:
            sols.append(x)
    if not sols:
        return None
    if hint is not None:
        hu = np.array(pl.uv(hint))
        x = min(sols, key=lambda v: float(np.linalg.norm(v[:2] - hu)))
    else:
        # iç teğet: merkez üç doğrunun kesişim noktalarının oluşturduğu üçgenin içinde
        pts = []
        for i in range(3):
            n1, d1, _ = L[i]
            n2, d2, _ = L[(i + 1) % 3]
            M = np.array([n1, n2])
            try:
                pts.append(np.linalg.solve(M, np.array([d1, d2])))
            except np.linalg.LinAlgError:
                pass
        g = np.mean(pts, axis=0) if pts else np.mean([l[2] for l in L], axis=0)
        x = min(sols, key=lambda v: float(np.linalg.norm(v[:2] - g)))
    h = pl.dist(lines[0][0])
    return _on(pl, (x[0], x[1]), h), float(x[2])


# ================================================================ geometri yansıtma

def project_poly(P, pl):
    """Çoklu çizgiyi düzleme dik izdüşürür."""
    P = np.asarray(P, dtype=np.float64)
    return P - np.outer((P - pl.o) @ pl.n, pl.n)


def project_bezier(P, pl):
    """Kübik bezier'in düzleme izdüşümü (afin: kontrol noktaları izdüşer, tam)."""
    return tuple(project_poly(np.array([_a(q) for q in P]), pl))


def segs_from_poly(P, closed=False):
    """İzdüşmüş çoklu çizgiden segmentler: doğru, çember / yay, değilse noktalardan spline."""
    P = np.asarray(P, dtype=np.float64)
    if len(P) < 2:
        return None, False
    if closed and np.linalg.norm(P[0] - P[-1]) > 1e-9 * (1.0 + float(np.abs(P).max())):
        P = np.vstack([P, P[:1]])
    size = float(np.linalg.norm(P.max(axis=0) - P.min(axis=0)))
    if size < 1e-12:
        return None, False
    if dm.is_straight_poly(P):
        return [dm.line_seg(P[0], P[-1])], False
    is_closed = float(np.linalg.norm(P[0] - P[-1])) <= 1e-7 * (1.0 + size)
    c = dm.circle_center(P) if is_closed else None
    if c is not None:
        R = float(np.mean(np.linalg.norm(P[:-1] - c, axis=1)))
        n = dm.unit(np.cross(P[len(P) // 4] - c, P[len(P) // 2] - c))
        if n is not None:
            e1 = (P[0] - c) / R
            e2 = np.cross(n, e1)
            if float(np.dot(P[1] - P[0], e2)) < 0:
                e2 = -e2
            segs = dm._arc_from_basis(c, R, e1, e2, 2 * math.pi)
            return _close(segs), True
    if not is_closed and len(P) >= 3:
        arc = dm.arc_3pt(P[0], P[len(P) // 2], P[-1])
        if arc is not None:
            dev = np.abs(np.linalg.norm(P - arc["center"], axis=1) - arc["radius"]).max()
            if dev <= 1e-3 * arc["radius"]:
                return arc["segs"], False
    idx = np.unique(np.linspace(0, len(P) - 1, min(len(P), 9)).round().astype(int))
    Q = P[idx]
    if is_closed:
        Q = Q[:-1]
        segs = dm.fit_bezier(list(Q) + [Q[0]])
        return _close(segs), True
    return dm.fit_bezier(list(Q)), False


def arc_slot_center(c, p0, p_end, r, pl, flip=False):
    """Merkez noktalı yay kanal: yay merkezi c, başlangıç p0, bitiş yönü p_end."""
    arc = dm.center_arc(c, p0, p_end, pl.n, flip)
    if arc is None:
        return None
    segs = arc["segs"]
    k = len(segs)
    pm = segs[k // 2]["p"][0] if k % 2 == 0 else \
        dm.sample(segs[k // 2], 3)[1]
    return arc_slot(p0, arc["end"], pm, r, pl)
