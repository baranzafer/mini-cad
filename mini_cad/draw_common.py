"""Çizim aracının ortak parçaları: sabitler, renkler, ölçü ayrıştırma, yakalama referansları
(_Refs), GPU çizim yardımcıları, taslak düzenleme yardımcıları ve araç tabloları.

draw.py ve draw_*.py mixin modülleri buradan içe aktarır. draw.py bu adları geriye dönük
uyum için yeniden dışa aktarır (draw.dm, draw.is_running, draw.cleanup_all, draw._STATE ...).
"""
import blf
import bpy
import gpu
import math
import numpy as np
from gpu_extras.batch import batch_for_shader

from . import core
from . import drawmath as dm

SNAP_PX = 12

GUIDE_PX = 8

REF_PX = 300

COL_DONE = (0.25, 0.85, 1.0, 1.0)

COL_RUBBER = (1.0, 0.62, 0.1, 1.0)

COL_SNAP = (1.0, 0.85, 0.15, 1.0)

COL_GUIDE = (0.6, 0.9, 0.6, 0.9)

COL_REF = (0.6, 0.9, 0.6, 0.6)

COL_U = (0.95, 0.3, 0.3, 0.9)

COL_V = (0.4, 0.9, 0.3, 0.9)

COL_BOX = (0.08, 0.08, 0.08, 0.78)

COL_TEXT = (0.95, 0.95, 0.95, 1.0)

COL_ACTIVE = (1.0, 0.75, 0.25, 1.0)

COL_GRID = (0.75, 0.75, 0.8, 0.22)

PLANE_COLS = {"XY": (0.72, 0.72, 0.75), "XZ": (0.72, 0.72, 0.75), "YZ": (0.72, 0.72, 0.75),
              "FACE": (0.85, 0.85, 0.88)}

AXIS_COLS = ((1.0, 0.2, 0.32, 0.95), (0.54, 0.86, 0.0, 0.95), (0.16, 0.56, 1.0, 0.95))

def _axis_col(v):
    """Blender eksen renkleri: X kırmızı, Y yeşil, Z mavi; eksene paralel değilse gri."""
    a = np.abs(np.asarray(v, dtype=np.float64))
    k = int(np.argmax(a))
    return AXIS_COLS[k] if a[k] > 0.999 else (0.8, 0.8, 0.8, 0.9)

GRID_PX = 6          # ızgara mıknatısı (piksel): bilerek zayıf

GRID_MIN_PX = 18     # ekranda ızgara aralığı en az bu kadar piksel

PRIORITY = {"Başlangıç": -1, "Uç": 0, "Merkez": 0, "Nokta": 0, "Orta": 1, "Kesişim": 2,
            "Yakın": 3}

PASS_KEYS = {
    "MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "TRACKPADPAN", "TRACKPADZOOM",
    "MOUSEROTATE", "MOUSESMARTZOOM", "NDOF_MOTION",
    "NUMPAD_0", "NUMPAD_1", "NUMPAD_2", "NUMPAD_3", "NUMPAD_4", "NUMPAD_5", "NUMPAD_6",
    "NUMPAD_7", "NUMPAD_8", "NUMPAD_9", "NUMPAD_PERIOD", "NUMPAD_PLUS", "NUMPAD_MINUS",
    "NUMPAD_SLASH", "NUMPAD_ASTERIX", "HOME", "N",
}

MODIFIERS = {"LEFT_SHIFT", "RIGHT_SHIFT", "LEFT_CTRL", "RIGHT_CTRL"}

_UNIT_SUFFIX = {"MICROMETERS": "um", "MILLIMETERS": "mm", "CENTIMETERS": "cm",
                "METERS": "m", "KILOMETERS": "km", "INCHES": "in", "FEET": "ft",
                "MILES": "mi", "THOU": "thou"}

_STATE = {"active": None}

_HANDLES = []

_LAST = {"curve": ""}

# ================================================================ değer girişi

def parse_length(text):
    t = text.strip().replace(",", ".")
    if not t:
        return None
    try:
        us = bpy.context.scene.unit_settings
        if us.system == "NONE":
            v = float(t)
        else:
            try:
                v = float(t)
                bare = True
            except ValueError:
                bare = False
            if bare:
                suf = _UNIT_SUFFIX.get(getattr(us, "length_unit", ""), None)
                v = bpy.utils.units.to_value(us.system, "LENGTH", t + suf) if suf else v
            else:
                v = bpy.utils.units.to_value(us.system, "LENGTH", t)
            v = v / (us.scale_length or 1.0)
    except Exception:
        return None
    return v if v > 0 else None

