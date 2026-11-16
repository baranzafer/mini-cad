"""Profil Süpürme (v0.26.0) — Inventor "Süpür" (Sweep) mantığı.

Bir PROFİL (düzlemsel eğri: yay, kıvrım, herhangi bir kapalı / açık şekil) bir YOL (gövde
kenarı, boolean'ın oluşturduğu kenar ya da tel kafes eğrisi) boyunca süpürülür; çıkan katı
gövdeye boolean olarak uygulanır: Çıkar (pah / oyma / yontma), Birleştir (pervaz / kabartma),
Kesişim. Fillet'in kuramadığı kenarlarda istenen kesit elle verilebilir.

Profilin yerleşimi:
  * AUTO (Yolun başına yerleştir): profil kendi düzleminde çizilir. Profil objesinin
    ORİJİNİ yolun başlangıç noktasına, profil düzlemi yola DİK düzleme oturur.
    Profilin +Y ekseni dışarıyı gösterir: gövde kenarında iki yan yüzün açıortayı (gövdeden
    dışarı), değilse dünya +Z'ye en yakın dik yön. +X onlara dik. Açı / kaydırma / ölçek /
    aynalama ile ince ayar yapılır.
  * KEEP (Olduğu yerde): profil çizildiği yerde süpürülür (Inventor'daki gibi profil yolun
    başında, yola dik çizilmiş olmalı).
Açık profil kapatma: NONE (kapalı olmalı), CHORD (uçlar düz çizgiyle — oluk / kanal),
ORIGIN (dışarıdan: uçlar +Y yönünde köşenin üstüne çıkıp birleşir — köşe pahı / yuvarlatma /
yontma için; araç köşeyi kapsar, yan çizgileri gövde yüzeyleriyle çakışmaz).
Kapalı profil gövdenin dışına biraz taşmalı: yüzeyle tam çakışan araç yüzleri (özellikle
eğrisel yüzlerde) boolean'ı bozar.
Açık yol iki uçtan teğet doğrultusunda UZATILIR: kesim kenarın bittiği yüzleri temiz geçer
(çakışık uç yüzleri boolean'ı zorlamaz).

Bu modül bpy KULLANMAZ (hesap sürecinde çalışır).
"""

import math

import numpy as np

from . import geometry as g
from .errors import CadError

from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace,
                                BRepBuilderAPI_MakeWire)
from OCP.Geom import Geom_BezierCurve
from OCP.gp import gp_Pnt

_MakePipe = g._optional("OCP.BRepOffsetAPI", "BRepOffsetAPI_MakePipe")
_MakePipeShell = g._optional("OCP.BRepOffsetAPI", "BRepOffsetAPI_MakePipeShell")
_Trihedron = g._optional("OCP.GeomFill", "GeomFill_Trihedron")
_GeomAbs_C2 = g._optional("OCP.GeomAbs", "GeomAbs_C2")
_Transition = g._optional("OCP.BRepBuilderAPI", "BRepBuilderAPI_TransitionMode")
_ThruSections = g._optional("OCP.BRepOffsetAPI", "BRepOffsetAPI_ThruSections")
G1_DEG = 12.0          # yol parçaları arasında bundan büyük kırılma = keskin köşe (koşu böl)

MODEL = "Model kaynaklı: "


def _np(p):
    return np.asarray(p, dtype=np.float64)


def _unit(v):
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-12 else None


def _bez(P, t):
    P = _np(P)
    if len(P) == 2:
        return P[0] + (P[1] - P[0]) * t
    s = 1.0 - t
    return s ** 3 * P[0] + 3 * s * s * t * P[1] + 3 * s * t * t * P[2] + t ** 3 * P[3]


def _samples(piece, n=32):
    kind, P = piece
    if kind == "pts":
        return _np(P)
    return np.array([_bez(P, t) for t in np.linspace(0.0, 1.0, n)])


