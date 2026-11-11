"""OpenCASCADE ile geometri işlemleri. Bu modül sadece çekirdek yüklüyken içe aktarılır.

Boolean, mesh→katı, yön/onarım ve fillet koruma katmanlarının bir kısmı FORGE
eklentisinden uyarlanmıştır: Copyright (C) 2026 Paul Ogunsola / RenderCraftStudio,
GPL-3.0-or-later (kernel/brep.py: _safe_bool, heal_if_invalid, orient_outward,
mesh_to_solid, fillet_edges_by_index). Bu dosya da GPL-3.0-or-later lisanslıdır.

Temel ilke: tel kafesteki her segmentten TEK bir OCC kenarı, her köşeden TEK bir OCC
köşesi üretilir; o kenarı paylaşan bütün yüzeyler aynı nesneyi kullanır (gerçek ortak
topoloji). Düz segmentler gerçek doğru, düzlemsel döngüler gerçek düzlem olur. Böylece
fillet motoru analitik ve toleranssız geometriyle çalışır.

Segment formatı: {"p": [Vector...], "tag": (...), "ref": (...)}; 'p' 2 nokta (doğru)
veya 4 nokta (kübik bezier).
"""

import importlib
import math

import numpy as np

from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepBuilderAPI import (BRepBuilderAPI_Copy, BRepBuilderAPI_MakeEdge,
                                BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeSolid,
                                BRepBuilderAPI_MakeVertex, BRepBuilderAPI_MakeWire,
                                BRepBuilderAPI_Sewing, BRepBuilderAPI_Transform)
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeFilling
from OCP.Geom import Geom_BezierCurve, Geom_BSplineCurve
from OCP.GeomAbs import GeomAbs_C0
from OCP.TopAbs import (TopAbs_EDGE, TopAbs_FACE, TopAbs_REVERSED, TopAbs_SHELL,
                        TopAbs_SOLID, TopAbs_VERTEX)
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS, TopoDS_Compound
from OCP.gp import gp_Ax2, gp_Dir, gp_Pln, gp_Pnt, gp_Trsf

from .errors import CadError


# ================================================================ uyumluluk

def _static(cls, name):
    """OCP statik metotları bazı sürümlerde '_s' son ekiyle, bazılarında eksiz."""
    fn = getattr(cls, name + "_s", None) or getattr(cls, name, None)
    if fn is None:
        raise CadError(f"OCP uyumsuzluğu: {cls.__name__}.{name} bulunamadı")
    return fn


def _optional(modname, clsname):
    try:
        return getattr(importlib.import_module(modname), clsname)
    except Exception:
        return None


_FACE_CAST = _static(TopoDS, "Face")
_SHELL_CAST = _static(TopoDS, "Shell")
_EDGE_CAST = _static(TopoDS, "Edge")
_TRIANGULATION = _static(BRep_Tool, "Triangulation")

_PntArray = _optional("OCP.TColgp", "TColgp_Array1OfPnt")
_RealArray = _optional("OCP.TColStd", "TColStd_Array1OfReal")
_IntArray = _optional("OCP.TColStd", "TColStd_Array1OfInteger")
_GeomFill_BSplineCurves = _optional("OCP.GeomFill", "GeomFill_BSplineCurves")
_GeomFill_CoonsStyle = _optional("OCP.GeomFill", "GeomFill_CoonsStyle")
_ToolTri = _optional("OCP.BRepLib", "BRepLib_ToolTriangulatedShape")
_BRepLib = _optional("OCP.BRepLib", "BRepLib")
_ShapeFix_Face = _optional("OCP.ShapeFix", "ShapeFix_Face")
_BRepCheck_Analyzer = _optional("OCP.BRepCheck", "BRepCheck_Analyzer")
_BRepAdaptor_Curve = _optional("OCP.BRepAdaptor", "BRepAdaptor_Curve")
_MakeFillet = _optional("OCP.BRepFilletAPI", "BRepFilletAPI_MakeFillet")
_MakeChamfer = _optional("OCP.BRepFilletAPI", "BRepFilletAPI_MakeChamfer")
_IndexedMap = _optional("OCP.TopTools", "TopTools_IndexedMapOfShape")
_DataMapAnc = _optional("OCP.TopTools", "TopTools_IndexedDataMapOfShapeListOfShape")
_ListIter = _optional("OCP.TopTools", "TopTools_ListIteratorOfListOfShape")
_GeomAbs_G1 = _optional("OCP.GeomAbs", "GeomAbs_G1")
_STEPWriter = _optional("OCP.STEPControl", "STEPControl_Writer")
_STEP_AsIs = _optional("OCP.STEPControl", "STEPControl_AsIs")
_RetDone = _optional("OCP.IFSelect", "IFSelect_RetDone")
_BOOL_ALGOS = {
    "CUT": _optional("OCP.BRepAlgoAPI", "BRepAlgoAPI_Cut"),
    "UNION": _optional("OCP.BRepAlgoAPI", "BRepAlgoAPI_Fuse"),
    "INTERSECT": _optional("OCP.BRepAlgoAPI", "BRepAlgoAPI_Common"),
}
_Unify = _optional("OCP.ShapeUpgrade", "ShapeUpgrade_UnifySameDomain")
_DistSS = _optional("OCP.BRepExtrema", "BRepExtrema_DistShapeShape")
_MakePolygon = _optional("OCP.BRepBuilderAPI", "BRepBuilderAPI_MakePolygon")
_GTrsf = _optional("OCP.gp", "gp_GTrsf")
_GTransform = _optional("OCP.BRepBuilderAPI", "BRepBuilderAPI_GTransform")
_GProps = _optional("OCP.GProp", "GProp_GProps")
_ShapeList = _optional("OCP.TopTools", "TopTools_ListOfShape")
_TopoIter = _optional("OCP.TopoDS", "TopoDS_Iterator")
_Pnt2Array = _optional("OCP.TColgp", "TColgp_Array2OfPnt")
_BezierSurface = _optional("OCP.Geom", "Geom_BezierSurface")
_SurfAdaptor = _optional("OCP.BRepAdaptor", "BRepAdaptor_Surface")
_SLProps = _optional("OCP.GeomLProp", "GeomLProp_SLProps")
_ChFi3d_FilletShape = _optional("OCP.ChFi3d", "ChFi3d_FilletShape")
_TopAbs_COMPOUND = _optional("OCP.TopAbs", "TopAbs_COMPOUND")
_BRepGProp = _optional("OCP.BRepGProp", "BRepGProp")
_Pnt2dArray = _optional("OCP.TColgp", "TColgp_Array1OfPnt2d")
_gp_Pnt2d = _optional("OCP.gp", "gp_Pnt2d")

if _PntArray is None:
    raise CadError("OCP: TColgp_Array1OfPnt bulunamadı (OCP 7.9 gerekli)")


def _pnt(v):
    return gp_Pnt(float(v[0]), float(v[1]), float(v[2]))


def _pnt_array(points):
    arr = _PntArray(1, len(points))
    for i, p in enumerate(points):
        arr.SetValue(i + 1, _pnt(p))
    return arr


def _cubic(pts):
    """2 noktalı doğruyu kübik bezier kontrol noktalarına yükselt."""
    if len(pts) == 4:
        return pts
    a, b = pts
    return [a, a + (b - a) / 3.0, a + (b - a) * (2.0 / 3.0), b]


def _np(pts):
    return np.array([tuple(p) for p in pts], dtype=np.float64)


def _pkey(p):
    return (round(p[0], 7), round(p[1], 7), round(p[2], 7))


def _ekey(pts):
    """Yönden bağımsız segment anahtarı."""
    a = tuple(_pkey(p) for p in pts)
    b = tuple(reversed(a))
    return min(a, b)


def is_straight(pts):
    """Bezier tutamaçları uç noktaları birleştiren doğru üzerindeyse True."""
    if len(pts) == 2:
        return True
    P = _np(pts)
    d = P[3] - P[0]
    L = float(np.linalg.norm(d))
    if L < 1e-12:
        return False
    d /= L
    tol = 1e-7 + 1e-6 * L
    for k in (1, 2):
        v = P[k] - P[0]
        if np.linalg.norm(v - np.dot(v, d) * d) > tol:
            return False
        t = np.dot(v, d)
        if t < -tol or t > L + tol:   # tutamaç doğru üzerinde ama dışarı taşıyor
            return False
    return True


def plane_of(chain):
    """Döngünün bütün kontrol noktaları bir düzlemdeyse (merkez, normal), değilse None."""
    P = np.vstack([_np(s["p"]) for s in chain])
    c = P.mean(axis=0)
    size = float(np.linalg.norm(P.max(axis=0) - P.min(axis=0)))
    if size < 1e-12:
        return None
    _, sv, vt = np.linalg.svd(P - c)
    n = vt[2]
    dev = float(np.abs((P - c) @ n).max())
    if dev > 1e-7 + 1e-6 * size:
        return None
    return c, n


# ================================================================ yüzey üreticileri

FILL_FINAL = dict(degree=3, nbpts=15, nbiter=2, maxdeg=8, maxseg=9)
FILL_PREVIEW = dict(degree=3, nbpts=8, nbiter=1, maxdeg=6, maxseg=4)

# Yüzey birleşimi: komşu yüzlerle ortak kenarda süreklilik (Keskin = G0, yalnızca konum)
# (OCC 7.9 dolgu aracı kenar kısıtında G2'yi kabul etmiyor: yalnızca G1)
BLEND_LABELS = {"TANGENT": "teğet (G1)"}


def _blend_order(blend):
    return {"TANGENT": _GeomAbs_G1}.get(blend)


def _is_anchor(p):
    """Kaynaşmada sabit kalan yama: keskin, düzlemsel ya da açıkça Düzlem / Coons."""
    if p.get("blend", "SHARP") not in BLEND_LABELS or p["method"] in ("PLANE", "COONS"):
        return True
    return p["method"] == "AUTO" and plane_of(p["chain"]) is not None


def blend_order(patches):
    """Kurma sırası: önce sabit yamalar, sonra kaynaşacaklar (onlar komşularına uyar).
    Aynı gruptaki sıra korunur."""
    return sorted(patches, key=lambda p: 0 if _is_anchor(p) else 1)


