"""Çizim aracının bpy'siz matematiği: çalışma düzlemi, teğet yay, bezier noktaları,
sezgisel yakalama (çıkarım) ve uzunluk/açı hesapları. Başsız test edilebilir."""

import math

import numpy as np

from . import snapmath

AXIS_PLANES = {
    # ad: (u ekseni, v ekseni) — normal = u × v
    "XY": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)),
    "XZ": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)),
    "YZ": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
}
PLANE_LABELS = {"LOCK": "Seçili düzlem", "XY": "Üst (XY)", "XZ": "Ön (XZ)", "YZ": "Yan (YZ)", "VIEW": "Görünüş",
                "FACE": "Yüz"}

KIND_LABELS = {"H": "Yatay", "V": "Dikey", "parallel": "Paralel", "perpendicular": "Dik",
               "prev_par": "Doğrusal", "prev_perp": "Dik (önceki)"}


def unit(v):
    v = np.asarray(v, dtype=np.float64)
    n = float(np.linalg.norm(v))
    return None if n < 1e-12 else v / n


class Plane:
    """Çalışma düzlemi: köken + (u, v) eksenleri, normal = u × v."""

    def __init__(self, origin, u, v, name):
        self.o = np.asarray(origin, dtype=np.float64)
        self.u = unit(u)
        vv = np.asarray(v, dtype=np.float64)
        vv = vv - np.dot(vv, self.u) * self.u        # dikleştir
        self.v = unit(vv)
        self.n = np.cross(self.u, self.v)
        self.name = name

    @classmethod
    def axis(cls, name, origin):
        u, v = AXIS_PLANES[name]
        return cls(origin, u, v, name)

    @classmethod
    def from_normal(cls, origin, normal, name, u_hint=None):
        n = unit(normal)
        if u_hint is not None:
            u = np.asarray(u_hint, dtype=np.float64)
            u = u - np.dot(u, n) * n
            u = unit(u)
        else:
            u = None
        if u is None:
            for ref in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)):
                r = np.asarray(ref)
                u = unit(r - np.dot(r, n) * n)
                if u is not None and abs(np.dot(r, n)) < 0.95:
                    break
        v = np.cross(n, u)
        return cls(origin, u, v, name)

    def moved(self, origin):
        return Plane(origin, self.u, self.v, self.name)

    def uv(self, p):
        d = np.asarray(p, dtype=np.float64) - self.o
        return (float(np.dot(d, self.u)), float(np.dot(d, self.v)))

    def xyz(self, uv):
        return self.o + self.u * uv[0] + self.v * uv[1]

    def dist(self, p):
        return float(np.dot(np.asarray(p, dtype=np.float64) - self.o, self.n))

    def ray_hit(self, origin, direction):
        d = np.asarray(direction, dtype=np.float64)
        den = float(np.dot(d, self.n))
        if abs(den) < 1e-9:
            return None
        t = float(np.dot(self.o - np.asarray(origin, dtype=np.float64), self.n)) / den
        return np.asarray(origin, dtype=np.float64) + d * t


def auto_axis_plane(view_dir):
    """Bakış yönüne en çok dönük eksen düzlemi."""
    d = np.abs(np.asarray(view_dir, dtype=np.float64))
    return ("YZ", "XZ", "XY")[int(np.argmax(d))]


# ---------------------------------------------------------------- segmentler

def line_seg(a, b):
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    return {"kind": "line", "p": (a, a + (b - a) / 3.0, a + (b - a) * (2.0 / 3.0), b)}


