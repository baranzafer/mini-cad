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
# v0.25.1: Coons yüzeyi için OCC'nin "StretchStyle"ı (doğrusal harmanlama = klasik Coons).
# "CoonsStyle" adına rağmen kübik harmanlama kullanıyor: yüzey kenarlardan sıfır eğimle ayrılıp
# S biçimli oluyordu (iki kemer + iki düz kenar: düz çizgili yüzeyden 0.12 sapma → 0.0004)
_GeomFill_CoonsStyle = _optional("OCP.GeomFill", "GeomFill_StretchStyle")
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
_SA_Surface = _optional("OCP.ShapeAnalysis", "ShapeAnalysis_Surface")
_PointsToBSpline = _optional("OCP.GeomAPI", "GeomAPI_PointsToBSpline")
_GeomFill = _optional("OCP.GeomFill", "GeomFill")
_GeomAbs_C2 = _optional("OCP.GeomAbs", "GeomAbs_C2")
_PointsToBSplineSurface = _optional("OCP.GeomAPI", "GeomAPI_PointsToBSplineSurface")

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
BLEND_LABELS = {"TANGENT": "teğet (G1)", "TANGENT_FREE": "teğet (G1, serbest)"}

# v0.24.0: Teğet (G1) 4 kenarlı yamada Hermite-Coons SINIR YÜZEYİ olarak kurulur (mühendislik
# programlarındaki gibi gergin; teğetlik yapı gereği, teğet ağırlığı ayarlanır). Kurulamazsa
# ya da yama 4 kenarlı değilse dolgu; 4 kenarlıda dolgu Coons yüzeyinden başlar.
# Serbest: eski davranış (boş plakadan dolgu), dışa "balon" gibi taşabilir.
BLEND_SEEDED = {"TANGENT"}
# örnekleme (tam, önizleme). 25'te ağırlık 2'de uydurma kenar yakınındaki türevi kaçırıyordu
# (kenar ortasında 6°); 33'te ≤ 0.5° (41: ≤ 0.2° ama süre 2 katı)
HERMITE_GRID = {False: 33, True: 17}


def _blend_order(blend):
    return {"TANGENT": _GeomAbs_G1, "TANGENT_FREE": _GeomAbs_G1}.get(blend)


def _is_anchor(p):
    """Kaynaşmada sabit kalan yama: keskin, düzlemsel ya da açıkça Düzlem / Coons."""
    if p.get("blend", "SHARP") not in BLEND_LABELS or p["method"] in ("PLANE", "COONS"):
        return True
    return p["method"] == "AUTO" and plane_of(p["chain"]) is not None