def coons_available():
    return None not in (_GeomFill_BSplineCurves, _GeomFill_CoonsStyle, _RealArray, _IntArray)


def _bspline_from_side(side):
    """Bir kenar grubundaki ardışık segmentleri tek kübik BSpline'a çevirir."""
    poles = []
    for i, seg in enumerate(side):
        c = _cubic(seg["p"])
        poles += c if i == 0 else c[1:]
    nseg = len(side)
    knots = _RealArray(1, nseg + 1)
    mults = _IntArray(1, nseg + 1)
    for i in range(nseg + 1):
        knots.SetValue(i + 1, float(i))
        mults.SetValue(i + 1, 4 if i in (0, nseg) else 3)
    return Geom_BSplineCurve(_pnt_array(poles), knots, mults, 3)


def _fix_face(face):
    if _ShapeFix_Face is None:
        return face
    try:
        fx = _ShapeFix_Face(face)
        fx.Perform()
        return fx.Face()
    except Exception:
        return face


def face_usable(face):
    """Yüz geçerli mi ve üçgenlenebiliyor mu? (görünmeyen yüz kalmasın)"""
    try:
        if _BRepCheck_Analyzer is not None and not _BRepCheck_Analyzer(face).IsValid():
            return False
        BRepMesh_IncrementalMesh(face, 0.05, True, 0.5, False)
        tri = _TRIANGULATION(face, TopLoc_Location())
        return tri is not None and tri.NbTriangles() > 0
    except Exception:
        return False


class Builder:
    """Bir yeniden hesaplama turundaki köşe/kenar/yüz kayıtları.
    Önceki turun kayıtları (prev) değişmeyen parçalar için yeniden kullanılır; böylece
    önbellekteki yüzler de yeni kenarlarla aynı topolojiyi paylaşmaya devam eder."""

    def __init__(self, prev=None):
        self.prev = prev
        self.verts, self.edges, self.faces = {}, {}, {}
        self.face_keys = []
        self.edge_owner = {}     # kenar anahtarı -> (bu turda o kenarı ilk kullanan yüz, anahtarı)

    def _get(self, table, key):
        v = getattr(self, table).get(key)
        if v is None and self.prev is not None:
            v = getattr(self.prev, table).get(key)
        return v

    def vertex(self, p):
        k = _pkey(p)
        v = self._get("verts", k)
        if v is None:
            v = BRepBuilderAPI_MakeVertex(_pnt(p)).Vertex()
        self.verts[k] = v
        return v

    def edge(self, pts):
        k = _ekey(pts)
        e = self._get("edges", k)
        if e is None:
            v0, v1 = self.vertex(pts[0]), self.vertex(pts[-1])
            if is_straight(pts):
                me = BRepBuilderAPI_MakeEdge(v0, v1)
            else:
                me = BRepBuilderAPI_MakeEdge(Geom_BezierCurve(_pnt_array(pts)), v0, v1)
            if not me.IsDone():
                raise CadError("Kenar oluşturulamadı")
            e = me.Edge()
        else:
            self.vertex(pts[0])
            self.vertex(pts[-1])
        self.edges[k] = e
        return e

    def _wire(self, chain):
        mw = BRepBuilderAPI_MakeWire()
        for s in chain:
            mw.Add(self.edge(s["p"]))
        if not mw.IsDone():
            raise CadError("Kenarlar kapalı bir tel oluşturmuyor")
        return mw.Wire()

    def _own(self, ekeys, res, key):
        for k in ekeys:
            self.edge_owner.setdefault(k, (res[0], key))

    def face(self, chain, sides, method, preview, blend="SHARP"):
        ekeys = [_ekey(s["p"]) for s in chain]
        key = (tuple(ekeys), method, preview if method == "FILL" else False)
        nbrs = []                    # [(segment, (komşu yüz, anahtarı))] — kaynaşma kısıtları
        if blend in BLEND_LABELS and method in ("AUTO", "FILL") and \
                _blend_order(blend) is not None:
            seen = set()
            for s, k in zip(chain, ekeys):
                own = self.edge_owner.get(k)
                if own is not None and k not in seen:
                    seen.add(k)
                    nbrs.append((s, own))
            if nbrs:
                key = key + (blend, preview, tuple(hash(o[1]) for _, o in nbrs))
        self.face_keys.append(key)
        hit = self._get("faces", key)
        if hit is not None:
            # Kenarları da bu tura kaydet (paylaşım bozulmasın)
            for s in chain:
                self.edge(s["p"])
            self.faces[key] = hit
            self._own(ekeys, hit, key)
            return hit
        wire = self._wire(chain)
        res = None
        tried = []
        blend_note = ""
        if method in ("AUTO", "PLANE"):
            res = self._planar(chain, wire)
            if res is not None and not face_usable(res[0]):
                tried.append("Düzlem")
                res = None
            if res is None and method == "PLANE":
                raise CadError("Döngü düzlemsel değil")
        if res is None and nbrs:
            # Komşu yüzlere teğet / eğrilik sürekliliğiyle dolgu (ortak kenarda kaynaşır)
            try:
                res = self._filling(chain, preview, nbrs, blend)
                if not face_usable(res[0]):
                    res = None
            except CadError:
                res = None
            if res is None:
                blend_note = f" ({BLEND_LABELS[blend]} kurulamadı, keskin birleşim)"
        if res is None and (method == "COONS" or (method == "AUTO" and len(sides) == 4
                                                 and coons_available())):
            try:
                res = self._coons(sides, wire)
                if not face_usable(res[0]):
                    tried.append("Coons")
                    res = None
                    if method == "COONS":
                        raise CadError("Coons yüzeyi geçersiz çıktı; Otomatik veya Dolgu dene")
            except CadError:
                if method == "COONS":
                    raise
        if res is None:
            res = self._filling(chain, preview)
            if not face_usable(res[0]):
                raise CadError("Yüzey geçersiz çıktı (" + ", ".join(tried + ["Dolgu"]) +
                               " denendi). Döngüdeki eğrileri kontrol et")
            if tried:
                res = (res[0], res[1] + f" ({'/'.join(tried)} geçersizdi)")
        if blend_note:
            res = (res[0], res[1] + blend_note)
        self.faces[key] = res
        self._own(ekeys, res, key)
        return res

    def _planar(self, chain, wire):
        pl = plane_of(chain)
        if pl is None:
            return None
        mf = BRepBuilderAPI_MakeFace(wire, True)
        if not mf.IsDone():
            c, n = pl
            mf = BRepBuilderAPI_MakeFace(gp_Pln(_pnt(c), gp_Dir(*map(float, n))), wire, True)
            if not mf.IsDone():
                return None
            return _fix_face(mf.Face()), "Düzlem"
        return mf.Face(), "Düzlem"

    def _coons(self, sides, wire):
        if not coons_available():
            raise CadError("Bu OCP sürümünde Coons desteği yok")
        if len(sides) != 4:
            raise CadError(f"Coons için tam 4 kenar gerekli, bu döngüde {len(sides)} kenar var")
        curves = [_bspline_from_side(s) for s in sides]
        try:
            fill = _GeomFill_BSplineCurves(curves[0], curves[1], curves[2], curves[3],
                                           _GeomFill_CoonsStyle)
            mf = BRepBuilderAPI_MakeFace(fill.Surface(), wire, True)
        except Exception as e:
            raise CadError(f"Coons yüzeyi hesaplanamadı: {e}")
        if not mf.IsDone():
            raise CadError("Coons yüzeyi oluşturulamadı")
        return _fix_face(mf.Face()), "Coons"

    def _filling(self, chain, preview, nbrs=None, blend=None):
        """Dolgu yüzeyi. nbrs verilirse o kenarlar komşu yüze teğet (G1) sürekliliğiyle
        bağlanır; diğer kenarlar yalnızca konumdan (C0)."""
        prm = FILL_PREVIEW if preview else FILL_FINAL
        filler = BRepOffsetAPI_MakeFilling(prm["degree"], prm["nbpts"], prm["nbiter"], False,
                                           1e-5, 1e-4, 1e-2, 0.1, prm["maxdeg"], prm["maxseg"])
        sup = {id(s): own[0] for s, own in (nbrs or ())}
        order = _blend_order(blend) if sup else None
        n_cons = 0
        try:
            for s in chain:
                e = self.edge(s["p"])
                f = sup.get(id(s))
                if f is not None and order is not None:
                    filler.Add(e, _FACE_CAST(f), order, True)
                    n_cons += 1
                else:
                    filler.Add(e, GeomAbs_C0, True)
            filler.Build()
        except Exception as e:
            raise CadError(f"Dolgu yüzeyi hesaplanamadı: {e}")
        if not filler.IsDone():
            raise CadError("Dolgu yüzeyi hesaplanamadı")
        exp = TopExp_Explorer(filler.Shape(), TopAbs_FACE)
        if not exp.More():
            raise CadError("Dolgu yüz üretmedi")
        label = "Dolgu"
        if n_cons:
            label += f" · {n_cons} kenarda {BLEND_LABELS[blend]}"
        return _FACE_CAST(exp.Current()), label


# ================================================================ birleştirme

def assemble(faces, mirrors, sew_tol, make_solid):
    """Yüzleri (ortak kenarları koruyarak) birleştirir, aynalar, diker ve mümkünse katıya
    çevirir. (shape, açıklama) döndürür."""
    bb = BRep_Builder()
    comp = TopoDS_Compound()
    bb.MakeCompound(comp)
    for f in faces:
        bb.Add(comp, f)
    # Bileşiğin tamamı kopyalanır: paylaşım korunur, önbellekteki yüzler bozulmaz
    base = BRepBuilderAPI_Copy(comp).Shape()
    parts = [base]
    for origin, normal in mirrors:
        trsf = gp_Trsf()
        trsf.SetMirror(gp_Ax2(_pnt(origin), gp_Dir(*normal)))
        parts += [BRepBuilderAPI_Transform(p, trsf, True).Shape() for p in parts]

    if len(faces) == 1 and len(parts) == 1:
        exp = TopExp_Explorer(base, TopAbs_FACE)
        return exp.Current(), "Tek yüzey"

    sew = BRepBuilderAPI_Sewing(sew_tol)
    for p in parts:
        sew.Add(p)
    try:
        sew.Perform()
    except Exception as e:
        raise CadError(f"Yüzeyler dikilemedi: {e}")
    shape = sew.SewedShape()
    free = sew.NbFreeEdges()

    if free > 0 or not make_solid:
        info = "Açık kabuk" if free > 0 else "Kabuk"
        return shape, f"{info} · {free} serbest kenar" if free else info

    solid, info = shell_to_solid(shape)
    if solid is None:
        return shape, info
    return prepare_solid(solid), info


