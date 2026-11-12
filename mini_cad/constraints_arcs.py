"""Yay kısıtları (v0.19.0, Inventor 2D Aşama 4):

  RADIUS      yarıçap / çap ölçüsü (daire: çap gösterilir, değer hep yarıçap saklanır)
  CONCENTRIC  iki yay / daire eş merkezli
  SMOOTH      pürüzsüz (G2): teğet + birleşimde eğrilik eşit (en az biri spline olmalı)

Yay merkezi çözücüye SANAL bir nokta olarak eklenir (constraints.solve_all); yayın düğümleri
merkeze RADIUSN / EQDIST denklemleriyle bağlanır, böylece diğer kısıtlarla birlikte çözülür.
Çözümden sonra yayın tutamaçları yeni merkez ve uçlardan tam çember yayı olarak yeniden
kurulur (rebuild_group). Yay grubu: aynı çembere ait ardışık yay segmentleri (daire: hepsi).
"""

import math

import numpy as np
from mathutils import Vector

from . import core
from . import drawmath as dm
from .constraints_refs import _npts, _spline, _world


def seg_bez(ob, si, i):
    """i. segmentin dünya koordinatında 4 kontrol noktası (ileri yön)."""
    sp = _spline(ob, si)
    n = _npts(sp)
    mw = ob.matrix_world
    a, b = sp.bezier_points[i], sp.bezier_points[(i + 1) % n]
    return [np.array(mw @ v) for v in (a.co, a.handle_right, b.handle_left, b.co)]


def arc_group(ob, si, i):
    """i. segmentin ait olduğu yay grubu ya da None (yay değilse).
    {"segs": [...], "nodes": [...], "c", "R", "n", "closed"}"""
    sp = _spline(ob, si) if ob is not None else None
    if sp is None or sp.type != "BEZIER":
        return None
    nseg = core._seg_count(sp)
    if not (0 <= i < nseg):
        return None
    arc = dm.arc_of_bezier(seg_bez(ob, si, i))
    if arc is None:
        return None
    c, R, nn = arc
    tol = 1e-5 * (1.0 + R)

    def same(j):
        a = dm.arc_of_bezier(seg_bez(ob, si, j))
        return a is not None and np.linalg.norm(a[0] - c) <= tol and abs(a[1] - R) <= tol and \
            float(np.dot(a[2], nn)) > 0.999

    cyc = sp.use_cyclic_u
    segs = [i]
    j = i
    while True:                          # ileri
        j2 = j + 1
        if j2 >= nseg:
            if not cyc:
                break
            j2 = 0
        if j2 in segs or not same(j2):
            break
        segs.append(j2)
        j = j2
    j = i
    while True:                          # geri
        j2 = j - 1
        if j2 < 0:
            if not cyc:
                break
            j2 = nseg - 1
        if j2 in segs or not same(j2):
            break
        segs.insert(0, j2)
        j = j2
    n = _npts(sp)
    nodes = []
    for s in segs:
        for k in (s, (s + 1) % n):
            if k not in nodes:
                nodes.append(k)
    closed = cyc and len(segs) == nseg
    pos = [_world(ob, si, k) for k in nodes]
    return {"segs": segs, "nodes": nodes, "c": c, "R": R, "n": nn, "closed": closed, "pos": pos}


def _ang(v, e1, e2):
    return math.atan2(float(np.dot(v, e2)), float(np.dot(v, e1)))


def _respace(g, P, C):
    """Çözümden sonra düğümler çember boyunca kaymış olabilir: daire düğümleri eski açı
    aralıklarıyla, açık yayın ara düğümleri eski oranlarla yeniden yerleştirilir (uçlar
    çözümde kalır). Yeni konumlar listesi."""
    nn = dm.unit(g["n"])
    c0 = np.asarray(g["c"], dtype=np.float64)
    O = [np.asarray(q, dtype=np.float64) - c0 for q in g["pos"]]
    if len(P) < 3 or float(np.linalg.norm(O[0])) < 1e-12:
        return P
    f1 = O[0] / np.linalg.norm(O[0])
    f2 = np.cross(nn, f1)
    oa = [(_ang(o, f1, f2)) % (2 * math.pi) for o in O]
    V = [p - C - nn * float(np.dot(p - C, nn)) for p in P]
    if float(np.linalg.norm(V[0])) < 1e-12:
        return P
    e1 = V[0] / np.linalg.norm(V[0])
    e2 = np.cross(nn, e1)
    h0 = float(np.dot(P[0] - C, nn))
    if g["closed"]:
        R = float(np.mean([np.linalg.norm(v) for v in V]))
        out = [P[0]]
        for a in oa[1:]:
            out.append(C + nn * h0 + R * (math.cos(a) * e1 + math.sin(a) * e2))
        return out
    total0 = oa[-1] if oa[-1] > 1e-9 else oa[-1] + 2 * math.pi
    total = _ang(V[-1], e1, e2) % (2 * math.pi)
    if total <= 1e-9:
        total += 2 * math.pi
    R = 0.5 * (float(np.linalg.norm(V[0])) + float(np.linalg.norm(V[-1])))
    out = [P[0]]
    for a in oa[1:-1]:
        t = (a / total0) * total
        out.append(C + nn * h0 + R * (math.cos(t) * e1 + math.sin(t) * e2))
    return out + [P[-1]]