def parse_angle(text):
    t = text.strip().replace(",", ".").rstrip("°").strip()
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None

# ================================================================ yakalama verisi

def _bezier(p, t):
    p0, p1, p2, p3 = p
    u = 1.0 - t
    return u ** 3 * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t ** 3 * p3

class _Refs:
    """Görünür tel kafes ve CAD gövdelerinden yakalama noktaları, doğru parçaları ve kısıt
    seçimi için kimlikli tel kafes segmentleri / noktaları."""

    def __init__(self, context, strokes=(), points=()):
        pts, kinds, ids, chords, chord_ids, polys = [], [], [], [], [], []
        seen = {}
        self.wsegs = []          # [(obje adı, spline, segment, örnekler)]
        self.wpts = []           # [((obje adı, spline, nokta), konum)]
        self.arcs = []           # [(merkez, yarıçap, normal)] tel kafesteki çember yayları
        self.rays = []           # [(uç nokta, dışa teğet)] eğri uçlarından teğet uzantılar

        def add_pt(p, kind, pid=None):
            k = tuple(np.round(p, 6))
            j = seen.get(k)
            if j is not None:
                if PRIORITY[kind] < PRIORITY[kinds[j]]:
                    kinds[j] = kind
                if ids[j] is None and pid is not None:
                    ids[j] = pid
                return
            seen[k] = len(pts)
            pts.append(np.asarray(p, dtype=np.float64))
            kinds.append(kind)
            ids.append(pid)

        for ob in context.visible_objects:
            if ob.type == "CURVE":
                mw = ob.matrix_world
                for si, sp in enumerate(ob.data.splines):
                    if sp.type not in ("BEZIER", "POLY"):
                        continue
                    npt = len(sp.bezier_points) if sp.type == "BEZIER" else len(sp.points)
                    if npt == 1 and not sp.use_cyclic_u:      # tek noktalı spline: Nokta
                        q = sp.bezier_points[0].co if sp.type == "BEZIER" else sp.points[0].co.xyz
                        P0 = np.array(tuple(mw @ q), dtype=np.float64)
                        add_pt(P0, "Nokta", (ob.name, si, 0))
                        self.wpts.append(((ob.name, si, 0), P0))
                        continue
                    for i in range(core._seg_count(sp)):
                        try:
                            s = core._spline_segment(ob, si, sp, i, mw)
                        except Exception:
                            s = None
                        if s is None:
                            continue
                        P = [np.array(tuple(v), dtype=np.float64) for v in s["p"]]
                        j = (i + 1) % npt
                        add_pt(P[0], "Uç", (ob.name, si, i))
                        add_pt(P[-1], "Uç", (ob.name, si, j))
                        self.wpts.append(((ob.name, si, i), P[0]))
                        if j != 0 or not sp.use_cyclic_u:
                            self.wpts.append(((ob.name, si, j), P[-1]))
                        sid = ("seg", ob.name, si, i)
                        if len(P) == 2:
                            add_pt(0.5 * (P[0] + P[1]), "Orta")
                            chords.append((P[0], P[1]))
                            chord_ids.append(sid)
                            S = np.array(P)
                        else:
                            add_pt(_bezier(P, 0.5), "Orta")
                            S = np.array([_bezier(P, t) for t in np.linspace(0, 1, 24)])
                            if dm.is_straight_poly(np.array(P)):
                                chords.append((P[0], P[3]))
                                chord_ids.append(sid)
                            else:
                                arc = dm.arc_of_bezier(P)
                                if arc is not None:
                                    add_pt(arc[0], "Merkez")
                                    if not any(np.linalg.norm(arc[0] - a[0]) < 1e-6 and
                                               abs(arc[1] - a[1]) < 1e-6 for a in self.arcs):
                                        self.arcs.append(arc)
                                t0 = dm.unit(P[1] - P[0])
                                t1 = dm.unit(P[3] - P[2])
                                if t0 is not None:
                                    self.rays.append((P[0], -t0))
                                if t1 is not None:
                                    self.rays.append((P[3], t1))
                        polys.append(S)
                        self.wsegs.append((ob.name, si, i, S))
            elif ob.type == "MESH" and ob.cad.is_cad:
                for E in core._display.get(ob.name, {}).get("edges") or ():
                    P = np.asarray(E, dtype=np.float64)
                    if len(P) < 2:
                        continue
                    c = dm.circle_center(P)
                    if c is not None:
                        add_pt(c, "Merkez")
                    else:
                        add_pt(P[0], "Uç")
                        add_pt(P[-1], "Uç")
                    add_pt(dm.poly_mid(P), "Orta")
                    if dm.is_straight_poly(P):
                        chords.append((P[0], P[-1]))
                        chord_ids.append(None)
                    polys.append(P)
        for p in points:                         # taslak noktaları
            add_pt(np.asarray(p, dtype=np.float64), "Nokta")
        for st in strokes:                       # hafızadaki taslak çizgiler
            for sg in st["segs"]:
                P = list(sg["p"])
                add_pt(P[0], "Uç")
                add_pt(P[3], "Uç")
                add_pt(_bezier(P, 0.5), "Orta")
                if sg["kind"] == "line":
                    chords.append((P[0], P[3]))
                    chord_ids.append(None)
                    polys.append(np.array([P[0], P[3]]))
                else:
                    polys.append(np.array([_bezier(P, t) for t in np.linspace(0, 1, 24)]))
                    arc = dm.arc_of_bezier(P)
                    if arc is not None:
                        add_pt(arc[0], "Merkez")
                        self.arcs.append(arc)
        self.P = np.array(pts) if pts else np.zeros((0, 3))
        self.kinds = kinds
        self.ids = ids
        self.chords = chords
        self.chord_ids = chord_ids
        a_list, b_list = [], []
        for S in polys:
            a_list.append(S[:-1])
            b_list.append(S[1:])
        self.A = np.vstack(a_list) if a_list else np.zeros((0, 3))
        self.B = np.vstack(b_list) if b_list else np.zeros((0, 3))
        wa, wb, wo = [], [], []
        for k, (_, _, _, S) in enumerate(self.wsegs):
            wa.append(S[:-1])
            wb.append(S[1:])
            wo.append(np.full(len(S) - 1, k))
        self.WA = np.vstack(wa) if wa else np.zeros((0, 3))
        self.WB = np.vstack(wb) if wb else np.zeros((0, 3))
        self.Wown = np.concatenate(wo) if wo else np.zeros(0, dtype=int)

