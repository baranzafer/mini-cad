"""Kesişim (birleşim) noktasını eğriler üzerinde kaydırma — v0.34.0.

Tel kafeste birden çok eğrinin buluştuğu bir nokta ince ayar için sürüklenirken nokta
serbestçe değil, o noktadan geçen eğrilerin ÜZERİNDE ve DOĞRULTUSUNDA kayar:

* noktanın ait olduğu eğri (zincir) kayılan yönde kısalır, öbür yanda o kadar uzar — iki
  komşu parça yeniden kurulur: kısalan parça aynı eğrinin alt parçası (şekil birebir),
  uzayan parça eski iki parçanın birleşimine teğetleri korunarak uydurulur;
* eğrinin ucundaysa uç teğeti boyunca dışarı doğru da uzatılabilir;
* noktadan geçip orada düğümü olmayan eğri (T birleşimi) yalnızca yol olur, değişmez;
* noktada ucu / düğümü olan öbür eğriler yeni konuma taşınır (bağlantı kopmaz).

Bu modül saf numpy'dir (bpy yok); çizim aracı (draw_edit.py) ve kaydedilmiş tel kafes
için ortak kullanılır. Segmentler (4,3) kübik bezier dizileridir; doğrular da üçte bir
tutamaçlı bezier olarak tutulur ve `lines` bayrağıyla işaretlenir.
"""
import numpy as np

from .sketchmath import bez_deriv, bez_point, bez_sub

SAMPLES = 64          # yol örnekleme sıklığı (dal başına)
T_MIN = 0.02          # komşu parçanın en az bu kadarı kalsın (sıfır uzunluk olmasın)


def _unit(v):
    n = float(np.linalg.norm(v))
    return None if n < 1e-15 else v / n