def blend_prepare(builder, patches):
    """v0.23.1: iki kaynaşan (sabit olmayan) yamanın ortak kenarları. Bu kenarlarda yamalar
    birbirine sırayla değil, ortak bir TEĞET ŞERİDİNE (iki yamanın keskin hâllerinin
    ortalama teğet düzlemi) G1 bağlanır: sonuç kurma sırasından bağımsız olur. Eskiden
    ilk kurulan (kısıtsız) dolgu komşusuna kötü bir destek olabiliyor, teğetlik
    sağlanamıyordu (yuvarlatılmış dikdörtgen → daire modelinde 35°)."""
    owners = {}
    for p in patches:
        if p.get("holes") or p.get("blend", "SHARP") not in BLEND_LABELS or _is_anchor(p):
            continue
        for k in {_ekey(s["p"]) for s in p["chain"]}:
            owners.setdefault(k, []).append(p)
    builder.ribbon_pairs = {k: [(q["chain"], q["sides"], q["method"]) for q in v]
                            for k, v in owners.items() if len(v) == 2}


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
        self.ribbons = {}        # teğet şeritleri (kaynaşan iki yamanın ortak kenarı)
        self.ribbon_pairs = {}   # kenar anahtarı -> [(zincir, kenarlar, yöntem)] (blend_prepare)
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

    def face(self, chain, sides, method, preview, blend="SHARP", holes=None, weight=1.0):
        ekeys = [_ekey(s["p"]) for s in chain]
        key = (tuple(ekeys), method, preview if method == "FILL" else False)
        weight = float(weight) if blend in BLEND_SEEDED and method in ("AUTO", "FILL") and \
            weight else 1.0
        if holes:
            return self._holed(chain, holes, ekeys, key)
        nbrs = []                    # [(segment, (komşu yüz, anahtarı))] — kaynaşma kısıtları
        if blend in BLEND_LABELS and method in ("AUTO", "FILL") and \
                _blend_order(blend) is not None:
            seen = set()
            for s, k in zip(chain, ekeys):
                if k in seen:
                    continue
                seen.add(k)
                rib = self._ribbon(k, s["p"], preview) if k in self.ribbon_pairs else None
                if rib is not None:
                    nbrs.append((s, rib))
                    continue
                own = self.edge_owner.get(k)
                if own is not None:
                    nbrs.append((s, own))
            if nbrs or weight != 1.0:
                key = key + (blend, preview, tuple(hash(o[1]) for _, o in nbrs),
                             round(weight, 4))
        self.face_keys.append(key)
        hit = self._get("faces", key)
        if hit is not None:
            # Kenarları da bu tura kaydet (paylaşım bozulmasın)
            for s in chain:
                self.edge(s["p"])
            self.faces[key] = hit
            self._own(ekeys, hit, key)
            return hit
        res = self._make(chain, sides, method, preview, nbrs, blend, weight)
        self.faces[key] = res
        self._own(ekeys, res, key)
        return res

    def _make(self, chain, sides, method, preview, nbrs=(), blend="SHARP", weight=1.0):
        """Yüzü kurar (önbellek / kayıt yok)."""
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
        if res is None and blend in BLEND_SEEDED and len(sides) in (3, 4) and \
                (nbrs or weight != 1.0):
            # Hermite-Coons sınır yüzeyi: komşulara teğet, teğet ağırlığıyla
            try:
                res = self._hermite(chain, sides, wire, preview, weight)
                if res is not None and not face_usable(res[0]):
                    res = None
            except CadError:
                res = None
        if res is None and nbrs:
            # Komşu yüzlere teğet / eğrilik sürekliliğiyle dolgu (ortak kenarda kaynaşır)
            try:
                res = self._filling(chain, preview, nbrs, blend, sides=sides)
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
        if res is None and method == "AUTO" and len(sides) == 3 and coons_available():
            # v0.24.1: eğri 3 kenarlı yama: tepesi noktaya inmiş Coons (ör. kare→daire köşe
            # yaması tam koni olur; Dolgu %3-5 dışa taşıyordu)
            try:
                r3 = self._hermite(chain, sides, wire, preview, 1.0, tangent=False)
                if r3 is not None and face_usable(r3[0]):
                    res = (r3[0], "Coons (3 kenar)")
            except CadError:
                pass
        if res is None:
            res = self._filling(chain, preview)
            if not face_usable(res[0]):
                raise CadError("Yüzey geçersiz çıktı (" + ", ".join(tried + ["Dolgu"]) +
                               " denendi). Döngüdeki eğrileri kontrol et")
            if tried:
                res = (res[0], res[1] + f" ({'/'.join(tried)} geçersizdi)")
        if blend_note:
            res = (res[0], res[1] + blend_note)
        return res

    def _sharp(self, chain, sides, method, preview):
        """Yamanın keskin (kaynaşmasız) hâli; kayıt yapmaz (teğet şeridi için)."""
        key = (tuple(_ekey(s["p"]) for s in chain), method, preview if method == "FILL"
               else False)
        hit = self._get("faces", key)
        if hit is None:
            hit = self._make(chain, sides, method, preview)
        self.faces[key] = hit
        return hit[0]

    def _ribbon(self, k, pts, preview):
        """Ortak kenar boyunca teğet şeridi: (yüz, anahtar) | None. İki yamanın keskin
        hâllerinin kenardaki normalleri ortalanır; şerit kenar eğrisinden bu ortak teğet
        düzleminde, kenara dik yönde uzanan dar bir yüzeydir."""
        pair = self.ribbon_pairs.get(k)
        if not pair or None in (_SA_Surface, _SLProps, _PointsToBSpline, _GeomFill,
                                _RealArray):
            return None
        rkey = ("ribbon", k, preview,
                tuple((tuple(_ekey(x["p"]) for x in ch), m) for ch, _sd, m in pair))
        hit = self._get("ribbons", rkey)
        if hit is None:
            try:
                # şeridin dayandığı keskin yüzler önizlemede de tam kalitede (teğet düzlemi
                # kaba dolgudan alınırsa önizlemede 9°'ye varan kırılma kalıyordu)
                faces = [self._sharp(ch, sd, m, False) for ch, sd, m in pair]
                hit = _make_ribbon(faces, pts)
            except Exception:
                hit = None
            if hit is None:
                return None
        self.ribbons[rkey] = hit
        return hit, rkey

    def _holed(self, chain, holes, ekeys, key):
        """Delikli düzlemsel yüz: dış tel + delik telleri (kenarlar ortak topolojiden)."""
        hkeys = tuple(tuple(_ekey(s["p"]) for s in h) for h in holes)
        key = key + ("holes", hkeys)
        self.face_keys.append(key)
        hit = self._get("faces", key)
        if hit is not None:
            for s in chain:
                self.edge(s["p"])
            for h in holes:
                for s in h:
                    self.edge(s["p"])
            self.faces[key] = hit
            self._own(ekeys, hit, key)
            return hit
        pl = plane_of(chain + [s for h in holes for s in h])
        if pl is None:
            raise CadError("Delikli yüzey düzlemsel olmalı (döngüler aynı düzlemde değil)")
        outer = self._wire(chain)
        mf = BRepBuilderAPI_MakeFace(outer, True)
        if not mf.IsDone():
            c, n = pl
            mf = BRepBuilderAPI_MakeFace(gp_Pln(_pnt(c), gp_Dir(*map(float, n))), outer, True)
            if not mf.IsDone():
                raise CadError("Dış sınırdan yüz oluşturulamadı")
        c, n = pl
        n = np.asarray(n, dtype=np.float64)

        def signed_area(ch):
            P = np.vstack([_np(x["p"]) for x in ch])
            u = P[1] - P[0] if len(P) > 1 else np.array([1.0, 0, 0])
            u = u - n * float(np.dot(u, n))
            u = u / max(float(np.linalg.norm(u)), 1e-15)
            v = np.cross(n, u)
            x, y = (P - c) @ u, (P - c) @ v
            return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
        so = signed_area(chain)
        for h in holes:
            w = self._wire(h)
            # delik teli dış telin tersi yönde dönmeli
            if signed_area(h) * so > 0:
                w = _static(TopoDS, "Wire")(w.Reversed())
            mf.Add(w)
        if not mf.IsDone():
            raise CadError("Delikler yüze eklenemedi")
        face = mf.Face()
        if _BRepCheck_Analyzer is not None and not _BRepCheck_Analyzer(face).IsValid():
            face = _fix_face(face)
        if not face_usable(face):
            raise CadError("Delikli yüz geçersiz çıktı (delikler dış sınırın içinde mi?)")
        res = (face, f"Düzlem · {len(holes)} delik")
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
        face = _fix_face(mf.Face())
        if not face_usable(face):
            # v0.24.0: yüzeyin parametre yönü tel yönünün tersiyse kırpılan yüz "ters" çıkıp
            # geçersiz sayılıyordu (4 kenarlı eğri yamalar hep Dolgu'ya düşüyordu)
            try:
                mf2 = BRepBuilderAPI_MakeFace(fill.Surface(),
                                              _static(TopoDS, "Wire")(wire.Reversed()), True)
                if mf2.IsDone():
                    f2 = _fix_face(mf2.Face())
                    if face_usable(f2):
                        face = f2
            except Exception:
                pass
        return face, "Coons"

    @staticmethod
    def _coons_surface(sides):
        """4 kenarlı yamanın Coons sınır yüzeyi (Geom) | None."""
        if len(sides) != 4 or not coons_available():
            return None
        try:
            curves = [_bspline_from_side(s) for s in sides]
            return _GeomFill_BSplineCurves(curves[0], curves[1], curves[2], curves[3],
                                           _GeomFill_CoonsStyle).Surface()
        except Exception:
            return None

    @staticmethod
    def _support_edge(face, edge, pts):
        """Teğet kısıtı için destek yüzünde kullanılacak kenar. Kısıt kenarının o yüzde
        parametrik eğrisi (pcurve) olmalı: yoksa OCC dolgu aracı ÇÖKER (segfault). Ortak kenar
        yüzdeyse o; değilse (Dolgu yüzleri kenarları kopyalar) yüzün aynı geometrideki kendi
        kenarı; bulunamazsa None (o kenar keskin kalır). v0.23.1"""
        if _has_pcurve(edge, face):
            return edge
        if _BRepAdaptor_Curve is None:
            return None
        P = _np(_cubic(_np(pts)))
        S = np.array([_bez(P, t) for t in np.linspace(0.0, 1.0, 65)])
        a, b = S[0], S[-1]
        tol = 1e-4 * (1.0 + float(np.ptp(S, axis=0).max()))
        degen = _static(BRep_Tool, "Degenerated")
        exp = TopExp_Explorer(face, TopAbs_EDGE)
        while exp.More():
            e = _EDGE_CAST(exp.Current())
            exp.Next()
            try:
                if degen(e):
                    continue
                c = _BRepAdaptor_Curve(e)
                u0, u1 = c.FirstParameter(), c.LastParameter()
                Q = []
                for u in (u0, u0 + (u1 - u0) * 0.25, 0.5 * (u0 + u1), u0 + (u1 - u0) * 0.75, u1):
                    q = c.Value(u)
                    Q.append((q.X(), q.Y(), q.Z()))
                Q = np.array(Q)
            except Exception:
                continue
            ends = min(np.linalg.norm(Q[0] - a) + np.linalg.norm(Q[-1] - b),
                       np.linalg.norm(Q[0] - b) + np.linalg.norm(Q[-1] - a))
            if ends > 2 * tol:
                continue
            if max(float(np.min(np.linalg.norm(S - q, axis=1))) for q in Q[1:-1]) > \
                    tol + float(np.linalg.norm(S[1] - S[0])):
                continue
            if _has_pcurve(e, face):
                return e
        return None

    def _filling(self, chain, preview, nbrs=None, blend=None, sides=None):
        """Dolgu yüzeyi. nbrs verilirse o kenarlar komşu yüze teğet (G1) sürekliliğiyle
        bağlanır; diğer kenarlar yalnızca konumdan (C0).
        v0.24.0: blend "TANGENT" ve 4 kenar: dolgu Coons sınır yüzeyinden başlar (balon
        etkisi: yuvarlatılmış dikdörtgen → daire modelinde yama boyunun %1,3'ü → %0,5)."""
        base = self._coons_surface(sides) if blend in BLEND_SEEDED and sides is not None \
            else None
        prm = FILL_PREVIEW if preview else FILL_FINAL
        nbiter = prm["nbiter"]
        if nbrs and blend in BLEND_LABELS:
            nbiter = max(nbiter, 2)      # önizlemede tek tur teğetliği tutturamıyor (12° → 2°)
        filler = BRepOffsetAPI_MakeFilling(prm["degree"], prm["nbpts"], nbiter, False,
                                           1e-5, 1e-4, 1e-2, 0.1, prm["maxdeg"], prm["maxseg"])
        sup = {id(s): own[0] for s, own in (nbrs or ())}
        order = _blend_order(blend) if sup else None
        n_cons = 0
        if base is not None and blend in BLEND_SEEDED:
            try:
                filler.LoadInitSurface(BRepBuilderAPI_MakeFace(base, 1e-6).Face())
            except Exception:
                pass
        try:
            for s in chain:
                e = self.edge(s["p"])
                f = sup.get(id(s))
                es = None
                if f is not None and order is not None:
                    f = _FACE_CAST(f)
                    es = self._support_edge(f, e, s["p"])
                if es is not None:
                    filler.Add(es, f, order, True)
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
        if base is not None and blend in BLEND_SEEDED and sides is not None and \
                len(sides) == 4:
            label = "Sınır dolgusu"
        if n_cons:
            label += f" · {n_cons} kenarda {BLEND_LABELS[blend]}"
        return _FACE_CAST(exp.Current()), label

    # ------------------------------------------------------------ Hermite-Coons (v0.24.0)

    def _side_plane(self, seg):
        """Kenar segmentinde teğet düzlemini veren yüzler: [(yüz, ağırlık)] | None (serbest).
        Kaynaşan komşu: iki yamanın keskin hâlleri (ortalanır); sabit komşu: onun yüzü."""
        P = np.array(seg["p"], dtype=np.float64)
        if float(np.linalg.norm(P - P[0], axis=1).max()) < 1e-12:
            return None                                    # dejenere (üçgen tepesi)
        k = _ekey(seg["p"])
        pair = self.ribbon_pairs.get(k)
        if pair:
            try:
                return [self._sharp(ch, sd, m, False) for ch, sd, m in pair]
            except CadError:
                return None
        own = self.edge_owner.get(k)
        if own is not None:
            return [own[0]]
        return None

    def _hermite(self, chain, sides, wire, preview, weight=1.0, tangent=True):
        """4 kenarlı yamanın teğet ağırlıklı (bikübik Hermite) Coons sınır yüzeyi.

        Sınır eğrileri aynen geçilir. Her kenarda yüzeyin kenardan ayrılış türevi
        (çapraz türev) doğrusal Coons yüzeyininkidir; komşusu olan kenarda bu türev ortak teğet
        düzlemine yatırılır (komşu da aynı düzlemi kullandığı için G1 yapı gereği), büyüklüğü
        kenar ortasında teğet ağırlığı kadar ölçeklenir (köşelerde 1: uyumluluk). Yüzey ızgarada
        örneklenip B-spline'a uydurulur ve telle kırpılır. (yüz, etiket) | None"""
        if None in (_PointsToBSplineSurface, _Pnt2Array, _GeomAbs_C2, _SA_Surface, _SLProps):
            return None
        sd = [[{"p": [tuple(map(float, q)) for q in sg["p"]]} for sg in side] for side in sides]
        if len(sd) == 3:
            sd = _tri_to_quad(sd)
            if sd is None:
                return None
        # kenarları döngü yönünde sırala: side[i] sonu = side[i+1] başı
        def ends(side):
            return np.array(side[0]["p"][0]), np.array(side[-1]["p"][-1])

        def rev(side):
            return [{"p": list(reversed(sg["p"]))} for sg in reversed(side)]
        a0, b0 = ends(sd[0])
        a1, b1 = ends(sd[1])
        if min(np.linalg.norm(a0 - a1), np.linalg.norm(a0 - b1)) < \
                min(np.linalg.norm(b0 - a1), np.linalg.norm(b0 - b1)):
            sd[0] = rev(sd[0])
        for i in range(1, 4):
            prev_end = ends(sd[i - 1])[1]
            a, b = ends(sd[i])
            if np.linalg.norm(b - prev_end) < np.linalg.norm(a - prev_end):
                sd[i] = rev(sd[i])
        B = np.array([q for side in sd for sg in side for q in sg["p"]], dtype=np.float64)
        size = float(np.linalg.norm(np.ptp(B, axis=0)))
        if size < 1e-9 or np.linalg.norm(ends(sd[3])[1] - ends(sd[0])[0]) > 1e-4 * size:
            return None

        def curve(side):
            Ps = [_np(_cubic(_np(sg["p"]))) for sg in side]
            n = len(Ps)

            def f(t):
                x = min(max(t, 0.0), 1.0) * n
                i = min(int(x), n - 1)
                tt = x - i
                return _bez(Ps[i], tt), _bez_d(Ps[i], tt) * n, side[i]
            return f
        cs = [curve(side) for side in sd]
        Cg = B.mean(axis=0)                     # yamanın ağırlık merkezi (içeri yönü)
        planes = [[self._side_plane(sg) if tangent else None for sg in side] for side in sd]

        # c0(u)=S(u,0): kenar 0; d1(v)=S(1,v): kenar 1; c1(u)=S(u,1): kenar 2 ters;
        # d0(v)=S(0,v): kenar 3 ters
        def c0(u):
            p, d, _ = cs[0](u)
            return p, d

        def d1(v):
            p, d, _ = cs[1](v)
            return p, d

        def c1(u):
            p, d, _ = cs[2](1.0 - u)
            return p, -d

        def d0(v):
            p, d, _ = cs[3](1.0 - v)
            return p, -d
        P00, P10, P11, P01 = c0(0)[0], c0(1)[0], c1(1)[0], c1(0)[0]

        def sv0(u):           # doğrusal Coons'un v=0'daki çapraz türevi
            return c1(u)[0] - c0(u)[0] + (1 - u) * d0(0)[1] + u * d1(0)[1] - \
                (1 - u) * (P01 - P00) - u * (P11 - P10)

        def sv1(u):
            return c1(u)[0] - c0(u)[0] + (1 - u) * d0(1)[1] + u * d1(1)[1] - \
                (1 - u) * (P01 - P00) - u * (P11 - P10)

        def su0(v):
            return d1(v)[0] - d0(v)[0] + (1 - v) * c0(0)[1] + v * c1(0)[1] - \
                (1 - v) * (P10 - P00) - v * (P11 - P01)

        def su1(v):
            return d1(v)[0] - d0(v)[0] + (1 - v) * c0(1)[1] + v * c1(1)[1] - \
                (1 - v) * (P10 - P00) - v * (P11 - P01)
        n_tan = [0]

        # türev yönü: u=0 / v=0 kenarında (kenar 0, 3) içeri, u=1 / v=1 kenarında (1, 2) dışarı
        inward = {0: 1.0, 3: 1.0, 1: -1.0, 2: -1.0}

        def adj(side_i, t_side, vec, t_edge, compat=None):
            """Çapraz türevi kenarın teğet düzlemine yatır, ağırlıkla ölçekle. compat:
            kenarın iki ucundaki köşe-uyumlu türevler (komşu sınır eğrilerinin teğetleri);
            uçlara yakın (%20) bunlara yumuşakça geçilir: köşede teğet düzlemi komşu eğriyi
            içermiyorsa (üç yüzeye birden teğet olunamaz) hata köşede kalır, kenara yayılmaz."""
            p, _d, sg = cs[side_i](t_side)
            j = sd[side_i].index(sg)
            faces = planes[side_i][j]
            out = np.asarray(vec, dtype=np.float64)
            if faces:
                # normaller kenarın tam ucundan değil biraz içeriden: uç komşu yüzün tekil
                # noktası olabilir (ör. koni tepesi), normal tanımsız / çöp (v0.24.1)
                pn = cs[side_i](min(max(t_side, 2e-3), 1.0 - 2e-3))[0]
                ns = []
                for f in faces:
                    try:
                        nv = _face_normal(f, pn)
                    except Exception:
                        nv = None
                    if nv is not None and np.linalg.norm(nv) > 1e-12:
                        ns.append(nv / np.linalg.norm(nv))
                if ns:
                    if len(ns) == 2 and float(np.dot(ns[0], ns[1])) < 0:
                        ns[1] = -ns[1]
                    n = sum(ns)
                    n = n / max(float(np.linalg.norm(n)), 1e-15)
                    m = float(np.linalg.norm(out))
                    # teğet düzleminde: kenar boyu (T) bileşeni korunur, kenara dik (D) bileşen
                    # yamanın içine doğru ve büyüklük korunacak şekilde; yüzey düzleme dik
                    # yaklaşıyorsa izdüşüm sıfıra yakın çıkıp yön kenar boyuna dönmesin
                    T = _d / max(float(np.linalg.norm(_d)), 1e-15)
                    D = np.cross(n, T)
                    nd = float(np.linalg.norm(D))
                    if nd > 1e-12 and m > 1e-15:
                        D = D / nd
                        # içeri yönü yamanın merkezinden (türev kenara paralelleşince türevin
                        # işareti rastgeleleşiyor, uç düzeltmesi yüzeyi katlıyordu — v0.24.1)
                        inn = Cg - p
                        inn = inn - float(np.dot(inn, T)) * T
                        ref = out
                        if abs(float(np.dot(D, out))) < 0.2 * m and \
                                float(np.linalg.norm(inn)) > 1e-9 * size:
                            ref = inward[side_i] * inn
                        if float(np.dot(D, ref)) < 0:
                            D = -D
                        vt = float(np.dot(out, T))
                        vd = math.sqrt(max(m * m - vt * vt, (0.25 * m) ** 2))
                        out = vt * T + vd * D
                    else:
                        out = out - float(np.dot(out, n)) * n
                    out = out * (1.0 + (weight - 1.0) * math.sin(math.pi * t_edge) ** 2)
            if compat is not None:
                # yalnızca uçtaki FARK (uyumlu − ham) yumuşakça eklenir: uç zaten uyumluysa
                # (ör. koni) türev hiç değişmez (v0.24.1; önce türevin kendisi uç değerine
                # çekiliyordu, kare→daire köşe konisi ~%2 bozuluyor, tepede büzülme oluyordu)
                dl = 0.2
                for end, cv, raw in compat:
                    x = abs(t_edge - end) / dl
                    if x < 1.0:
                        beta = 1.0 - (3 * x * x - 2 * x * x * x)
                        out = out + beta * (np.asarray(cv) - raw)
            return out

        # köşe uyumlu türevler: S_v(0,0)=d0'(0) ... (komşu sınır eğrilerinin teğetleri)
        cmp_t0 = (d0(0.0)[1], d1(0.0)[1])
        cmp_t1 = (d0(1.0)[1], d1(1.0)[1])
        cmp_s0 = (c0(0.0)[1], c1(0.0)[1])
        cmp_s1 = (c0(1.0)[1], c1(1.0)[1])

        def with_raw(side_i, tside, vec, cmp):
            # (uç, uyumlu değer, o uçtaki ham düzeltilmiş türev)
            return [(0.0, cmp[0], adj(side_i, tside(0.0), vec(0.0), 0.0)),
                    (1.0, cmp[1], adj(side_i, tside(1.0), vec(1.0), 1.0))]
        cmp_t0 = with_raw(0, lambda u: u, sv0, cmp_t0)
        cmp_t1 = with_raw(2, lambda u: 1.0 - u, sv1, cmp_t1)
        cmp_s0 = with_raw(3, lambda v: 1.0 - v, su0, cmp_s0)
        cmp_s1 = with_raw(1, lambda v: v, su1, cmp_s1)

        def t0(u):
            return adj(0, u, sv0(u), u, cmp_t0)

        def t1(u):
            return adj(2, 1.0 - u, sv1(u), u, cmp_t1)

        def s0(v):
            return adj(3, 1.0 - v, su0(v), v, cmp_s0)

        def s1(v):
            return adj(1, v, su1(v), v, cmp_s1)
        for i, side in enumerate(sd):
            n_tan[0] += 1 if any(planes[i]) else 0
        h = 2e-3

        def dd(f, t):
            # uçta tek yönlü, uca dokunmayan fark (uç değeri tekil olabilir)
            if t <= 0.0:
                return (f(2 * h) - f(h)) / h
            if t >= 1.0:
                return (f(1.0 - h) - f(1.0 - 2 * h)) / h
            return (f(t + h) - f(t - h)) / (2 * h)
        # Köşe twist'leri Gregory biçiminde: köşede iki kenarın istediği değerler farklıysa
        # twist hangi kenara yakınsa onunkine kayar; böylece iki kenarın çapraz türevi de tam
        # sağlanır (ortalama twist teğet kenarlara ~2° kırılma sızdırıyordu)
        tw = {(0, 0): (dd(s0, 0.0), dd(t0, 0.0)), (0, 1): (dd(s0, 1.0), dd(t1, 0.0)),
              (1, 0): (dd(s1, 0.0), dd(t0, 1.0)), (1, 1): (dd(s1, 1.0), dd(t1, 1.0))}

        def twist(cu, cv, u, v):
            a, b = tw[(cu, cv)]               # a: v-kenarı (u sabit) için, b: u-kenarı için
            du = u if cu == 0 else 1.0 - u
            dv = v if cv == 0 else 1.0 - v
            if du + dv < 1e-12:
                return 0.5 * (a + b)
            return (du * a + dv * b) / (du + dv)
        Mfix = [[P00, P01, t0(0.0), t1(0.0)],
                [P10, P11, t0(1.0), t1(1.0)],
                [s0(0.0), s0(1.0), None, None],
                [s1(0.0), s1(1.0), None, None]]

        def H(t):
            return (2 * t ** 3 - 3 * t ** 2 + 1, -2 * t ** 3 + 3 * t ** 2, t ** 3 - 2 * t ** 2 + t,
                    t ** 3 - t ** 2)
        N = HERMITE_GRID[bool(preview)]
        ts = np.linspace(0.0, 1.0, N)
        C0 = [c0(u)[0] for u in ts]
        C1 = [c1(u)[0] for u in ts]
        T0 = [t0(u) for u in ts]
        T1 = [t1(u) for u in ts]
        D0 = [d0(v)[0] for v in ts]
        D1 = [d1(v)[0] for v in ts]
        S0 = [s0(v) for v in ts]
        S1 = [s1(v) for v in ts]
        Hs = [H(t) for t in ts]
        G = np.zeros((N, N, 3))
        for i, u in enumerate(ts):
            hu = Hs[i]
            for j, v in enumerate(ts):
                hv = Hs[j]
                Lu = hu[0] * D0[j] + hu[1] * D1[j] + hu[2] * S0[j] + hu[3] * S1[j]
                Lv = hv[0] * C0[i] + hv[1] * C1[i] + hv[2] * T0[i] + hv[3] * T1[i]
                Bt = sum(hu[a] * hv[b] * Mfix[a][b] for a in range(4) for b in range(4)
                         if Mfix[a][b] is not None)
                Bt = Bt + hu[2] * hv[2] * twist(0, 0, u, v) + hu[2] * hv[3] * twist(0, 1, u, v) \
                    + hu[3] * hv[2] * twist(1, 0, u, v) + hu[3] * hv[3] * twist(1, 1, u, v)
                G[i, j] = Lu + Lv - Bt
        if not _grid_sane(G, B):
            return None                          # güvenli yedek: Coons'tan başlayan dolgu
        arr = _Pnt2Array(1, N, 1, N)
        for i in range(N):
            for j in range(N):
                arr.SetValue(i + 1, j + 1, _pnt(G[i, j]))
        fit = _PointsToBSplineSurface(arr, 3, 8, _GeomAbs_C2, 1e-6 * max(size, 1e-3))
        if not fit.IsDone():
            return None
        surf = fit.Surface()
        face = None
        for w in (wire, _static(TopoDS, "Wire")(wire.Reversed())):
            try:
                mf = BRepBuilderAPI_MakeFace(surf, w, True)
                if not mf.IsDone():
                    continue
                f = _fix_face(mf.Face())
                if face_usable(f):
                    face = f
                    break
            except Exception:
                continue
        if face is None:
            return None
        label = "Sınır yüzeyi"
        if n_tan[0]:
            label += f" · {n_tan[0]} kenarda {BLEND_LABELS['TANGENT']}"
        if abs(weight - 1.0) > 1e-9:
            label += f" · teğet ağırlığı {weight:.2f}"
        return face, label


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


