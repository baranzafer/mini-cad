"""bpy'siz yüzey bölme matematiği (v0.25.0, Yüzeyi Böl).

  - kübik bezier: değer, türev, de Casteljau bölme, en yakın parametre
  - "kenar" (side): döngü yönünde sıralı segment listesi; [0, 1] parametresiyle değer
  - Coons yüzeyi: 4 kenar (3 kenarda tepe noktaya inmiş 4. kenar) ile doğrusal Coons
  - üçgen ağ: en yakın nokta, ışın kesişimi (kesim eğrisini gerçek yüzeye izdüşürmek için)
  - noktalardan geçen bezier zinciri (hata sınırına kadar sıklaştırılarak)
"""
import math

import numpy as np


def cubic(p):
    """2 ya da 4 noktalı segment → (4, 3) kübik kontrol noktaları."""
    P = np.array([tuple(map(float, q)) for q in p], dtype=np.float64)
    if len(P) == 2:
        a, b = P
        return np.array([a, a + (b - a) / 3.0, a + (b - a) * (2.0 / 3.0), b])
    return P


def bez(P, t):
    m = 1.0 - t
    return m * m * m * P[0] + 3 * m * m * t * P[1] + 3 * m * t * t * P[2] + t * t * t * P[3]


def bez_d(P, t):
    m = 1.0 - t
    return 3 * (m * m * (P[1] - P[0]) + 2 * m * t * (P[2] - P[1]) + t * t * (P[3] - P[2]))


def split_bez(P, t):
    """de Casteljau: (sol 4 nokta, sağ 4 nokta)."""
    P = np.asarray(P, dtype=np.float64)
    a, b, c = P[0] + (P[1] - P[0]) * t, P[1] + (P[2] - P[1]) * t, P[2] + (P[3] - P[2]) * t
    d, e = a + (b - a) * t, b + (c - b) * t
    f = d + (e - d) * t
    return np.array([P[0], a, d, f]), np.array([f, e, c, P[3]])


def closest_t(P, q, n=64):
    """Bezier üzerinde q'ya en yakın parametre ve uzaklık."""
    q = np.asarray(q, dtype=np.float64)
    ts = np.linspace(0.0, 1.0, n + 1)
    S = np.array([bez(P, t) for t in ts])
    i = int(np.argmin(np.linalg.norm(S - q, axis=1)))
    t = ts[i]
    for _ in range(12):                      # Newton inceltme
        d = bez_d(P, t)
        f = float(np.dot(bez(P, t) - q, d))
        dd = 6 * ((1 - t) * (P[2] - 2 * P[1] + P[0]) + t * (P[3] - 2 * P[2] + P[1]))
        g = float(np.dot(d, d) + np.dot(bez(P, t) - q, dd))
        if abs(g) < 1e-18:
            break
        t2 = min(1.0, max(0.0, t - f / g))
        if abs(t2 - t) < 1e-12:
            t = t2
            break
        t = t2
    return t, float(np.linalg.norm(bez(P, t) - q))


# ---------------------------------------------------------------- kenarlar

def side_eval(side, t):
    """side: [(4,3) kübik] döngü yönünde. t ∈ [0,1] → nokta (segmentler eşit parametre payı)."""
    n = len(side)
    x = min(max(t, 0.0), 1.0) * n
    i = min(int(x), n - 1)
    return bez(side[i], x - i)


def side_param(side, q):
    """q'nun kenar üzerindeki parametresi (t, uzaklık)."""
    n = len(side)
    best = None
    for i, P in enumerate(side):
        t, d = closest_t(P, q)
        if best is None or d < best[1]:
            best = ((i + t) / n, d)
    return best


def tri_to_quad(sides):
    """3 kenar → tepesi noktaya inmiş 4 kenar. Taban: en eğri kenar (eşitse en uzun);
    döngü [taban, yan1, (tepe), yan2]. (yeni kenarlar, taban sırası)."""
    def score(side):
        P = np.vstack(side)
        a, b = P[0], P[-1]
        L = float(np.linalg.norm(b - a))
        if L < 1e-12:
            return 0.0
        ch = (b - a) / L
        dev = float(np.max(np.linalg.norm((P - a) - np.outer((P - a) @ ch, ch), axis=1)))
        return dev + 1e-6 * L
    k = int(np.argmax([score(s) for s in sides]))
    sd = sides[k:] + sides[:k]
    apex = sd[1][-1][3]
    return [sd[0], sd[1], [np.array([apex, apex, apex, apex])], sd[2]], k