def tangent_arc(p0, t0, p1, max_angle=math.pi / 2):
    """p0'da t0 yönüne teğet başlayıp p1'den geçen çember yayı (3D'de, t0 ile p0→p1'in
    belirlediği düzlemde). Kübik bezier parçaları listesi ya da düz/belirsizse None."""
    p0, p1 = np.asarray(p0, dtype=np.float64), np.asarray(p1, dtype=np.float64)
    t0 = unit(t0)
    if t0 is None:
        return None
    c = p1 - p0
    L = float(np.linalg.norm(c))
    if L < 1e-12:
        return None
    x = float(np.dot(c, t0))
    cp = c - x * t0
    y = float(np.linalg.norm(cp))
    if y < 1e-6 * L:
        return None                   # teğet doğrultusunda: düz çizgi (ya da tam geri)
    e2 = cp / y
    R = (x * x + y * y) / (2.0 * y)
    theta = 2.0 * math.atan2(y, x)    # toplam dönüş (0..2π)
    center = p0 + e2 * R
    k = max(1, int(math.ceil(theta / max_angle - 1e-9)))
    phi = theta / k
    h = 4.0 / 3.0 * math.tan(phi / 4.0) * R

    def P(a):
        return center + R * (math.sin(a) * t0 - math.cos(a) * e2)

    def T(a):
        return math.cos(a) * t0 + math.sin(a) * e2

    segs = []
    for j in range(k):
        a0, a1 = j * phi, (j + 1) * phi
        A = p0 if j == 0 else P(a0)
        B = p1 if j == k - 1 else P(a1)
        segs.append({"kind": "arc", "p": (A, A + T(a0) * h, B - T(a1) * h, B)})
    return {"segs": segs, "radius": R, "angle": theta, "center": center,
            "end_tangent": T(theta)}


def end_tangent(seg):
    p = seg["p"]
    t = unit(p[3] - p[2])
    return t if t is not None else unit(p[3] - p[0])


def start_tangent(seg):
    p = seg["p"]
    t = unit(p[1] - p[0])
    return t if t is not None else unit(p[3] - p[0])


def bezier_points(segs, cyclic):
    """Ardışık segmentlerden Blender bezier noktaları:
    [{"co", "hl", "hr", "tl", "tr"}]. Doğru tarafı VECTOR (düzenlenince de düz kalır),
    yay tarafı teğet birleşimde ALIGNED, değilse FREE."""
    n = len(segs)
    m = n if cyclic else n + 1
    out = []
    for i in range(m):
        prev = segs[i - 1] if (i > 0 or cyclic) else None
        nxt = segs[i] if i < n else None
        co = nxt["p"][0] if nxt is not None else prev["p"][3]
        hl = prev["p"][2] if prev is not None else None
        hr = nxt["p"][1] if nxt is not None else None
        tl = tr = None
        if prev is not None:
            tl = "VECTOR" if prev["kind"] == "line" else "FREE"
        if nxt is not None:
            tr = "VECTOR" if nxt["kind"] == "line" else "FREE"
        if prev is not None and nxt is not None:
            a, b = end_tangent(prev), start_tangent(nxt)
            smooth = a is not None and b is not None and float(np.dot(a, b)) > math.cos(
                math.radians(0.5))
            if smooth:
                if tl == "FREE":
                    tl = "ALIGNED"
                if tr == "FREE":
                    tr = "ALIGNED"
        if hl is None:
            hl = co - (hr - co)
            tl = tr
        if hr is None:
            hr = co - (hl - co)
            tr = tl
        out.append({"co": co, "hl": hl, "hr": hr, "tl": tl, "tr": tr})
    return out


def sample(seg, n=16):
    p0, p1, p2, p3 = seg["p"]
    t = np.linspace(0.0, 1.0, n)[:, None]
    u = 1.0 - t
    return u ** 3 * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t ** 3 * p3


# ---------------------------------------------------------------- ölçüler

def seg_angle(plane, a, b):
    """a→b doğrultusunun düzlemdeki açısı (derece, u ekseninden saat yönü tersine)."""
    ua, va = plane.uv(a)
    ub, vb = plane.uv(b)
    return math.degrees(math.atan2(vb - va, ub - ua))


