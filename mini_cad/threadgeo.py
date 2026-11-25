"""Diş, vida ve somun katıları (v0.36.0) — OCC.

Diş: threadmath'in (s, t) çokgeni eksenel düzleme konur ve helis boyunca Frenet
çerçevesiyle süpürülür (helisin Frenet normali hep eksene bakar: profil eksene göre
dönmeden ilerler). Çokgen adımdan dar olduğundan helisin komşu turları değmez.

- Dişli delik: gövde − matkap (holemath profili) − diş süpürmesi (her ağız için bir tane).
- Vida:        silindir − oluk süpürmesi; uç pahı (zarf ile kesişim) + baş + anahtar yuvası.
- Somun:       altıgen prizma (pahlı) − matkap − diş süpürmesi.

Süpürmeler katının iki ucundan taşar: uç yüzleri gövde kapaklarıyla çakışmaz. Boolean
sonucu denetlenir (geçerli mi, hacim mantıklı mı); sessizce yanlış çıkarsa küçük bir
bulanık toleransla yeniden denenir.

Yerel çerçeve: eksen +z. Vidada baş z ≥ 0 (havşa başında baş z ≤ 0, üstü z = 0'da), gövde
z = −L'ye iner. Delik aracında z malzemeye doğrudur (deliğin ekseni).
"""

import math

import numpy as np

from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepBuilderAPI import (BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeFace,
                                BRepBuilderAPI_MakePolygon, BRepBuilderAPI_MakeWire,
                                BRepBuilderAPI_Transform)
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepGProp import BRepGProp
from OCP.BRepLib import BRepLib
from OCP.BRepOffsetAPI import BRepOffsetAPI_MakePipeShell
from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakePrism, BRepPrimAPI_MakeRevol
from OCP.GC import GC_MakeArcOfCircle
from OCP.GProp import GProp_GProps
from OCP.Geom import Geom_CylindricalSurface
from OCP.Geom2d import Geom2d_Line
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopTools import TopTools_ListOfShape
from OCP.gp import (gp_Ax1, gp_Ax2, gp_Ax3, gp_Dir, gp_Dir2d, gp_Pnt, gp_Pnt2d, gp_Trsf,
                    gp_Vec)

from . import threadmath as tm
from .errors import CadError

Z = gp_Dir(0, 0, 1)
O = gp_Pnt(0, 0, 0)


# ---------------------------------------------------------------- yardımcılar

def _vol(s):
    g = GProp_GProps()
    try:
        BRepGProp.VolumeProperties_s(s, g, 1e-4)
    except Exception:
        BRepGProp.VolumeProperties_s(s, g)
    return float(g.Mass())


def _n_solids(s):
    e = TopExp_Explorer(s, TopAbs_SOLID)
    n = 0
    while e.More():
        n += 1
        e.Next()
    return n


def _valid(s):
    try:
        return BRepCheck_Analyzer(s).IsValid()
    except Exception:
        return False


def _rotz(shape, ang):
    if abs(ang) < 1e-15:
        return shape
    t = gp_Trsf()
    t.SetRotation(gp_Ax1(O, Z), ang)
    return BRepBuilderAPI_Transform(shape, t, True).Shape()


def _movez(shape, dz):
    if abs(dz) < 1e-18:
        return shape
    t = gp_Trsf()
    t.SetTranslation(gp_Vec(0, 0, dz))
    return BRepBuilderAPI_Transform(shape, t, True).Shape()


def place(shape, co, axis):
    """Yerel (eksen +z, başlangıç 0) şekli dünyaya taşı: başlangıç co, +z → axis."""
    d = np.asarray(axis, float)
    d /= max(float(np.linalg.norm(d)), 1e-15)
    a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    x = np.cross(a, d)
    x /= np.linalg.norm(x)
    t = gp_Trsf()
    t.SetTransformation(gp_Ax3(gp_Pnt(*map(float, co)), gp_Dir(*map(float, d)),
                               gp_Dir(*map(float, x))), gp_Ax3())
    return BRepBuilderAPI_Transform(shape, t, True).Shape()


