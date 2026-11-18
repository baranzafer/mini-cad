"""Yüzey sınırı teşhisi (v0.31.0): seçili kenarlar neden kapalı döngü oluşturmuyor ve nasıl
düzelir? bpy'siz (numpy).

Girdi: [(ref, P)] — ref herhangi bir kimlik (ör. (eğri adı, spline, segment)), P 4×3 bezier
kontrol noktaları (dünya). tol: kaynak toleransı (join_tol), near: "niyet edilmiş" yakınlık
(uçların birleşmesi istendiği varsayılan mesafe; seçimin boyuna göre).

Bulunan sorunlar (her biri kullanıcıya sorulan bir onarım önerisi taşır):
  TINY   çok kısa (neredeyse sıfır boy) parça            → seçimden çıkar
  DUP    üst üste binen iki kenar                         → birini seçimden çıkar
  TJUNC  bir uç başka bir kenarın ORTASINA değiyor        → kenarı o noktada böl + ucu oraya kaynak
         (kenarda nokta olmasa da snap ile bağlanmış çizgi)
  GAP    iki uç birbirine çok yakın ama değmiyor          → uçları ortak noktada birleştir
  EXTRA  döngüye katılmayan fazla parça (taşan uç, dal)   → seçimden çıkar
  BRANCH üç ya da daha çok kenarın buluştuğu köşe         → (yalnız bilgi) fazla kenarı çıkar

Sorun: {"kind", "msg", "pts": [işaret noktaları], "fix": {...}}; fix türleri
  {"op": "drop", "ref"} · {"op": "weld", "ends": [(ref, uç)], "to": nokta}
  {"op": "split", "ref", "t", "to", "end": (ref, uç)}
"""

import numpy as np

N_SAMP = 33


def bez(P, t):
    t = np.asarray(t, dtype=np.float64)[..., None]
    u = 1.0 - t
    return u ** 3 * P[0] + 3 * u * u * t * P[1] + 3 * u * t * t * P[2] + t ** 3 * P[3]


def samples(P, n=N_SAMP):
    return bez(P, np.linspace(0.0, 1.0, n))


def length(P):
    S = samples(P)
    return float(np.linalg.norm(np.diff(S, axis=0), axis=1).sum())


def closest(P, q):
    """(t, uzaklık, nokta): bezier üzerinde q'ya en yakın nokta (örnek + daraltma)."""
    t = np.linspace(0.0, 1.0, N_SAMP)
    S = bez(P, t)
    d = np.linalg.norm(S - q, axis=1)
    j = int(np.argmin(d))
    lo, hi = t[max(j - 1, 0)], t[min(j + 1, N_SAMP - 1)]
    for _ in range(30):                              # altın oran araması
        a = lo + (hi - lo) * 0.382
        b = lo + (hi - lo) * 0.618
        if np.linalg.norm(bez(P, a) - q) < np.linalg.norm(bez(P, b) - q):
            hi = b
        else:
            lo = a
    tt = 0.5 * (lo + hi)
    p = bez(P, tt)
    return float(tt), float(np.linalg.norm(p - q)), p


def near_for(segs, tol):
    """Niyet edilen yakınlık: seçim boyunun %1'i (en az 10 tol, en çok 5 cm)."""
    if not segs:
        return tol * 10
    pts = np.vstack([s[1] for s in segs])
    size = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
    return float(min(max(tol * 10.0, size * 0.01), max(0.05, tol * 10.0)))


def _ends(segs):
    return [(i, e, segs[i][1][0 if e == 0 else 3]) for i in range(len(segs)) for e in (0, 1)]


def _cluster(segs, tol):
    """Uçları tol ile düğümlere topla: (düğüm noktaları, uç→düğüm)."""
    nodes, of = [], {}
    for i, e, p in _ends(segs):
        k = next((n for n, q in enumerate(nodes) if np.linalg.norm(q - p) <= tol), None)
        if k is None:
            nodes.append(p.copy())
            k = len(nodes) - 1
        of[(i, e)] = k
    return nodes, of


def _fmt(d):
    return f"{d * 1000:.2f} mm" if d < 1.0 else f"{d:.3f} m"