def apply_locks(plane, anchor, p, length=None, angle=None):
    """Yazılan uzunluk/açı kilitlerini uygular. anchor ve p dünya koordinatında."""
    a_uv = plane.uv(anchor)
    p_uv = plane.uv(p)
    d = np.array([p_uv[0] - a_uv[0], p_uv[1] - a_uv[1]])
    if angle is not None:
        dirv = np.array([math.cos(math.radians(angle)), math.sin(math.radians(angle))])
        if length is None:
            length = max(float(np.dot(d, dirv)), 0.0)
    else:
        if length is None:
            return p
        n = float(np.linalg.norm(d))
        if n < 1e-12:
            off = np.asarray(p, dtype=np.float64) - np.asarray(anchor, dtype=np.float64)
            dd = unit(off)
            if dd is None:
                return plane.xyz((a_uv[0] + length, a_uv[1]))
            return np.asarray(anchor, dtype=np.float64) + dd * length
        dirv = d / n
    q = (a_uv[0] + dirv[0] * length, a_uv[1] + dirv[1] * length)
    # anchor düzlemin dışındaysa (3D uç noktaya yapışılmış) yüksekliğini koru
    return plane.xyz(q) + plane.n * plane.dist(anchor)


# ---------------------------------------------------------------- çıkarım

def refine(anchor, p, ref_dirs, ref_pts, ref_segs, tol, tol_deg=3.0, shift=False,
           prev_dir=None):
    """Düzlem (u, v) koordinatlarında sezgisel yakalama (FORGE snap_math ile).
    anchor: önceki nokta ya da None. Döner: (uv, bilgi) — bilgi None ise yakalama yok.
    bilgi: {"kind": etiket, "guides": [(yön, ref uv)], "ref_seg": (a, b), "dir": (du, dv)}"""
    p = (float(p[0]), float(p[1]))
    if anchor is not None and shift:
        r = snapmath.angle_step_snap(anchor, p, (1.0, 0.0), 15.0)
        if r is not None:
            q, deg = r
            q = _project_on_dir(anchor, p, _dir(anchor, q), q)
            return q, {"kind": f"{deg:.0f}°", "dir": _dir(anchor, q)}
    if anchor is not None:
        cands = [(1.0, 0.0, "H", None), (0.0, 1.0, "V", None)]
        if prev_dir is not None:
            pd = prev_dir
            cands += [(pd[0], pd[1], "prev_par", None), (-pd[1], pd[0], "prev_perp", None)]
        cands += snapmath.expand_parallel_perp(ref_dirs)
        ds = snapmath.direction_snap(anchor, p, cands, tol_deg)
        if ds is not None:
            q, kind, tag, _ = ds
            d = _dir(anchor, q)
            q = _project_on_dir(anchor, p, d, q)      # imleç doğrultuya izdüşer (polar izleme)
            info = {"kind": KIND_LABELS.get(kind, kind), "dir": d}
            if tag is not None and kind in ("parallel", "perpendicular"):
                info["ref_seg"] = tag
            g = _dir_guide(anchor, d, q, ref_pts, tol)
            if g is not None:
                q, guide = g
                info["guides"] = [guide]
                info["kind"] += " + Hiza"
            return q, info
    q, guides = snapmath.hv_align_snap(p, ref_pts, tol, skip=anchor)
    if guides:
        return q, {"kind": "Hiza", "guides": [(k, ref) for k, _, ref in guides]}
    ext = snapmath.extension_snap(p, ref_segs, tol)
    if ext is not None:
        q, tag, seg = ext
        return q, {"kind": "Uzantı", "ref_seg": seg}
    return p, None


def _project_on_dir(anchor, p, d, fallback):
    if d is None:
        return fallback
    t = (p[0] - anchor[0]) * d[0] + (p[1] - anchor[1]) * d[1]
    if t <= 1e-12:
        return fallback
    return (anchor[0] + d[0] * t, anchor[1] + d[1] * t)