def place_matrix(shape, m):
    """4×4 (satır düzeni) dönüşümle taşı (vida objesinin dünya matrisi)."""
    t = gp_Trsf()
    t.SetValues(*(float(m[i][j]) for i in range(3) for j in range(4)))
    return BRepBuilderAPI_Transform(shape, t, True).Shape()


def _bop(cls, a, b_list, fuzzy=0.0):
    algo = cls()
    args, tls = TopTools_ListOfShape(), TopTools_ListOfShape()
    args.Append(a)
    for b in b_list:
        tls.Append(b)
    algo.SetArguments(args)
    algo.SetTools(tls)
    algo.SetRunParallel(True)
    if fuzzy > 0:
        algo.SetFuzzyValue(float(fuzzy))
    algo.Build()
    if not algo.IsDone():
        return None
    r = algo.Shape()
    return None if r is None or r.IsNull() else r


def checked(op, a, tools, scale, lo=None, hi=None, what="diş"):
    """Denetimli boolean: sonuç geçerli, tek katı ve hacmi [lo, hi] içinde olmalı; değilse
    bulanık toleransla yeniden dener. CadError."""
    cls = {"CUT": BRepAlgoAPI_Cut, "FUSE": BRepAlgoAPI_Fuse, "COMMON": BRepAlgoAPI_Common}[op]
    last = "çekirdek sonuç vermedi"
    n0 = max(_n_solids(a), 1)
    for fz in (0.0, 1e-5 * scale, 1e-4 * scale):
        r = _bop(cls, a, tools, fz)
        if r is None:
            continue
        v = _vol(r)
        if not _valid(r):
            last = "geçersiz katı"
            continue
        if _n_solids(r) > n0 and op != "CUT":
            last = f"{_n_solids(r)} parça"
            continue
        if (lo is not None and v < lo) or (hi is not None and v > hi):
            last = f"hacim beklenen aralıkta değil ({v:.4g})"
            continue
        return r
    raise CadError(f"Model kaynaklı: {what} hesaplanamadı ({last}); boşluk / adım / "
                   "yükseklik değerlerini denetle")


def _poly_face(pts_xz):
    poly = BRepBuilderAPI_MakePolygon()
    for x, z in pts_xz:
        poly.Add(gp_Pnt(float(x), 0.0, float(z)))
    poly.Close()
    return poly.Wire()


def _revolve_rz(pts):
    """(r, z) kapalı çokgenini z ekseni etrafında döndür."""
    w = _poly_face(pts)
    f = BRepBuilderAPI_MakeFace(w, True).Face()
    rv = BRepPrimAPI_MakeRevol(f, gp_Ax1(O, Z), 2.0 * math.pi)
    rv.Build()
    return rv.Shape()


def _cyl(r, z0, z1):
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(0, 0, z0), Z), r, z1 - z0).Shape()


def _hex_prism(s, z0, z1, ang0=0.0):
    """Anahtar ağzı s olan altıgen prizma."""
    rc = 0.5 * s / math.cos(math.pi / 6)
    poly = BRepBuilderAPI_MakePolygon()
    for k in range(6):
        a = ang0 + k * math.pi / 3
        poly.Add(gp_Pnt(rc * math.cos(a), rc * math.sin(a), z0))
    poly.Close()
    f = BRepBuilderAPI_MakeFace(poly.Wire(), True).Face()
    return BRepPrimAPI_MakePrism(f, gp_Vec(0, 0, z1 - z0)).Shape()


def _box(x0, x1, y0, y1, z0, z1):
    poly = BRepBuilderAPI_MakePolygon()
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        poly.Add(gp_Pnt(x, y, z0))
    poly.Close()
    f = BRepBuilderAPI_MakeFace(poly.Wire(), True).Face()
    return BRepPrimAPI_MakePrism(f, gp_Vec(0, 0, z1 - z0)).Shape()


# ---------------------------------------------------------------- helisel süpürme

