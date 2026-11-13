"""Yüzeyi Böl (v0.25.0): mevcut yüzeylere yeni kenar ekleyerek onları ikiye böler.

İki yöntem (araç açıkken R / K ile geçilir):

  Döngü kesimi (R)  Blender'daki Ctrl+R gibi: bir yüzey kenarının üzerine gel; kesim o kenardan
                    karşı kenara gider ve komşu 4 kenarlı yüzeyler boyunca halka olarak sürer.
                    Konum: fare (kenar boyunca); yazılan oran (0.3 / %30); C: ortala.
                    Tekerlek / + −: kesim sayısı (eşit aralıklı). Tık: uygula.
  Bıçak (K)         Yüzey sınırında iki nokta seç (köşelere ve kenar ortalarına yapışır).
                    Kesim yüzeyin üzerinde yatar: 3 / 4 kenarlı yüzeyde yüzeyin parametre doğrusu
                    (V ile Görünüş: ekrandaki düz çizginin yüzeye izdüşümü), diğerlerinde görünüş
                    yönünde izdüşüm. Sağ tık: noktaları bırak.

Kesim eğrisi önce sınır eğrilerinden (Coons) hesaplanır, sonra gövdenin mesh'ine izdüşürülür
ve tel kafese gerçek bir bezier spline olarak yazılır. Kesimin uçları kenar ortasına düşüyorsa
o kenara yeni bezier noktası eklenir (core.remap_insert bütün referansları günceller). Yüzey
iki yüzeye ayrılır (ayarları kopyalanır); komşu yüzeyler bölünen kenarın iki yarısını alır.
"""
import math

import bpy
import numpy as np

from . import core
from . import surfmath as sm
from .errors import CadError

PICK_PX = 12
COL_EDGE = (0.35, 0.9, 0.45, 0.45)
COL_HOVER = (1.0, 0.62, 0.1, 1.0)
COL_CUT = (1.0, 0.85, 0.2, 1.0)
COL_PT = (0.2, 0.75, 1.0, 1.0)
CUT_SAMPLES = 33

_STATE = {"active": None}
_HANDLES = []


# ================================================================ veri yardımcıları

def _key(ref):
    ob, si, k = ref
    return (ob.name if hasattr(ob, "name") else ob, si, k)


def _obj(name):
    return bpy.data.objects.get(name) if isinstance(name, str) else name