def shell_to_solid(shape):
    """Tek kapalı kabuğu katıya çevirir. (katı | None, açıklama)."""
    shells = []
    exp = TopExp_Explorer(shape, TopAbs_SHELL)
    while exp.More():
        shells.append(_SHELL_CAST(exp.Current()))
        exp.Next()
    if len(shells) != 1:
        return None, f"{len(shells)} ayrı kabuk, katı yapılamadı"
    ms = BRepBuilderAPI_MakeSolid(shells[0])
    if not ms.IsDone():
        return None, "Kapalı kabuk, katı yapılamadı"
    solid = ms.Solid()
    if _BRepLib is not None:
        try:
            _static(_BRepLib, "OrientClosedSolid")(solid)
        except Exception:
            pass
    return solid, "Kapalı katı"


# ================================================================ bevel (fillet / pah)

EDGE_SAMPLES = 9


def _reflect(P, origin, normal):
    o = np.asarray(origin, dtype=np.float64)
    n = np.asarray(normal, dtype=np.float64)
    n = n / np.linalg.norm(n)
    return P - 2.0 * ((P - o) @ n)[:, None] * n


def _min_dist(P, A, B):
    """P (n,3) noktalarının A->B alt segment kümesine en kısa uzaklıkları (n,)."""
    ab = B - A
    denom = np.einsum("ij,ij->i", ab, ab)
    denom = np.where(denom < 1e-18, 1e-18, denom)
    ap = P[:, None, :] - A[None, :, :]
    t = np.clip(np.einsum("nmk,mk->nm", ap, ab) / denom, 0.0, 1.0)
    closest = A[None, :, :] + t[..., None] * ab[None, :, :]
    return np.linalg.norm(closest - P[:, None, :], axis=2).min(axis=1)


def _shape_edges(shape):
    edges = []
    if _IndexedMap is not None:
        m = _IndexedMap()
        _static(TopExp, "MapShapes")(shape, TopAbs_EDGE, m)
        for i in range(1, m.Extent() + 1):
            edges.append(_EDGE_CAST(m.FindKey(i)))
        return edges
    exp = TopExp_Explorer(shape, TopAbs_EDGE)
    while exp.More():
        e = _EDGE_CAST(exp.Current())
        if not any(e.IsSame(x) for x in edges):
            edges.append(e)
        exp.Next()
    return edges


def _edge_samples(edge):
    c = _BRepAdaptor_Curve(edge)
    u0, u1 = c.FirstParameter(), c.LastParameter()
    pts = []
    for k in range(EDGE_SAMPLES):
        p = c.Value(u0 + (u1 - u0) * k / (EDGE_SAMPLES - 1))
        pts.append((p.X(), p.Y(), p.Z()))
    return np.array(pts, dtype=np.float64)


def match_edges(shape, polys, tol):
    """Tamamı verilen eğri örneklerinin (polys) üzerinde kalan kenarları döndürür."""
    if not polys:
        return []
    A = np.vstack([p[:-1] for p in polys])
    B = np.vstack([p[1:] for p in polys])
    out = []
    for e in _shape_edges(shape):
        try:
            if _static(BRep_Tool, "Degenerated")(e):
                continue
            S = _edge_samples(e)
        except Exception:
            continue
        if _min_dist(S, A, B).max() <= tol:
            out.append(e)
    return out


def _edge_vertices(e):
    try:
        return [_static(TopExp, "FirstVertex")(e), _static(TopExp, "LastVertex")(e)]
    except Exception:
        return []


def feature_groups(edge_lists):
    """Ortak köşe paylaşan özellikleri aynı gruba toplar (birleşim-bul).
    edge_lists: her özellik için OCC kenar listesi. Grupların listesini döndürür."""
    n = len(edge_lists)
    verts = [[v for e in el for v in _edge_vertices(e)] for el in edge_lists]
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(n):
        for j in range(i + 1, n):
            if find(i) == find(j):
                continue
            if any(a.IsSame(b) for a in verts[i] for b in verts[j]):
                parent[find(j)] = find(i)
    groups = {}
    for i in range(n):
        if edge_lists[i]:
            groups.setdefault(find(i), []).append(i)
    return sorted(groups.values(), key=lambda g: g[0])


# ---------------------------------------------------------------- köşe yaması pürüzsüzleştirme

CORNER_FILL = dict(degree=3, nbpts=20, nbiter=3, maxdeg=8, maxseg=12)
FILLET_PRECISE = (1e-3, 1e-5, 1e-6, 1e-5, 1e-6, 1e-5)  # Tang, Tesp, T2d, TApp3d, TolApp2d, Fleche


def _list_shapes(lst):
    """TopTools_ListOfShape'i Python listesine çevirir; OCP sürümüne göre farklı yollar dener."""
    out = []
    try:
        for x in lst:
            out.append(x)
        return out
    except Exception:
        out = []
    if _ListIter is not None:
        try:
            it = _ListIter(lst)
            while it.More():
                out.append(it.Value())
                it.Next()
            return out
        except Exception:
            out = []
    try:                                   # son çare: ilk / son eleman
        n = lst.Extent() if hasattr(lst, "Extent") else lst.Size()
        if n >= 1:
            out.append(lst.First())
        if n >= 2:
            out.append(lst.Last())
    except Exception:
        pass
    return out


def _list_size(lst):
    for name in ("Extent", "Size"):
        fn = getattr(lst, name, None)
        if fn is not None:
            try:
                return int(fn())
            except Exception:
                pass
    return len(_list_shapes(lst))


def _shape_faces(shape):
    out = []
    if _IndexedMap is not None:
        m = _IndexedMap()
        _static(TopExp, "MapShapes")(shape, TopAbs_FACE, m)
        for i in range(1, m.Extent() + 1):
            out.append(_FACE_CAST(m.FindKey(i)))
        return out
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        f = _FACE_CAST(exp.Current())
        if not any(f.IsSame(x) for x in out):
            out.append(f)
        exp.Next()
    return out


def _vertex_point(v):
    p = _static(BRep_Tool, "Pnt")(_static(TopoDS, "Vertex")(v))
    return np.array([p.X(), p.Y(), p.Z()], dtype=np.float64)


def _face_center(face):
    pts = []
    exp = TopExp_Explorer(face, TopAbs_VERTEX)
    while exp.More():
        pts.append(_vertex_point(exp.Current()))
        exp.Next()
    return np.mean(pts, axis=0) if pts else None


_FILLET_MODE = {"fast": False}   # önizlemede hızlı (Polynomial) fillet
_FAIL = {"why": ""}               # son fillet başarısızlığının nedeni (kullanıcıya gösterilir)

FAIL_TEXT = {
    "no_match": "kenar gövdede bulunamadı",
    "not_two_face": "kenar iki yüzün birleştiği yerde değil (gövde kapalı katı mı?)",
    "build": "çekirdek bu ölçüyle hesaplayamadı · ölçüyü küçült",
    "invalid": "sonuç bozuk geometri üretti (köşede yarıçap sığmıyor) · ölçüyü küçült",
}


def fail_reason(default="hesaplanamadı"):
    why = _FAIL["why"]
    if why.startswith("hata:"):
        return why
    return FAIL_TEXT.get(why, default)


def fillet_accept(base, out):
    """OCC köşe birleşimlerinde 'başarılı' deyip bozuk gövde döndürebilir (FORGE notu).
    Taban geçerliyken sonuç geçersizse reddet. Hızlı önizlemede ağır kontrol atlanır."""
    if out is None:
        return False
    if _FILLET_MODE["fast"] or _BRepCheck_Analyzer is None:
        return True
    try:
        if not _BRepCheck_Analyzer(out, True).IsValid():
            return not _BRepCheck_Analyzer(base, True).IsValid()
    except Exception:
        pass
    return True


def two_face_filter(shape):
    """Sadece tam iki yüz arasındaki kenarlar fillet'lenebilir (açık/dejenere kenar elenir)."""
    if _DataMapAnc is None:
        return lambda e: True
    anc = _DataMapAnc()
    try:
        _static(TopExp, "MapShapesAndAncestors")(shape, TopAbs_EDGE, TopAbs_FACE, anc)
    except Exception:
        return lambda e: True

    def ok(e):
        try:
            if not anc.Contains(e):
                return False
            lst = anc.FindFromKey(e)
            n = _list_size(lst)
            if n < 2:
                return False                   # açık (serbest) kenar
            faces = _list_shapes(lst)
            uniq = []
            for f in faces:
                if not any(f.IsSame(x) for x in uniq):
                    uniq.append(f)
            if len(faces) >= 2 and len(uniq) < 2:
                return False                   # dikiş kenarı (aynı yüz iki kez)
            return n == 2 or len(uniq) == 2
        except Exception:
            return True                         # emin değilsek çekirdeğe bırak
    return ok


def _new_fillet(shape, precise):
    mk = _MakeFillet(shape)
    if _FILLET_MODE["fast"] and _ChFi3d_FilletShape is not None:
        try:
            mk.SetFilletShape(_ChFi3d_FilletShape.ChFi3d_Polynomial)
        except Exception:
            pass
    if precise and not _FILLET_MODE["fast"]:
        try:
            mk.SetParams(*FILLET_PRECISE)
        except Exception:
            pass
    return mk


