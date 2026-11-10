"""Teğet kısıtı planlaması (Inventor benzeri): ortak uç bulma, doğru / yay tarafı seçimi,
tutamaç yönü, yay koşusu, "arcslide" (yay çemberi korunur, birleşim çember üzerinde kayar,
doğru öteler / kısalır) ve çözücüye verilecek plan. Yalnızca constraints.solve_all çağırır.
"""

import math
import numpy as np
from mathutils import Vector

from . import core
from .constraints_refs import _last_pos, _npts, _spline, _world, all_constraints, ref_points


DIR_KINDS = {"AXIS", "PARALLEL", "PERP", "COLLINEAR", "ANGLE"}


def _seg_straight(ob, si, seg):
    sp = _spline(ob, si)
    if sp.type != "BEZIER":
        return True
    n = len(sp.bezier_points)
    a, b = sp.bezier_points[seg], sp.bezier_points[(seg + 1) % n]
    if a.handle_right_type == "VECTOR" and b.handle_left_type == "VECTOR":
        return True
    P = np.array([tuple(a.co), tuple(a.handle_right), tuple(b.handle_left), tuple(b.co)])
    d = P[3] - P[0]
    L = float(np.linalg.norm(d))
    if L < 1e-12:
        return False
    d /= L
    off = P - P[0]
    return float(np.linalg.norm(off - np.outer(off @ d, d), axis=1).max()) <= 1e-6 * L + 1e-9


def _side(ob, si, k):
    """Spline'ın k. noktası bir uçsa / birleşimse: o noktaya bağlı segment(ler)in bilgisi."""
    sp = _spline(ob, si)
    n = _npts(sp)
    nseg = core._seg_count(sp)
    out = []
    if k < nseg:                                   # k'dan çıkan segment
        out.append({"seg": k, "far": (k + 1) % n, "hand": "R"})
    if k > 0 or sp.use_cyclic_u:                   # k'ya giren segment
        s = (k - 1) % n
        if s < nseg:
            out.append({"seg": s, "far": s, "hand": "L"})
    return out


def _joint(c):
    """Teğet kısıtının iki kenarının birleştiği nokta (farklı eğrilerde de olabilir).
    Seçilen segment birleşime değmiyorsa aynı eğrinin uç noktalarına bakılır."""
    ra, rb = c.refs[0], c.refs[1]
    for r in (ra, rb):
        if ref_points(r.obj, r.spline, r.index, False) is None:
            return None, "referans kayboldu"

    def cands(r):
        sp = _spline(r.obj, r.spline)
        n = _npts(sp)
        ks = [r.index, (r.index + 1) % n]
        if not sp.use_cyclic_u:
            ks += [0, n - 1]
        return list(dict.fromkeys(ks))

    best = None
    for ka in cands(ra):
        pa = _world(ra.obj, ra.spline, ka)
        for kb in cands(rb):
            if ra.obj == rb.obj and ra.spline == rb.spline and ka != kb:
                continue
            pb = _world(rb.obj, rb.spline, kb)
            d = float(np.linalg.norm(pa - pb))
            tol = 1e-6 * (1.0 + float(np.abs(pa).max()))
            if d <= tol and (best is None or d < best[0]):
                best = (d, ka, kb)
    if best is None:
        return None, "kenarlar ortak bir uçta birleşmiyor (önce uçları Çakışık yap)"
    return (best[1], best[2]), ""


def _pick_side(r, k):
    """Birleşim noktasında, seçilen segmente en yakın bağlı segment."""
    sides = _side(r.obj, r.spline, k)
    if not sides:
        return None
    for sd in sides:
        if sd["seg"] == r.index:
            return sd
    return sides[0]


def _handle_vec(ob, si, k, hand):
    bp = _spline(ob, si).bezier_points[k]
    h = bp.handle_right if hand == "R" else bp.handle_left
    mw = ob.matrix_world
    return np.array(mw @ h) - np.array(mw @ bp.co)