def _line_bez(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    return np.array([a, a + (b - a) / 3.0, a + (b - a) * (2.0 / 3.0), b])


def _is_straight(P, tol=1e-7):
    P = np.asarray(P, float)
    d = P[3] - P[0]
    L = float(np.linalg.norm(d))
    if L < 1e-12:
        return True
    u = d / L
    for q in (P[1], P[2]):
        w = q - P[0]
        if float(np.linalg.norm(w - u * np.dot(w, u))) > tol * max(L, 1.0):
            return False
    return True


def sample(P, n=24):
    P = np.asarray(P, float)
    return np.array([bez_point(P, t) for t in np.linspace(0.0, 1.0, n)])


def fit_cubic(pts, t0, t1):
    """Uçları ve uç teğet doğrultuları sabit kübik bezier (Schneider en küçük kareler).
    pts: (K,3) örnekler (ilk / son = uçlar), t0: başlangıçta ileri, t1: sonda ileri yön."""
    pts = np.asarray(pts, float)
    a, b = pts[0], pts[-1]
    chord = float(np.linalg.norm(b - a))
    d = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    if d[-1] < 1e-15:
        return _line_bez(a, b)
    u = d / d[-1]
    t0 = _unit(np.asarray(t0, float))
    t1 = _unit(np.asarray(t1, float))
    if t0 is None or t1 is None:
        return _line_bez(a, b)
    v = 1.0 - u
    B0, B1, B2, B3 = v ** 3, 3 * v * v * u, 3 * v * u * u, u ** 3
    A1 = B1[:, None] * t0[None, :]
    A2 = -B2[:, None] * t1[None, :]
    R = pts - (B0 + B1)[:, None] * a[None, :] - (B2 + B3)[:, None] * b[None, :]
    C = np.array([[np.sum(A1 * A1), np.sum(A1 * A2)], [np.sum(A1 * A2), np.sum(A2 * A2)]])
    X = np.array([np.sum(A1 * R), np.sum(A2 * R)])
    try:
        al, be = np.linalg.solve(C, X)
    except np.linalg.LinAlgError:
        al = be = chord / 3.0
    eps = 1e-6 * max(chord, 1e-9)
    if not (np.isfinite(al) and np.isfinite(be)) or al < eps or be < eps:
        al = be = chord / 3.0
    return np.array([a, a + t0 * al, b - t1 * be, b])


def _tangent(P, t):
    P = np.asarray(P, float)
    g = _unit(bez_deriv(P, t))
    if g is None:                       # tutamaç uca çökmüş: kirişe bak
        g = _unit(P[3] - P[0])
    return g


def join(Pa, Pb, line_a=False, line_b=False):
    """Pa (sonu Pb'nin başı) ile Pb'yi tek kübik parçaya birleştirir. Döner: (P, doğru_mu)."""
    Pa, Pb = np.asarray(Pa, float), np.asarray(Pb, float)
    if line_a and line_b:
        da, db = _unit(Pa[3] - Pa[0]), _unit(Pb[3] - Pb[0])
        if da is not None and db is not None and float(np.dot(da, db)) > 1 - 1e-9:
            return _line_bez(Pa[0], Pb[3]), True
    pts = np.vstack([sample(Pa, 24), sample(Pb, 24)[1:]])
    return fit_cubic(pts, _tangent(Pa, 0.0), _tangent(Pb, 1.0)), False


class Branch:
    """Düğümden çıkan bir kayma yolu.

    kind: "f" (zincirin j. parçası boyunca ileri), "b" (j-1. parça boyunca geri),
          "x" (uç teğeti boyunca dışa uzatma), "p" (geçen eğri — yalnız yol).
    owner: zincir sırası (f / b / x) ya da None (p).
    """

    def __init__(self, kind, owner, path, params, P=None, ext_dir=None):
        self.kind, self.owner = kind, owner
        self.path = np.asarray(path, float)        # (K,3), path[0] = düğüm
        self.params = np.asarray(params, float)    # her örneğin parametresi
        self.P = None if P is None else np.asarray(P, float)
        self.ext_dir = ext_dir
        seg = np.linalg.norm(np.diff(self.path, axis=0), axis=1)
        self.cum = np.r_[0.0, np.cumsum(seg)]       # yay uzunluğu (ölçü yazmak için)

    def at(self, s):
        """Yay uzunluğu s'deki (parametre, konum)."""
        s = float(np.clip(s, 0.0, self.cum[-1]))
        i = int(np.searchsorted(self.cum, s))
        i = min(max(i, 1), len(self.cum) - 1)
        L = self.cum[i] - self.cum[i - 1]
        f = 0.0 if L < 1e-15 else (s - self.cum[i - 1]) / L
        par = self.params[i - 1] + (self.params[i] - self.params[i - 1]) * f
        return par, self.point(par)

    def point(self, par):
        if self.kind == "x":
            return self.path[0] + self.ext_dir * par
        return bez_point(self.P, par)

    def length_at(self, par):
        return float(np.interp(par, self.params, self.cum)) if self.params[-1] > self.params[0] \
            else float(np.interp(-par, -self.params, self.cum))


def node_of(segs, j, cyclic):
    n = len(segs)
    return np.asarray(segs[j][0] if j < n else segs[n - 1][3], float)


def chain_branches(ci, segs, j, cyclic, ext_len=None):
    """Zincirin j. düğümünden çıkan dallar (f / b / x)."""
    n = len(segs)
    out = []
    if n == 0:
        return out
    q = node_of(segs, j, cyclic)
    has_out = j < n
    has_in = j > 0 or cyclic
    jin = (j - 1) % n
    ts = np.linspace(0.0, 1.0 - T_MIN, SAMPLES)
    if has_out:
        P = np.asarray(segs[j], float)
        out.append(Branch("f", ci, [bez_point(P, t) for t in ts], ts, P))
    if has_in:
        P = np.asarray(segs[jin], float)
        tb = 1.0 - ts
        out.append(Branch("b", ci, [bez_point(P, t) for t in tb], tb, P))
    if not cyclic and (j == 0 or j == n):
        P = np.asarray(segs[0] if j == 0 else segs[n - 1], float)
        d = -_tangent(P, 0.0) if j == 0 else _tangent(P, 1.0)
        L = ext_len if ext_len is not None else \
            float(np.sum(np.linalg.norm(np.diff(sample(P, 12), axis=0), axis=1)))
        es = np.linspace(0.0, max(L, 1e-9), SAMPLES)
        out.append(Branch("x", ci, [q + d * s for s in es], es, ext_dir=d))
    return out


def passing_branches(P, t0):
    """Düğümden (P(t0)) geçen ama orada düğümü olmayan eğri parçası: iki yönde yol."""
    P = np.asarray(P, float)
    out = []
    for lo, hi in ((t0, 1.0), (t0, 0.0)):
        if abs(hi - lo) < 1e-6:
            continue
        ts = np.linspace(lo, hi, SAMPLES)
        out.append(Branch("p", None, [bez_point(P, t) for t in ts], ts, P))
    return out


def closest_param(P, q, n=48):
    """Bezier üzerinde q'ya en yakın parametre ve uzaklık."""
    P = np.asarray(P, float)
    ts = np.linspace(0.0, 1.0, n)
    S = np.array([bez_point(P, t) for t in ts])
    i = int(np.argmin(np.linalg.norm(S - q, axis=1)))
    lo, hi = ts[max(i - 1, 0)], ts[min(i + 1, n - 1)]
    for _ in range(30):                 # altın oran benzeri daraltma
        m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        if np.linalg.norm(bez_point(P, m1) - q) < np.linalg.norm(bez_point(P, m2) - q):
            hi = m2
        else:
            lo = m1
    t = 0.5 * (lo + hi)
    return t, float(np.linalg.norm(bez_point(P, t) - q))


def slide_chain(segs, lines, j, cyclic, kind, par):
    """Zincirin j. düğümünü dal (kind) boyunca par'a kaydırır.

    segs: (4,3) diziler, lines: doğru bayrakları. Döner: (yeni segs, yeni lines, yeni nokta).
    Kısalan parça aynı eğrinin alt parçasıdır; öbür yandaki parça teğetler korunarak uzar."""
    segs = [np.asarray(s, float).copy() for s in segs]
    lines = list(lines)
    n = len(segs)
    jin = (j - 1) % n
    has_in = j > 0 or cyclic
    has_out = j < n
    if kind == "f":
        P = segs[j]
        t = float(np.clip(par, 0.0, 1.0 - T_MIN))
        head = bez_sub(P, 0.0, t)
        segs[j] = np.array(bez_sub(P, t, 1.0))
        if has_in and t > 1e-9:
            segs[jin], lines[jin] = join(segs[jin], head, lines[jin], lines[j])
        new = segs[j][0]
    elif kind == "b":
        P = segs[jin]
        t = float(np.clip(par, T_MIN, 1.0))
        tail = bez_sub(P, t, 1.0)
        segs[jin] = np.array(bez_sub(P, 0.0, t))
        if has_out and t < 1 - 1e-9:
            segs[j], lines[j] = join(tail, segs[j], lines[jin], lines[j])
        new = segs[jin][3]
    elif kind == "x":
        if j == 0:
            P = segs[0]
            d = -_tangent(P, 0.0)
            q = P[0] + d * float(par)
            if lines[0]:
                segs[0] = _line_bez(q, P[3])
            elif par > 1e-12:
                segs[0], _ = join(_line_bez(q, P[0]), P, True, False)
        else:
            P = segs[n - 1]
            d = _tangent(P, 1.0)
            q = P[3] + d * float(par)
            if lines[n - 1]:
                segs[n - 1] = _line_bez(P[0], q)
            elif par > 1e-12:
                segs[n - 1], _ = join(P, _line_bez(P[3], q), False, True)
        new = q
    else:
        raise ValueError(kind)
    for i, s in enumerate(segs):
        if lines[i]:
            segs[i] = _line_bez(s[0], s[3])
    return segs, lines, np.asarray(new, float)


def move_node(segs, lines, j, cyclic, new):
    """Düğümü taşır (bağlı öbür eğriler için): doğrular düz kalır, eğrilerde tutamaç
    noktayla birlikte gider."""
    segs = [np.asarray(s, float).copy() for s in segs]
    n = len(segs)
    touch = []
    if j < n:
        touch.append((j, 0))
    if j > 0:
        touch.append((j - 1, 3))
    elif cyclic:
        touch.append((n - 1, 3))
    for k, end in touch:
        P = segs[k]
        delta = new - P[end]
        P[end] = new
        if lines[k]:
            segs[k] = _line_bez(P[0], P[3])
        else:
            P[1 if end == 0 else 2] += delta
    return segs


class Slider:
    """Bir birleşim düğümünün kayma oturumu.

    chains: [(segs, lines, cyclic)] — düğümü taşıyan zincirler
    nodes:  [(chain_index, j)] — her zincirin düğümdeki indisi (aynı zincirde birden çok
            olabilir: kapalı eğri / kendini kesen)
    passing: [(P, t0)] — düğümden geçen öbür eğri parçaları (yalnız yol)
    """

    def __init__(self, chains, nodes, passing=(), ext_len=None):
        self.chains = [([np.asarray(s, float) for s in sg], list(ln), bool(cy))
                       for sg, ln, cy in chains]
        self.nodes = list(nodes)
        self.origin = node_of(self.chains[nodes[0][0]][0], nodes[0][1],
                              self.chains[nodes[0][0]][2]) if nodes else None
        self.branches = []
        for ci, j in self.nodes:
            sg, _ln, cy = self.chains[ci]
            self.branches += [(b, j) for b in chain_branches(ci, sg, j, cy, ext_len)]
        for P, t0 in passing:
            self.branches += [(b, None) for b in passing_branches(P, t0)]
        self.snaps = []                 # [(dal sırası, parametre, tür)]

    def add_snap_points(self, pts, kinds, tol):
        """Yolların üzerine düşen yakalama noktaları (uç / orta / kesişim...)."""
        pts = np.asarray(pts, float).reshape(-1, 3)
        for bi, (b, _j) in enumerate(self.branches):
            if not len(pts):
                break
            for k, p in enumerate(pts):
                if np.linalg.norm(p - b.path[0]) < tol:
                    continue
                d = np.linalg.norm(b.path - p, axis=1)
                i = int(np.argmin(d))
                gap = float(np.max(np.diff(b.cum))) if len(b.cum) > 1 else 0.0
                if d[i] > 4 * tol + gap:
                    continue
                par = self._refine(b, p, i)
                if np.linalg.norm(b.point(par) - p) < tol:
                    self.snaps.append((bi, par, kinds[k]))

    def add_crossings(self, polylines, tol):
        """Yolların öbür eğrilerle kesiştiği yerler (3B yakın geçiş) — 'Kesişim' yakalaması."""
        for bi, (b, _j) in enumerate(self.branches):
            for S in polylines:
                S = np.asarray(S, float)
                if len(S) < 2:
                    continue
                d = _poly_dist(b.path, S)
                for i in range(1, len(d) - 1):
                    if d[i] <= d[i - 1] and d[i] <= d[i + 1] and d[i] < tol:
                        if np.linalg.norm(b.path[i] - b.path[0]) < 2 * tol:
                            continue
                        par = b.params[i]
                        self.snaps.append((bi, par, "Kesişim"))

    @staticmethod
    def _refine(b, p, i):
        lo = b.params[max(i - 1, 0)]
        hi = b.params[min(i + 1, len(b.params) - 1)]
        for _ in range(30):
            m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
            if np.linalg.norm(b.point(m1) - p) < np.linalg.norm(b.point(m2) - p):
                hi = m2
            else:
                lo = m1
        return 0.5 * (lo + hi)

    def apply(self, bi, par):
        """Dal bi üzerinde par'a kaydır. Döner: (yeni zincir segmentleri listesi, nokta)."""
        b, j = self.branches[bi]
        out = [(list(sg), list(ln)) for sg, ln, _cy in self.chains]
        if b.kind == "p":
            new = b.point(par)
        else:
            sg, ln, cy = self.chains[b.owner]
            nsg, nln, new = slide_chain(sg, ln, j, cy, b.kind, par)
            out[b.owner] = (nsg, nln)
        for ci, jj in self.nodes:
            if b.kind != "p" and ci == b.owner and jj == j:
                continue
            sg, ln = out[ci]
            out[ci] = (move_node(sg, ln, jj, self.chains[ci][2], new), ln)
        return out, new


def _poly_dist(Q, S):
    """Q'nun her noktasının S çoklu çizgisine uzaklığı."""
    A, B = S[:-1], S[1:]
    AB = B - A
    L2 = np.maximum(np.sum(AB * AB, axis=1), 1e-30)
    W = Q[:, None, :] - A[None, :, :]
    t = np.clip(np.sum(W * AB[None], axis=2) / L2[None], 0.0, 1.0)
    C = A[None] + t[..., None] * AB[None]
    return np.min(np.linalg.norm(Q[:, None, :] - C, axis=2), axis=1)