def _bez(P, t):
    """Kübik bezier noktası (P: 4×3)."""
    m = 1.0 - t
    return m * m * m * P[0] + 3 * m * m * t * P[1] + 3 * m * t * t * P[2] + t * t * t * P[3]


def _bez_d(P, t):
    m = 1.0 - t
    return 3 * (m * m * (P[1] - P[0]) + 2 * m * t * (P[2] - P[1]) + t * t * (P[3] - P[2]))


_SA_CACHE = {}


def _face_normal(face, p):
    """Yüzün p noktasına en yakın yerdeki (yönelimli) normali | None."""
    hk = hash(face)
    ent = _SA_CACHE.get(hk)
    if ent is None or not ent[0].IsSame(face):
        surf = _static(BRep_Tool, "Surface")(face)
        ent = (face, surf, _SA_Surface(surf))
        if len(_SA_CACHE) > 256:
            _SA_CACHE.clear()
        _SA_CACHE[hk] = ent
    _f, surf, sa = ent
    uv = sa.ValueOfUV(_pnt(p), 1e-7)
    pr = _SLProps(surf, uv.X(), uv.Y(), 1, 1e-9)
    if not pr.IsNormalDefined():
        return None
    n = pr.Normal()
    n = np.array([n.X(), n.Y(), n.Z()])
    return -n if face.Orientation() == TopAbs_REVERSED else n