def _corner_candidates(mk, before, after, edges_r):
    """Fillet işleminin ürettiği köşe yamaları: ne özgün yüzlerden ne de kenar şeritlerinden
    gelen, en az iki fillet kenarının buluştuğu bir köşenin yakınındaki yüzler.
    (yüzler, köşe sayısı, en büyük yarıçap) döndürür."""
    vs, cnt, rmax = [], [], []
    for e, r in edges_r:
        for v in _edge_vertices(e):
            k = next((j for j, w in enumerate(vs) if w.IsSame(v)), None)
            if k is None:
                vs.append(v)
                cnt.append(0)
                rmax.append(0.0)
                k = len(vs) - 1
            cnt[k] += 1
            rmax[k] = max(rmax[k], r)
    hubs = [(_vertex_point(v), r) for v, c, r in zip(vs, cnt, rmax) if c >= 2]
    if not hubs:
        return [], 0, 0.0
    known = []
    for f in _shape_faces(before):
        try:
            if mk.IsDeleted(f):
                continue
        except Exception:
            pass
        try:
            mods = _list_shapes(mk.Modified(f))
        except Exception:
            mods = []
        known += mods if mods else [f]
    for e, _ in edges_r:
        try:
            known += _list_shapes(mk.Generated(e))
        except Exception:
            pass
    out = []
    for f in _shape_faces(after):
        if any(f.IsSame(k) for k in known):
            continue
        c = _face_center(f)
        if c is not None and any(np.linalg.norm(c - h) <= 2.5 * r for h, r in hubs):
            out.append(f)
    return out, len(hubs), max(r for _, r in hubs)


def _refill_face(face, anc):
    """Yüzü, kenarlarından komşu yüzlere TEĞET (G1) minimum enerjili bir dolguyla
    yeniden kurar. (yeni yüz, sapma) | None."""
    p = CORNER_FILL
    filler = BRepOffsetAPI_MakeFilling(p["degree"], p["nbpts"], p["nbiter"], False,
                                       1e-6, 1e-5, 1e-3, 0.1, p["maxdeg"], p["maxseg"])
    degen = _static(BRep_Tool, "Degenerated")
    seen, n = [], 0
    exp = TopExp_Explorer(face, TopAbs_EDGE)
    while exp.More():
        e = _EDGE_CAST(exp.Current())
        exp.Next()
        if any(e.IsSame(x) for x in seen):
            continue
        seen.append(e)
        if degen(e):
            continue
        support = None
        try:
            for f2 in _list_shapes(anc.FindFromKey(e)):
                if not f2.IsSame(face):
                    support = _FACE_CAST(f2)
                    break
        except Exception:
            support = None
        if support is not None:
            filler.Add(e, support, _GeomAbs_G1, True)
        else:
            filler.Add(e, GeomAbs_C0, True)
        n += 1
    if n < 2:
        return None
    filler.Build()
    if not filler.IsDone():
        return None
    exp2 = TopExp_Explorer(filler.Shape(), TopAbs_FACE)
    if not exp2.More():
        return None
    err = 0.0
    try:
        err = float(filler.G0Error())
    except Exception:
        pass
    return _FACE_CAST(exp2.Current()), err


def _smooth_corners(before, mk, after, edges_r):
    """OCC'nin köşe yamalarını G1 dolguyla değiştirir. (gövde, değiştirilen yama sayısı).
    Herhangi bir adım başarısız olursa OCC'nin sonucu aynen döner."""
    if None in (_DataMapAnc, _GeomAbs_G1):
        return after, 0
    try:
        if after.ShapeType() != TopAbs_SOLID:
            return after, 0
        corners, n_hubs, rmax = _corner_candidates(mk, before, after, edges_r)
        if not corners or len(corners) > 2 * n_hubs:
            return after, 0
        anc = _DataMapAnc()
        _static(TopExp, "MapShapesAndAncestors")(after, TopAbs_EDGE, TopAbs_FACE, anc)
        new_faces, err = [], 0.0
        for f in corners:
            r = _refill_face(f, anc)
            if r is None:
                return after, 0
            new_faces.append(r[0])
            err = max(err, r[1])
        if err > 0.02 * rmax:
            return after, 0
        rest = [f for f in _shape_faces(after) if not any(f.IsSame(c) for c in corners)]
        sew = BRepBuilderAPI_Sewing(min(max(1e-5, 4.0 * err), 1e-2))
        for f in rest + new_faces:
            sew.Add(f)
        sew.Perform()
        if sew.NbFreeEdges() > 0:
            return after, 0
        solid, _ = shell_to_solid(sew.SewedShape())
        if solid is None:
            return after, 0
        return solid, len(corners)
    except Exception:
        return after, 0


def _build_once(cur, kind, sel, feats, polys, tol, precise, smooth, stats):
    try:
        mk = _new_fillet(cur, precise) if kind == "FILLET" else _MakeChamfer(cur)
        added = []
        okf = two_face_filter(cur)
        n_match = n_bad = 0
        for i in sel:
            r = float(feats[i]["size"])
            for e in match_edges(cur, polys[i], tol):
                n_match += 1
                if not okf(e):
                    n_bad += 1
                    continue
                if kind == "FILLET":
                    try:
                        if mk.Contour(e) != 0:
                            continue   # aynı teğet zincirde zaten var
                    except Exception:
                        pass
                mk.Add(r, e)
                added.append((e, r))
        if not added:
            _FAIL["why"] = "no_match" if n_match == 0 else "not_two_face"
            return None
        mk.Build()
        if not mk.IsDone():
            _FAIL["why"] = "build"
            return None
        out = mk.Shape()
        if not fillet_accept(cur, out):
            _FAIL["why"] = "invalid"
            return None
        if kind == "FILLET" and smooth and len(added) > 1:
            out, n = _smooth_corners(cur, mk, out, added)
            if stats is not None:
                stats["corners"] = stats.get("corners", 0) + n
        return out
    except Exception as ex:
        _FAIL["why"] = f"hata: {ex}"
        return None


def _try_apply(shape, idxs, feats, polys, tol, smooth=False, stats=None):
    """Verilen özellikleri tek işlemde uygular (önce fillet'ler, sonra pahlar).
    Fillet önce hassas toleranslarla, olmazsa varsayılanla denenir.
    Başarılıysa yeni gövde, değilse None."""
    cur = shape
    for kind in ("FILLET", "CHAMFER"):
        sel = [i for i in idxs if feats[i]["kind"] == kind and feats[i]["size"] > 1e-9]
        if not sel:
            continue
        out = None
        for precise in ((True, False) if kind == "FILLET" else (False,)):
            out = _build_once(cur, kind, sel, feats, polys, tol, precise, smooth, stats)
            if out is not None:
                break
        if out is None:
            return None
        cur = out
    return cur


def _apply_edgewise(shape, i, feats, polys, tol):
    """Bir özelliğin kenarlarını TEK TEK uygular: her adımda kalan ilk kenar yalnız başına
    fillet'lenir. Köşe yaması oluşmaz; sonraki fillet öncekinin yüzeyiyle kesişir."""
    kind = feats[i]["kind"]
    size = float(feats[i]["size"])
    if size <= 1e-9:
        return shape
    maker = _MakeFillet if kind == "FILLET" else _MakeChamfer
    cur = shape
    first = match_edges(cur, polys[i], tol)
    if not first:
        return None
    for _ in range(len(first) + 2):
        es = match_edges(cur, polys[i], tol)
        if not es:
            return cur
        nxt = None
        for precise in ((True, False) if kind == "FILLET" else (False,)):
            try:
                okf = two_face_filter(cur)
                cand = [e for e in es if okf(e)]
                if not cand:
                    return None
                mk = _new_fillet(cur, precise) if kind == "FILLET" else maker(cur)
                mk.Add(size, cand[0])
                mk.Build()
                if mk.IsDone() and fillet_accept(cur, mk.Shape()):
                    nxt = mk.Shape()
                    break
            except Exception:
                pass
        if nxt is None:
            return None
        cur = nxt
    return cur


def _edge_length(e):
    S = _edge_samples(e)
    return float(np.linalg.norm(np.diff(S, axis=0), axis=1).sum())


def radius_law(r, r_start, r_end, length, factor, max_frac=0.45):
    """Kenar boyunca (göreli parametre, yarıçap) noktaları. Uçta daha büyük bir komşu
    yarıçap varsa, kenarın yarıçapı o uca yaklaşırken yumuşakça ona yükselir.
    Sabit yarıçapsa None döndürür."""
    eps = 1e-9
    f0 = min(max_frac, factor * r_start / length) if r_start > r + eps and length > eps else 0.0
    f1 = min(max_frac, factor * r_end / length) if r_end > r + eps and length > eps else 0.0
    if f0 == 0.0 and f1 == 0.0:
        return None
    pts = [(0.0, r_start if f0 else r)]
    if f0:
        pts.append((f0, r))
    if f1:
        pts.append((1.0 - f1, r))
    pts.append((1.0, r_end if f1 else r))
    return pts


def _apply_transition(shape, g, feats, polys, tol, factor, smooth=False, stats=None):
    """Köşede farklı yarıçaplı fillet'ler buluşuyorsa küçük olanların yarıçapını köşeye
    yaklaştıkça en büyük yarıçapa yükseltir; köşede hepsi eşitlenir ve birlikte hesaplanır.
    (gövde | None, {özellik: köşede geçiş var mı}) döndürür."""
    if _Pnt2dArray is None or _gp_Pnt2d is None:
        return None, {}
    items = []
    okf = two_face_filter(shape)
    for i in g:
        if feats[i]["kind"] != "FILLET" or feats[i]["size"] <= 1e-9:
            continue
        for e in match_edges(shape, polys[i], tol):
            if okf(e):
                items.append((e, i, float(feats[i]["size"])))
    if not items:
        return None, {}
    # Her köşedeki en büyük yarıçap
    verts, vmax = [], []

    def vidx(v):
        for k, w in enumerate(verts):
            if w.IsSame(v):
                return k
        verts.append(v)
        vmax.append(0.0)
        return len(verts) - 1

    ends = []
    for e, i, r in items:
        vs = _edge_vertices(e)
        ks = [vidx(v) for v in vs]
        for k in ks:
            vmax[k] = max(vmax[k], r)
        ends.append((vs, ks))
    out = None
    for precise in (True, False):
        out, ramped, mk = _transition_once(shape, items, ends, vmax, factor, precise)
        if out is not None:
            break
    if out is None:
        return None, {}
    if smooth and len(items) > 1:
        out, n = _smooth_corners(shape, mk, out, [(e, r) for e, _, r in items])
        if stats is not None:
            stats["corners"] = stats.get("corners", 0) + n
    chamfers = [i for i in g if feats[i]["kind"] == "CHAMFER"]
    if chamfers:
        out = _try_apply(out, chamfers, feats, polys, tol)
        if out is None:
            return None, {}
    return out, ramped