def diagnose(segs, tol, near=None, names=None):
    """Sorun listesi (önem / onarım sırasıyla)."""
    segs = [(r, np.asarray(P, dtype=np.float64).reshape(4, 3)) for r, P in segs]
    near = near_for(segs, tol) if near is None else near
    name = (lambda r: names(r)) if names else (lambda r: str(r))
    out = []
    lens = [length(P) for _r, P in segs]

    # TINY
    for i, (r, P) in enumerate(segs):
        if lens[i] < max(near * 0.5, tol * 2):
            out.append({"kind": "TINY", "pts": [P[0], P[3]],
                        "msg": f"{name(r)}: çok kısa parça ({_fmt(lens[i])}). Seçimden "
                               "çıkarayım mı?",
                        "fix": {"op": "drop", "ref": r}})
    if out:
        return out

    # DUP
    S = [samples(P) for _r, P in segs]
    for i in range(len(segs)):
        for j in range(i + 1, len(segs)):
            a, b = segs[i][1], segs[j][1]
            same = (np.linalg.norm(a[0] - b[0]) < near and np.linalg.norm(a[3] - b[3]) < near) \
                or (np.linalg.norm(a[0] - b[3]) < near and np.linalg.norm(a[3] - b[0]) < near)
            if not same:
                continue
            dmax = max(float(np.min(np.linalg.norm(S[j] - p, axis=1))) for p in S[i])
            if dmax < near:
                out.append({"kind": "DUP", "pts": [S[j][N_SAMP // 2]],
                            "msg": f"{name(segs[i][0])} ile {name(segs[j][0])} üst üste "
                                   f"biniyor. {name(segs[j][0])} seçimden çıksın mı?",
                            "fix": {"op": "drop", "ref": segs[j][0]}})
    if out:
        return out

    nodes, of = _cluster(segs, tol)
    deg = {}
    for (i, e), k in of.items():
        deg[k] = deg.get(k, 0) + 1
    open_ends = [(i, e) for (i, e), k in of.items() if deg[k] == 1]

    # TJUNC: açık uç başka bir kenarın ortasında
    for i, e in open_ends:
        p = segs[i][1][0 if e == 0 else 3]
        best = None
        for j, (rj, Pj) in enumerate(segs):
            if j == i:
                continue
            if min(np.linalg.norm(p - Pj[0]), np.linalg.norm(p - Pj[3])) < near:
                continue                              # uca yakın: GAP'in işi
            t, d, q = closest(Pj, p)
            if d < near and 0.01 < t < 0.99 and (best is None or d < best[1]):
                best = (j, d, t, q)
        if best is not None:
            j, d, t, q = best
            out.append({"kind": "TJUNC", "pts": [q],
                        "msg": f"{name(segs[i][0])} ucu {name(segs[j][0])} kenarının "
                               "ortasına değiyor" + (f" ({_fmt(d)})" if d > 1e-6 else "") +
                               ". Kenarı bu noktada bölüp "
                               "uçları kaynatayım mı?",
                        "fix": {"op": "split", "ref": segs[j][0], "t": t, "to": q,
                                "end": (segs[i][0], e)}})
    if out:
        return out[:1]                    # bölme sıraları kaydırır: birer birer

    # GAP: yakın ama değmeyen açık uçlar
    used = set()
    for a in range(len(open_ends)):
        if open_ends[a] in used:
            continue
        i, e = open_ends[a]
        p = segs[i][1][0 if e == 0 else 3]
        best = None
        for b in range(len(open_ends)):
            if b == a or open_ends[b] in used:
                continue
            j, f = open_ends[b]
            if j == i and len(segs) > 1:
                continue
            q = segs[j][1][0 if f == 0 else 3]
            d = float(np.linalg.norm(p - q))
            if d < near and (best is None or d < best[0]):
                best = (d, (j, f), q)
        if best is not None:
            d, (j, f), q = best
            used |= {(i, e), (j, f)}
            m = (p + q) * 0.5
            out.append({"kind": "GAP", "pts": [m],
                        "msg": f"{name(segs[i][0])} ile {name(segs[j][0])} uçları arasında "
                               f"{_fmt(d)} boşluk. Uçları birleştireyim mi?",
                        "fix": {"op": "weld", "ends": [(segs[i][0], e), (segs[j][0], f)],
                                "to": m}})
    if out:
        return out

    # EXTRA / BRANCH: döngüye katılmayan parçalar
    alive = set(range(len(segs)))
    while True:
        deg = {}
        for i in alive:
            for e in (0, 1):
                deg[of[(i, e)]] = deg.get(of[(i, e)], 0) + 1
        dead = {i for i in alive if deg[of[(i, 0)]] == 1 or deg[of[(i, 1)]] == 1}
        if not dead:
            break
        alive -= dead
    for i in range(len(segs)):
        if i not in alive and alive:
            r, P = segs[i]
            out.append({"kind": "EXTRA", "pts": [samples(P)[N_SAMP // 2]],
                        "msg": f"{name(r)} döngüye katılmıyor (taşan / fazla parça). Seçimden "
                               "çıkarayım mı?",
                        "fix": {"op": "drop", "ref": r}})
    if out:
        return out
    deg = {}
    for i in alive:
        for e in (0, 1):
            deg[of[(i, e)]] = deg.get(of[(i, e)], 0) + 1
    for k, n in deg.items():
        if n > 2:
            out.append({"kind": "BRANCH", "pts": [nodes[k]], "fix": None,
                        "msg": f"Bu köşede {n} kenar buluşuyor: yüzey sınırı tek döngü "
                               "olmalı. Fazla kenarı seçimden çıkar (ya da ayrı yüzey yap)"})
    return out


def split_bez(P, t):
    """de Casteljau: (sol, sağ) 4×3 kontrol noktaları."""
    P = np.asarray(P, dtype=np.float64)
    a = P[:-1] * (1 - t) + P[1:] * t
    b = a[:-1] * (1 - t) + a[1:] * t
    c = b[0] * (1 - t) + b[1] * t
    return np.array([P[0], a[0], b[0], c]), np.array([c, b[1], a[2], P[3]])


def apply_fix(segs, fix, new_ref=None):
    """Onarımı düz veride uygula (test ve önizleme için; Blender'da repair.py aynısını
    eğri verisine yapar). segs: [(ref, P)]. new_ref(ref) → bölünen kenarın 2. yarısının kimliği."""
    segs = [(r, np.asarray(P, dtype=np.float64).copy()) for r, P in segs]
    op = fix["op"]
    if op == "drop":
        return [(r, P) for r, P in segs if r != fix["ref"]]
    if op == "weld":
        for ref, e in fix["ends"]:
            for r, P in segs:
                if r == ref:
                    k = 0 if e == 0 else 3
                    d = np.asarray(fix["to"]) - P[k]
                    P[k] += d
                    P[1 if k == 0 else 2] += d          # tutamaç uçla birlikte
        return segs
    if op == "split":
        out = []
        for r, P in segs:
            if r == fix["ref"]:
                L, R = split_bez(P, fix["t"])
                out += [(r, L), ((new_ref or (lambda x: (x, "b")))(r), R)]
            else:
                out.append((r, P))
        return apply_fix(out, {"op": "weld", "ends": [fix["end"]], "to": fix["to"]})
    raise ValueError(op)


def plan(segs, tol, near=None, names=None, new_ref=None, limit=24):
    """'Hepsini düzelt' yapılırsa sırayla uygulanacak bütün onarımlar (düz veride benzetim).
    İlk adımın sorunları gerçek kimliklerle, sonrakiler benzetimdeki kimliklerle anlatılır.
    Ayrıca sonda düzeltilemeyen (BRANCH gibi) sorunlar da listelenir."""
    segs = [(r, np.asarray(P, dtype=np.float64).reshape(4, 3)) for r, P in segs]
    near = near_for(segs, tol) if near is None else near
    out = []
    for _ in range(limit):
        iss = diagnose(segs, tol, near, names)
        fx = [i for i in iss if i["fix"]]
        if not fx:
            out += [i for i in iss if not i["fix"]]
            break
        out.append(fx[0])
        segs = apply_fix(segs, fx[0]["fix"], new_ref)
    return out


def scan(segs, tol, near=None, names=None, same_curve=None):
    """v0.32.0: bütün tel kafeste (döngü aramadan) gizli uyuşmazlıklar — görünümde fark
    edilmez ama yüzey / fillet / boolean'da sorun çıkarır. diagnose'dan farkı: erken dönmez,
    döngü / dal (EXTRA / BRANCH) aramaz. same_curve(a, b): aynı eğride ardışık mı (ortak uç)."""
    segs = [(r, np.asarray(P, dtype=np.float64).reshape(4, 3)) for r, P in segs]
    if not segs:
        return []
    near = near_for(segs, tol) if near is None else near
    name = (lambda r: names(r)) if names else (lambda r: str(r))
    out = []
    lens = [length(P) for _r, P in segs]
    for i, (r, P) in enumerate(segs):
        if lens[i] < max(near * 0.25, tol * 2):
            out.append({"kind": "TINY", "pts": [P[0]],
                        "msg": f"{name(r)}: çok kısa parça ({_fmt(lens[i])}). Yüzey ve fillet "
                               "bu noktada sorun çıkarır",
                        "fix": {"op": "drop", "ref": r}})
    lo = np.array([P.min(axis=0) for _r, P in segs]) - near
    hi = np.array([P.max(axis=0) for _r, P in segs]) + near
    S = [None] * len(segs)
    for i in range(len(segs)):
        a = segs[i][1]
        if lens[i] <= tol:
            continue                      # sıfır boy parça: TINY'nin işi (çiftlere girmez)
        cand = np.nonzero(np.all(lo[i + 1:] <= hi[i], axis=1) & np.all(hi[i + 1:] >= lo[i], axis=1))[0]
        for j in cand + i + 1:
            b = segs[j][1]
            if lens[j] <= tol:
                continue
            same = (np.linalg.norm(a[0] - b[0]) < near and np.linalg.norm(a[3] - b[3]) < near) \
                or (np.linalg.norm(a[0] - b[3]) < near and np.linalg.norm(a[3] - b[0]) < near)
            if not same:
                continue
            S[i] = S[i] if S[i] is not None else samples(a)
            S[j] = S[j] if S[j] is not None else samples(b)
            dmax = max(float(np.min(np.linalg.norm(S[j] - p, axis=1))) for p in S[i])
            if dmax < near:
                out.append({"kind": "DUP", "pts": [S[j][N_SAMP // 2]],
                            "msg": f"{name(segs[i][0])} ile {name(segs[j][0])} üst üste "
                                   "biniyor: yüzeyde fazla kenar / çift kenar hatası verir",
                            "fix": {"op": "drop", "ref": segs[j][0]}})
    nodes, of = _cluster(segs, tol)
    deg = {}
    for k in of.values():
        deg[k] = deg.get(k, 0) + 1
    open_ends = [(i, e) for (i, e), k in of.items() if deg[k] == 1]
    seen_gap = set()
    for i, e in open_ends:
        p = segs[i][1][0 if e == 0 else 3]
        # GAP: yakın ama kaynamamış uç
        best = None
        for (i2, e2), k in of.items():
            if i2 == i:
                continue
            q = segs[i2][1][0 if e2 == 0 else 3]
            d = float(np.linalg.norm(p - q))
            if tol < d < near and (best is None or d < best[0]):
                best = (d, (i2, e2), q)
        if best is not None:
            d, (j, f), q = best
            key = tuple(sorted([(i, e), (j, f)]))
            if key not in seen_gap:
                seen_gap.add(key)
                m = (p + q) * 0.5 if deg[of[(j, f)]] == 1 else q
                out.append({"kind": "GAP", "pts": [m],
                            "msg": f"{name(segs[i][0])} ucu {name(segs[j][0])} ucuna "
                                   f"{_fmt(d)} yakın ama değmiyor: yüzey kurarken döngü "
                                   "kapanmaz",
                            "fix": {"op": "weld", "ends": [(segs[i][0], e)] +
                                    ([(segs[j][0], f)] if deg[of[(j, f)]] == 1 else []),
                                    "to": m}})
            continue
        # TJUNC: kenarın ortasına değen uç (kenarda nokta yok)
        for j, (rj, Pj) in enumerate(segs):
            if j == i or not (np.all(lo[j] <= p) and np.all(p <= hi[j])):
                continue
            if min(np.linalg.norm(p - Pj[0]), np.linalg.norm(p - Pj[3])) < near:
                continue
            t, d, q = closest(Pj, p)
            if d < near and 0.01 < t < 0.99:
                out.append({"kind": "TJUNC", "pts": [q],
                            "msg": f"{name(segs[i][0])} ucu {name(rj)} kenarının ortasına "
                                   "bağlı ama orada nokta yok: yüzeyler burada dikişsiz "
                                   "birleşmez, yüzey kurulamayabilir",
                            "fix": {"op": "split", "ref": rj, "t": t, "to": q,
                                    "end": (segs[i][0], e)}})
                break
    return out