def _make_ribbon(faces, pts, n_samples=17):
    """Teğet şeridi yüzü: kenar eğrisi C(t) ile C(t) + w·D(t) arası doğrusal yüzey;
    D, iki yüzün ortalama normaline ve kenar teğetine dik. | None"""
    P = _np(_cubic(_np(pts)))
    ts = np.linspace(0.0, 1.0, n_samples)
    C = np.array([_bez(P, t) for t in ts])
    length = float(np.sum(np.linalg.norm(np.diff(C, axis=0), axis=1)))
    if length < 1e-9:
        return None
    w = 0.1 * length
    R = []
    prev = None
    for t, c in zip(ts, C):
        ns = [_face_normal(f, c) for f in faces]
        ns = [n / np.linalg.norm(n) for n in ns if n is not None and np.linalg.norm(n) > 1e-12]
        if not ns:
            return None
        if len(ns) == 2 and float(np.dot(ns[0], ns[1])) < 0:
            ns[1] = -ns[1]                       # yönelim farkı: yalnızca düzlem önemli
        n = ns[0] + (ns[1] if len(ns) == 2 else 0.0)
        T = _bez_d(P, t)
        D = np.cross(n, T)
        nd = float(np.linalg.norm(D))
        if nd < 1e-12:
            return None
        D = D / nd
        if prev is not None and float(np.dot(D, prev)) < 0:
            D = -D                               # şerit kenarın hep aynı yanında
        prev = D
        R.append(c + w * D)
    par = _RealArray(1, n_samples)
    for i, t in enumerate(ts):
        par.SetValue(i + 1, float(t))
    curves = []
    for Q in (C, np.array(R)):
        ap = _PointsToBSpline(_pnt_array(Q), par, 3, 8, _GeomAbs_C2, 1e-7)
        if not ap.IsDone():
            return None
        curves.append(ap.Curve())
    surf = _static(_GeomFill, "Surface")(curves[0], curves[1])
    mf = BRepBuilderAPI_MakeFace(surf, 1e-7)
    if not mf.IsDone():
        return None
    return mf.Face()