def _rev(piece):
    kind, P = piece
    return kind, _np(P)[::-1]


def chain_pieces(pieces, tol):
    """Parçaları uç uca dizer, gerekirse ters çevirir. ([parça], kapalı mı, kopuk parça sayısı)."""
    if not pieces:
        return [], False, 0
    left = [(k, _np(P)) for k, P in pieces]
    ends = lambda pc: (_np(pc[1][0]), _np(pc[1][-1]))
    # açık zincirde başlangıç: ucu başka hiçbir parçaya değmeyen parça
    start = 0
    for i, pc in enumerate(left):
        a, _b = ends(pc)
        touch = any(np.linalg.norm(a - q) <= tol for j, o in enumerate(left) if j != i
                    for q in ends(o))
        if not touch:
            start = i
            break
    out = [left.pop(start)]
    if len(out[0]) and left:
        # başlangıç parçasının serbest ucu başta olsun
        a, b = ends(out[0])
        if any(np.linalg.norm(a - q) <= tol for o in left for q in ends(o)) and \
                not any(np.linalg.norm(b - q) <= tol for o in left for q in ends(o)):
            out[0] = _rev(out[0])
    while left:
        tail = ends(out[-1])[1]
        k = None
        for i, pc in enumerate(left):
            a, b = ends(pc)
            if np.linalg.norm(a - tail) <= tol:
                k, flip = i, False
                break
            if np.linalg.norm(b - tail) <= tol:
                k, flip = i, True
                break
        if k is None:
            break
        pc = left.pop(k)
        out.append(_rev(pc) if flip else pc)
    closed = np.linalg.norm(ends(out[0])[0] - ends(out[-1])[1]) <= tol
    return out, bool(closed), len(left)