def rebuild_group(ob, si, g, C):
    """Grubun yaylarını yeni merkez C ve (çözülmüş) düğüm konumlarından yeniden kurar.
    Yön ve dönüş ekseni korunur. Değişiklik yoksa yazmaz."""
    sp = _spline(ob, si)
    n = _npts(sp)
    nn = dm.unit(g["n"])
    mwi = ob.matrix_world.inverted()
    changed = False
    C = np.asarray(C, dtype=np.float64)
    if "pos" in g:                            # çember boyunca kaymış düğümleri düzelt
        P = [_world(ob, si, k) for k in g["nodes"]]
        Q = _respace(g, P, C)
        for k, p, q in zip(g["nodes"], P, Q):
            if float(np.linalg.norm(p - q)) > 1e-12 * (1.0 + float(np.abs(q).max())):
                sp.bezier_points[k].co = mwi @ Vector(tuple(q))
                changed = True
    for s in g["segs"]:
        ia, ib = s, (s + 1) % n
        a, b = _world(ob, si, ia), _world(ob, si, ib)
        va, vb = a - C, b - C
        va = va - nn * float(np.dot(va, nn))
        vb = vb - nn * float(np.dot(vb, nn))
        Ra, Rb = float(np.linalg.norm(va)), float(np.linalg.norm(vb))
        if Ra < 1e-12 or Rb < 1e-12:
            continue
        R = 0.5 * (Ra + Rb)
        e1 = va / Ra
        e2 = np.cross(nn, e1)
        th = math.atan2(float(np.dot(vb, e2)), float(np.dot(vb, e1)))
        if th <= 1e-9:
            th += 2 * math.pi
        h = 4.0 / 3.0 * math.tan(th / 4.0) * R
        ta = np.cross(nn, va / Ra)
        tb = np.cross(nn, vb / Rb)
        hr, hl = a + ta * h, b - tb * h
        bpa, bpb = sp.bezier_points[ia], sp.bezier_points[ib]
        old_r = np.array(ob.matrix_world @ bpa.handle_right)
        old_l = np.array(ob.matrix_world @ bpb.handle_left)
        tol = 1e-9 * (1.0 + R)
        if np.linalg.norm(old_r - hr) > tol:
            if bpa.handle_right_type in ("VECTOR", "AUTO", "AUTO_CLAMPED"):
                bpa.handle_right_type = "FREE"
            bpa.handle_right = mwi @ Vector(tuple(hr))
            changed = True
        if np.linalg.norm(old_l - hl) > tol:
            if bpb.handle_left_type in ("VECTOR", "AUTO", "AUTO_CLAMPED"):
                bpb.handle_left_type = "FREE"
            bpb.handle_left = mwi @ Vector(tuple(hl))
            changed = True
    if changed:
        try:
            ob.data.update_tag()
        except Exception:
            pass
    return changed


def group_key(ob, si, g):
    return ("@c", ob.name, si, min(g["segs"]))


def radius_of(c):
    """Yarıçap kısıtının ölçtüğü yayın şu anki yarıçapı (yoksa None)."""
    if not len(c.refs):
        return None
    r = c.refs[0]
    g = arc_group(r.obj, r.spline, r.index)
    return None if g is None else g["R"]