def _transition_once(shape, items, ends, vmax, factor, precise):
    ramped = {}
    try:
        mk = _new_fillet(shape, precise)
        for (e, i, r), (vs, ks) in zip(items, ends):
            try:
                if mk.Contour(e) != 0:
                    continue
            except Exception:
                pass
            law = None
            if len(ks) == 2:
                law = radius_law(r, vmax[ks[0]], vmax[ks[1]], _edge_length(e), factor)
            if law is None:
                mk.Add(r, e)
                continue
            mk.Add(e)
            ic = mk.Contour(e)
            iinc = 1
            for j in range(1, mk.NbEdges(ic) + 1):
                if mk.Edge(ic, j).IsSame(e):
                    iinc = j
                    break
            # Fillet zinciri kenarın tersi yönünde kurulmuşsa yasayı çevir
            try:
                if mk.FirstVertex(ic).IsSame(vs[1]) and not vs[0].IsSame(vs[1]):
                    law = [(1.0 - u, rr) for u, rr in reversed(law)]
            except Exception:
                pass
            arr = _Pnt2dArray(1, len(law))
            for k, (u, rr) in enumerate(law):
                arr.SetValue(k + 1, _gp_Pnt2d(float(u), float(rr)))
            mk.SetRadius(arr, ic, iinc)
            ramped[i] = True
        mk.Build()
        if not mk.IsDone() or not fillet_accept(shape, mk.Shape()):
            return None, {}, None
        return mk.Shape(), ramped, mk
    except Exception:
        return None, {}, None


def apply_features(shape, feats, mirrors, tol, corner_mode="JOINT", factor=3.0,
                   smooth_corners=True, fast=False):
    """fast=True: önizleme için hızlı (Polynomial) fillet, ağır doğrulama yok."""
    _FILLET_MODE["fast"] = bool(fast)
    try:
        return _apply_features(shape, feats, mirrors, tol, corner_mode, factor,
                               smooth_corners)
    finally:
        _FILLET_MODE["fast"] = False


def _apply_features(shape, feats, mirrors, tol, corner_mode, factor, smooth_corners):
    """feats: [{"kind": "FILLET"|"CHAMFER", "size": float, "polys": [np(K,3)]}]

    Ortak köşesi olan bevel'ler tek işlemde birlikte hesaplanır (köşe birleşimi doğru
    çözülür); birbirine değmeyen gruplar ayrı işlemlerde uygulanır, sıra önemsizdir.
    Birlikte hesaplama başarısız olursa iki sıralı alternatif denenir.
    (shape, [(ok, bilgi)]) döndürür."""
    if None in (_BRepAdaptor_Curve, _MakeFillet, _MakeChamfer):
        raise CadError("Bu OCP sürümünde fillet desteği bulunamadı")
    n = len(feats)
    polys = []
    for f in feats:
        p = list(f["polys"]) + list(f.get("geo_polys", ()))
        for origin, normal in mirrors:
            p += [_reflect(q, origin, normal) for q in p]
        polys.append(p)
    results = [None] * n
    edge_lists = [match_edges(shape, polys[i], tol) for i in range(n)]
    for i in range(n):
        if not edge_lists[i]:
            results[i] = (False, "Gövdede eşleşen kenar yok (iki yüzeyin birleştiği kenar olmalı)")

    def sequential(shape, order, edgewise=False):
        cur, res = shape, {}
        for i in order:
            if edgewise:
                o = _apply_edgewise(cur, i, feats, polys, tol)
            else:
                o = _try_apply(cur, [i], feats, polys, tol, smooth_corners)
            if o is not None:
                cur = o
                res[i] = (True, "uygulandı")
            else:
                res[i] = (False, f"Hesaplanamadı: {fail_reason()}")
        return cur, res

    def corner_note(stats):
        n = stats.get("corners", 0)
        return f" · {n} köşe yaması pürüzsüzleştirildi" if n else ""

    def joint(shape, g):
        stats = {}
        o = _try_apply(shape, g, feats, polys, tol, smooth_corners, stats)
        if o is None:
            return shape, {i: (False, f"Hesaplanamadı: {fail_reason()}") for i in g}
        return o, {i: (True, "uygulandı · ortak köşe yamasıyla" + corner_note(stats))
                   for i in g}

    def transition(shape, g):
        stats = {}
        o, ramped = _apply_transition(shape, g, feats, polys, tol, factor, smooth_corners,
                                      stats)
        if o is None:
            return shape, {i: (False, "Geçişle hesaplanamadı") for i in g}
        note = corner_note(stats)
        return o, {i: (True, ("uygulandı · köşede yumuşak yarıçap geçişi" if ramped.get(i)
                              else "uygulandı") + note) for i in g}

    seq_orders = {
        "HISTORY": lambda g: sorted(g),
        "BIG_FIRST": lambda g: sorted(g, key=lambda i: -feats[i]["size"]),
        "SMALL_FIRST": lambda g: sorted(g, key=lambda i: feats[i]["size"]),
    }
    for g in feature_groups(edge_lists):
        if len(g) == 1:
            stats = {}
            if corner_mode == "EDGEWISE":
                out = _apply_edgewise(shape, g[0], feats, polys, tol)
                if out is None:
                    out = _try_apply(shape, g, feats, polys, tol)
            else:
                out = _try_apply(shape, g, feats, polys, tol, smooth_corners, stats)
            if out is not None:
                shape = out
                results[g[0]] = (True, "uygulandı" + corner_note(stats))
            else:
                results[g[0]] = (False, f"Hesaplanamadı: {fail_reason()}")
            continue
        # Tercih edilen yöntem önce, diğerleri yedek olarak denenir
        attempts = []
        if corner_mode == "TRANSITION":
            attempts.append(("TRANS", None))
            attempts.append(("JOINT", None))
        elif corner_mode == "JOINT":
            attempts.append(("JOINT", None))
        elif corner_mode == "EDGEWISE":
            attempts.append(("EDGE", sorted(g)))
            attempts.append(("SEQ", sorted(g)))
        else:
            attempts.append(("SEQ", seq_orders.get(corner_mode, seq_orders["HISTORY"])(g)))
            attempts.append(("JOINT", None))
        for mode in ("HISTORY", "BIG_FIRST", "SMALL_FIRST"):
            order = seq_orders[mode](g)
            if all(a[1] != order for a in attempts):
                attempts.append(("SEQ", order))
        best = None
        for n_try, (kind, order) in enumerate(attempts):
            if kind == "TRANS":
                cur, res = transition(shape, g)
            elif kind == "JOINT":
                cur, res = joint(shape, g)
            else:
                cur, res = sequential(shape, order, edgewise=(kind == "EDGE"))
            score = sum(ok for ok, _ in res.values())
            if n_try > 0 and score:
                res = {i: (ok, (msg + " (yedek yöntemle)") if ok else msg)
                       for i, (ok, msg) in res.items()}
            if best is None or score > best[0]:
                best = (score, cur, res)
            if score == len(g):
                break
        _, shape, res = best
        for i, r in res.items():
            results[i] = r
    return shape, results


# ================================================================ üçgenleme

def _face_normals(face, tri):
    if _ToolTri is None:
        return None
    try:
        _static(_ToolTri, "ComputeNormals")(face, tri)
        if not tri.HasNormals():
            return None
        out = []
        for i in range(1, tri.NbNodes() + 1):
            n = tri.Normal(i)
            out.append((n.X(), n.Y(), n.Z()))
        return out
    except Exception:
        return None


def _tdir(n, trsf):
    try:
        d = gp_Dir(*n).Transformed(trsf)
        return (d.X(), d.Y(), d.Z())
    except Exception:
        return (0.0, 0.0, 0.0)   # dejenere nokta: fix_normals düzeltir


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


NORMAL_FIX_COS = math.cos(math.radians(35.0))


def fix_normals(verts, tris, normals):
    """Yüzey normali, o noktaya değen üçgenlerin ortalama yönünden çok sapıyorsa (sivri
    uçlar, dejenere noktalar) üçgen ortalamasını kullanır. Liste döndürür."""
    V = np.asarray(verts, dtype=np.float64)
    T = np.asarray(tris, dtype=np.int64)
    N = np.asarray(normals, dtype=np.float64)
    if len(T) == 0 or len(N) != len(V):
        return list(map(tuple, N))
    tn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])   # alanla ağırlıklı
    acc = np.zeros_like(V)
    for k in range(3):
        np.add.at(acc, T[:, k], tn)
    alen = np.linalg.norm(acc, axis=1)
    has = alen > 1e-20
    avg = np.zeros_like(V)
    avg[has] = acc[has] / alen[has, None]
    nlen = np.linalg.norm(N, axis=1)
    bad_n = ~np.isfinite(N).all(axis=1) | (nlen < 1e-9)
    Nn = np.where(bad_n[:, None], 0.0, N / np.where(nlen < 1e-9, 1.0, nlen)[:, None])
    dot = np.einsum("ij,ij->i", Nn, avg)
    replace = has & (bad_n | (dot < NORMAL_FIX_COS))
    Nn[replace] = avg[replace]
    return [tuple(map(float, n)) for n in Nn]


_ShapeFix_Shape = _optional("OCP.ShapeFix", "ShapeFix_Shape")
_BRepTools = _optional("OCP.BRepTools", "BRepTools")


def _mesh_face_alone(face, lin, ang):
    """Tek bir yüzü ayrıca üçgenlemeyi dener (önce aynı, sonra göreli sapmayla)."""
    for args in ((lin, False, ang, False), (0.01, True, ang, False)):
        try:
            BRepMesh_IncrementalMesh(face, *args)
            tri = _TRIANGULATION(face, TopLoc_Location())
            if tri is not None and tri.NbNodes() > 0:
                return True
        except Exception:
            pass
    return False


LAST_FAILED = 0   # son üçgenlemede görüntülenemeyen yüz sayısı


def tessellate(shape, lin_defl, ang_defl):
    """(verts, tris, normals) döndürür. Üçgenlenemeyen yüzler tek tek yeniden denenir;
    hiçbiri olmazsa gövde onarılıp baştan denenir."""
    try:
        return _tessellate(shape, lin_defl, ang_defl)
    except CadError as first:
        if _ShapeFix_Shape is None:
            raise
        try:
            if _BRepTools is not None:
                _static(_BRepTools, "Clean")(shape)
            sf = _ShapeFix_Shape(shape)
            sf.Perform()
            fixed = sf.Shape()
        except Exception:
            raise first
        try:
            return _tessellate(fixed, lin_defl, ang_defl)
        except CadError:
            raise first