def _set_handle_dir(ob, si, k, hand, direction):
    """Eğrinin birleşimdeki tutamacını verilen dünya yönüne çevirir (boyu korunur)."""
    sp = _spline(ob, si)
    if sp.type != "BEZIER":
        return False
    bp = sp.bezier_points[k]
    mw = ob.matrix_world
    cur = _handle_vec(ob, si, k, hand)
    L = float(np.linalg.norm(cur))
    d = direction / max(float(np.linalg.norm(direction)), 1e-15)
    if L < 1e-12:
        return False
    if float(np.linalg.norm(cur / L - d)) < 1e-9:
        return False
    world = np.array(mw @ bp.co) + d * L
    local = mw.inverted() @ Vector(tuple(world))
    attr = "handle_right" if hand == "R" else "handle_left"
    typ = attr + "_type"
    if getattr(bp, typ) in ("VECTOR", "AUTO"):
        setattr(bp, typ, "FREE")
    setattr(bp, attr, local)
    return True


def _line_constrained(scene, r):
    for ob, _i, c in all_constraints(scene):
        if not c.enabled or c.kind not in DIR_KINDS:
            continue
        for x in c.refs:
            if not x.point and x.obj == r.obj and x.spline == r.spline and x.index == r.index:
                return True
    return False


def _bez(ob, si, a, b, forward):
    """a'dan b'ye giden segmentin dünya koordinatında 4 kontrol noktası."""
    sp = _spline(ob, si)
    mw = ob.matrix_world
    pa, pb = sp.bezier_points[a], sp.bezier_points[b]
    ha = pa.handle_right if forward else pa.handle_left
    hb = pb.handle_left if forward else pb.handle_right
    return [np.array(mw @ v) for v in (pa.co, ha, hb, pb.co)]


def _arc_run(ob, si, k, hand):
    """Birleşim noktası k'dan başlayıp eğrinin içine doğru giden, aynı çembere ait ardışık
    yay segmentleri. {"idx": [k, ..., B], "fwd", "c", "R", "n"} ya da yay değilse None."""
    from . import drawmath as dm
    sp = _spline(ob, si)
    if sp.type != "BEZIER" or sp.use_cyclic_u:
        return None
    n = len(sp.bezier_points)
    fwd = hand == "R"
    idx = [k]
    arc = None
    while True:
        a = idx[-1]
        b = a + 1 if fwd else a - 1
        if not (0 <= b < n):
            break
        P = _bez(ob, si, a, b, fwd)
        cur = dm.arc_of_bezier(P)
        if cur is None:
            break
        if arc is None:
            arc = cur
        elif np.linalg.norm(cur[0] - arc[0]) > 1e-4 * arc[1] or \
                abs(cur[1] - arc[1]) > 1e-4 * arc[1]:
            break
        idx.append(b)
    if arc is None or len(idx) < 2:
        return None
    return {"idx": idx, "fwd": fwd, "c": arc[0], "R": arc[1], "n": arc[2]}


def _set_world(ob, bp, attr, p):
    setattr(bp, attr, ob.matrix_world.inverted() @ Vector(tuple(float(x) for x in p)))