def _project(P, M, region):
    """(n,3) dünya noktaları -> piksel (n,2), görünür mü (n,), derinlik (n,)."""
    P = np.asarray(P, dtype=np.float64).reshape(-1, 3)
    h = np.hstack([P, np.ones((len(P), 1))]) @ M.T
    w = h[:, 3:4]
    ok = w[:, 0] > 1e-6
    w = np.where(np.abs(w) < 1e-9, 1e-9, w)
    ndc = h[:, :3] / w
    px = np.stack([(ndc[:, 0] + 1.0) * 0.5 * region.width,
                   (ndc[:, 1] + 1.0) * 0.5 * region.height], axis=1)
    return px, ok, ndc[:, 2]

def _seg_px_dist(a, b, m):
    ab = b - a
    den = np.einsum("ij,ij->i", ab, ab)
    den = np.where(den < 1e-12, 1e-12, den)
    t = np.clip(np.einsum("ij,ij->i", m - a, ab) / den, 0.0, 1.0)
    return np.linalg.norm(a + ab * t[:, None] - m, axis=1), t

# ================================================================ mod yönetimi

def is_running():
    return _STATE["active"] is not None

def _remove_handle(h):
    try:
        bpy.types.SpaceView3D.draw_handler_remove(h, "WINDOW")
    except Exception:
        pass
    if h in _HANDLES:
        _HANDLES.remove(h)

def cleanup_all():
    for h in list(_HANDLES):
        _remove_handle(h)
    op = _STATE["active"]
    if op is not None:
        op.stop_request = True
    _STATE["active"] = None
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    except Exception:
        pass

def _shader(name):
    return gpu.shader.from_builtin(name)