def _helix(r, lead, height, left):
    ax = gp_Ax3(O, Z)
    surf = Geom_CylindricalSurface(ax, r)
    sgn = -1.0 if left else 1.0
    l2 = Geom2d_Line(gp_Pnt2d(0, 0), gp_Dir2d(sgn * 2 * math.pi, lead))
    ulen = math.hypot(2 * math.pi, lead) * height / lead
    e = BRepBuilderAPI_MakeEdge(l2, surf, 0.0, ulen).Edge()
    BRepLib.BuildCurves3d_s(e)
    return BRepBuilderAPI_MakeWire(e).Wire()


def sweep(poly_st, r0, z0, height, lead, left=False, phase=0.0):
    """(s, t) çokgenini (r = r0 + t, z = z0 + s) helis boyunca süpür: z0'dan height kadar
    yükselir. Kapalı katı."""
    ss = [q[0] for q in poly_st]
    zmid = 0.5 * (min(ss) + max(ss))
    # profil helisin başladığı yerde (açı 0) ve z = 0 çevresinde kurulur, sonra kaydırılır
    pts = [(r0 + t, s - zmid) for s, t in poly_st]
    rs = max(r0 * 0.5, 1e-9)
    sp = _helix(rs, lead, height, left)
    ps = BRepOffsetAPI_MakePipeShell(sp)
    ps.SetMode(True)                      # Frenet: profil eksene göre dönmez
    ps.Add(_poly_face(pts), False, False)
    ps.Build()
    if not ps.IsDone():
        raise CadError("Diş süpürmesi kurulamadı")
    ps.MakeSolid()
    sh = ps.Shape()
    if _vol(sh) < 0:
        sh.Reverse()
    sh = _movez(sh, z0 + zmid)
    return _rotz(sh, phase)


def sweeps(poly_st, r0, z0, z1, spec, trim=None):
    """Bütün ağızlar için süpürmeler [şekil] — z0..z1 aralığını kaplar (uçlardan taşar).

    trim (za, zb): diş malzemenin içinde bitecekse süpürme bu aralıkla kırpılır (düz uç).
    Ucu katının içinde kalan ham süpürmeyle kesim OCC'de sessizce hiçbir şey yapmıyordu."""
    P = float(spec["P"])
    n = max(int(spec.get("starts", 1)), 1)
    lead = P * n
    left = spec.get("hand") == "LEFT"
    out = []
    rmax = r0 + 4.0 * P + max(abs(q[1]) for q in poly_st)
    for k in range(n):
        sh = sweep(poly_st, r0, z0 - lead, (z1 - z0) + 2.0 * lead, lead, left,
                   phase=2.0 * math.pi * k / n)
        if trim is not None:
            lim = _cyl(rmax, float(trim[0]), float(trim[1]))
            r = _bop(BRepAlgoAPI_Common, sh, [lim])
            if r is None or _vol(r) <= 0:
                raise CadError("Diş ucu kırpılamadı")
            sh = r
        out.append(sh)
    return out


def tooth_volume(poly_st, r0, height, spec):
    """Süpürmelerin toplam hacmi (Pappus): denetim için."""
    P = float(spec["P"])
    n = max(int(spec.get("starts", 1)), 1)
    return tm.thread_volume_per_turn(poly_st, r0) * (height / (P * n)) * n


# ---------------------------------------------------------------- dişli delik

def tapped_tools(spec, d_hole, engage, z0, z1):
    """Dişli deliğin diş süpürmeleri (yerel çerçeve, z malzemeye doğru): z0 (yüzeyin
    üstü) .. z1 (diş boyu). (araçlar, matkap çapı, toplam araç hacmi)."""
    r_root, _R = tm.radii(spec)
    poly, t_d, _h = tm.tooth_region(spec, d_hole, engage)
    if len(poly) < 3:
        raise CadError("Model kaynaklı: diş profili oluşmadı (boşluk çok büyük)")
    tools = sweeps(poly, r_root, z0, z1, spec)
    vol = sum(_vol(t) for t in tools)
    return tools, 2.0 * (r_root + t_d), vol


