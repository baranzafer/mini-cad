"""3D geometrik kısıt çözücü (bpy'siz, numpy).

Yöntem: en az hareketle izdüşüm. Kullanıcının son konumları x0'dan, ağırlıklı en küçük
yer değiştirmeyle bütün kısıtları sağlayan x aranır:
    min  ½ (x − x0)ᵀ W (x − x0)    öyle ki   c(x) = 0
Her adımda kısıtlar doğrusallaştırılır (Gauss-Newton), artık kısıt fazlalığı (ör. paralel
kısıtın 3 denkleminden 2'si bağımsız) küçük bir sönümle tolere edilir. Kullanıcının az önce
taşıdığı noktalar yüksek ağırlık alır: onlar yerinde kalır, diğerleri uyum sağlar.

Kısıt: (tür, nokta indeksleri, parametreler)
  AXIS        (a, b)          {"axis": 0|1|2}     segment eksene paralel
  PARALLEL    (a, b, c, d)                        iki segment paralel
  PERP        (a, b, c, d)                        iki segment dik
  COLLINEAR   (a, b, c, d)                        aynı doğru üzerinde
  EQUAL       (a, b, c, d)                        eşit boy
  DISTANCE    (a, b)          {"value": L}        boy / iki nokta arası mesafe
  ANGLE       (a, b, c, d)    {"value": derece}   iki segment arası açı
  FIX         (a,)            {"pos": (x,y,z)}    nokta sabit
  COINCIDENT  (a, b)                              iki nokta çakışık
  SYMMETRIC   (a, b)          {"axis", "offset"}  eksene dik düzleme göre simetrik
"""

import math

import numpy as np


def _u(d):
    n = float(np.linalg.norm(d))
    return d / n if n > 1e-15 else d * 0.0, n


def residual(kind, P, prm):
    """Bir kısıtın artığı (sıfır = sağlanıyor). P: ilgili noktalar (k,3)."""
    if kind == "AXIS":
        d = P[1] - P[0]
        k = prm["axis"]
        return np.array([d[j] for j in range(3) if j != k])
    if kind in ("PARALLEL", "PERP", "COLLINEAR", "EQUAL", "ANGLE"):
        d1, d2 = P[1] - P[0], P[3] - P[2]
        u1, l1 = _u(d1)
        u2, l2 = _u(d2)
        if kind == "PARALLEL":
            return np.cross(u1, u2)
        if kind == "PERP":
            return np.array([float(np.dot(u1, u2))])
        if kind == "COLLINEAR":
            return np.concatenate([np.cross(u1, u2) * max(l1, 1e-12),
                                   np.cross(u1, P[2] - P[0])])
        if kind == "EQUAL":
            return np.array([l1 - l2])
        ang = math.atan2(float(np.linalg.norm(np.cross(u1, u2))), float(np.dot(u1, u2)))
        return np.array([ang - math.radians(prm["value"])])
    if kind == "TLINE":
        # doğru (P0 = ortak uç, P1 = uzak uç) eğrinin uçtaki teğetine paralel
        u, _ = _u(P[1] - P[0])
        t, _ = _u(np.asarray(prm["dir"], dtype=np.float64))
        return np.cross(u, t)
    if kind == "DISTANCE":
        return np.array([float(np.linalg.norm(P[1] - P[0])) - prm["value"]])
    if kind == "FIX":
        return P[0] - np.asarray(prm["pos"], dtype=np.float64)
    if kind == "COINCIDENT":
        return P[1] - P[0]
    if kind == "SYMMETRIC":
        k, o = prm["axis"], prm.get("offset", 0.0)
        r = [0.5 * (P[0][k] + P[1][k]) - o]
        r += [P[0][j] - P[1][j] for j in range(3) if j != k]
        return np.array(r)
    return np.zeros(0)


def evaluate(x, cons):
    """Bütün artıklar ve (seyrek bloklarla kurulan) Jacobian."""
    X = x.reshape(-1, 3)
    rows, blocks = [], []
    for kind, idx, prm in cons:
        P = X[list(idx)].copy()
        r = residual(kind, P, prm)
        m = len(r)
        Jl = np.zeros((m, 3 * len(idx)))
        h = 1e-7 * (1.0 + float(np.abs(P).max()))
        for a in range(len(idx)):
            for k in range(3):
                Q = P.copy()
                Q[a, k] += h
                rp = residual(kind, Q, prm)
                Q[a, k] -= 2 * h
                rm = residual(kind, Q, prm)
                Jl[:, 3 * a + k] = (rp - rm) / (2 * h)
        rows.append(r)
        blocks.append((idx, Jl))
    m = sum(len(r) for r in rows)
    J = np.zeros((m, x.size))
    row = 0
    for (idx, Jl), r in zip(blocks, rows):
        for a, i in enumerate(idx):
            J[row:row + len(r), 3 * i:3 * i + 3] += Jl[:, 3 * a:3 * a + 3]
        row += len(r)
    c = np.concatenate(rows) if rows else np.zeros(0)
    return c, J


def solve(x0, cons, weights=None, iters=60, tol=None):
    """(x, başarılı mı, kısıt başına artık normu) döndürür. x0: (n,3)."""
    x0 = np.asarray(x0, dtype=np.float64).reshape(-1)
    if not cons or x0.size == 0:
        return x0.reshape(-1, 3), True, []
    scale = 1.0 + float(np.abs(x0).max())
    if tol is None:
        tol = 1e-8 * scale
    w = np.ones(x0.size) if weights is None else np.repeat(np.asarray(weights, float), 3)
    winv = 1.0 / w
    x = x0.copy()
    c, J = evaluate(x, cons)
    err = float(np.abs(c).max()) if c.size else 0.0
    stall = 0
    for _ in range(iters):
        if err <= tol or stall >= 4:
            break
        b = J @ (x - x0) - c
        A = (J * winv) @ J.T
        mu = 1e-12 * (np.trace(A) + 1e-30) + 1e-24
        try:
            lam = np.linalg.solve(A + mu * np.eye(len(A)), b)
        except np.linalg.LinAlgError:
            lam = np.linalg.lstsq(A, b, rcond=None)[0]
        target = x0 + winv * (J.T @ lam)
        # küçük adım arama: artık büyürse adımı kısalt
        step = 1.0
        for _ls in range(5):
            xn = x + step * (target - x)
            cn, Jn = evaluate(xn, cons)
            en = float(np.abs(cn).max()) if cn.size else 0.0
            if en < err or en <= tol:
                break
            step *= 0.5
        stall = stall + 1 if en > err * 0.95 else 0
        x, c, J, err = xn, cn, Jn, en
    X = x.reshape(-1, 3)
    per = [float(np.linalg.norm(residual(k, X[list(i)], p))) for k, i, p in cons]
    ok = err <= max(tol * 1000, 1e-7 * scale)
    return X, ok, per


def measure(kind, P):
    """Ölçü kısıtının mevcut değeri (oluştururken kullanılır)."""
    if kind == "DISTANCE":
        return float(np.linalg.norm(P[1] - P[0]))
    if kind == "ANGLE":
        u1, _ = _u(P[1] - P[0])
        u2, _ = _u(P[3] - P[2])
        return math.degrees(math.atan2(float(np.linalg.norm(np.cross(u1, u2))),
                                       float(np.dot(u1, u2))))
    return 0.0