def coons(sides, u, v):
    """Doğrusal Coons: sides döngü yönünde 4 kenar; c0 = kenar0 (v=0), d1 = kenar1 (u=1),
    c1 = kenar2 ters (v=1), d0 = kenar3 ters (u=0)."""
    c0 = side_eval(sides[0], u)
    c1 = side_eval(sides[2], 1.0 - u)
    d0 = side_eval(sides[3], 1.0 - v)
    d1 = side_eval(sides[1], v)
    P00, P10 = side_eval(sides[0], 0.0), side_eval(sides[0], 1.0)
    P11, P01 = side_eval(sides[2], 0.0), side_eval(sides[2], 1.0)
    return (1 - v) * c0 + v * c1 + (1 - u) * d0 + u * d1 - \
        ((1 - u) * (1 - v) * P00 + u * (1 - v) * P10 + (1 - u) * v * P01 + u * v * P11)


def side_uv(j, t):
    """Kenar j üzerindeki t parametresinin Coons (u, v) karşılığı."""
    return [(t, 0.0), (1.0, t), (1.0 - t, 1.0), (0.0, 1.0 - t)][j]


# ---------------------------------------------------------------- üçgen ağ

def _closest_on_tris(p, A, B, C):
    """p'ye her üçgende en yakın nokta (Ericson). (m,3) A, B, C → (m,3)."""
    ab, ac, ap = B - A, C - A, p - A
    d1, d2 = np.einsum("ij,ij->i", ab, ap), np.einsum("ij,ij->i", ac, ap)
    bp = p - B
    d3, d4 = np.einsum("ij,ij->i", ab, bp), np.einsum("ij,ij->i", ac, bp)
    cp = p - C
    d5, d6 = np.einsum("ij,ij->i", ab, cp), np.einsum("ij,ij->i", ac, cp)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    out = np.empty_like(A)
    den = va + vb + vc
    den = np.where(np.abs(den) < 1e-300, 1e-300, den)
    v = vb / den
    w = vc / den
    out[:] = A + ab * v[:, None] + ac * w[:, None]                 # iç bölge
    # kenar BC
    m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    if m.any():
        ww = (d4 - d3) / np.maximum((d4 - d3) + (d5 - d6), 1e-300)
        out[m] = (B + (C - B) * ww[:, None])[m]
    m2 = (vb <= 0) & (d2 >= 0) & (d6 <= 0)                         # kenar AC
    if m2.any():
        ww = d2 / np.where(np.abs(d2 - d6) < 1e-300, 1e-300, d2 - d6)
        out[m2] = (A + ac * ww[:, None])[m2]
    m3 = (vc <= 0) & (d1 >= 0) & (d3 <= 0)                         # kenar AB
    if m3.any():
        vv = d1 / np.where(np.abs(d1 - d3) < 1e-300, 1e-300, d1 - d3)
        out[m3] = (A + ab * vv[:, None])[m3]
    out[(d6 >= 0) & (d5 <= d6)] = C[(d6 >= 0) & (d5 <= d6)]          # köşeler
    out[(d3 >= 0) & (d4 <= d3)] = B[(d3 >= 0) & (d4 <= d3)]
    out[(d1 <= 0) & (d2 <= 0)] = A[(d1 <= 0) & (d2 <= 0)]
    return out