def tapped_hole_tool(drill_local, spec, d_hole, engage, z0, z1, trim=None):
    """Dişli deliğin tek aracı (yerel): matkap (holemath profili döndürmesi) ∪ diş."""
    r_root, _R = tm.radii(spec)
    poly, _t_d, _h = tm.tooth_region(spec, d_hole, engage)
    if len(poly) < 3:
        raise CadError("Model kaynaklı: diş profili oluşmadı (boşluk çok büyük)")
    teeth = sweeps(poly, r_root, z0, z1, spec, trim=trim)
    return fuse_tool(drill_local, teeth, 2.0 * max(z1 - z0, float(spec["D"])))


# ---------------------------------------------------------------- vida

def screw_solid(sp, spec, d_screw):
    """Vida katısı (yerel çerçeve). sp: {"head", "drive", "L" (baş altından uca; havşa
    başta toplam boy), "thread_len" (0: tam), "tip_chamfer" (bool), "modeled" (bool),
    "head_dims": {"dk", "k", "s", "t", "angle"}, "drive_s", "drive_t"}."""
    L = float(sp["L"])
    if L <= 0:
        raise CadError("Model kaynaklı: vida boyu sıfır")
    P = float(spec["P"])
    r_root, R = tm.radii(spec)
    poly, t_c, h = tm.groove_region(spec, d_screw)
    rc = r_root + t_c                          # vida silindiri (tepe)
    head = sp.get("head", "SOCKET")
    hd = sp.get("head_dims") or {}
    scale = 2.0 * max(L, R)
    # gövde (shank) — havşa başta baş konisi z ≤ 0 tarafındadır
    k_csk = 0.0
    if head == "CSK":
        ang = math.radians(float(hd.get("angle", 90.0)))
        k_csk = max(0.5 * float(hd["dk"]) - R, 0.0) / math.tan(0.5 * ang)
    top = 0.5 * float(hd.get("k", 0.0)) if head not in ("NONE", "CSK") else 0.0
    ztop_sh = top if top > 0 else 0.0
    n = max(int(spec.get("starts", 1)), 1)
    lead = P * n
    # diş aralığı: uçtan z_top'a
    tl = float(sp.get("thread_len") or 0.0)
    if head == "NONE":
        z_top = ztop_sh + 2.0 * lead if (tl <= 0 or tl >= L) else -(L - tl)
    else:
        z_top = -(k_csk + 0.5 * P) if (tl <= 0 or tl >= L - k_csk) else -(L - tl)
    modeled = sp.get("modeled", True) and z_top > -L + 0.5 * P
    ext = 4.0 * lead
    # Sağlam kurgu (OCC'de silindir kapağının dairesi helisel yüzeyi kesince kesim sessizce
    # boş dönüyordu): uzun silindir − iki ucu düzlemle kırpılmış oluk (uçları silindirin
    # içinde) → uç pahlı zarfla kesişim (zarfın daireleri oluğa değmez).
    z_lo = -L - ext
    z_hi = (ztop_sh + ext) if head == "NONE" else ztop_sh
    shank = _cyl(rc, z_lo, z_hi)
    if modeled:
        z_end = z_top if head != "NONE" or z_top < ztop_sh else ztop_sh + 1.5 * lead
        tools = sweeps(poly, r_root, -L - 2 * lead, z_end + lead, spec,
                       trim=(-L - 1.5 * lead, z_end))
        clip = tm._clip(poly, 1, t_c, False)
        est = tm.thread_volume_per_turn(clip, r_root) * n * (z_end + L + 1.5 * lead) / lead
        v0 = _vol(shank)
        shank = checked("CUT", shank, tools, scale, lo=v0 - est * 1.08, hi=v0 - est * 0.9,
                        what="vida dişi")
    # uç (pahlı ya da düz) ve üst sınır
    e = rc + 0.05 * R + 1e-9
    if sp.get("tip_chamfer", True):
        r_tip = min(max(r_root * 0.92 - 0.05 * h, 0.2 * R), rc * 0.95)
        prof = [(0.0, -L), (r_tip, -L), (e, -L + (e - r_tip)), (e, ztop_sh), (0.0, ztop_sh)]
    else:
        prof = [(0.0, -L), (e, -L), (e, ztop_sh), (0.0, ztop_sh)]
    if head != "NONE":
        prof[-2] = (e, ztop_sh + R)
        prof[-1] = (0.0, ztop_sh + R)
    env = _revolve_rz(prof)
    v0 = _vol(shank)
    keep = math.pi * rc * rc * (ztop_sh + L)
    shank = checked("COMMON", shank, [env], scale, lo=min(keep * 0.55, v0 * 0.3),
                    hi=keep * 1.0001, what="vida ucu")
    # baş
    hs = head_solid(head, hd, R)
    if hs is not None:
        v0, v1 = _vol(shank), _vol(hs)
        shank = checked("FUSE", shank, [hs], scale, lo=max(v0, v1) * 0.999,
                        hi=(v0 + v1) * 1.001, what="vida başı")
    # anahtar yuvası
    dr = drive_tool(sp.get("drive", "HEXSOCKET"), head, hd, R)
    if dr is not None:
        v0 = _vol(shank)
        shank = checked("CUT", shank, [dr], scale, lo=v0 * 0.5, hi=v0, what="anahtar yuvası")
    return shank