def center_dist_value(c):
    """Merkez mesafesi: yay–yay merkezleri, yay merkezi–nokta, yay merkezi–doğru."""
    if len(c.refs) != 2:
        return None
    ra, rb = c.refs[0], c.refs[1]
    ga = arc_group(ra.obj, ra.spline, ra.index) if not ra.point else None
    if ga is None:
        return None
    if not rb.point:
        gb = arc_group(rb.obj, rb.spline, rb.index)
        if gb is not None:
            return float(np.linalg.norm(ga["c"] - gb["c"]))
        P = seg_bez(rb.obj, rb.spline, rb.index)
        d = dm.unit(P[3] - P[0])
        if d is None:
            return None
        return float(np.linalg.norm(np.cross(ga["c"] - P[0], d)))
    return float(np.linalg.norm(ga["c"] - _world(rb.obj, rb.spline, rb.index)))


def centers_dist(c):
    gs = [arc_group(r.obj, r.spline, r.index) for r in c.refs]
    if len(gs) != 2 or None in gs:
        return None
    return float(np.linalg.norm(gs[0]["c"] - gs[1]["c"]))


# ---------------------------------------------------------------- pürüzsüz (G2)

def _oriented(ob, si, seg, at_start):
    """Segmenti birleşimden dışarı doğru yönlendirilmiş 4 nokta ve yazılacak tutamaç."""
    P = seg_bez(ob, si, seg)
    sp = _spline(ob, si)
    n = _npts(sp)
    if at_start:
        return P, (seg + 1) % n, "handle_left"
    return P[::-1], seg, "handle_right"


def _curv_vec(Q):
    """Q0'daki eğrilik vektörü (yöne bağlı değil)."""
    d1 = 3.0 * (Q[1] - Q[0])
    d2 = 6.0 * (Q[2] - 2.0 * Q[1] + Q[0])
    L2 = float(np.dot(d1, d1))
    if L2 < 1e-24:
        return None
    t = d1 / math.sqrt(L2)
    return (d2 - t * float(np.dot(d2, t))) / L2


def _kind(Q):
    if dm.is_straight_poly(np.array([np.asarray(q) for q in Q])):
        return "line"
    return "arc" if dm.arc_of_bezier(Q) is not None else "curve"


def smooth_post(c, joint):
    """Teğetlikten SONRA çalışır: serbest spline'ın birleşimdeki eğriliği komşusununkine
    eşitlenir (2. kontrol noktası teğete dik yönde ayarlanır). (değişti mi / ok, bilgi)"""
    if joint is None:
        return False, "kenarlar ortak bir uçta birleşmiyor"
    ka, kb = joint
    sides = []
    for r, k in ((c.refs[0], ka), (c.refs[1], kb)):
        sp = _spline(r.obj, r.spline)
        if sp is None or sp.type != "BEZIER":
            return False, "bezier çizgi gerekli"
        n = _npts(sp)
        if r.index == k:
            at_start = True
        elif (r.index + 1) % n == k:
            at_start = False
        else:
            return False, "seçilen kenar birleşime değmiyor"
        Q, bi, attr = _oriented(r.obj, r.spline, r.index, at_start)
        sides.append((r, Q, bi, attr, _kind(Q)))
    free = [s for s in sides if s[4] == "curve"]
    if not free:
        return False, "pürüzsüz için en az bir kenar spline olmalı (doğru / yay eğriliği sabit)"
    tgt = free[-1]
    other = sides[0] if tgt is sides[1] else sides[1]
    kv = _curv_vec(other[1])
    if kv is None:
        return False, "eğrilik hesaplanamadı"
    r, Q, bi, attr, _ = tgt
    t = dm.unit(Q[1] - Q[0])
    if t is None:
        return False, "tutamaç sıfır boylu"
    kv = kv - t * float(np.dot(kv, t))
    L = float(np.linalg.norm(Q[1] - Q[0]))
    W = Q[2] - 2.0 * Q[1] + Q[0]
    W_new = t * float(np.dot(W, t)) + kv * 1.5 * L * L
    Q2 = W_new + 2.0 * Q[1] - Q[0]
    if float(np.linalg.norm(Q2 - Q[2])) <= 1e-9 * (1.0 + float(np.abs(Q2).max())):
        return True, ""
    sp = _spline(r.obj, r.spline)
    bp = sp.bezier_points[bi]
    tattr = attr + "_type"
    if getattr(bp, tattr) in ("VECTOR", "AUTO", "AUTO_CLAMPED"):
        setattr(bp, tattr, "FREE")
    setattr(bp, attr, r.obj.matrix_world.inverted() @ Vector(tuple(Q2)))
    try:
        r.obj.data.update_tag()
    except Exception:
        pass
    return True, ""