class Mesh:
    """Dünya koordinatlarında üçgen ağ (gövde mesh'i) — en yakın nokta ve ışın sorguları."""

    def __init__(self, V, T):
        self.V = np.asarray(V, dtype=np.float64).reshape(-1, 3)
        self.T = np.asarray(T, dtype=np.int64).reshape(-1, 3)
        self.A, self.B, self.C = self.V[self.T[:, 0]], self.V[self.T[:, 1]], self.V[self.T[:, 2]]
        self.cen = (self.A + self.B + self.C) / 3.0
        self.rad = np.max(np.stack([np.linalg.norm(X - self.cen, axis=1)
                                    for X in (self.A, self.B, self.C)]), axis=0) \
            if len(self.T) else np.zeros(0)

    def __bool__(self):
        return len(self.T) > 0

    def closest(self, p, k=96):
        """p'ye ağ üzerindeki en yakın nokta ve uzaklık."""
        p = np.asarray(p, dtype=np.float64)
        dc = np.linalg.norm(self.cen - p, axis=1) - self.rad
        idx = np.argpartition(dc, min(k, len(dc) - 1))[:k] if len(dc) > k else np.arange(len(dc))
        Q = _closest_on_tris(p, self.A[idx], self.B[idx], self.C[idx])
        d = np.linalg.norm(Q - p, axis=1)
        j = int(np.argmin(d))
        return Q[j], float(d[j])

    def ray(self, o, d):
        """Işının (o + s·d, s serbest) ağla kesişimleri: [(s, nokta)] s'ye göre sıralı."""
        o = np.asarray(o, dtype=np.float64)
        d = np.asarray(d, dtype=np.float64)
        e1, e2 = self.B - self.A, self.C - self.A
        h = np.cross(d, e2)
        a = np.einsum("ij,ij->i", e1, h)
        ok = np.abs(a) > 1e-14
        f = np.where(ok, 1.0 / np.where(ok, a, 1.0), 0.0)
        s_ = o - self.A
        u = f * np.einsum("ij,ij->i", s_, h)
        q = np.cross(s_, e1)
        v = f * (q @ d)
        t = f * np.einsum("ij,ij->i", e2, q)
        hit = ok & (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9)
        ts = np.sort(t[hit])
        return [(float(x), o + d * float(x)) for x in ts]


def project_points(mesh, pts, view_dir=None, keep_ends=True):
    """Noktaları ağa izdüşürür. view_dir verilirse görünüş yönünde (noktaya en yakın kesişim),
    yoksa en yakın noktaya. Uçlar (sınırda) korunur."""
    if mesh is None or not mesh:
        return [np.asarray(p, dtype=np.float64) for p in pts]
    out = []
    n = len(pts)
    for i, p in enumerate(pts):
        p = np.asarray(p, dtype=np.float64)
        if keep_ends and i in (0, n - 1):
            out.append(p)
            continue
        q = None
        if view_dir is not None:
            hits = mesh.ray(p, np.asarray(view_dir, dtype=np.float64))
            if hits:
                q = min(hits, key=lambda h: abs(h[0]))[1]
        if q is None:
            q = mesh.closest(p)[0]
        out.append(q)
    return out


# ---------------------------------------------------------------- eğri uydurma

def _dense_tangent(P, i):
    """Yoğun örnek dizisinde i. noktadaki birim teğet (uçlarda 3 noktalı tek yönlü fark)."""
    n = len(P)
    if n < 3:
        t = P[-1] - P[0]
    elif i == 0:
        t = -3 * P[0] + 4 * P[1] - P[2]
    elif i == n - 1:
        t = 3 * P[-1] - 4 * P[-2] + P[-3]
    else:
        d0 = float(np.linalg.norm(P[i] - P[i - 1]))
        d1 = float(np.linalg.norm(P[i + 1] - P[i]))
        t = (P[i] - P[i - 1]) / max(d0, 1e-12) * d1 + (P[i + 1] - P[i]) / max(d1, 1e-12) * d0
    L = float(np.linalg.norm(t))
    return t / L if L > 1e-15 else np.zeros(3)


def _catmull(P, idx):
    """Yoğun örnekler P'nin idx düğümlerinden geçen kübik zincir; teğetler yoğun örneklerden,
    tutamaç boyu yay açısına göre (çember yayını tam verir)."""
    K = P[idx]
    T = [_dense_tangent(P, i) for i in idx]
    segs = []
    for i in range(len(K) - 1):
        L = float(np.linalg.norm(K[i + 1] - K[i]))
        c = float(np.clip(np.dot(T[i], T[i + 1]), -1.0, 1.0))
        th = math.acos(c)
        h = L / 3.0 if th < 1e-6 else L * (2.0 / 3.0) * math.tan(th / 4.0) / math.sin(th / 2.0)
        segs.append(np.array([K[i], K[i] + T[i] * h, K[i + 1] - T[i + 1] * h, K[i + 1]]))
    return segs