def _arc_slide(rl, kl, far, rc, run):
    """Inventor gibi teğet: yay ÇEMBERİ korunur (merkez ve yarıçap aynı kalır), birleşim
    noktası çember üzerinde doğrunun yönüne teğet olan yere kayar; yay o noktadan diğer
    ucuna kadar yeniden kurulur. Doğru aynı yönde kalır: ucu birleşimle gider, boyu ve
    konumu değişir. (değişti mi, bilgi)"""
    from . import drawmath as dm
    J = _world(rl.obj, rl.spline, kl)
    F = _world(rl.obj, rl.spline, far)
    d = J - F
    L = float(np.linalg.norm(d))
    if L < 1e-12:
        return False, "doğru sıfır uzunlukta"
    d /= L
    C, R, nrm = run["c"], run["R"], run["n"]
    if abs(float(np.dot(d, nrm))) > 1e-3:
        return None, "doğru yayın düzleminde değil"
    w = dm.unit(np.cross(nrm, d))
    cands = [C + R * w, C - R * w]
    T = min(cands, key=lambda q: float(np.linalg.norm(q - J)))
    tol = 1e-7 * (1.0 + float(np.abs(C).max()) + R)
    if float(np.linalg.norm(T - J)) <= tol:
        return False, ""
    ob, si = rc.obj, rc.spline
    sp = _spline(ob, si)
    idx, fwd = run["idx"], run["fwd"]
    B = _world(ob, si, idx[-1])
    P0 = _bez(ob, si, idx[0], idx[1], fwd)
    v0, v1 = P0[0] - C, 0.125 * (P0[0] + 3 * P0[1] + 3 * P0[2] + P0[3]) - C
    ndir = nrm if float(np.dot(np.cross(v0, v1), nrm)) >= 0 else -nrm
    e1 = (T - C) / R
    e2 = np.cross(ndir, e1)
    bv = B - C
    theta = math.atan2(float(np.dot(np.cross(e1, bv), ndir)), float(np.dot(e1, bv)))
    theta %= 2 * math.pi
    if theta < 1e-6:
        return None, "birleşim yayın öbür ucuna kaydı; yay çok kısa"
    k = len(idx) - 1
    segs = dm._arc_from_basis(C, R, e1, e2, theta, T, B, max_angle=theta / k + 1e-9)
    if len(segs) != k:
        return None, "yay yeniden kurulamadı"
    bps = sp.bezier_points
    saved = [(bps[i].handle_left_type, bps[i].handle_right_type) for i in idx]
    for i in idx:
        bps[i].handle_left_type = "FREE"
        bps[i].handle_right_type = "FREE"
    out_h = "handle_right" if fwd else "handle_left"
    in_h = "handle_left" if fwd else "handle_right"
    same_point = rl.obj == rc.obj and rl.spline == rc.spline and kl == idx[0]
    for j, sg in enumerate(segs):
        A, h1, h2, Bj = sg["p"]
        pa, pb = bps[idx[j]], bps[idx[j + 1]]
        _set_world(ob, pa, "co", A)
        _set_world(ob, pa, out_h, h1)
        _set_world(ob, pb, in_h, h2)
        if j == 0 and not same_point:            # çizgi ucu: kullanılmayan tutamaç ayna
            _set_world(ob, pa, in_h, 2 * A - h1)
    for i, (tl, tr) in zip(idx, saved):
        bps[i].handle_left_type = "ALIGNED" if tl == "FREE" else tl
        bps[i].handle_right_type = "ALIGNED" if tr == "FREE" else tr
    if same_point:
        bps[idx[0]].handle_left_type, bps[idx[0]].handle_right_type = saved[0]
    # doğru: aynı yönde kalır, ortak ucu T'ye gider, uzak ucu sadece yana kayar
    delta = T - J
    perp = delta - np.dot(delta, d) * d
    lsp = _spline(rl.obj, rl.spline)
    for pi, target in ((kl, T), (far, F + perp)):
        if same_point and pi == kl:
            continue
        if lsp.type == "BEZIER":
            bp = lsp.bezier_points[pi]
            old = np.array(rl.obj.matrix_world @ bp.co)
            dl = Vector(tuple(target - old))
            mwi3 = rl.obj.matrix_world.inverted().to_3x3()
            _set_world(rl.obj, bp, "co", target)
            if bp.handle_left_type in ("FREE", "ALIGNED"):
                bp.handle_left = bp.handle_left + mwi3 @ dl
            if bp.handle_right_type in ("FREE", "ALIGNED"):
                bp.handle_right = bp.handle_right + mwi3 @ dl
        else:
            q = rl.obj.matrix_world.inverted() @ Vector(tuple(target))
            lsp.points[pi].co = (q.x, q.y, q.z, lsp.points[pi].co[3])
    for o, sidx, pis in ((ob, si, idx), (rl.obj, rl.spline, [kl, far])):
        for pi in pis:
            _last_pos[(o.name, sidx, pi)] = _world(o, sidx, pi)
    for o in {ob.name: ob, rl.obj.name: rl.obj}.values():
        try:
            o.data.update_tag()
        except Exception:
            pass
    return True, ""