def _dir(a, b):
    d = unit((b[0] - a[0], b[1] - a[1]))
    return None if d is None else (float(d[0]), float(d[1]))


def _dir_guide(anchor, d, q, ref_pts, tol):
    """Yakalanan doğrultu üzerinde, bir hizalama kılavuzunun kesiştiği nokta (q'ya yakınsa)."""
    if d is None:
        return None
    best = None
    for ru, rv, tag in ref_pts:
        if abs(ru - anchor[0]) < 1e-12 and abs(rv - anchor[1]) < 1e-12:
            continue
        for kind, coord, comp in (("V", ru, 0), ("H", rv, 1)):
            if abs(d[comp]) < 0.2:
                continue
            t = (coord - anchor[comp]) / d[comp]
            if t <= 0:
                continue
            c = (anchor[0] + d[0] * t, anchor[1] + d[1] * t)
            e = math.hypot(c[0] - q[0], c[1] - q[1])
            if e <= tol and (best is None or e < best[0]):
                best = (e, c, (kind, (ru, rv)))
    if best is None:
        return None
    return best[1], best[2]


# ---------------------------------------------------------------- 3D yardımcılar

def closest_on_segment_to_ray(a, b, ro, rd):
    """[a,b] doğru parçasının fare ışınına (ro + s·rd) en yakın noktası."""
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    ro, rd = np.asarray(ro, dtype=np.float64), unit(rd)
    u = b - a
    w = a - ro
    A, B, C = float(np.dot(u, u)), float(np.dot(u, rd)), 1.0
    D, E = float(np.dot(u, w)), float(np.dot(rd, w))
    den = A * C - B * B
    if A < 1e-18:
        return a
    t = 0.0 if abs(den) < 1e-18 else (B * E - C * D) / den
    t = min(1.0, max(0.0, t))
    return a + u * t


def segment_intersection(a, b, c, d, tol):
    """İki 3D doğru parçasının kesişimi (aralarındaki boşluk tol'dan küçükse)."""
    a, b, c, d = (np.asarray(x, dtype=np.float64) for x in (a, b, c, d))
    u, v, w = b - a, d - c, a - c
    A, B, C = np.dot(u, u), np.dot(u, v), np.dot(v, v)
    D, E = np.dot(u, w), np.dot(v, w)
    den = A * C - B * B
    if A < 1e-18 or C < 1e-18 or abs(den) < 1e-14 * A * C:
        return None                    # paralel
    s = (B * E - C * D) / den
    t = (A * E - B * D) / den
    if not (-1e-6 <= s <= 1 + 1e-6 and -1e-6 <= t <= 1 + 1e-6):
        return None
    p, q = a + u * s, c + v * t
    if np.linalg.norm(p - q) > tol:
        return None
    if min(s, 1 - s) < 1e-6 and min(t, 1 - t) < 1e-6:
        return None                    # zaten ortak uç nokta
    return 0.5 * (p + q)


def poly_mid(P):
    """Çizgi üzerindeki yay uzunluğu ortası."""
    P = np.asarray(P, dtype=np.float64)
    L = np.linalg.norm(np.diff(P, axis=0), axis=1)
    tot = float(L.sum())
    if tot < 1e-12:
        return P[0]
    c = np.concatenate([[0.0], np.cumsum(L)])
    k = int(np.searchsorted(c, tot * 0.5)) - 1
    k = min(max(k, 0), len(L) - 1)
    t = (tot * 0.5 - c[k]) / max(L[k], 1e-18)
    return P[k] + (P[k + 1] - P[k]) * t


def circle_center(P):
    """Kapalı ve çembere yakın bir çizginin merkezi (değilse None)."""
    P = np.asarray(P, dtype=np.float64)
    if len(P) < 8 or np.linalg.norm(P[0] - P[-1]) > 1e-6 * (1 + np.abs(P).max()):
        return None
    c = P[:-1].mean(axis=0)
    r = np.linalg.norm(P[:-1] - c, axis=1)
    if r.mean() < 1e-9 or r.std() > 0.01 * r.mean():
        return None
    return c