def head_solid(head, hd, R):
    if head == "NONE":
        return None
    dk, k = float(hd["dk"]), float(hd["k"])
    if head == "CSK":
        ang = math.radians(float(hd.get("angle", 90.0)))
        hc = max(0.5 * dk - R, 0.0) / math.tan(0.5 * ang)
        return _revolve_rz([(0.0, 0.0), (0.5 * dk, 0.0), (R * 0.999, -hc), (0.0, -hc)])
    if head == "HEX":
        s = float(hd["s"])
        hx = _hex_prism(s, 0.0, k)
        ch = 0.5 * s / math.cos(math.pi / 6) + 1e-6
        rtop = 0.5 * s * 0.95
        env = _revolve_rz([(0.0, -1e-3 * k), (ch * 1.2, -1e-3 * k), (ch * 1.2, k - (ch * 1.2 - rtop)
                                                                     * math.tan(math.radians(30))),
                           (rtop, k + 1e-3 * k), (0.0, k + 1e-3 * k)])
        r = _bop(BRepAlgoAPI_Common, hx, [env])
        return r if r is not None else hx
    if head == "BUTTON":
        a = 0.5 * dk
        Rs = (a * a + k * k) / (2 * k)
        arc = GC_MakeArcOfCircle(gp_Pnt(a, 0, 0),
                                 gp_Pnt(a * 0.6, 0, (Rs * Rs - (a * 0.6) ** 2) ** 0.5 - (Rs - k)),
                                 gp_Pnt(0, 0, k)).Value()
        w = BRepBuilderAPI_MakeWire()
        w.Add(BRepBuilderAPI_MakeEdge(gp_Pnt(0, 0, 0), gp_Pnt(a, 0, 0)).Edge())
        w.Add(BRepBuilderAPI_MakeEdge(arc).Edge())
        w.Add(BRepBuilderAPI_MakeEdge(gp_Pnt(0, 0, k), gp_Pnt(0, 0, 0)).Edge())
        f = BRepBuilderAPI_MakeFace(w.Wire(), True).Face()
        rv = BRepPrimAPI_MakeRevol(f, gp_Ax1(O, Z), 2.0 * math.pi)
        rv.Build()
        return rv.Shape()
    # SOCKET / CHEESE / LOWHEAD: pahlı silindir
    c = min(0.08 * dk, 0.3 * k)
    return _revolve_rz([(0.0, 0.0), (0.5 * dk, 0.0), (0.5 * dk, k - c), (0.5 * dk - c, k),
                        (0.0, k)])