def body_mesh(ob):
    """Gövdenin mesh'i dünya koordinatında (surfmath.Mesh) | None."""
    try:
        me = ob.data
        try:
            me.calc_loop_triangles()         # eski sürümler; yenilerde kendiliğinden hesaplı
        except AttributeError:
            pass
        nv, nt = len(me.vertices), len(me.loop_triangles)
        if not nt:
            return None
        V = np.empty(nv * 3, dtype=np.float64)
        me.vertices.foreach_get("co", V)
        T = np.empty(nt * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", T)
        M = np.array([list(r) for r in ob.matrix_world], dtype=np.float64)
        V = V.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
        return sm.Mesh(V, T.reshape(-1, 3))
    except Exception:
        return None


class PatchGeom:
    """Bir yüzeyin sınırı: sıralı segmentler (dünya), kenarlar, referanslar."""

    def __init__(self, body, idx, tol):
        self.idx = idx
        self.ok = False
        self.err = ""
        patch = body.cad.patches[idx]
        self.refs = core.patch_refs(patch)
        segs = []
        for r in self.refs:
            s = core._ref_segment(r)
            if s is not None:
                s = dict(s, p=[v.copy() for v in s["p"]], start=np.array(tuple(s["p"][0])))
                segs.append(s)
        try:
            loops = core.chain_loops(segs, tol)
        except CadError as e:
            self.err = str(e)
            return
        if len(loops) != 1:
            self.err = "delikli yüzey bölünemez"
            return
        chain = loops[0]
        self.chain = chain
        self.keys = [s["ref"] for s in chain]
        self.rev = [float(np.linalg.norm(np.array(tuple(s["p"][0])) - s["start"])) >
                    float(np.linalg.norm(np.array(tuple(s["p"][-1])) - s["start"]))
                    for s in chain]
        self.P = [sm.cubic(s["p"]) for s in chain]
        pos = {id(s): i for i, s in enumerate(chain)}
        sides = core.split_sides(chain)
        self.side_idx = [[pos[id(s)] for s in side] for side in sides]
        self.sides = [[self.P[i] for i in side] for side in self.side_idx]
        self.verts = [P[0] for P in self.P]
        self.ok = True

    @property
    def nsides(self):
        return len(self.sides) if self.ok else 0

    def has(self, key):
        return self.ok and key in self.keys

    def locate(self, key, t_seg):
        """Spline yönündeki t_seg → (kenar sırası j, kenar parametresi τ)."""
        c = self.keys.index(key)
        tc = 1.0 - t_seg if self.rev[c] else t_seg
        for j, side in enumerate(self.side_idx):
            if c in side:
                m = side.index(c)
                return j, (m + tc) / len(side)
        raise CadError("kenar bulunamadı")

    def at(self, j, tau):
        """Kenar j'nin τ noktası → (segment anahtarı, spline yönünde t, dünya noktası)."""
        side = self.side_idx[j]
        x = min(max(tau, 0.0), 1.0) * len(side)
        m = min(int(x), len(side) - 1)
        tc = x - m
        c = side[m]
        return self.keys[c], (1.0 - tc if self.rev[c] else tc), sm.bez(self.P[c], tc)

    def quad(self):
        """Coons için 4 kenar (3 kenarlıda tepesi noktaya inmiş) ve 3→4 kenar eşlemesi."""
        if self.nsides == 4:
            return self.sides, [0, 1, 2, 3]
        if self.nsides == 3:
            q, k = sm.tri_to_quad(self.sides)
            return q, [(k + i) % 3 for i in (0, 1)] + [None, (k + 2) % 3]
        return None, None

    def near_boundary(self, q, tol):
        """q'nun üzerinde bulunduğu kenarlar: [(kenar j, τ)] (köşe iki kenarda birden)."""
        out = []
        for j, side in enumerate(self.sides):
            tau, d = sm.side_param(side, q)
            if d <= tol:
                out.append((j, tau))
        return out


def body_geoms(body, tol):
    return [PatchGeom(body, i, tol) for i in range(len(body.cad.patches))]


def _size(geoms):
    P = [v for g in geoms if g.ok for v in g.verts]
    if not P:
        return 1.0
    P = np.array(P)
    return max(float(np.linalg.norm(np.ptp(P, axis=0))), 1e-6)


# ================================================================ kesim planlama

def _coons_cut(g, j0, tau0, j1, tau1, n=CUT_SAMPLES):
    """Yüzeyin parametre doğrusu boyunca kesim noktaları (3 / 4 kenarlı)."""
    q, m = g.quad()
    inv = {v: i for i, v in enumerate(m) if v is not None}
    if j0 not in inv or j1 not in inv:
        return None
    u0, v0 = sm.side_uv(inv[j0], tau0)
    u1, v1 = sm.side_uv(inv[j1], tau1)
    return [sm.coons(q, u0 + (u1 - u0) * s, v0 + (v1 - v0) * s) for s in np.linspace(0, 1, n)]


def ring_cuts(geoms, key, t_seg, mesh=None):
    """Döngü kesimi: (anahtar, t) noktasından geçen, 4 kenarlı yüzeyler boyunca halka.
    [{"patch", "pts"}]"""
    cuts = []
    visited = set()
    starts = [g.idx for g in geoms if g.has(key)]
    for s_idx in starts:
        cur = (s_idx, key, t_seg)
        while cur is not None:
            idx, k, ts = cur
            g = geoms[idx]
            if idx in visited or g.nsides != 4:
                break
            visited.add(idx)
            j, tau = g.locate(k, ts)
            j2 = (j + 2) % 4
            pts = _coons_cut(g, j, tau, j2, 1.0 - tau)
            k2, ts2, _ = g.at(j2, 1.0 - tau)
            cuts.append({"patch": idx, "pts": sm.project_points(mesh, pts)})
            nxt = [h.idx for h in geoms if h.idx != idx and h.has(k2)]
            cur = (nxt[0], k2, ts2) if nxt else None
    return cuts


def knife_cut(geoms, A, B, mesh=None, view_dir=None, mode="SURFACE", tol=1e-6, ray=None):
    """Bıçak: A, B sınır noktaları (dünya). (kesim | None, hata metni)."""
    cands = []
    for g in geoms:
        if not g.ok:
            continue
        pair = [(a, b) for a in g.near_boundary(A, tol) for b in g.near_boundary(B, tol)
                if a[0] != b[0]]
        if pair:
            cands.append((g,) + pair[0])
    if not cands:
        return None, "İki nokta aynı yüzeyin farklı kenarlarında olmalı"
    best = None
    for g, a, b in cands:
        pts = None
        if mode == "SURFACE" and g.nsides in (3, 4):
            pts = _coons_cut(g, a[0], a[1], b[0], b[1])
        if pts is None:
            pts = [A + (B - A) * s for s in np.linspace(0, 1, CUT_SAMPLES)]
            pts = sm.project_points(mesh, pts, view_dir=view_dir)
        else:
            pts = sm.project_points(mesh, pts)
        score = 0.0
        if ray is not None:                 # imlece en yakın aday (iki yüzeyin ortak köşeleri)
            o, d = ray
            mid = pts[len(pts) // 2] - o
            score = float(np.linalg.norm(mid - d * float(np.dot(mid, d))))
        if best is None or score < best[0]:
            best = (score, {"patch": g.idx, "pts": pts})
    return best[1], ""


# ================================================================ uygulama

def _all_wire_refs(body):
    out, seen = [], set()
    for p in body.cad.patches:
        for r in core.patch_refs(p):
            k = _key(r)
            if k not in seen:
                seen.add(k)
                out.append(r)
    return out


def _find_on_wire(body, q, tol):
    """q'dan geçen tel kafes segmenti: (ob, si, k, t, uzaklık) | None (en yakın)."""
    best = None
    for ob, si, k in _all_wire_refs(body):
        s = core._ref_segment((ob, si, k))
        if s is None:
            continue
        t, d = sm.closest_t(sm.cubic(s["p"]), q)
        if d <= tol and (best is None or d < best[4]):
            best = (ob, si, k, t, d)
    return best


def _check_insertable(ob, si):
    sp = ob.data.splines[si]
    if sp.type != "BEZIER":
        raise CadError(f"'{ob.name}' spline {si}: yalnızca bezier kenarlar bölünebilir "
                       "(poly eğriyi bezier'e çevir)")
    for lk in getattr(ob.cad, "links", ()):
        lists = [lk.src, lk.dst]
        for txt in lists:
            if si in core._int_list(txt):
                raise CadError(f"'{ob.name}' spline {si} bir desen / yansıtma ilişkisinde: "
                               "önce ilişkiyi kaldır")


def insert_point(ob, si, k, t):
    """Bezier spline'ın k. segmentine t'de (de Casteljau) nokta ekler; biçim değişmez.
    Referanslar core.remap_insert ile güncellenir. Devre dışı kalan kısıt sayısı."""
    _check_insertable(ob, si)
    sp = ob.data.splines[si]
    bps = sp.bezier_points
    n = len(bps)
    a, b = bps[k], bps[(k + 1) % n]
    P = np.array([tuple(a.co), tuple(a.handle_right), tuple(b.handle_left), tuple(b.co)],
                 dtype=np.float64)
    L, R = sm.split_bez(P, t)
    straight = a.handle_right_type == "VECTOR" and b.handle_left_type == "VECTOR"

    def rec(p):
        return {"co": tuple(p.co), "hl": tuple(p.handle_left), "hr": tuple(p.handle_right),
                "tl": p.handle_left_type, "tr": p.handle_right_type,
                "radius": getattr(p, "radius", 1.0), "tilt": getattr(p, "tilt", 0.0)}
    data = [rec(p) for p in bps]

    def fix_types(d, side):
        # değişen tutamaç: AUTO / VECTOR yeniden hesaplanıp biçimi bozmasın
        if straight:
            return
        if "AUTO" in (d["tl"], d["tr"]):
            d["tl"] = d["tr"] = "ALIGNED"
        key = "tr" if side == "r" else "tl"
        if d[key] == "VECTOR":
            d[key] = "FREE"
    da = data[k]
    da["hr"] = tuple(L[1])
    fix_types(da, "r")
    db = data[(k + 1) % n]
    db["hl"] = tuple(R[2])
    fix_types(db, "l")
    new = {"co": tuple(L[3]), "hl": tuple(L[2]), "hr": tuple(R[1]),
           "tl": "VECTOR" if straight else "ALIGNED", "tr": "VECTOR" if straight else "ALIGNED",
           "radius": da["radius"], "tilt": da["tilt"]}
    data.insert(k + 1, new)
    bps.add(1)
    try:
        from mathutils import Vector
    except Exception:          # testler
        Vector = None

    def V(x):
        return Vector(x) if Vector is not None else np.array(x, dtype=np.float64)
    for p, d in zip(bps, data):
        p.handle_left_type = "FREE"
        p.handle_right_type = "FREE"
        p.co = V(d["co"])
        p.handle_left = V(d["hl"])
        p.handle_right = V(d["hr"])
        try:
            p.radius, p.tilt = d["radius"], d["tilt"]
        except Exception:
            pass
    for p, d in zip(bps, data):
        p.handle_left_type = d["tl"]
        p.handle_right_type = d["tr"]
    try:
        ob.data.update_tag()
    except Exception:
        pass
    _n, off = core.remap_insert(ob, si, k)
    return off


def ensure_vertex(body, q, tol):
    """q bir tel kafes köşesi değilse üzerindeki segmente nokta ekler. (eklendi mi, kapanan
    kısıt sayısı)"""
    hit = _find_on_wire(body, q, tol)
    if hit is None:
        raise CadError("Kesimin ucu bir yüzey kenarında değil")
    ob, si, k, t, _d = hit
    s = core._ref_segment((ob, si, k))
    P = sm.cubic(s["p"])
    L = float(np.linalg.norm(P[3] - P[0])) + 1e-12
    if float(np.linalg.norm(sm.bez(P, t) - P[0])) <= tol or t <= 1e-6 or \
            float(np.linalg.norm(sm.bez(P, t) - P[3])) <= tol or t >= 1 - 1e-6 or L < tol:
        return False, 0
    # objenin yerel uzayında aynı t (afin dönüşüm parametreyi korur)
    return True, insert_point(ob, si, k, t)


def write_spline(ob, segs):
    """Dünya koordinatındaki bezier zincirini objeye yeni spline olarak yazar. Spline sırası."""
    cu = ob.data
    if getattr(cu, "dimensions", "3D") != "3D":
        cu.dimensions = "3D"
    M = np.array([list(r) for r in ob.matrix_world], dtype=np.float64)
    Mi = np.linalg.inv(M)

    def loc(p):
        return tuple((Mi @ np.r_[np.asarray(p, dtype=np.float64), 1.0])[:3])
    try:
        from mathutils import Vector
    except Exception:
        Vector = None

    def V(x):
        return Vector(x) if Vector is not None else np.array(x, dtype=np.float64)
    pts = []
    for i, P in enumerate(segs):
        if i == 0:
            pts.append({"co": P[0], "hl": P[0] - (P[1] - P[0]), "hr": P[1]})
        else:
            pts[-1]["hr"] = P[1]
        pts.append({"co": P[3], "hl": P[2], "hr": P[3] + (P[3] - P[2])})
    straight = len(segs) == 1 and np.allclose(segs[0][1], segs[0][0] + (segs[0][3] -
                                                                       segs[0][0]) / 3.0)
    sp = cu.splines.new("BEZIER")
    bps = sp.bezier_points
    bps.add(len(pts) - 1)
    for b, p in zip(bps, pts):
        b.handle_left_type = "FREE"
        b.handle_right_type = "FREE"
        b.co = V(loc(p["co"]))
        b.handle_left = V(loc(p["hl"]))
        b.handle_right = V(loc(p["hr"]))
    for i, b in enumerate(bps):
        if straight:
            b.handle_left_type = b.handle_right_type = "VECTOR"
        elif 0 < i < len(bps) - 1:
            b.handle_left_type = b.handle_right_type = "ALIGNED"
    sp.use_cyclic_u = False
    try:
        cu.update_tag()
    except Exception:
        pass
    return len(cu.splines) - 1


def split_patch(body, pidx, A, B, cut_refs, tol):
    """Yüzeyi A–B köşelerinden ikiye ayırır: biri bu yüzey (A→B yayı + kesim), diğeri yeni
    yüzey (B→A yayı + kesim). Yeni yüzeyin sırası."""
    props = body.cad
    patch = props.patches[pidx]
    if not len(patch.segs) and len(patch.curves):          # eski: eğrinin tamamı
        refs = core.patch_refs(patch)
        for ob, si, k in refs:
            x = patch.segs.add()
            x.obj, x.spline, x.seg = ob, si, k
        patch.curves.clear()
    refs = core.patch_refs(patch)
    segs = [s for s in (core._ref_segment(r) for r in refs) if s is not None]
    chain = core.chain_loop(segs, tol)
    V = [np.array(tuple(s["p"][0])) for s in chain]
    iA = int(np.argmin([np.linalg.norm(v - A) for v in V]))
    iB = int(np.argmin([np.linalg.norm(v - B) for v in V]))
    if np.linalg.norm(V[iA] - A) > tol or np.linalg.norm(V[iB] - B) > tol or iA == iB:
        raise CadError("Kesimin uçları yüzeyin köşelerine oturmadı")
    n = len(chain)
    arc1 = [chain[(iA + i) % n]["ref"] for i in range((iB - iA) % n)]
    arc2 = [chain[(iB + i) % n]["ref"] for i in range((iA - iB) % n)]

    def fill(p, keys):
        p.segs.clear()
        for name, si, k in list(keys) + list(cut_refs):
            x = p.segs.add()
            x.obj, x.spline, x.seg = _obj(name), si, k
    fill(patch, arc1)
    new = props.patches.add()
    for a in ("method", "enabled", "blend", "own_weight", "tangent_weight"):
        if hasattr(patch, a):
            try:
                setattr(new, a, getattr(patch, a))
            except Exception:
                pass
    new.name = _unique_name(props, patch.name)
    fill(new, arc2)
    for p in (patch, new):
        if getattr(p, "method", "AUTO") == "COONS" and len(p.segs) < 4:
            p.method = "AUTO"
    return len(props.patches) - 1


def _unique_name(props, base):
    names = {p.name for p in props.patches}
    root = base.rstrip("0123456789").rstrip(".") or "Yüzey"
    i = 2
    while f"{root}.{i}" in names:
        i += 1
    return f"{root}.{i}"


def validate_cuts(body, ends, tol):
    """Kesim uçları bir kenarda mı, o kenar bölünebilir mi? Değilse CadError (değişiklik
    yapılmadan)."""
    for A, B in ends:
        if float(np.linalg.norm(A - B)) <= tol:
            raise CadError("Kesimin iki ucu aynı noktada")
        for q in (A, B):
            hit = _find_on_wire(body, q, tol)
            if hit is None:
                raise CadError("Kesimin ucu bir yüzey kenarında değil")
            ob, si, k, t, _d = hit
            s = core._ref_segment((ob, si, k))
            P = sm.cubic(s["p"])
            if float(np.linalg.norm(sm.bez(P, t) - P[0])) > tol and \
                    float(np.linalg.norm(sm.bez(P, t) - P[3])) > tol:
                _check_insertable(ob, si)


def apply_cuts(body, cuts, tol=None):
    """Kesimleri uygular: uç noktaları köşe yapar, kesim spline'larını yazar, yüzeyleri böler.
    (bölünen yüzey sayısı, eklenen kenar noktası, devre dışı kalan kısıt)."""
    props = body.cad
    tol = tol if tol is not None else max(min(props.join_tol, 1e-3), 1e-6)
    geoms0 = body_geoms(body, tol)
    size = _size(geoms0)
    # mesh'in kendi sapmasından sıkı uydurma eğriyi üçgen yüzlerin köşeliliğine uydurur
    fit_tol = max(tol * 0.5, size * 5e-4, 2.0 * float(getattr(props, "lin_defl", 0.0) or 0.0))
    n_ins = n_off = 0
    ends = []
    for c in cuts:
        A, B = np.asarray(c["pts"][0], float), np.asarray(c["pts"][-1], float)
        ends.append((A, B))
    validate_cuts(body, ends, tol)                 # hiçbir şey değişmeden önce
    for A, B in ends:
        for q in (A, B):
            added, off = ensure_vertex(body, q, tol)
            n_ins += int(added)
            n_off += off
    lineage = {c["patch"]: [c["patch"]] for c in cuts}
    done = 0
    for c, (A, B) in zip(cuts, ends):
        hit = _find_on_wire(body, A, tol)
        ob = hit[0] if hit is not None else _obj(geoms0[c["patch"]].keys[0][0])
        segs = sm.fit_chain([np.asarray(p, float) for p in c["pts"]], fit_tol)
        si = write_spline(ob, segs)
        cut_refs = [(ob.name, si, i) for i in range(len(segs))]
        target = None
        for pidx in lineage[c["patch"]]:
            g = PatchGeom(body, pidx, tol)
            if not g.ok:
                continue
            vs = np.array(g.verts)
            if np.min(np.linalg.norm(vs - A, axis=1)) <= tol and \
                    np.min(np.linalg.norm(vs - B, axis=1)) <= tol:
                target = pidx
                break
        if target is None:
            raise CadError("Kesilecek yüzey bulunamadı")
        new = split_patch(body, target, A, B, cut_refs, tol)
        lineage[c["patch"]].append(new)
        done += 1
    return done, n_ins, n_off


# ================================================================ modal araç

def is_running():
    return _STATE["active"] is not None


def get_target(context):
    """Hedef gövde (ui.get_target ile aynı kural)."""
    ob = getattr(context, "active_object", None)
    try:
        if ob is not None and ob.cad.is_cad:
            return ob
    except Exception:
        pass
    t = getattr(context.scene, "minicad_target", None)
    if t is not None and t.name in context.scene.objects:
        return t
    return None


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


def _sample(P, n=24):
    return np.array([sm.bez(P, t) for t in np.linspace(0.0, 1.0, n)])


class MINICAD_OT_split_surface(bpy.types.Operator):
    """Mevcut yüzeylere yeni kenar ekleyerek onları böler (döngü kesimi / bıçak)."""
    bl_idname = "minicad.split_surface"
    bl_label = "Yüzeyi Böl"
    bl_description = ("Yüzeylere yeni kenar ekleyip böler. R: döngü kesimi (Ctrl+R gibi, kenara "
                      "gel, tekerlek: adet, tık: uygula) · K: bıçak (sınırda iki nokta) · "
                      "Esc: çık")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        try:
            return context.area is not None and context.area.type == "VIEW_3D" and \
                get_target(context) is not None
        except Exception:
            return False

    # ------------------------------------------------------------ hazırlık

    def _load(self, context):
        self.body = get_target(context)
        props = self.body.cad
        self.tol = max(min(props.join_tol, 1e-3), 1e-6)
        self.geoms = body_geoms(self.body, self.tol)
        self.mesh = body_mesh(self.body)
        self.edges = []                      # [(anahtar, (4,3), örnekler)]
        seen = set()
        for g in self.geoms:
            if not g.ok:
                continue
            for key, P, rv in zip(g.keys, g.P, g.rev):
                if key in seen:
                    continue
                seen.add(key)
                Ps = P[::-1].copy() if rv else P          # spline yönünde
                self.edges.append((key, Ps, _sample(Ps)))
        self.dirty = False

    def invoke(self, context, event):
        if _STATE["active"] is not None:
            cleanup_all()
            return {"CANCELLED"}
        for mod in ("draw", "pick"):
            try:
                __import__(f"{__package__}.{mod}", fromlist=["cleanup_all"]).cleanup_all()
            except Exception:
                pass
        self.area = context.area
        self.region = next((r for r in self.area.regions if r.type == "WINDOW"), None)
        self.rv3d = self.area.spaces.active.region_3d
        if self.region is None or self.rv3d is None:
            self.report({"ERROR"}, "3D görünüm bulunamadı")
            return {"CANCELLED"}
        if context.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass
        try:
            self._load(context)
        except Exception as e:
            self.report({"ERROR"}, f"Yüzeyi Böl açılamadı: {e}")
            return {"CANCELLED"}
        if not self.edges:
            self.report({"WARNING"}, "Hedef gövdede bölünecek yüzey yok")
            return {"CANCELLED"}
        self.stop_request = False
        self.mode = "LOOP"
        self.count = 1
        self.typed = ""
        self.center = False
        self.view_proj = False
        self.hover = None                    # (kenar sırası, t)
        self.knife = []                      # seçilen sınır noktaları (dünya)
        self.snap = None                     # bıçakta imlecin yapıştığı nokta
        self.preview = []                    # [kesim]
        self.mouse = (0.0, 0.0)
        self.done = 0
        self.radius = PICK_PX * context.preferences.system.ui_scale
        self._h = bpy.types.SpaceView3D.draw_handler_add(self._draw, (), "WINDOW", "POST_VIEW")
        _HANDLES.append(self._h)
        _STATE["active"] = self
        context.window_manager.modal_handler_add(self)
        self._status(context)
        self.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def _finish(self, context):
        if getattr(self, "_h", None) is not None:
            _remove_handle(self._h)
            self._h = None
        if _STATE["active"] is self:
            _STATE["active"] = None
        try:
            context.workspace.status_text_set(None)
        except Exception:
            pass
        try:
            self.area.tag_redraw()
        except Exception:
            pass

    def _status(self, context, msg=""):
        if self.mode == "LOOP":
            pos = f"konum {self.typed}_" if self.typed else ("ortada" if self.center else
                                                             "fareyle")
            txt = (f"Yüzeyi Böl · DÖNGÜ KESİMİ · {self.count} kesim · {pos}  |  kenara gel, "
                   "tık: uygula  |  tekerlek / + −: adet  |  oran yaz (0.3)  |  C: ortala  |  "
                   "K: bıçak  |  Esc: çık")
        else:
            proj = "görünüş" if self.view_proj else "yüzey"
            txt = (f"Yüzeyi Böl · BIÇAK · {len(self.knife)}/2 nokta · izdüşüm: {proj}  |  "
                   "sınıra tıkla  |  V: izdüşüm  |  sağ tık: bırak  |  R: döngü kesimi  |  "
                   "Esc: çık")
        if msg:
            txt = f"{msg}   —   {txt}"
        try:
            context.workspace.status_text_set(txt)
        except Exception:
            pass

    # ------------------------------------------------------------ fare

    def _M(self):
        return np.array([list(r) for r in self.rv3d.perspective_matrix], dtype=np.float64)

    def _px(self, X):
        from .draw_common import _project
        return _project(X, self._M(), self.region)

    def _ray(self, mx, my):
        from bpy_extras import view3d_utils as vu
        o = np.array(tuple(vu.region_2d_to_origin_3d(self.region, self.rv3d, (mx, my))))
        d = np.array(tuple(vu.region_2d_to_vector_3d(self.region, self.rv3d, (mx, my))))
        return o, d / max(float(np.linalg.norm(d)), 1e-15)

    def _pick_edge(self, mx, my):
        """İmlecin altındaki kenar: (sıra, t spline yönünde) | None."""
        from .draw_common import _seg_px_dist
        m = np.array([mx, my], dtype=np.float64)
        best = None
        for i, (_k, P, S) in enumerate(self.edges):
            px, ok, z = self._px(S)
            if not ok.all():
                continue
            d, t = _seg_px_dist(px[:-1], px[1:], m)
            j = int(np.argmin(d))
            if d[j] <= self.radius and (best is None or d[j] < best[0] - 1e-9 or
                                        (abs(d[j] - best[0]) < 2 and z[j] < best[3])):
                tt = (j + float(t[j])) / (len(S) - 1)
                best = (float(d[j]), i, tt, float(z[j]))
        if best is None:
            return None
        i, tt = best[1], best[2]
        _k, P, S = self.edges[i]
        # örnek parametresinden gerçek bezier parametresine (yakın nokta)
        t, _ = sm.closest_t(P, sm.bez(P, tt))
        return i, t

    def _knife_snap(self, mx, my):
        """Bıçak: imlecin yapıştığı sınır noktası (köşe > kenar ortası > kenar üstü)."""
        h = self._pick_edge(mx, my)
        if h is None:
            return None
        i, t = h
        _k, P, S = self.edges[i]
        cand = [(0.0, "köşe"), (1.0, "köşe"), (0.5, "orta")]
        m = np.array([mx, my])
        for tt, kind in cand:
            px, ok, _ = self._px(sm.bez(P, tt)[None, :])
            if ok[0] and float(np.linalg.norm(px[0] - m)) <= self.radius:
                return sm.bez(P, tt), kind
        return sm.bez(P, t), "kenar"

    def _update(self, context, mx, my):
        self.mouse = (mx, my)
        self.preview = []
        self.plan = None
        if self.dirty:
            self._load(context)
        if self.mode == "LOOP":
            self.hover = self._pick_edge(mx, my)
            if self.hover is None:
                return
            i, t = self.hover
            key = self.edges[i][0]
            ts = [t]
            if self.count > 1:
                ts = [(c + 1) / (self.count + 1) for c in range(self.count)]
            elif self.typed:
                v = _parse_ratio(self.typed)
                if v is not None:
                    ts = [v]
            elif self.center:
                ts = [0.5]
            ts = [tt for tt in ts if 0.0 < tt < 1.0]
            self.plan = ("LOOP", key, ts)
            self.preview = self._cuts(None)
        else:
            self.snap = self._knife_snap(mx, my)
            if len(self.knife) == 1 and self.snap is not None:
                self.plan = ("KNIFE", self.knife[0], np.asarray(self.snap[0], float),
                             self._ray(mx, my))
                self.preview = self._cuts(None)

    def _cuts(self, mesh):
        """Plan → kesimler (mesh verilirse gerçek yüzeye izdüşürülmüş)."""
        plan = getattr(self, "plan", None)
        if plan is None:
            return []
        if plan[0] == "LOOP":
            out = []
            for tt in plan[2]:
                out += ring_cuts(self.geoms, plan[1], tt, mesh)
            return out
        _m, A, B, (o, d) = plan
        if mesh is None and self.view_proj:
            mesh = self.mesh                 # görünüş izdüşümü önizlemede de gerekli
        cut, _err = knife_cut(self.geoms, A, B, mesh, view_dir=d,
                              mode="VIEW" if self.view_proj else "SURFACE", tol=self.tol,
                              ray=(o, d))
        return [cut] if cut is not None else []

    # ------------------------------------------------------------ uygula

    def _apply(self, context, cuts):
        if not cuts:
            return
        body = get_target(context)
        if body is None or body != self.body:
            self.dirty = True
            self._status(context, "Hedef gövde değişti, yeniden dene")
            return
        try:
            cuts = self._cuts(self.mesh) or cuts     # gerçek yüzeye izdüşürülmüş
        except Exception:
            pass
        try:
            n, ins, off = apply_cuts(self.body, cuts, self.tol)
        except CadError as e:
            self.report({"ERROR"}, str(e))
            self._status(context, f"Bölünemedi: {e}")
            self.dirty = True
            return
        try:
            core.rebuild(self.body)
        except Exception:
            pass
        try:
            bpy.ops.ed.undo_push(message="Mini CAD: Yüzeyi Böl")
        except Exception:
            pass
        self.done += n
        msg = f"{n} yüzey bölündü"
        if ins:
            msg += f" · {ins} kenar noktası eklendi"
        if off:
            msg += f" · {off} kısıt devre dışı (bölünen kenarda)"
        try:
            from . import recorder
            recorder.log("böl", msg)
        except Exception:
            pass
        self.report({"INFO"}, msg)
        self.typed = ""
        self.knife = []
        self.dirty = True
        self._status(context, msg)

    # ------------------------------------------------------------ olaylar

    PASS = {"MIDDLEMOUSE", "TRACKPADPAN", "TRACKPADZOOM", "MOUSEROTATE", "MOUSESMARTZOOM",
            "NDOF_MOTION", "NUMPAD_0", "NUMPAD_1", "NUMPAD_2", "NUMPAD_3", "NUMPAD_4",
            "NUMPAD_5", "NUMPAD_6", "NUMPAD_7", "NUMPAD_8", "NUMPAD_9", "NUMPAD_PERIOD",
            "NUMPAD_SLASH", "NUMPAD_ASTERIX", "HOME"}
    DIGITS = {"ZERO": "0", "ONE": "1", "TWO": "2", "THREE": "3", "FOUR": "4", "FIVE": "5",
              "SIX": "6", "SEVEN": "7", "EIGHT": "8", "NINE": "9", "PERIOD": ".",
              "COMMA": ".", "NUMPAD_PERIOD": "."}

    def modal(self, context, event):
        if getattr(self, "stop_request", False) or _STATE["active"] is not self:
            self._finish(context)
            return {"CANCELLED"}
        r = self.region
        mx, my = event.mouse_x - r.x, event.mouse_y - r.y
        inside = 0 <= mx < r.width and 0 <= my < r.height
        et, press = event.type, event.value == "PRESS"
        if et in self.PASS or not inside:
            return {"PASS_THROUGH"}
        if press and (event.ctrl or event.alt or event.oskey) and et not in {"LEFTMOUSE"}:
            self.dirty = True                   # Ctrl+Z vb. Blender'a: veriyi yeniden oku
            return {"PASS_THROUGH"}
        if et in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            self._update(context, mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if not press:
            return {"RUNNING_MODAL"}
        msg = ""
        if et == "ESC":
            if self.mode == "KNIFE" and self.knife:
                self.knife = []
            elif self.typed:
                self.typed = ""
            else:
                self._finish(context)
                return {"FINISHED"} if self.done else {"CANCELLED"}
        elif et == "R":
            self.mode, self.knife = "LOOP", []
        elif et == "K":
            self.mode, self.typed = "KNIFE", ""
        elif et == "V" and self.mode == "KNIFE":
            self.view_proj = not self.view_proj
        elif et == "C" and self.mode == "LOOP":
            self.center = not self.center
            self.typed = ""
        elif et in {"WHEELUPMOUSE", "NUMPAD_PLUS", "PLUS", "EQUAL", "PAGE_UP"} and \
                self.mode == "LOOP":
            if et.startswith("WHEEL") and self.hover is None:
                return {"PASS_THROUGH"}
            self.count = min(self.count + 1, 16)
            self.typed = ""
        elif et in {"WHEELDOWNMOUSE", "NUMPAD_MINUS", "MINUS", "PAGE_DOWN"} and \
                self.mode == "LOOP":
            if et.startswith("WHEEL") and self.hover is None:
                return {"PASS_THROUGH"}
            self.count = max(self.count - 1, 1)
        elif et in self.DIGITS and self.mode == "LOOP":
            self.typed += self.DIGITS[et]
            self.count = 1
        elif et == "BACK_SPACE" and self.mode == "LOOP":
            self.typed = self.typed[:-1]
        elif et == "RIGHTMOUSE":
            if self.mode == "KNIFE" and self.knife:
                self.knife = []
            else:
                self._finish(context)
                return {"FINISHED"} if self.done else {"CANCELLED"}
        elif et in {"LEFTMOUSE", "RET", "NUMPAD_ENTER"}:
            self._update(context, mx, my)
            if self.mode == "LOOP":
                if self.preview:
                    self._apply(context, list(self.preview))
                else:
                    msg = "Bir yüzey kenarının üzerine gel"
            else:
                if self.snap is None:
                    msg = "Yüzey sınırına tıkla"
                elif not self.knife:
                    self.knife = [np.asarray(self.snap[0], float)]
                else:
                    if self.preview:
                        self._apply(context, list(self.preview))
                    else:
                        msg = "Bu iki nokta aynı yüzeyin farklı kenarlarında değil"
        else:
            self.dirty = True
            return {"PASS_THROUGH"}
        self._update(context, mx, my)
        self._status(context, msg)
        self.area.tag_redraw()
        return {"RUNNING_MODAL"}

    # ------------------------------------------------------------ çizim

    def _draw(self):
        if _STATE["active"] is not self:
            return
        try:
            import gpu
            from gpu_extras.batch import batch_for_shader
            shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
            region = bpy.context.region
            vp = (region.width, region.height) if region else (1000, 1000)
            gpu.state.blend_set("ALPHA")
            gpu.state.depth_test_set("NONE")

            def lines(polys, color, width):
                co = []
                for S in polys:
                    S = [tuple(map(float, p)) for p in S]
                    for a, b in zip(S[:-1], S[1:]):
                        co += [a, b]
                if not co:
                    return
                batch = batch_for_shader(shader, "LINES", {"pos": co})
                shader.bind()
                shader.uniform_float("viewportSize", vp)
                shader.uniform_float("lineWidth", width)
                shader.uniform_float("color", color)
                batch.draw(shader)
            lines([e[2] for e in self.edges], COL_EDGE, 1.5)
            if self.mode == "LOOP" and self.hover is not None:
                lines([self.edges[self.hover[0]][2]], COL_HOVER, 4.0)
            lines([c["pts"] for c in self.preview], COL_CUT, 3.0)
            marks = list(self.knife) + ([self.snap[0]] if self.mode == "KNIFE" and
                                        self.snap is not None else [])
            if marks:
                s = 0.01 * max(_size(self.geoms), 1e-6)
                cr = []
                for p in marks:
                    p = np.asarray(p, float)
                    for ax in np.eye(3):
                        cr.append([p - ax * s, p + ax * s])
                lines(cr, COL_PT, 3.0)
            gpu.state.blend_set("NONE")
        except Exception as e:
            print("[Mini CAD] bölme çizim hatası:", e)


def _parse_ratio(txt):
    try:
        v = float(txt)
    except ValueError:
        return None
    if v > 1.0:
        v = v / 100.0                        # 30 → %30
    return v if 0.0 < v < 1.0 else None


classes = (MINICAD_OT_split_surface,)


@bpy.app.handlers.persistent
def _on_load_pre(_dummy):
    cleanup_all()


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.app.handlers.load_pre.append(_on_load_pre)


def unregister():
    cleanup_all()
    if _on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load_pre)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