def arc_of_bezier(P):
    """Kübik bezier bir çember yayıysa (merkez, yarıçap, normal), değilse None."""
    P = [np.asarray(p, dtype=np.float64) for p in P]
    if len(P) != 4:
        return None

    def B(t):
        u = 1.0 - t
        return u ** 3 * P[0] + 3 * u * u * t * P[1] + 3 * u * t * t * P[2] + t ** 3 * P[3]

    a, m, b = B(0.0), B(0.5), B(1.0)
    v1, v2 = m - a, b - a
    n = np.cross(v1, v2)
    nn = float(np.dot(n, n))
    L = float(np.linalg.norm(v2))
    if L < 1e-12 or nn < 1e-12 * L ** 4:
        return None
    c = a + (np.cross(n, v1) * float(np.dot(v2, v2)) + np.cross(v2, n) * float(np.dot(v1, v1))) \
        / (2.0 * nn)
    R = float(np.linalg.norm(a - c))
    for t in (0.2, 0.35, 0.65, 0.8):
        if abs(float(np.linalg.norm(B(t) - c)) - R) > 2e-3 * R:
            return None
    return c, R, n / math.sqrt(nn)


def is_straight_poly(P):
    P = np.asarray(P, dtype=np.float64)
    d = P[-1] - P[0]
    L = float(np.linalg.norm(d))
    if L < 1e-12:
        return False
    d /= L
    off = P - P[0]
    dev = np.linalg.norm(off - np.outer(off @ d, d), axis=1).max()
    return dev <= 1e-6 * L + 1e-9


# ---------------------------------------------------------------- yay / daire / spline

def _arc_from_basis(center, R, e1, e2, theta, p_start=None, p_end=None, max_angle=math.pi / 2):
    """center + R(cos a·e1 + sin a·e2), a ∈ [0, theta] → kübik bezier parçaları."""
    k = max(1, int(math.ceil(abs(theta) / max_angle - 1e-9)))
    phi = theta / k
    h = 4.0 / 3.0 * math.tan(phi / 4.0) * R

    def P(a):
        return center + R * (math.cos(a) * e1 + math.sin(a) * e2)

    def T(a):
        return -math.sin(a) * e1 + math.cos(a) * e2

    segs = []
    for j in range(k):
        a0, a1 = j * phi, (j + 1) * phi
        A = p_start if (j == 0 and p_start is not None) else P(a0)
        B = p_end if (j == k - 1 and p_end is not None) else P(a1)
        segs.append({"kind": "arc", "p": (A, A + T(a0) * h, B - T(a1) * h, B)})
    return segs


def arc_3pt(p0, pm, p1):
    """p0'dan başlayıp pm'den geçerek p1'de biten çember yayı. Noktalar doğrusalsa None."""
    p0, pm, p1 = (np.asarray(p, dtype=np.float64) for p in (p0, pm, p1))
    a, b = pm - p0, p1 - p0
    n = np.cross(a, b)
    nn = float(np.dot(n, n))
    if nn < 1e-18 * (float(np.dot(a, a)) * float(np.dot(b, b)) + 1e-30):
        return None
    c = p0 + (np.cross(n, a) * float(np.dot(b, b)) + np.cross(b, n) * float(np.dot(a, a))) \
        / (2.0 * nn)
    R = float(np.linalg.norm(p0 - c))
    e1 = (p0 - c) / R
    nu = n / math.sqrt(nn)
    e2 = np.cross(nu, e1)

    def ang(p):
        v = p - c
        t = math.atan2(float(np.dot(v, e2)), float(np.dot(v, e1)))
        return t % (2 * math.pi)

    tm, t1 = ang(pm), ang(p1)
    theta = t1 if tm <= t1 else t1 - 2 * math.pi
    if theta < 0:                        # öbür yönde git
        e2 = -e2
        theta = -theta
    return {"segs": _arc_from_basis(c, R, e1, e2, theta, p0, p1), "radius": R,
            "angle": theta, "center": c}