def fit_chain(pts, tol, max_segs=8):
    """Sıralı noktalardan geçen bezier zinciri: en az segmentle, örneklere uzaklık ≤ tol.
    Düz bir dizi tek doğru olur. [(4,3)]"""
    P = np.array([np.asarray(p, dtype=np.float64) for p in pts])
    a, b = P[0], P[-1]
    ch = b - a
    L = float(np.linalg.norm(ch))
    if L > 1e-12:
        u = ch / L
        dev = float(np.max(np.linalg.norm((P - a) - np.outer((P - a) @ u, u), axis=1)))
        if dev <= tol:
            return [cubic([a, b])]
    n = len(P)
    best = None
    k = 1
    while k <= max_segs:
        idx = np.unique(np.round(np.linspace(0, n - 1, k + 1)).astype(int))
        segs = _catmull(P, idx) if len(idx) > 2 else [_hermite_fit(P)]
        err = _chain_error(segs, P)
        if best is None or err < best[0]:
            best = (err, segs)
        if err <= tol:
            break
        k += 1
    return best[1]


def _hermite_fit(P):
    """Tek segment: uçlar sabit, uç teğetleri örneklerden, boylar en küçük kareler."""
    a, b = P[0], P[-1]
    ta = P[1] - P[0]
    tb = P[-1] - P[-2]
    ta = ta / max(float(np.linalg.norm(ta)), 1e-15)
    tb = tb / max(float(np.linalg.norm(tb)), 1e-15)
    s = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))])
    t = s / max(s[-1], 1e-15)
    B0, B1 = (1 - t) ** 3 + 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t * t + t ** 3
    Ba, Bb = 3 * (1 - t) ** 2 * t, -3 * (1 - t) * t * t
    R = P - np.outer(B0, a) - np.outer(B1, b)
    M = np.stack([np.outer(Ba, ta).ravel(), np.outer(Bb, tb).ravel()], axis=1)
    try:
        x, *_ = np.linalg.lstsq(M, R.ravel(), rcond=None)
        la, lb = float(x[0]), float(x[1])
    except Exception:
        la = lb = float(np.linalg.norm(b - a)) / 3.0
    L = float(np.linalg.norm(b - a))
    la = la if la > 1e-6 * L else L / 3.0
    lb = lb if lb > 1e-6 * L else L / 3.0
    return np.array([a, a + ta * la, b - tb * lb, b])


def _chain_error(segs, P):
    """Örneklerin zincire gerçek (en yakın nokta) uzaklıklarının en büyüğü."""
    return float(max(min(closest_t(sg, p, 16)[1] for sg in segs) for p in P))


# ---------------------------------------------------------------- v0.25.12: kilitli yakalama

def _golden(f, a, b, it=60):
    """[a, b] aralığında f'nin en küçüğü (altın oran araması)."""
    g = 0.6180339887498949
    c, d = b - g * (b - a), a + g * (b - a)
    fc, fd = f(c), f(d)
    for _ in range(it):
        if fc < fd:
            b, d, fd = d, c, fc
            c = b - g * (b - a)
            fc = f(c)
        else:
            a, c, fc = c, d, fd
            d = a + g * (b - a)
            fd = f(d)
    return 0.5 * (a + b)


def _line_dist(X, o, d):
    w = np.asarray(X, dtype=np.float64) - o
    return w - np.multiply.outer(w @ d, d) if w.ndim == 2 else w - d * float(w @ d)