def _tessellate(shape, lin_defl, ang_defl):
    BRepMesh_IncrementalMesh(shape, lin_defl, False, ang_defl, True)
    verts, tris, normals = [], [], []
    n_faces = n_failed = 0
    have_normals = True
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = _FACE_CAST(exp.Current())
        n_faces += 1
        loc = TopLoc_Location()
        tri = _TRIANGULATION(face, loc)
        if tri is None or tri.NbNodes() == 0:
            if _mesh_face_alone(face, lin_defl, ang_defl):
                loc = TopLoc_Location()
                tri = _TRIANGULATION(face, loc)
            else:
                n_failed += 1
        if tri is not None and tri.NbNodes() > 0:
            trsf = loc.Transformation()
            off = len(verts)
            fverts = []
            for i in range(1, tri.NbNodes() + 1):
                p = tri.Node(i).Transformed(trsf)
                fverts.append((p.X(), p.Y(), p.Z()))
            rev = face.Orientation() == TopAbs_REVERSED
            ftris = []
            for i in range(1, tri.NbTriangles() + 1):
                t = tri.Triangle(i)
                a, b, c = t.Value(1) - 1, t.Value(2) - 1, t.Value(3) - 1
                ftris.append((a, c, b) if rev else (a, b, c))

            fn = _face_normals(face, tri)
            if fn is not None:
                fn = [_tdir(n, trsf) for n in fn]
                score = 0.0
                for (a, b, c) in ftris[:50]:
                    g = _cross(_sub(fverts[b], fverts[a]), _sub(fverts[c], fverts[a]))
                    nn = fn[a]
                    score += g[0] * nn[0] + g[1] * nn[1] + g[2] * nn[2]
                if score < 0:
                    fn = [(-x, -y, -z) for (x, y, z) in fn]
                fn = fix_normals(fverts, ftris, fn)
                normals += fn
            else:
                have_normals = False

            verts += fverts
            tris += [(a + off, b + off, c + off) for (a, b, c) in ftris]
        exp.Next()
    global LAST_FAILED
    LAST_FAILED = n_failed
    if not tris:
        if n_faces == 0:
            raise CadError("Gövdede hiç yüz yok (yüzey üretilemedi)")
        raise CadError(f"Üçgenleme başarısız: {n_failed}/{n_faces} yüz üçgenlenemedi")
    return verts, tris, (normals if have_normals else None)


# ================================================================ STEP dışa aktarma

def write_step(shape, path, scale_to_mm):
    """Gövdeyi STEP (AP214, mm) olarak yazar. scale_to_mm: Blender biriminden mm'ye çarpan."""
    if _STEPWriter is None or _STEP_AsIs is None:
        raise CadError("Bu OCP sürümünde STEP yazıcı bulunamadı")
    out = shape
    if abs(scale_to_mm - 1.0) > 1e-12:
        tr = gp_Trsf()
        tr.SetScale(gp_Pnt(0.0, 0.0, 0.0), float(scale_to_mm))
        out = BRepBuilderAPI_Transform(shape, tr, True).Shape()
    w = _STEPWriter()
    st = w.Transfer(out, _STEP_AsIs)
    if _RetDone is not None and st != _RetDone:
        raise CadError("Gövde STEP formatına aktarılamadı")
    st = w.Write(str(path))
    if _RetDone is not None and st != _RetDone:
        raise CadError(f"STEP dosyası yazılamadı: {path}")


# ================================================================ boolean

def _is_identity(m, eps=1e-9):
    return all(abs(m[i][j] - (1.0 if i == j else 0.0)) <= eps for i in range(4) for j in range(4))


def transform_shape(shape, m):
    """4x4 matris (satır listesi) ile dönüştürür. Eşit olmayan ölçek için genel dönüşüm."""
    if _is_identity(m):
        return shape
    try:
        t = gp_Trsf()
        t.SetValues(*(float(m[i][j]) for i in range(3) for j in range(4)))
        return BRepBuilderAPI_Transform(shape, t, True).Shape()
    except Exception:
        if _GTrsf is None or _GTransform is None:
            raise CadError("Araç objesinin ölçeği desteklenmiyor (ölçeği uygula: Ctrl+A)")
        g = _GTrsf()
        for i in range(3):
            for j in range(4):
                g.SetValue(i + 1, j + 1, float(m[i][j]))
        return _GTransform(shape, g, True).Shape()


def mirror_copies(shape, mirrors):
    parts = [shape]
    for origin, normal in mirrors:
        trsf = gp_Trsf()
        trsf.SetMirror(gp_Ax2(_pnt(origin), gp_Dir(*normal)))
        parts += [BRepBuilderAPI_Transform(p, trsf, True).Shape() for p in parts]
    return parts


MAX_TOOL_FACES = 5000


def _newell(verts, idx):
    """Poligonun sarım normali (Blender sarımı tutarlı biçimde dışa bakar)."""
    nx = ny = nz = 0.0
    n = len(idx)
    for k in range(n):
        a = verts[idx[k]]
        b = verts[idx[(k + 1) % n]]
        nx += (a[1] - b[1]) * (a[2] + b[2])
        ny += (a[2] - b[2]) * (a[0] + b[0])
        nz += (a[0] - b[0]) * (a[1] + b[1])
    return (nx, ny, nz)


def _orient_to(face, want):
    """Yüzün OCC normali poligon sarımıyla çelişiyorsa yüzü çevirir (karışık yön olmasın)."""
    if _SurfAdaptor is None or _SLProps is None:
        return face
    try:
        ad = _SurfAdaptor(face)
        u = 0.5 * (ad.FirstUParameter() + ad.LastUParameter())
        v = 0.5 * (ad.FirstVParameter() + ad.LastVParameter())
        pr = _SLProps(_static(BRep_Tool, "Surface")(face), u, v, 1, 1e-9)
        if not pr.IsNormalDefined():
            return face
        n = pr.Normal()
        have = (n.X(), n.Y(), n.Z())
        if face.Orientation() == TopAbs_REVERSED:
            have = (-have[0], -have[1], -have[2])
        if want[0] * have[0] + want[1] * have[1] + want[2] * have[2] < 0.0:
            return _FACE_CAST(face.Reversed())
    except Exception:
        pass
    return face


def mesh_to_solid(verts, polys, tol=1e-6):
    """Kapalı bir Blender mesh'ini (dünya koordinatında) katıya çevirir (FORGE uyarlaması).
    Her poligon tek yüz: düzlemsel → düzlem; eğik quad → birebir bilinear yama (komşularla
    su geçirmez); diğer → yelpaze üçgenler. Yüzler poligon sarımına göre yönlenir,
    32-bit mesh koordinatlarına uygun toleranslarla birleştirilir, negatif hacim düzeltilir."""
    if _MakePolygon is None:
        raise CadError("Bu OCP sürümünde mesh dönüştürme yok")
    if len(polys) > MAX_TOOL_FACES:
        raise CadError(f"Araç mesh'i çok yoğun ({len(polys)} yüz, en fazla {MAX_TOOL_FACES})")
    sew = BRepBuilderAPI_Sewing(tol)
    added = 0

    def planar(idx):
        mp = _MakePolygon()
        for k in idx:
            mp.Add(_pnt(verts[k]))
        mp.Close()
        if not mp.IsDone():
            return None
        mf = BRepBuilderAPI_MakeFace(mp.Wire(), True)
        return mf.Face() if mf.IsDone() else None

    def bilinear(idx):
        if _Pnt2Array is None or _BezierSurface is None:
            return None
        try:
            arr = _Pnt2Array(1, 2, 1, 2)
            arr.SetValue(1, 1, _pnt(verts[idx[0]]))
            arr.SetValue(1, 2, _pnt(verts[idx[1]]))
            arr.SetValue(2, 1, _pnt(verts[idx[3]]))
            arr.SetValue(2, 2, _pnt(verts[idx[2]]))
            mf = BRepBuilderAPI_MakeFace(_BezierSurface(arr), 1e-7)
            return mf.Face() if mf.IsDone() else None
        except Exception:
            return None

    for poly in polys:
        if len(poly) < 3:
            continue
        want = _newell(verts, poly)
        f = planar(poly)
        if f is None and len(poly) == 4:
            f = bilinear(poly)
        if f is not None:
            sew.Add(_orient_to(f, want))
            added += 1
            continue
        for k in range(1, len(poly) - 1):        # yelpaze üçgenler
            tri = [poly[0], poly[k], poly[k + 1]]
            ft = planar(tri)
            if ft is not None:
                sew.Add(_orient_to(ft, _newell(verts, tri)))
                added += 1
    if added < 4:
        raise CadError("Araç mesh'inden yüz üretilemedi")
    sew.Perform()
    if sew.NbFreeEdges() > 0:
        raise CadError(f"Araç mesh'i kapalı değil ({sew.NbFreeEdges()} açık kenar); boolean "
                       "için delik içermeyen bir mesh gerekli")
    solid, _ = shell_to_solid(sew.SewedShape())
    if solid is None:
        raise CadError("Araç mesh'i kapalı (manifold) değil; boolean için delik içermeyen bir "
                       "mesh gerekli")
    solid = unify(solid, linear_tol=1e-6, angular_tol=1e-5)
    solid = ensure_outward(solid)
    v = volume(solid)
    if v is not None and abs(v) < 1e-12:
        raise CadError("Araç mesh'i sıfır hacimli")
    return solid


def unify(shape, linear_tol=None, angular_tol=None):
    """Aynı düzlem/yüzey üzerindeki parçalı yüzleri ve kenarları birleştirir.
    Mesh kaynaklı şekillerde 32-bit koordinat sapmasına uygun toleranslar verilebilir."""
    if _Unify is None:
        return shape
    try:
        u = _Unify(shape, True, True, False)
        if linear_tol is not None:
            u.SetLinearTolerance(float(linear_tol))
        if angular_tol is not None:
            u.SetAngularTolerance(float(angular_tol))
        u.Build()
        out = u.Shape()
        return shape if out is None or out.IsNull() else out
    except Exception:
        return shape