def _grid_sane(G, B):
    """Hermite ızgarası makul mü? Sınır noktalarının kutusunun çok dışına taşan ya da katlanan
    (komşu hücre normalleri ters) yüzey reddedilir. Böyle bir yüzey OCC'nin üçgenleyicisini
    sonsuz döngüye sokabiliyor (v0.24.1, bozuk twist ile görüldü)."""
    if not np.all(np.isfinite(G)):
        return False
    lo, hi = B.min(axis=0), B.max(axis=0)
    ext = float(np.max(hi - lo))
    pad = 0.75 * ext
    P = G.reshape(-1, 3)
    if np.any(P < lo - pad) or np.any(P > hi + pad):
        return False
    du = G[1:, :-1] - G[:-1, :-1]
    dv = G[:-1, 1:] - G[:-1, :-1]
    n = np.cross(du, dv)
    a = np.linalg.norm(n, axis=2)
    ok = a > 1e-9 * max(a.max(), 1e-300)
    nu = np.where(ok[..., None], n / np.maximum(a, 1e-300)[..., None], 0.0)
    for x, y, mx, my in ((nu[1:], nu[:-1], ok[1:], ok[:-1]),
                         (nu[:, 1:], nu[:, :-1], ok[:, 1:], ok[:, :-1])):
        d = np.einsum("ijk,ijk->ij", x, y)
        if np.any((d < 0.0) & mx & my):
            return False
    return True