def center_arc(center, p0, p_end, normal, flip=False):
    """Merkez, başlangıç ve bitiş yönünden yay (bitiş noktası yarıçapa izdüşer).
    Varsayılan: kısa yay; flip=True öbür taraf."""
    c = np.asarray(center, dtype=np.float64)
    p0 = np.asarray(p0, dtype=np.float64)
    n = unit(normal)
    v0 = p0 - c
    v0 = v0 - np.dot(v0, n) * n
    R = float(np.linalg.norm(v0))
    if R < 1e-12:
        return None
    e1 = v0 / R
    e2 = np.cross(n, e1)
    v1 = np.asarray(p_end, dtype=np.float64) - c
    t = math.atan2(float(np.dot(v1, e2)), float(np.dot(v1, e1)))
    if abs(t) < 1e-9:
        return None
    if flip:
        t = t - 2 * math.pi if t > 0 else t + 2 * math.pi
    if t < 0:
        e2, t = -e2, -t
    pend = c + R * (math.cos(t) * e1 + math.sin(t) * e2)
    return {"segs": _arc_from_basis(c, R, e1, e2, t, p0, pend), "radius": R, "angle": t,
            "center": c, "end": pend}


def circle(center, R, plane):
    """Kapalı daire: 4 çeyrek bezier (düzlemin u ekseninden başlar)."""
    c = np.asarray(center, dtype=np.float64)
    segs = _arc_from_basis(c, R, plane.u, plane.v, 2 * math.pi)
    segs[-1]["p"] = segs[-1]["p"][:3] + (segs[0]["p"][0],)
    return segs


def rectangle(c0, c1, plane):
    """Düzlemde iki karşı köşeden dikdörtgen (4 doğru, kapalı)."""
    a = plane.uv(c0)
    b = plane.uv(c1)
    base = plane.dist(c0)
    pts = [plane.xyz(q) + plane.n * base for q in ((a[0], a[1]), (b[0], a[1]), (b[0], b[1]),
                                                   (a[0], b[1]))]
    return [line_seg(pts[i], pts[(i + 1) % 4]) for i in range(4)]


def _insert_knot(P, U, p, u):
    """Boehm algoritması: u düğümünü bir kez ekler."""
    k = int(np.searchsorted(U, u, side="right")) - 1
    Q = []
    for i in range(len(P) + 1):
        if i <= k - p:
            Q.append(P[i])
        elif i >= k + 1:
            Q.append(P[i - 1])
        else:
            a = (u - U[i]) / (U[i + p] - U[i])
            Q.append((1 - a) * P[i - 1] + a * P[i])
    return Q, np.insert(U, k + 1, u)


def bspline_bezier(cvs):
    """Kontrol noktalı (CV) kübik B-spline'ı (uçlardan geçen, düzgün düğümlü) kübik bezier
    parçalarına çevirir. 2 nokta: doğru; 3 nokta: ikinci dereceden (kübiğe yükseltilir)."""
    P = [np.asarray(p, dtype=np.float64) for p in cvs]
    if len(P) < 2:
        return []
    if len(P) == 2:
        return [line_seg(P[0], P[1])]
    if len(P) == 3:
        a, b, c = P
        return [{"kind": "curve", "p": (a, a + (b - a) * (2 / 3), c + (b - c) * (2 / 3), c)}]
    p = 3
    n = len(P) - 1
    inner = list(np.linspace(0.0, 1.0, n - p + 2)[1:-1])
    U = np.array([0.0] * (p + 1) + inner + [1.0] * (p + 1))
    Q = list(P)
    for u in inner:
        for _ in range(p - 1):           # her iç düğümün katlılığı p olsun
            Q, U = _insert_knot(Q, U, p, u)
    segs = []
    for i in range(0, len(Q) - 1, 3):
        a, b, c, d = Q[i], Q[i + 1], Q[i + 2], Q[i + 3]
        segs.append({"kind": "curve", "p": (a, b, c, d)})
    return segs