def _poly(coords, color, width, region, closed=False):
    if len(coords) < 2:
        return
    pts = [tuple(c) if len(c) == 3 else (c[0], c[1], 0.0) for c in coords]
    seg = []
    for k in range(len(pts) - 1):
        seg += [pts[k], pts[k + 1]]
    if closed:
        seg += [pts[-1], pts[0]]
    sh = _shader("POLYLINE_UNIFORM_COLOR")
    batch = batch_for_shader(sh, "LINES", {"pos": seg})
    sh.bind()
    sh.uniform_float("viewportSize", (region.width, region.height))
    sh.uniform_float("lineWidth", width)
    sh.uniform_float("color", color)
    batch.draw(sh)

def _dashed(a, b, color, region, dash=6.0, gap=4.0):
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    L = float(np.linalg.norm(b - a))
    if L < 1:
        return
    d = (b - a) / L
    seg = []
    s = 0.0
    while s < L:
        e = min(L, s + dash)
        p, q = a + d * s, a + d * e
        seg += [(p[0], p[1], 0.0), (q[0], q[1], 0.0)]
        s = e + gap
    sh = _shader("POLYLINE_UNIFORM_COLOR")
    batch = batch_for_shader(sh, "LINES", {"pos": seg})
    sh.bind()
    sh.uniform_float("viewportSize", (region.width, region.height))
    sh.uniform_float("lineWidth", 1.3)
    sh.uniform_float("color", color)
    batch.draw(sh)

def _rect(x0, y0, x1, y1, color):
    sh = _shader("UNIFORM_COLOR")
    batch = batch_for_shader(sh, "TRIS", {"pos": [(x0, y0, 0.0), (x1, y0, 0.0), (x1, y1, 0.0),
                                                 (x0, y1, 0.0)]},
                             indices=[(0, 1, 2), (0, 2, 3)])
    sh.bind()
    sh.uniform_float("color", color)
    batch.draw(sh)

def _marker(kind, x, y, s, region):
    """Yakalama türüne göre işaret: kare uç, üçgen orta, daire merkez, X kesişim, elmas yakın."""
    if kind in ("Uç", "Başlangıç"):
        pts = [(x - s, y - s), (x + s, y - s), (x + s, y + s), (x - s, y + s)]
        _poly(pts, COL_SNAP, 2.0, region, closed=True)
    elif kind == "Orta":
        pts = [(x - s, y - s * 0.8), (x + s, y - s * 0.8), (x, y + s)]
        _poly(pts, COL_SNAP, 2.0, region, closed=True)
    elif kind == "Merkez":
        pts = [(x + s * math.cos(a), y + s * math.sin(a))
               for a in np.linspace(0, 2 * math.pi, 17)[:-1]]
        _poly(pts, COL_SNAP, 2.0, region, closed=True)
    elif kind == "Nokta":
        _poly([(x - s, y), (x + s, y)], COL_SNAP, 2.0, region)
        _poly([(x, y - s), (x, y + s)], COL_SNAP, 2.0, region)
        pts = [(x + s * 0.6 * math.cos(a), y + s * 0.6 * math.sin(a))
               for a in np.linspace(0, 2 * math.pi, 9)[:-1]]
        _poly(pts, COL_SNAP, 1.5, region, closed=True)
    elif kind == "Kesişim":
        _poly([(x - s, y - s), (x + s, y + s)], COL_SNAP, 2.0, region)
        _poly([(x - s, y + s), (x + s, y - s)], COL_SNAP, 2.0, region)
    else:
        pts = [(x, y - s), (x + s, y), (x, y + s), (x - s, y)]
        _poly(pts, COL_SNAP, 2.0, region, closed=True)

def _text(x, y, txt, color=COL_TEXT, size=12):
    font = 0
    try:
        blf.size(font, size)
    except TypeError:
        blf.size(font, size, 72)
    blf.color(font, *color)
    blf.position(font, x, y, 0)
    blf.draw(font, txt)
    return blf.dimensions(font, txt)

# ================================================================ taslak düzenleme yardımcıları

def _line_thirds(sg):
    a, b = sg["p"][0], sg["p"][3]
    sg["p"] = (a, a + (b - a) / 3.0, a + (b - a) * (2.0 / 3.0), b)