def _tri_to_quad(sd):
    """3 kenarlı yamayı, bir köşesi noktaya inmiş 4 kenarlıya çevirir (Hermite-Coons için).
    Taban: en eğri kenar (eğrilik eşitse en uzun); karşısındaki köşe tepe olur. Taban ve iki
    yan kenar döngü sırasıyla [taban, yan1, (tepe), yan2]."""
    def ends(side):
        return np.array(side[0]["p"][0]), np.array(side[-1]["p"][-1])

    def score(side):
        P = np.array([q for sg in side for q in sg["p"]], dtype=np.float64)
        a, b = P[0], P[-1]
        ch = b - a
        L = float(np.linalg.norm(ch))
        if L < 1e-12:
            return 0.0
        ch = ch / L
        dev = float(np.max(np.linalg.norm((P - a) - np.outer((P - a) @ ch, ch), axis=1)))
        return dev + 1e-6 * L
    k = int(np.argmax([score(x) for x in sd]))
    sd = sd[k:] + sd[:k]
    a0, b0 = ends(sd[0])
    a1, b1 = ends(sd[1])

    def gap(q):
        return min(np.linalg.norm(q - a0), np.linalg.norm(q - b0))
    apex = b1 if gap(b1) >= gap(a1) else a1                # tabanda olmayan köşe
    ap = tuple(map(float, apex))
    return [sd[0], sd[1], [{"p": [ap, ap, ap, ap]}], sd[2]]


def _has_pcurve(edge, face):
    """Kenarın yüz üzerinde parametrik eğrisi var mı? (düzlemde OCC kendisi hesaplar)"""
    try:
        c = _static(BRep_Tool, "CurveOnSurface")(edge, face, 0.0, 0.0)
    except Exception:
        return False
    return c is not None and not (hasattr(c, "IsNull") and c.IsNull())


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