def drive_tool(drive, head, hd, R):
    if drive == "NONE":
        return None
    k = float(hd.get("k", 0.0))
    ztop = 0.0 if head in ("CSK", "NONE") else k
    s = float(hd.get("s") or R)
    t = float(hd.get("t") or 0.5 * R)
    if head == "HEX" and drive == "HEXSOCKET":
        return None                            # altıgen başta yuva gerekmez
    if head == "NONE":
        t = min(t, R * 1.2)
        s = min(s, 1.1 * R) if drive == "HEXSOCKET" else s
    if drive == "HEXSOCKET":
        if head in ("NONE",):
            s = min(s, 1.0 * R)
        dz = 0.05 * t + 1e-6
        hx = _hex_prism(s, ztop - t, ztop + dz)
        # dipte 118° koni
        rc = 0.5 * s / math.cos(math.pi / 6)
        cone = _revolve_rz([(0.0, ztop - t - rc / math.tan(math.radians(59))), (rc, ztop - t),
                            (rc, ztop - t + 1e-3 * t), (0.0, ztop - t + 1e-3 * t)])
        r = _bop(BRepAlgoAPI_Fuse, hx, [cone])
        return r if r is not None else hx
    dk = float(hd.get("dk", 2 * R))
    w = max(0.16 * dk, 0.2 * R) if head not in ("NONE",) else 0.32 * R
    depth = max(min(0.45 * (k if k > 0 else 2 * R), 0.6 * R), 0.1 * R)
    if head == "CSK":
        depth = 0.45 * max(0.5 * dk - R, 0.2 * R)
    ext = 0.6 * dk + 1e-6
    b = _box(-ext, ext, -0.5 * w, 0.5 * w, ztop - depth, ztop + 0.1 * depth + 1e-6)
    if drive == "CROSS":
        b2 = _box(-0.5 * w, 0.5 * w, -ext * 0.7, ext * 0.7, ztop - depth, ztop + 0.1 * depth +
                  1e-6)
        r = _bop(BRepAlgoAPI_Fuse, b, [b2])
        return r if r is not None else b
    return b


# ---------------------------------------------------------------- somun

def nut_solid(spec, d_hole, engage, s, m, modeled=True, chamfer=True):
    """Altıgen somun (yerel: alt yüz z = 0, üst z = m) — iç diş delikle aynı kurallarla."""
    P = float(spec["P"])
    r_root, R = tm.radii(spec)
    scale = 2.0 * max(s, m)
    body = _hex_prism(s, 0.0, m)
    if chamfer:
        ch = 0.5 * s / math.cos(math.pi / 6)
        rb = 0.5 * s * 0.95
        dz = (ch * 1.2 - rb) * math.tan(math.radians(30))
        env = _revolve_rz([(0.0, -1e-3 * m), (rb, -1e-3 * m), (ch * 1.2, dz),
                           (ch * 1.2, m - dz), (rb, m + 1e-3 * m), (0.0, m + 1e-3 * m)])
        r = _bop(BRepAlgoAPI_Common, body, [env])
        body = r if r is not None else body
    poly, t_d, _h = tm.tooth_region(spec, d_hole, engage)
    rd = r_root + t_d if modeled else 0.5 * float(spec.get("tap", 2 * (R - 0.6 * P)))
    tool = _cyl(rd, -m, 2 * m)
    if modeled:
        tool = fuse_tool(tool, sweeps(poly, r_root, -P, m + P, spec), scale)
    v0 = _vol(body)
    return checked("CUT", body, [tool], scale, lo=0.05 * v0, hi=v0 * (1 - 1e-9),
                   what="somun dişi")


def fuse_tool(drill, teeth, scale):
    """Matkap + diş süpürmeleri tek araç. (Önce matkap, sonra diş kesilince OCC dişi
    sessizce atlıyordu; tek araçla tek kesim doğru.)"""
    vd = _vol(drill)
    vt = sum(_vol(t) for t in teeth)
    return checked("FUSE", drill, teeth, scale, lo=vd + 0.05 * vt, hi=(vd + vt) * 1.0001,
                   what="diş aracı")


# ---------------------------------------------------------------- dişli delik (gövdeye)