def _move_node(segs, j, new, cyclic):
    """Taslak çizgisinin j. noktasını taşır: doğrular düz kalır, eğrilerde tutamaçlar
    noktayla birlikte gider (eğrinin şekli korunur)."""
    n = len(segs)
    touch = []
    if j < n:
        touch.append((j, 0))
    if j > 0:
        touch.append((j - 1, 3))
    elif cyclic:
        touch.append((n - 1, 3))
    for k, end in touch:
        sg = segs[k]
        P = list(sg["p"])
        delta = new - P[end]
        P[end] = np.array(new)
        if sg["kind"] != "line":
            h = 1 if end == 0 else 2
            P[h] = P[h] + delta
        sg["p"] = tuple(P)
        if sg["kind"] == "line":
            _line_thirds(sg)

def _move_handle(segs, k, w, new, cyclic, orig):
    """Eğri tutamacını taşır; birleşim pürüzsüzse karşı tutamaç hizalı kalır (boyu korunur)."""
    n = len(segs)
    P = list(segs[k]["p"])
    P[w] = np.array(new)
    segs[k]["p"] = tuple(P)
    node = P[0] if w == 1 else P[3]
    if w == 1:
        ok = k > 0 or cyclic
        k2, w2 = (k - 1) % n, 2
    else:
        ok = k < n - 1 or cyclic
        k2, w2 = (k + 1) % n, 1
    if not ok or k2 == k or segs[k2]["kind"] == "line":
        return
    o_this = np.array(orig[k]["p"][w]) - np.array(node)
    o_other = np.array(orig[k2]["p"][w2]) - np.array(node)
    L1, L2 = float(np.linalg.norm(o_this)), float(np.linalg.norm(o_other))
    if L1 < 1e-12 or L2 < 1e-12:
        return
    if float(np.dot(o_this / L1, -o_other / L2)) < math.cos(math.radians(1.0)):
        return                                   # köşe: karşı tutamaç serbest
    dnew = np.array(new) - np.array(node)
    Ln = float(np.linalg.norm(dnew))
    if Ln < 1e-12:
        return
    Q = list(segs[k2]["p"])
    Q[w2] = np.array(node) - dnew / Ln * L2
    segs[k2]["p"] = tuple(Q)

# ================================================================ operatör

CHAIN_TOOLS = {"LINE", "TARC", "ARC3", "CARC", "CV", "FIT", "PEN"}

# Çok tıklamalı şekiller (draw_shapes): her tıkta çizimin yakalamaları geçerli
CLICK_SHAPES = {"RECT3", "RECTC", "RECT3C", "POLYGON", "SLOTCC", "SLOTO", "SLOTC", "ARCSLOT",
                "SLOTARCC", "ELLIPSE"}

SHAPE_TOOLS = {"CIRCLE", "RECT"} | CLICK_SHAPES

# Tıklayarak nesne seçen oluşturma araçları (taslakta çalışır, draw_shapes._pk_*)
PICK_TOOLS = {"CIRCT", "PROJECT"}

# Aynı tuşa tekrar basınca türler arasında geçiş (Inventor açılır menüsü gibi)
TOOL_CYCLES = {"R": ["RECT", "RECT3", "RECTC", "RECT3C"], "O": ["CIRCLE", "CIRCT", "ELLIPSE"]}

TOOL_KEYS = {"W": "SELECT", "L": "LINE", "E": "ARC3", "M": "CARC", "O": "CIRCLE",
             "R": "RECT", "S": "CV", "K": "FIT", "P": "PEN", "B": "TRIM"}

XFORM_TOOLS = {"MOVE", "COPY", "ROTATE", "SCALE", "STRETCH", "RPAT", "CPAT", "MIRROR"}

# Taslak üzerinde çalışan bütün araçlar (Değiştir + Düzenle / Desen)
MODIFY_TOOLS = {"TRIM", "EXTEND", "SPLIT", "OFFSET", "FILLET2D", "CHAMFER2D"} | XFORM_TOOLS | \
    {"CIRCT", "PROJECT"}

FIELDS = {"CIRCLE": ("Yarıçap", None), "RECT": ("Genişlik", "Yükseklik"),
          "ARC3": (None, None), "CARC": (None, None), "TARC": (None, None),
          "POINT": (None, None)}
FIELDS.update({t: (None, None) for t in CLICK_SHAPES})   # yazılanı şeklin kendisi uygular

AXIS_OF = {"Yatay": {"XY": 0, "XZ": 0, "YZ": 1}, "Dikey": {"XY": 1, "XZ": 2, "YZ": 2}}