def bez_plane_hits(P, o, n, eps=1e-9, samples=48):
    """Bezier'in (o, n) düzlemini kestiği parametreler. Eğri düzlemin içindeyse boş."""
    P = np.asarray(P, dtype=np.float64)
    n = np.asarray(n, dtype=np.float64)
    o = np.asarray(o, dtype=np.float64)
    ts = np.linspace(0.0, 1.0, samples + 1)
    f = np.array([float((bez(P, t) - o) @ n) for t in ts])
    scale = 1.0 + float(np.abs(P).max())
    if float(np.abs(f).max()) <= eps * scale:
        return []
    out = []
    for i in range(samples):
        a, b, fa, fb = ts[i], ts[i + 1], f[i], f[i + 1]
        if fa == 0.0:
            out.append(a)
            continue
        if fa * fb > 0.0 or fb == 0.0:
            continue                          # fb == 0: sonraki aralıkta fa == 0 olarak
        for _ in range(60):
            m = 0.5 * (a + b)
            fm = float((bez(P, m) - o) @ n)
            if fa * fm <= 0.0:
                b = m
            else:
                a, fa = m, fm
        out.append(0.5 * (a + b))
    if f[-1] == 0.0:
        out.append(1.0)
    return out


def bez_line_hits(P, o, d, tol, samples=48):
    """Bezier'in (o, d) doğrusuyla kesiştiği parametreler (uzaklık ≤ tol)."""
    P = np.asarray(P, dtype=np.float64)
    o = np.asarray(o, dtype=np.float64)
    d = np.asarray(d, dtype=np.float64)
    d = d / max(float(np.linalg.norm(d)), 1e-300)
    ts = np.linspace(0.0, 1.0, samples + 1)

    def h(t):
        return float(np.linalg.norm(_line_dist(bez(P, t), o, d)))
    H = np.array([h(t) for t in ts])
    out = []
    for i in range(samples + 1):
        if (i > 0 and H[i] > H[i - 1]) or (i < samples and H[i] > H[i + 1]):
            continue
        t = _golden(h, ts[max(i - 1, 0)], ts[min(i + 1, samples)])
        if h(t) <= tol and not any(abs(t - u) < 1e-6 for u in out):
            out.append(t)
    return out


def bez_ray_closest(P, ro, rd, samples=48):
    """Bezier üzerinde fare ışınına en yakın parametre."""
    P = np.asarray(P, dtype=np.float64)
    rd = np.asarray(rd, dtype=np.float64)
    rd = rd / max(float(np.linalg.norm(rd)), 1e-300)
    ro = np.asarray(ro, dtype=np.float64)

    def h(t):
        return float(np.linalg.norm(_line_dist(bez(P, t), ro, rd)))
    ts = np.linspace(0.0, 1.0, samples + 1)
    H = np.array([h(t) for t in ts])
    i = int(np.argmin(H))
    return _golden(h, ts[max(i - 1, 0)], ts[min(i + 1, samples)])


def poly_plane_hits(S, o, n, eps=1e-9):
    """Çoklu çizginin düzlemi kestiği noktalar."""
    S = np.asarray(S, dtype=np.float64)
    f = (S - o) @ np.asarray(n, dtype=np.float64)
    if float(np.abs(f).max()) <= eps * (1.0 + float(np.abs(S).max())):
        return []
    out = []
    for i in range(len(S) - 1):
        if f[i] == 0.0:
            out.append(S[i].copy())
        elif f[i] * f[i + 1] < 0.0:
            out.append(S[i] + (S[i + 1] - S[i]) * (f[i] / (f[i] - f[i + 1])))
    if f[-1] == 0.0:
        out.append(S[-1].copy())
    return out


def poly_line_hits(S, o, d, tol):
    """Çoklu çizginin doğruyla kesiştiği noktalar (uzaklık ≤ tol)."""
    S = np.asarray(S, dtype=np.float64)
    d = np.asarray(d, dtype=np.float64)
    d = d / max(float(np.linalg.norm(d)), 1e-300)
    out = []
    for i in range(len(S) - 1):
        a, b = S[i], S[i + 1]
        u = b - a
        w0 = a - o
        A, B, C = float(u @ u), float(u @ d), 1.0
        D, E = float(u @ w0), float(d @ w0)
        den = A * C - B * B
        s = (B * E - C * D) / den if den > 1e-18 else 0.0
        s = min(max(s, 0.0), 1.0)
        q = a + u * s
        if float(np.linalg.norm(_line_dist(q, o, d))) <= tol:
            out.append(q)
    return out