def _count(shape, kind):
    n = 0
    exp = TopExp_Explorer(shape, kind)
    while exp.More():
        n += 1
        exp.Next()
    return n


def _has_solid(shape):
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    return exp.More()


def volume(shape):
    if _GProps is None or _BRepGProp is None:
        return None
    try:
        g = _GProps()
        _static(_BRepGProp, "VolumeProperties")(shape, g)
        return float(g.Mass())
    except Exception:
        return None


def _single_solid(shape):
    sols = []
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    while exp.More():
        sols.append(exp.Current())
        exp.Next()
    return _static(TopoDS, "Solid")(sols[0]) if len(sols) == 1 else shape


def _faces_compound(shapes):
    bb = BRep_Builder()
    comp = TopoDS_Compound()
    bb.MakeCompound(comp)
    for sh in shapes:
        for f in _shape_faces(sh):
            bb.Add(comp, f)
    return comp


def boolean_new_edges(shape, before, tools, mode, tol):
    """Boolean sonucunda araç yüzeyi üzerinde kalan kenarlar.
    mode 'SECTION': aynı zamanda eski gövde yüzeyinde (kesişim çizgileri),
    mode 'ALL': araçtan gelen bütün kenarlar (cebin iç kenarları dahil)."""
    if _DistSS is None:
        return []
    tool_c = _faces_compound(tools)
    body_c = _faces_compound([before])
    degen = _static(BRep_Tool, "Degenerated")

    def near(S, comp):
        for p in S:
            try:
                d = _DistSS(BRepBuilderAPI_MakeVertex(_pnt(p)).Vertex(), comp)
                if not d.IsDone() or d.Value() > tol:
                    return False
            except Exception:
                return False
        return True

    out = []
    for e in _shape_edges(shape):
        try:
            if degen(e):
                continue
            S = _edge_samples(e)[[1, EDGE_SAMPLES // 2, EDGE_SAMPLES - 2]]
        except Exception:
            continue
        if near(S, tool_c) and (mode == "ALL" or near(S, body_c)):
            out.append(e)
    return out


def fillet_edges(shape, edges, r, smooth=True):
    """Verilen kenarları tek işlemde yuvarlar. Başarısızsa None."""
    for precise in (True, False):
        try:
            mk = _new_fillet(shape, precise)
            added = []
            okf = two_face_filter(shape)
            for e in edges:
                if not okf(e):
                    continue
                try:
                    if mk.Contour(e) != 0:
                        continue
                except Exception:
                    pass
                mk.Add(float(r), e)
                added.append((e, float(r)))
            if not added:
                return None
            mk.Build()
            if mk.IsDone() and fillet_accept(shape, mk.Shape()):
                out = mk.Shape()
                if smooth and len(added) > 1:
                    out, _ = _smooth_corners(shape, mk, out, added)
                return out
        except Exception:
            pass
    return None


# ---------------------------------------------------------------- koruma katmanları

def heal_if_invalid(shape):
    """Geçersiz şekli ShapeFix ile BİR kez onarmayı dener. (şekil, geçerli mi).
    Geçersiz bir gövde sonraki her işlemi bozar; bu yüzden işlem sınırlarında çağrılır."""
    if shape is None:
        return shape, False
    if _BRepCheck_Analyzer is None:
        return shape, True
    try:
        if _BRepCheck_Analyzer(shape, True).IsValid():
            return shape, True
    except Exception:
        return shape, True
    if _ShapeFix_Shape is None:
        return shape, False
    try:
        fx = _ShapeFix_Shape(shape)
        fx.Perform()
        healed = fx.Shape()
        if healed is not None and not healed.IsNull() and \
                _BRepCheck_Analyzer(healed, True).IsValid():
            return healed, True
    except Exception:
        pass
    return shape, False


def ensure_outward(shape):
    """Katıların yüzleri dışa baksın: OrientClosedSolid + negatif hacimse ters çevir.
    İçi dışına dönmüş katıyla yapılan boolean yanlış hacmi çıkarır."""
    try:
        exp = TopExp_Explorer(shape, TopAbs_SOLID)
        while exp.More():
            if _BRepLib is not None:
                try:
                    _static(_BRepLib, "OrientClosedSolid")(_static(TopoDS, "Solid")(exp.Current()))
                except Exception:
                    pass
            exp.Next()
    except Exception:
        pass
    v = volume(shape)
    if v is not None and v < 0.0:
        try:
            return shape.Reversed()
        except Exception:
            pass
    return shape


def prepare_solid(shape):
    """İşlem öncesi ortak kapı: onar + yönlendir."""
    shape, _ = heal_if_invalid(shape)
    return ensure_outward(shape)


def _bbox_diag(shape):
    try:
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        b = Bnd_Box()
        _static(BRepBndLib, "Add")(shape, b)
        if b.IsVoid():
            return 0.0
        x0, y0, z0, x1, y1, z1 = b.Get()
        return math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2)
    except Exception:
        return 0.0


def _unwrap_result(result, fallback):
    """Boolean sonucunu temiz bir katıya indirger (FORGE _safe_bool mantığı):
    tek çocuklu bileşik → içindeki katı; katısız bileşik/kabuk → katıya terfi;
    hiçbir şey yoksa hedef gövde aynen."""
    if result is None or result.IsNull():
        return fallback, "empty"
    try:
        if _TopAbs_COMPOUND is not None and result.ShapeType() == _TopAbs_COMPOUND:
            n_child = 0
            if _TopoIter is not None:
                it = _TopoIter(result)
                while it.More():
                    n_child += 1
                    it.Next()
            sols = []
            exp = TopExp_Explorer(result, TopAbs_SOLID)
            while exp.More():
                sols.append(_static(TopoDS, "Solid")(exp.Current()))
                exp.Next()
            if n_child > 1 and len(sols) > 1:
                return result, "multi"          # gerçekten birden çok parça
            if len(sols) == 1:
                return sols[0], "ok"
            if len(sols) > 1:
                return max(sols, key=_bbox_diag), "largest"
            solid, _ = shell_to_solid(result)
            if solid is not None:
                return solid, "promoted"
            if _shape_faces(result):
                return result, "faces"
            return fallback, "empty"
        if result.ShapeType() == TopAbs_SHELL:
            solid, _ = shell_to_solid(result)
            if solid is not None:
                return solid, "promoted"
    except Exception:
        pass
    return result, "ok"


def safe_boolean(op, a, b, fuzzy=0.0):
    """BRepAlgoAPI'yi güvenli yeni arayüzle (SetArguments/SetTools/Build) çalıştırır,
    paralel işlemeyi açar, başarısızsa küçük bir bulanık toleransla bir kez daha dener."""
    cls = _BOOL_ALGOS.get(op)
    if cls is None:
        raise CadError("Bu OCP sürümünde boolean desteği yok")
    scale = max(_bbox_diag(a), 1e-9)
    tries = [fuzzy] if fuzzy > 0 else [0.0, 1e-6 * scale, 1e-5 * scale]
    last_err = ""
    for fz in tries:
        try:
            if _ShapeList is not None:
                algo = cls()
                args, tls = _ShapeList(), _ShapeList()
                args.Append(a)
                tls.Append(b)
                algo.SetArguments(args)
                algo.SetTools(tls)
                try:
                    algo.SetRunParallel(True)
                except Exception:
                    pass
                if fz > 0:
                    try:
                        algo.SetFuzzyValue(float(fz))
                    except Exception:
                        pass
                algo.Build()
            else:
                algo = cls(a, b)
            failed = not algo.IsDone()
            try:
                failed = failed or bool(algo.HasErrors())
            except Exception:
                pass
            if failed:
                last_err = "çekirdek hata bildirdi"
                continue
            res = algo.Shape()
            if res is None or res.IsNull():
                last_err = "boş sonuç"
                continue
            return res
        except Exception as e:
            last_err = str(e)
    raise CadError(f"Boolean hesaplanamadı ({last_err}); araç gövdeyle düzgün kesişmiyor "
                   "olabilir ya da yüzeyler çakışıyor")


def apply_boolean(shape, tools, op, edge_size, edge_mode, tol, smooth=True, preview=False):
    """Gövdeye boolean uygular; istenirse oluşan yeni kenarları yuvarlar.
    (gövde, başarılı mı, bilgi) döndürür. Boolean başarısızsa CadError."""
    if op not in _BOOL_ALGOS or _BOOL_ALGOS[op] is None:
        raise CadError("Bu OCP sürümünde boolean desteği yok")
    if not _has_solid(shape):
        raise CadError("Ana gövde kapalı katı değil; boolean için önce bütün yüzeyleri tamamla")
    shape = prepare_solid(shape)
    tools = [prepare_solid(t) for t in tools]
    for t in tools:
        if not _has_solid(t):
            raise CadError("Araç kapalı bir hacim değil")
    vol0 = volume(shape)
    before = shape
    cur = shape
    fuzzy = 1e-5 * max(_bbox_diag(shape), 1e-9) if preview else 0.0
    for t in tools:
        res = safe_boolean(op, cur, t, fuzzy)
        cur, state = _unwrap_result(res, cur)
        if state == "empty" and op != "INTERSECT":
            raise CadError("Boolean boş sonuç verdi; gövde değiştirilmedi")
    cur = ensure_outward(_single_solid(unify(cur)))
    if not _shape_faces(cur):
        raise CadError("Boolean sonucu boş (araç gövdeyi tamamen kaplıyor olabilir)")
    vol1 = volume(cur)
    if vol0 is not None and vol1 is not None and abs(vol1 - vol0) <= 1e-9 * max(1.0, abs(vol0)):
        raise CadError("Araç gövdeyle kesişmiyor (hacim değişmedi); aracı gövdenin üzerine taşı")
    vol_txt = ""
    if vol0 and vol1 is not None:
        vol_txt = f" · hacim {(vol1 - vol0) / abs(vol0) * 100:+.1f}%"

    # Görünmeyen sonuçları yakala
    n_solids = _count(cur, TopAbs_SOLID)
    n_shells = _count(cur, TopAbs_SHELL)
    if op == "CUT" and n_solids == 1 and n_shells > 1:
        return cur, False, ("Araç gövdenin tamamen İÇİNDE: kesim içeride kapalı bir boşluk "
                            "açtı, dışarıdan görünmez. Aracı gövdenin yüzeyini kesecek şekilde "
                            "taşı" + vol_txt)
    if op == "UNION" and n_solids > 1:
        return cur, False, ("Araç gövdeye değmiyor: ayrı bir parça olarak eklendi. Aracı "
                            "gövdeyle kesişecek şekilde taşı" + vol_txt)
    if op == "CUT" and n_solids > 1:
        vol_txt += f" · gövde {n_solids} parçaya bölündü"

    if edge_size <= 1e-9:
        return cur, True, "uygulandı" + vol_txt
    edges = boolean_new_edges(cur, before, tools, edge_mode, tol)
    if not edges:
        return cur, True, "uygulandı · yuvarlanacak yeni kenar bulunamadı" + vol_txt
    _FILLET_MODE["fast"] = bool(preview)
    try:
        out = fillet_edges(cur, edges, edge_size, smooth and not preview)
    finally:
        _FILLET_MODE["fast"] = False
    if out is None:
        return cur, False, (f"kesim uygulandı ama {len(edges)} yeni kenar yuvarlanamadı "
                            "· ölçüyü küçült" + vol_txt)
    return out, True, f"uygulandı · {len(edges)} yeni kenar yuvarlandı" + vol_txt


# ================================================================ görüntüleme yardımcıları

def shape_edge_polylines(shape, samples=24):
    """Gövdenin gerçek CAD kenarlarını (üçgen değil) çizim için nokta dizileri olarak verir."""
    out = []
    degen = _static(BRep_Tool, "Degenerated")
    for e in _shape_edges(shape):
        try:
            if degen(e):
                continue
            c = _BRepAdaptor_Curve(e)
            u0, u1 = c.FirstParameter(), c.LastParameter()
            pts = []
            for k in range(samples + 1):
                p = c.Value(u0 + (u1 - u0) * k / samples)
                pts.append((p.X(), p.Y(), p.Z()))
            out.append(pts)
        except Exception:
            continue
    return out


# ================================================================ gövde kenarı kimliği

def edge_poly(e, n):
    """Kenarı parametre aralığında eşit aralıklı n noktayla örnekler (n,3)."""
    c = _BRepAdaptor_Curve(e)
    u0, u1 = c.FirstParameter(), c.LastParameter()
    pts = []
    for k in range(n):
        p = c.Value(u0 + (u1 - u0) * k / (n - 1))
        pts.append((p.X(), p.Y(), p.Z()))
    return np.array(pts, dtype=np.float64)


def edge_dense(e, tol, n0=65, n_max=4097):
    """Kenarı, kirişlerin kenardan sapması tol'un küçük bir kesrinin altında kalacak kadar
    sık örnekler; böylece match_edges eğri kenarları da kendi toleransıyla tanır."""
    n = n0
    while True:
        P = edge_poly(e, 2 * n - 1)
        even, odd = P[0::2], P[1::2]
        sag = float(np.linalg.norm(odd - 0.5 * (even[:-1] + even[1:]), axis=1).max()) \
            if len(odd) else 0.0
        if sag <= 0.25 * tol or n >= n_max:
            return P
        n = 2 * n - 1


def edge_records(edges):
    """Kenarların taşınabilir tanımlayıcıları: çizim için 65 nokta, kimlik için 9 nokta + boy.
    65 noktanın her 8.'si tam olarak 9 noktalık tanımlayıcıdır."""
    out = []
    degen = _static(BRep_Tool, "Degenerated")
    for e in edges:
        try:
            if degen(e):
                continue
            P = edge_poly(e, 65)
        except Exception:
            continue
        L = float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())
        if L <= 1e-12:
            continue
        out.append({"edge": e, "poly": P, "s": P[::8].copy(), "len": L})
    return out