def _tangent_plan(c, scene):
    """Teğet kısıtını uygulama planı:
      ("same", fn)          aynı eğride komşu: tutamaç türleri hizalı yapılır
      ("tline", pts, dir)   doğru, eğrinin teğetine döndürülür (eğri / yay bozulmaz)
      ("handle", fn)        eğrinin tutamacı doğruya / öbür eğriye hizalanır
    ya da (None, hata)."""
    if len(c.refs) != 2 or c.refs[0].point or c.refs[1].point:
        return None, "iki kenar gerekli"
    j, why = _joint(c)
    if j is None:
        return None, why
    ka, kb = j
    ra, rb = c.refs[0], c.refs[1]
    same_pt = ra.obj == rb.obj and ra.spline == rb.spline and ka == kb
    if same_pt:
        sp = _spline(ra.obj, ra.spline)
        if sp.type != "BEZIER":
            return None, "bezier çizgi gerekli"
        _sa, _sb = _pick_side(ra, ka), _pick_side(rb, kb)
        if _sa is not None and _sb is not None and _sa["seg"] != _sb["seg"]:
            _la = _seg_straight(ra.obj, ra.spline, _sa["seg"])
            _lb = _seg_straight(rb.obj, rb.spline, _sb["seg"])
            if _la != _lb:
                same_pt = False                  # doğru + yay: genel (Inventor gibi) yol
    if same_pt:

        def same():
            bp = sp.bezier_points[ka]
            if (bp.handle_left_type, bp.handle_right_type) == ("VECTOR", "VECTOR"):
                return False, "iki düz doğru teğet olamaz; Doğrusal kısıtını kullan"
            if bp.handle_left_type != "VECTOR" and bp.handle_left_type != "ALIGNED":
                bp.handle_left_type = "ALIGNED"
            if bp.handle_right_type != "VECTOR" and bp.handle_right_type != "ALIGNED":
                bp.handle_right_type = "ALIGNED"
            return True, ""
        return ("same", same), ""
    sa, sb = _pick_side(ra, ka), _pick_side(rb, kb)
    if sa is None or sb is None:
        return None, "birleşimde segment bulunamadı"
    la = _seg_straight(ra.obj, ra.spline, sa["seg"])
    lb = _seg_straight(rb.obj, rb.spline, sb["seg"])
    if la and lb:
        return None, "iki düz doğru teğet olamaz; Doğrusal kısıtını kullan"
    if la != lb:
        (rl, kl, sl), (rc, kc, scv) = ((ra, ka, sa), (rb, kb, sb)) if la else \
            ((rb, kb, sb), (ra, ka, sa))
        if _spline(rc.obj, rc.spline).type != "BEZIER":
            return None, "eğri bezier olmalı"
        tdir = _handle_vec(rc.obj, rc.spline, kc, scv["hand"])
        if float(np.linalg.norm(tdir)) < 1e-12:
            return None, "eğrinin uçtaki tutamacı sıfır uzunlukta"
        line_ref = type("R", (), {"obj": rl.obj, "spline": rl.spline, "index": sl["seg"]})
        run = _arc_run(rc.obj, rc.spline, kc, scv["hand"])
        if run is not None and _line_constrained(scene, line_ref):
            def slide():
                ch, info = _arc_slide(rl, kl, sl["far"], rc, run_now())
                if ch is None:            # yaya uygun değilse eski yöntem
                    d = _world(rl.obj, rl.spline, kl) - _world(rl.obj, rl.spline, sl["far"])
                    _set_handle_dir(rc.obj, rc.spline, kc, scv["hand"], d)
                    return True, info + "; eğrinin ucu doğruya uyduruldu"
                return True, ""

            def run_now():
                return _arc_run(rc.obj, rc.spline, kc, scv["hand"]) or run
            return ("handle", slide), ""
        if not _line_constrained(scene, line_ref):
            pts = [(rl.obj, rl.spline, kl), (rl.obj, rl.spline, sl["far"])]
            keep = [(rc.obj.name, rc.spline, kc)]          # yayın ucu yerinde kalsın
            if run is not None:
                keep += [(rc.obj.name, rc.spline, i) for i in run["idx"]]
            return ("tline", pts, tdir, keep), ""

        def adapt():
            d = _world(rl.obj, rl.spline, kl) - _world(rl.obj, rl.spline, sl["far"])
            _set_handle_dir(rc.obj, rc.spline, kc, scv["hand"], d)
            return True, "doğru başka kısıtlara bağlı: eğrinin ucu doğruya uyduruldu"
        return ("handle", adapt), ""

    def curves():
        ta = _handle_vec(ra.obj, ra.spline, ka, sa["hand"])
        if float(np.linalg.norm(ta)) < 1e-12:
            return False, "eğrinin uçtaki tutamacı sıfır uzunlukta"
        _set_handle_dir(rb.obj, rb.spline, kb, sb["hand"], -ta)
        return True, ""
    return ("handle", curves), ""