def fit_bezier(pts):
    """Noktalardan geçen pürüzsüz eğri (kiriş uzunluğuyla Catmull-Rom → bezier)."""
    P = [np.asarray(p, dtype=np.float64) for p in pts]
    if len(P) < 2:
        return []
    if len(P) == 2:
        return [line_seg(P[0], P[1])]
    n = len(P)
    T = []
    for i in range(n):
        if i == 0:
            t = P[1] - P[0]
        elif i == n - 1:
            t = P[-1] - P[-2]
        else:
            d0 = float(np.linalg.norm(P[i] - P[i - 1]))
            d1 = float(np.linalg.norm(P[i + 1] - P[i]))
            t = (P[i] - P[i - 1]) / max(d0, 1e-12) * d1 + (P[i + 1] - P[i]) / max(d1, 1e-12) * d0
            t = t / max(d0 + d1, 1e-12)
        T.append(unit(t) if unit(t) is not None else np.zeros(3))
    segs = []
    for i in range(n - 1):
        L = float(np.linalg.norm(P[i + 1] - P[i]))
        segs.append({"kind": "curve", "p": (P[i], P[i] + T[i] * L / 3.0,
                                            P[i + 1] - T[i + 1] * L / 3.0, P[i + 1])})
    return segs


def pen_seg(a, a_out, b, b_in):
    """Kalem aracı: a'nın çıkış tutamacı ve b'nin giriş tutamacıyla bezier (yoksa düz)."""
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if a_out is None and b_in is None:
        return line_seg(a, b)
    h1 = a + a_out if a_out is not None else a + (b - a) / 3.0
    h2 = b - b_in if b_in is not None else b - (b - a) / 3.0
    return {"kind": "curve", "p": (a, h1, h2, b)}


# ---------------------------------------------------------------- ızgara (spot ışığı)

def grid_falloff(d, R, fade):
    """Merkeze uzaklık d için saydamlık çarpanı: iç yarıçap R(1−fade) içinde 1, R'de 0
    (yumuşak geçiş, smoothstep)."""
    r0 = R * (1.0 - min(max(fade, 0.0), 1.0))
    if d <= r0:
        return 1.0
    if d >= R:
        return 0.0
    t = (d - r0) / max(R - r0, 1e-12)
    return 1.0 - t * t * (3.0 - 2.0 * t)


def grid_segments(q, g0, gs, R, fade, k=6):
    """İmleç (q, düzlem uv) çevresinde dairesel ızgara: ızgara çizgileri (g0 kökenli, gs
    aralıklı) R yarıçaplı daireyle kırpılır, kısa parçalara bölünür. [(uv0, uv1, a0, a1)]"""
    out = []
    n = int(math.ceil(R / gs)) + 1
    for axis in (0, 1):
        o = 1 - axis
        base = g0[axis] + round((q[axis] - g0[axis]) / gs) * gs
        for j in range(-n, n + 1):
            c = base + j * gs
            h = c - q[axis]
            if abs(h) >= R:
                continue
            half = math.sqrt(R * R - h * h)
            lo, hi = q[o] - half, q[o] + half
            m = max(2, int(math.ceil((hi - lo) / gs * k)))
            ts = np.linspace(lo, hi, m + 1)
            prev = None
            for t in ts:
                p = [0.0, 0.0]
                p[axis], p[o] = c, float(t)
                a = grid_falloff(math.hypot(p[0] - q[0], p[1] - q[1]), R, fade)
                if prev is not None and (a > 1e-4 or prev[1] > 1e-4):
                    out.append((prev[0], tuple(p), prev[1], a))
                prev = (tuple(p), a)
    return out