def tapped_hole(p, through_depth):
    """holemath parametrelerinden (p["thr"] modellenmiş) yerel dişli delik aracı.

    (araç, yoklama noktaları) — yoklama noktaları dişin içinde (matkabın dışında) kalan
    yerel noktalardır: kesimden sonra gövdede hâlâ malzeme varsa diş açılmamış demektir."""
    from . import holemath
    th = p["thr"]
    spec = th["spec"]
    P = float(spec["P"])
    n = max(int(spec.get("starts", 1)), 1)
    lead = P * n
    through = bool(p.get("through"))
    depth = float(through_depth if through else p["depth"])
    q = dict(p, top=5.0 * lead + P, mouth_d=0.0)
    prof = holemath.profile(q, through_depth)
    drill = _revolve_rz([(r, z) for r, z in prof])
    mouth = None
    md = float(p.get("mouth_d") or 0.0)
    if md > float(p["d"]) * 1.001:
        # ağız pahı: koninin alt dairesi diş tabanının içinde kalır (daire helisel yüzeyi
        # kesmesin); koni yanı dişi keser
        r_root, _R = tm.radii(spec)
        poly_t, _td, _h = tm.tooth_region(spec, float(th["d_hole"]), float(th.get("engage",
                                                                                1.0)))
        r_b = r_root + min(q_[1] for q_ in poly_t) - 0.05 * P
        a = math.radians(float(p.get("mouth_angle", 90.0))) * 0.5
        rm = 0.5 * md
        hb = (rm - r_b) / math.tan(a)
        top = 5.0 * lead + P
        mouth = _revolve_rz([(0.0, -top), (rm + top * math.tan(a), -top), (r_b, hb),
                             (0.0, hb)])
    z0 = -2.0 * lead
    L = float(th.get("length") or 0.0)
    if through:
        z1 = depth - 3.0 * lead
        if L > 0:
            z1 = min(z1, L)
        trim = (z0 - 2.0 * lead, z1) if L > 0 and L < depth - 3.0 * lead else None
    else:
        z1 = depth - 0.6 * P
        if L > 0:
            z1 = min(z1, L)
        if z1 <= 0.5 * P:
            raise CadError("Model kaynaklı: dişli delik çok sığ (en az bir adım derinlik)")
        trim = (z0 - 2.0 * lead, z1)
    tool = tapped_hole_tool(drill, spec, float(th["d_hole"]), float(th.get("engage", 1.0)),
                            z0, z1, trim=trim)
    if mouth is not None:
        v0, v1 = _vol(tool), _vol(mouth)
        tool = checked("FUSE", tool, [mouth], 2.0 * depth, lo=v0 * 1.0000001,
                       hi=(v0 + v1) * 1.0001, what="ağız pahı")
    probes = probe_points(spec, float(th["d_hole"]), float(th.get("engage", 1.0)), z0,
                          max(0.0, 0.5 * P), z1 - 0.5 * P)
    return tool, probes


def probe_points(spec, d_hole, engage, z0, z_lo, z_hi, k=4):
    """Dişin içinde (matkap dışında) yerel noktalar: helis süpürmesinin açı 0'daki kesitinin
    ağırlık merkezi, tur tur."""
    P = float(spec["P"])
    n = max(int(spec.get("starts", 1)), 1)
    lead = P * n
    r_root, _R = tm.radii(spec)
    poly, t_d, _h = tm.tooth_region(spec, d_hole, engage)
    # matkabın dışında kalan parçanın merkezi
    part = tm._clip(poly, 1, t_d + 0.02 * (max(q[1] for q in poly) - t_d), True)
    if len(part) < 3:
        return []
    _a, (sc, tc) = tm.area_centroid(part)
    ss = [q[0] for q in poly]
    zmid = 0.5 * (min(ss) + max(ss))
    # sweeps(): süpürme z0 − lead'den başlar, profil açı 0'da z_start + s'de durur
    z_start = (z0 - lead)
    base = z_start + zmid + (sc - zmid)
    out = []
    if z_hi <= z_lo:
        return out
    j0 = math.ceil((z_lo - base) / lead)
    j1 = math.floor((z_hi - base) / lead)
    js = list(range(j0, j1 + 1))
    if len(js) > k:
        step = (len(js) - 1) / (k - 1)
        js = [js[int(round(i * step))] for i in range(k)]
    for j in js:
        out.append((r_root + tc, 0.0, base + j * lead))
    return out