# ================================================================ hayalet fillet önizlemesi

_BRepGProp_Face = _optional("OCP.BRepGProp", "BRepGProp_Face")
_ShapeAnalysis_Surface = _optional("OCP.ShapeAnalysis", "ShapeAnalysis_Surface")
_SolidClassifier = _optional("OCP.BRepClass3d", "BRepClass3d_SolidClassifier")
_TopAbs_IN = _optional("OCP.TopAbs", "TopAbs_IN")
_TopAbs_OUT = _optional("OCP.TopAbs", "TopAbs_OUT")
_gp_Vec = _optional("OCP.gp", "gp_Vec")


def ghost_available():
    return None not in (_BRepGProp_Face, _ShapeAnalysis_Surface, _DataMapAnc, _gp_Vec,
                        _BRepAdaptor_Curve)


def _first_solid(shape):
    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    if exp.More():
        return _static(TopoDS, "Solid")(exp.Current())
    return None


def _slerp(a, b, n):
    """İki birim vektör arasında n+1 noktalı küresel ara değer (n,3)."""
    dot = float(np.clip(np.dot(a, b), -1.0, 1.0))
    om = math.acos(dot)
    t = np.linspace(0.0, 1.0, n + 1)[:, None]
    if om < 1e-6:
        return a[None, :] * (1 - t) + b[None, :] * t
    s = math.sin(om)
    return (np.sin((1 - t) * om) / s) * a[None, :] + (np.sin(t * om) / s) * b[None, :]


def fillet_ghost(shape, edges, kind, size, samples=12, arc=8):
    """Gerçek fillet'i hesaplamadan, kenarın iki komşu yüzünün normallerinden yaklaşık
    fillet şeridi üretir (FORGE kernel/fillet_ghost.py yaklaşımından uyarlandı, GPL-3.0).
    (köşeler (N,3), üçgenler (M,3), sınır çizgileri (K,3) nokta çiftleri) döndürür."""
    if not edges or size <= 1e-9 or not ghost_available():
        return None
    anc = _DataMapAnc()
    _static(TopExp, "MapShapesAndAncestors")(shape, TopAbs_EDGE, TopAbs_FACE, anc)
    solid = _first_solid(shape)
    clf = None
    if solid is not None and _SolidClassifier is not None:
        try:
            clf = _SolidClassifier(solid)
        except Exception:
            clf = None
    surf_tool = _static(BRep_Tool, "Surface")
    V, T, L = [], [], []
    chamfer = kind == "CHAMFER"
    ring = 2 if chamfer else arc + 1
    for e in edges:
        try:
            if not anc.Contains(e):
                continue
            faces = []
            for f in _list_shapes(anc.FindFromKey(e)):
                if not any(f.IsSame(x) for x in faces):
                    faces.append(f)
            if len(faces) != 2:
                continue
            f1, f2 = (_FACE_CAST(f) for f in faces)
            gp1, gp2 = _BRepGProp_Face(f1), _BRepGProp_Face(f2)
            sa1 = _ShapeAnalysis_Surface(surf_tool(f1))
            sa2 = _ShapeAnalysis_Surface(surf_tool(f2))
            c = _BRepAdaptor_Curve(e)
            u0, u1 = c.FirstParameter(), c.LastParameter()
            span = u1 - u0
            params = [u0 + span * (0.01 + 0.98 * k / (samples - 1)) for k in range(samples)]
        except Exception:
            continue
        rings = []
        sign = None
        mid = len(params) // 2
        order = [mid] + [k for k in range(len(params)) if k != mid]
        by_k = {}
        for k in order:
            try:
                P, D = gp_Pnt(), _gp_Vec()
                c.D1(params[k], P, D)
                t = np.array([D.X(), D.Y(), D.Z()])
                tl = np.linalg.norm(t)
                if tl < 1e-12:
                    continue
                t /= tl
                p = np.array([P.X(), P.Y(), P.Z()])
                ns = []
                for gpf, sa in ((gp1, sa1), (gp2, sa2)):
                    uv = sa.ValueOfUV(P, 1e-3)
                    Q, N = gp_Pnt(), _gp_Vec()
                    gpf.Normal(uv.X(), uv.Y(), Q, N)
                    n = np.array([N.X(), N.Y(), N.Z()])
                    nl = np.linalg.norm(n)
                    if nl < 1e-12:
                        raise ValueError
                    ns.append(n / nl)
                n1, n2 = ns
            except Exception:
                continue
            b = n1 + n2
            bl = np.linalg.norm(b)
            cos_phi = 0.5 * bl
            if bl < 1e-9 or cos_phi < 1e-3 or cos_phi > 0.9999:
                continue                     # karşıt ya da teğet yüzler: fillet yok
            b /= bl
            if sign is None:
                sign = 1.0                   # varsayılan dışbükey
                if clf is not None and _TopAbs_IN is not None:
                    try:
                        d = min(0.5 * size, max(1e-4, 0.05 * size))
                        q = p + b * d
                        clf.Perform(gp_Pnt(*map(float, q)), 1e-7)
                        if clf.State() == _TopAbs_IN:
                            sign = -1.0      # içbükey: merkez gövdenin dışında
                    except Exception:
                        pass
            if chamfer:
                pts = []
                for n in (n1, n2):
                    u = np.cross(t, n)
                    ul = np.linalg.norm(u)
                    if ul < 1e-12:
                        break
                    u /= ul
                    if np.dot(u, b) * sign > 0:
                        u = -u
                    pts.append(p + size * u)
                if len(pts) != 2:
                    continue
                by_k[k] = np.array(pts)
            else:
                cen = p - sign * b * (size / cos_phi)
                by_k[k] = cen + size * _slerp(sign * n1, sign * n2, arc)
        rings = [by_k[k] for k in range(len(params)) if k in by_k]
        if len(rings) < 2:
            continue
        base = sum(len(v) for v in V)
        R = np.array(rings)                      # (S, ring, 3)
        V.append(R.reshape(-1, 3))
        S = len(rings)
        for i in range(S - 1):
            for j in range(ring - 1):
                a = base + i * ring + j
                bq = a + ring
                T.append((a, bq, a + 1))
                T.append((a + 1, bq, bq + 1))
        for side in (0, ring - 1):               # şeridin iki teğet sınırı
            line = R[:, side, :]
            for i in range(S - 1):
                L.append(line[i])
                L.append(line[i + 1])
        for i in (0, S - 1):                     # uç kesitler
            for j in range(ring - 1):
                L.append(R[i, j])
                L.append(R[i, j + 1])
    if not T:
        return None
    return (np.vstack(V).astype(np.float32), np.array(T, dtype=np.int32),
            np.array(L, dtype=np.float32))