def _edge(piece):
    kind, P = piece
    P = _np(P)
    if kind == "bez" and (len(P) == 2 or g.is_straight(P)):
        a, b = P[0], P[-1]
        if np.linalg.norm(b - a) < 1e-12:
            raise CadError(MODEL + "sıfır uzunlukta parça")
        me = BRepBuilderAPI_MakeEdge(gp_Pnt(*map(float, a)), gp_Pnt(*map(float, b)))
    elif kind == "bez":
        me = BRepBuilderAPI_MakeEdge(Geom_BezierCurve(g._pnt_array(P)))
    else:
        if g._PointsToBSpline is None:
            raise CadError("Bu OCP sürümünde eğri uydurma yok")
        # yoğun örnekten seyreltilmiş noktalar: uydurma hızlı ve pürüzsüz
        step = max(1, len(P) // 48)
        Q = np.vstack([P[::step], P[-1:]]) if (len(P) - 1) % step else P[::step]
        fit = g._PointsToBSpline(g._pnt_array(Q), 3, 8, _GeomAbs_C2, 1e-6)
        me = BRepBuilderAPI_MakeEdge(fit.Curve())
    if not me.IsDone():
        raise CadError("Kenar oluşturulamadı")
    return me.Edge()


def _wire(edges):
    mw = BRepBuilderAPI_MakeWire()
    for e in edges:
        mw.Add(e)
    if not mw.IsDone():
        raise CadError(MODEL + "parçalar tek bir tel oluşturmuyor (uçlar birbirine değmiyor)")
    return mw.Wire()


def _end_tangent(piece, at_end):
    S = _samples(piece, 64)
    if at_end:
        for k in range(2, len(S)):
            d = _unit(S[-1] - S[-k])
            if d is not None:
                return d
    else:
        for k in range(1, len(S) - 1):
            d = _unit(S[k] - S[0])
            if d is not None:
                return d
    raise CadError(MODEL + "yol parçası noktaya inmiş")


def _line(a, b):
    return BRepBuilderAPI_MakeEdge(gp_Pnt(*map(float, a)), gp_Pnt(*map(float, b))).Edge()


def path_wire(pieces, tol, extend=0.0, reverse=False):
    """Yol teli. (tel, başlangıç noktası, başlangıç teğeti, kapalı mı, uzunluk, ilk iç nokta)."""
    chain, closed, rest = chain_pieces(pieces, tol)
    if not chain:
        raise CadError(MODEL + "yol seçilmemiş: Kenar Seç'te yol kenarlarını seçip "
                               "'Seçimi Yol Yap' de")
    if rest:
        raise CadError(MODEL + f"yol kopuk: {rest} parça zincire bağlanmıyor (yol kenarları uç "
                               "uca gelmeli)")
    if reverse:
        chain = [_rev(p) for p in reversed(chain)]
    P0 = _np(chain[0][1][0])
    P1 = _np(chain[-1][1][-1])
    T0 = _end_tangent(chain[0], False)
    T1 = _end_tangent(chain[-1], True)
    length = float(sum(np.linalg.norm(np.diff(_samples(p), axis=0), axis=1).sum()
                       for p in chain))
    inner = _samples(chain[0], 64)[1]
    edges = [_edge(p) for p in chain]
    start = P0
    if extend > 1e-9 and not closed:
        start = P0 - T0 * extend
        edges = [_line(start, P0)] + edges + [_line(P1, P1 + T1 * extend)]
    return _wire(edges), start, T0, closed, length, inner, P0


def _profile_basis(pts, origin, axes):
    """Profil düzlemi: (çapa, U, V, N) — U profil objesinin X'i, N düzlem normali."""
    P = _np(pts)
    c = P.mean(axis=0)
    _u, sv, vt = np.linalg.svd(P - c)
    N = vt[2]
    size = float(np.linalg.norm(P.max(axis=0) - P.min(axis=0))) or 1.0
    dev = float(np.abs((P - c) @ N).max())
    if dev > 1e-3 * size:
        raise CadError(MODEL + f"profil düzlemsel değil (düzlemden {dev:.3g} sapıyor): profili "
                               "tek bir düzlemde çiz")
    X, Y, Z = (_np(a) for a in axes)
    if float(N @ Z) < 0:
        N = -N
    U = _unit(X - (X @ N) * N)
    if U is None:
        U = _unit(Y - (Y @ N) * N)
        U = _unit(np.cross(U, N)) if U is not None else _unit(np.cross(N, [1.0, 0.0, 0.0]))
    V = np.cross(N, U)
    A = _np(origin)
    A = A - ((A - c) @ N) * N                   # orijinin profil düzlemine izdüşümü
    return A, U, V, N, size


def _face_normal_at(shape, q, scale):
    """Gövdenin q noktasından geçen yüzlerinin (dışa bakan) normalleri."""
    out = []
    if None in (g._DistSS, g._ShapeAnalysis_Surface, g._BRepGProp_Face, g._gp_Vec):
        return out
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeVertex
    v = BRepBuilderAPI_MakeVertex(gp_Pnt(*map(float, q))).Vertex()
    surf_tool = g._static(g.BRep_Tool, "Surface")
    for f in g._shape_faces(shape):
        try:
            d = g._DistSS(v, f)
            if not d.IsDone() or d.Value() > 1e-3 * scale:
                continue
            P = gp_Pnt(*map(float, q))
            sa = g._ShapeAnalysis_Surface(surf_tool(f))
            uv = sa.ValueOfUV(P, 1e-4)
            Q, N = gp_Pnt(), g._gp_Vec()
            g._BRepGProp_Face(f).Normal(uv.X(), uv.Y(), Q, N)
            n = _unit(_np([N.X(), N.Y(), N.Z()]))
            if n is not None:
                out.append(n)
        except Exception:
            continue
    return out


def reference_dir(shape, mode, P, T, inner, scale):
    """Profilin +Y'sinin gideceği yön (yola dik). (yön, açıklama)"""
    if mode == "FACES" and shape is not None:
        ns = _face_normal_at(shape, inner, scale)
        if ns:
            b = np.sum(ns, axis=0)
            r = _unit(b - (b @ T) * T)
            if r is not None:
                return r, ("yüzlerin açıortayı" if len(ns) > 1 else "yüz normali")
    for ax in ((0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)):
        a = _np(ax)
        r = _unit(a - (a @ T) * T)
        if r is not None and abs(float(a @ T)) < 0.999:
            return r, ("dünya Z" if ax[2] else "dünya X")
    raise CadError("yol yönü belirlenemedi")


def profile_basis(prof):
    pts = np.vstack([_np(s) for s in prof["segs"]])
    return _profile_basis(pts, prof["origin"], prof["axes"])


def place_profile(prof, params, P, T, R, basis=None):
    """Profil segmentlerini yola dik düzleme yerleştiren nokta dönüşümü (P'de, teğet T, profil
    +Y → R)."""
    if basis is None:
        basis = profile_basis(prof)
    A, U, V, N, size = basis
    if params.get("place", "AUTO") == "KEEP":
        return (lambda p: _np(p)), basis
    V2 = R
    N2 = T
    U2 = np.cross(V2, N2)
    a = math.radians(float(params.get("angle", 0.0)))
    U3 = math.cos(a) * U2 + math.sin(a) * V2
    V3 = -math.sin(a) * U2 + math.cos(a) * V2
    if params.get("flip"):
        U3 = -U3
    s = float(params.get("scale", 1.0)) or 1.0
    O = _np(P) + float(params.get("off_x", 0.0)) * U3 + float(params.get("off_y", 0.0)) * V3

    def tf(p):
        d = _np(p) - A
        return O + s * ((d @ U) * U3 + (d @ V) * V3) + (d @ N) * N2
    return tf, basis


def _outward_close(prof, basis, a, b):
    """Açık profilin uçlarını DIŞARIDAN kapatan noktalar (kaynak düzlemde): uçlardan +Y
    yönünde orijinin (köşenin) de üstüne çıkıp birleşir. Böylece araç köşeyi kapsar ama yan
    çizgileri gövde yüzeyleriyle ÇAKIŞMAZ (çakışık eğrisel yüzler boolean'ı bozuyordu; dik
    kesişim temizdir). Gövdenin dışında kalan kısım zaten bir şey kesmez."""
    A, U, V, N, size = basis
    pts = np.vstack([_np(x) for x in prof["segs"]])
    vs = (pts - A) @ V
    top = max(0.0, float(vs.max())) + 0.5 * size
    a_v, b_v = float((a - A) @ V), float((b - A) @ V)
    return [b + V * (top - b_v), a + V * (top - a_v)]


def profile_wire(prof, tf, close, basis=None):
    """Profil teli (dönüştürülmüş). (tel, bilgi)"""
    pieces = [("bez", [tf(q) for q in s]) for s in prof["segs"]]
    if not pieces:
        raise CadError(MODEL + "profil eğrisinde segment yok")
    scale = float(np.linalg.norm(np.ptp(np.vstack([p[1] for p in pieces]), axis=0))) or 1.0
    chain, closed, rest = chain_pieces(pieces, 1e-5 * scale + 1e-9)
    note = ""
    if rest:
        note = f" · {rest} kopuk profil parçası kullanılmadı"
    edges = [_edge(p) for p in chain]
    if not closed:
        a, b = _np(chain[0][1][0]), _np(chain[-1][1][-1])
        if close == "CHORD":
            edges.append(_line(b, a))
            note += " · açık profil düz çizgiyle kapatıldı"
        elif close == "ORIGIN":
            # kaynak düzlemde uçlar (dönüşüm afin: ters izdüşümle değil, kaynak segmentlerden)
            src = chain_pieces([("bez", s) for s in prof["segs"]], 1e-5 * scale + 1e-9)[0]
            sa, sb = _np(src[0][1][0]), _np(src[-1][1][-1])
            if np.linalg.norm(tf(sa) - a) > np.linalg.norm(tf(sa) - b):
                sa, sb = sb, sa
            q1, q2 = (tf(q) for q in _outward_close(prof, basis, sa, sb))
            edges += [_line(b, q1), _line(q1, q2), _line(q2, a)]
            note += " · açık profil dışarıdan (köşeyi kapsayarak) kapatıldı"
        else:
            raise CadError(MODEL + "profil kapalı değil: profili kapat ya da 'Açık profil' "
                                   "seçeneğiyle (düz çizgi / köşeden) kapattır")
    return _wire(edges), note


def _polyline(chain):
    out = []
    for pc in chain:
        S = _samples(pc, 48)
        out.append(S if not out else S[1:])
    return np.vstack(out)


def _resample(P, n):
    d = np.r_[0.0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    if d[-1] < 1e-12:
        raise CadError(MODEL + "yol noktaya inmiş")
    t = np.linspace(0.0, d[-1], n)
    return np.column_stack([np.interp(t, d, P[:, k]) for k in range(3)]), float(d[-1])


def _tangents(P):
    T = np.gradient(P, axis=0)
    return T / np.maximum(np.linalg.norm(T, axis=1)[:, None], 1e-15)


def split_runs(chain, closed):
    """Yolu keskin köşelerden (G1 değil) koşulara böler: ([nokta dizisi], köşesiz kapalı döngü
    mü). Köşede iki aracın birleşimi gönye gibi kapanır (uçlar tam uzatılır)."""
    runs = [[chain[0]]]
    for a, b in zip(chain, chain[1:]):
        ang = math.degrees(math.acos(float(np.clip(_end_tangent(a, True) @
                                                   _end_tangent(b, False), -1, 1))))
        if ang > G1_DEG:
            runs.append([b])
        else:
            runs[-1].append(b)
    if closed and len(runs) > 1:
        ang = math.degrees(math.acos(float(np.clip(_end_tangent(chain[-1], True) @
                                                   _end_tangent(chain[0], False), -1, 1))))
        if ang <= G1_DEG:
            runs[0] = runs.pop() + runs[0]
    smooth_loop = closed and len(runs) == 1
    return [_polyline(r) for r in runs], smooth_loop


class _FaceFrames:
    """Yol noktalarında gövde yüzlerinin dışa bakan normalleri (kılavuz yüzey)."""

    def __init__(self, shape, poly, tol, scale):
        self.scale = scale
        surf_tool = g._static(g.BRep_Tool, "Surface")
        faces = []
        try:
            anc = g._DataMapAnc()
            g._static(g.TopExp, "MapShapesAndAncestors")(shape, g.TopAbs_EDGE, g.TopAbs_FACE,
                                                         anc)
            for e in g.match_edges(shape, [poly], max(tol, 1e-4 * scale)):
                for f in g._edge_faces(anc, e):
                    if not any(f.IsSame(x) for x in faces):
                        faces.append(f)
        except Exception:
            faces = []
        if not faces:
            faces = g._shape_faces(shape)
        self.faces = []
        for f in faces:
            try:
                self.faces.append((f, g._ShapeAnalysis_Surface(surf_tool(f)), g._BRepGProp_Face(f)))
            except Exception:
                pass

    def normals(self, p):
        hits = []
        P = gp_Pnt(*map(float, p))
        for f, sa, gpf in self.faces:
            try:
                uv = sa.ValueOfUV(P, 1e-5 * self.scale)
                if sa.Gap() > 2e-3 * self.scale:
                    continue
                st = g._FaceClassifier(f, g._gp_Pnt2d(uv.X(), uv.Y()), 1e-6).State()
                if st == g._TopAbs_OUT:
                    continue
                Q, N = gp_Pnt(), g._gp_Vec()
                gpf.Normal(uv.X(), uv.Y(), Q, N)
                n = _unit(_np([N.X(), N.Y(), N.Z()]))
                if n is not None:
                    hits.append((sa.Gap(), n))
            except Exception:
                continue
        hits.sort(key=lambda h: h[0])
        return [n for _, n in hits[:2]]


def _n_stations(L, size, lo=4, hi=40):
    return int(np.clip(L / max(0.5 * size, 1e-9), lo, hi)) + 1


def _frames_at(P, T, frames, scale):
    """Her istasyonda profilin +Y yönü: yüzlerin dışa bakan açıortayı (yola dik)."""
    Rs, prev, n_face = [], None, 0
    for p, t in zip(P, T):
        ns = frames.normals(p) if frames is not None else []
        r = None
        if ns:
            b = np.sum(ns, axis=0)
            r = _unit(b - (b @ t) * t)
            if r is not None:
                n_face += 1
        if r is None and prev is not None:
            r = _unit(prev - (prev @ t) * t)
        if r is None:
            r, _ = reference_dir(None, "Z", p, t, p, scale)
        if prev is not None and float(r @ prev) < 0:   # yan değiştirmesin
            r = -r
        Rs.append(r)
        prev = r
    return Rs, n_face


def _loft(stations, prof, params, basis, e0, e1, periodic=False):
    """İstasyonlardan (nokta, teğet, +Y) kesitler; uçlarda teğet doğrultusunda e0 / e1 uzatma.
    periodic: kapalı döngü — ilk kesit sona AYNI tel nesnesi olarak eklenir; OCC örgüyü
    periyodik kurar (tek parça halka, birleşim yeri / bindirme yok)."""
    P0, T0, R0 = stations[0]
    P1, T1, R1 = stations[-1]
    st = list(stations)
    if e0 > 1e-12:
        st = [(P0 - T0 * e0, T0, R0)] + st
    if e1 > 1e-12:
        st = st + [(P1 + T1 * e1, T1, R1)]
    ts = _ThruSections(True, False, 1e-6)
    try:
        ts.CheckCompatibility(False)
    except Exception:
        pass
    note = ""
    first = None
    for p, t, r in st:
        tf, _b = place_profile(prof, params, p, t, r, basis)
        w, note = profile_wire(prof, tf, params.get("close", "ORIGIN"), basis)
        ts.AddWire(w)
        if first is None:
            first = w
    if periodic:
        ts.AddWire(first)
    ts.Build()
    if not ts.IsDone():
        return None, "kesitlerden katı örülemedi"
    sol = ts.Shape()
    if not (g._has_solid(sol) and g._is_valid(sol)):
        return None, "örülen katı geçersiz"
    return g.ensure_outward(sol), note


def _face_tools(shape, chain, closed, prof, params, basis, ext, tol, scale):
    """Kılavuz yüzeyli süpürme (gövde kenarını izler): her istasyonda profil o noktadaki iki
    yan yüzün açıortayına göre yeniden yerleştirilir, kesitlerden katı örülür (ThruSections).
    Boru süpürmenin (Frenet) 3B döngüde dönüp gövdeye dalması böyle önlenir.
    ([katı], bilgi) | (None, sebep)"""
    size = basis[4] * float(params.get("scale", 1.0) or 1.0)
    runs, loop = split_runs(chain, closed)
    tools, note = [], ""
    if loop:
        # köşesiz kapalı döngü: istasyonlar ve çatılar bütün döngüde bir kez (periyodik teğet)
        # hesaplanır ve TEK periyodik örgü kurulur. İkiye bölüp iki araçla kesmek olmadı: iki
        # araç aynı yüzeyi yaklaşıkladığı için bindirmede yüzleri çakışıyor, OCC boolean'ı
        # ikinci kesimi yutuyordu (önce ayrı çatılarla: birleşimde basamak)
        Q = runs[0][:-1]
        L = float(np.linalg.norm(np.diff(runs[0], axis=0), axis=1).sum())
        n = _n_stations(L, size, 12, 80)
        P, _ = _resample(np.vstack([Q, Q[:1]]), n + 1)
        P = P[:-1]
        T = np.roll(P, -1, axis=0) - np.roll(P, 1, axis=0)
        T /= np.maximum(np.linalg.norm(T, axis=1)[:, None], 1e-15)
        Rs, n_face = _frames_at(P, T, _FaceFrames(shape, runs[0], tol, scale), scale)
        if n_face == 0:
            return None, "yol gövde yüzeyinde değil"
        st = [(P[i], T[i], Rs[i]) for i in range(n)]
        sol, note = _loft(st, prof, params, basis, 0.0, 0.0, periodic=True)
        if sol is not None:
            return [sol], note
        return None, note
    for poly in runs:
        L = float(np.linalg.norm(np.diff(poly, axis=0), axis=1).sum())
        P, _ = _resample(poly, _n_stations(L, size))
        T = _tangents(P)
        Rs, n_face = _frames_at(P, T, _FaceFrames(shape, poly, tol, scale), scale)
        if n_face == 0:
            return None, "yol gövde yüzeyinde değil"
        sol, note = _loft(list(zip(P, T, Rs)), prof, params, basis, ext, ext)
        if sol is None:
            return None, note
        tools.append(sol)
    return tools, note


def make_tool(shape, pieces, prof, params, tol):
    """Süpürme araç katıları. ([katı], bilgi). Hatalar CadError (kaynağı başta).
    Yüz açıortayı (FACES) modunda gövde kenarı kılavuz yüzeyle izlenir; diğer modlarda profil
    yol boyunca boru gibi (düzeltilmiş Frenet) süpürülür."""
    if _MakePipeShell is None and _MakePipe is None:
        raise CadError("Bu OCP sürümünde süpürme (pipe) desteği yok")
    scale = max(g._bbox_diag(shape), 1e-9) if shape is not None else 1.0
    if not prof.get("segs"):
        raise CadError(MODEL + "profil eğrisi seçilmemiş ya da boş")
    basis = profile_basis(prof)
    ext = float(params.get("extend", 0.0))
    if params.get("extend_auto", True):
        ext = max(ext, basis[4] * float(params.get("scale", 1.0) or 1.0))
    ctol = max(tol, 1e-6 * scale)
    chain, closed, rest = chain_pieces(pieces, ctol)
    if not chain:
        raise CadError(MODEL + "yol seçilmemiş: Kenar Seç'te yol kenarlarını seçip "
                               "'Seçimi Yol Yap' de")
    if rest:
        raise CadError(MODEL + f"yol kopuk: {rest} parça zincire bağlanmıyor (yol kenarları uç "
                               "uca gelmeli)")
    if params.get("reverse", False):
        chain = [_rev(p) for p in reversed(chain)]
    length = float(sum(np.linalg.norm(np.diff(_samples(p), axis=0), axis=1).sum()
                       for p in chain))
    head = f"yol {length:.3g}{' (kapalı)' if closed else ''}"
    if params.get("place", "AUTO") == "AUTO" and params.get("ref", "FACES") == "FACES" and \
            shape is not None and _ThruSections is not None:
        tools, note = _face_tools(shape, chain, closed, prof, params, basis, ext, tol, scale)
        fail = "" if tools else note
        if not fail:
            info = (f"{head} · profil kenarı izliyor (+Y = yüzlerin açıortayı)"
                    f"{f' · {len(tools)} parça' if len(tools) > 1 else ''}{note}")
            if ext > 1e-9 and not closed:
                info += f" · uçlar {ext:.3g} uzatıldı"
            return tools, info
        if fail != "yol gövde yüzeyinde değil":
            raise CadError("Çekirdek sınırı (OCC): profil kenar boyunca örülemedi (" + fail +
                           ") · yol çok keskin dönüyorsa (dönüş yarıçapı profilden küçük) kaynak "
                           "geometridir: profili küçült ya da yolu yumuşat")
        params = dict(params, ref="Z")       # yol gövdede değil: dünya Z'ye göre boru
    wire, start, T0, closed, length, inner, P0 = path_wire(
        pieces, ctol, ext, params.get("reverse", False))
    R, rtxt = reference_dir(shape, params.get("ref", "FACES"), P0, T0, inner, scale)
    tf, basis = place_profile(prof, params, start, T0, R, basis)
    pw, note = profile_wire(prof, tf, params.get("close", "ORIGIN"), basis)
    solid, how = _sweep(wire, pw, params.get("orient", "PATH"), T0, start)
    if solid is None:
        raise CadError("Çekirdek sınırı (OCC): profil yol boyunca süpürülemedi " + how +
                       " · yol çok keskin dönüyorsa (dönüş yarıçapı profilden küçük) kaynak "
                       "geometridir: profili küçült ya da yolu yumuşat")
    solid = g.ensure_outward(solid)
    vol = g.volume(solid)
    if vol is None or abs(vol) < 1e-12 * scale ** 3:
        raise CadError(MODEL + "süpürme hacimsiz çıktı (profil yolun doğrultusunda mı "
                               "çizildi? profil yola dik olmalı)")
    info = (f"{head} · profil "
            f"{'yerleşik' if params.get('place', 'AUTO') == 'KEEP' else 'yola dik, +Y=' + rtxt}"
            f"{note}")
    if ext > 1e-9 and not closed:
        info += f" · uçlar {ext:.3g} uzatıldı"
    return [solid], info


def _sweep(spine, prof_wire, orient, T0, start):
    """Önce yüzü boru gibi süpür (MakePipe, düzeltilmiş Frenet), olmazsa kabuk süpürme."""
    tried = []
    face = None
    try:
        mf = BRepBuilderAPI_MakeFace(prof_wire, True)
        if mf.IsDone():
            face = mf.Face()
    except Exception:
        face = None
    if face is None:
        return None, "(profil düzlemsel bir yüz oluşturmuyor)"
    if orient == "PATH" and _MakePipe is not None and _Trihedron is not None:
        try:
            mp = _MakePipe(spine, face, _Trihedron.GeomFill_IsCorrectedFrenet, False)
            mp.Build()
            if mp.IsDone():
                s = mp.Shape()
                if g._has_solid(s) and g._is_valid(s):
                    return s, ""
            tried.append("boru")
        except Exception as e:
            tried.append(f"boru ({e})")
    if _MakePipeShell is not None:
        for mode, corner in (("frenet", "right"), ("frenet", "round"), ("discrete", "right"),
                             ("fixed", "right")):
            if orient == "FIXED" and mode != "fixed":
                continue
            try:
                ps = _MakePipeShell(spine)
                if _Transition is not None:
                    # keskin köşeli yol (ör. kutunun üst kenarları): köşede gönye birleşim
                    try:
                        ps.SetTransitionMode(_Transition.BRepBuilderAPI_RightCorner
                                             if corner == "right" else
                                             _Transition.BRepBuilderAPI_RoundCorner)
                    except Exception:
                        pass
                if mode == "frenet":
                    ps.SetMode(False)                       # düzeltilmiş Frenet
                elif mode == "discrete":
                    ps.SetDiscreteMode()
                else:
                    from OCP.gp import gp_Ax2, gp_Dir
                    ps.SetMode(gp_Ax2(gp_Pnt(*map(float, start)), gp_Dir(*map(float, T0))))
                ps.Add(prof_wire, False, False)
                ps.Build()
                if not ps.IsDone():
                    tried.append(f"{mode}/{corner}")
                    continue
                ps.MakeSolid()
                s = ps.Shape()
                if g._has_solid(s) and g._is_valid(s):
                    return s, ""
                tried.append(f"{mode}/{corner} (geçersiz)")
            except Exception as e:
                tried.append(f"{mode} ({e})")
    return None, "(" + ", ".join(tried) + ")"
