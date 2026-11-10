"""Mesh kenarlarından yüzeylemeye hazır bezier tel kafes üretimi.

İlkeler:
  * Her bezier noktası tam olarak bir mesh köşesinin üzerindedir (sıfır kayma).
  * Tutamaçlar Blender'ın otomatik tutamaçlarıyla değil, burada hesaplanır:
    düz diziler birebir düz, gerçek köşeler keskin, eğri diziler noktalardan geçen pürüzsüz eğri.
  * Eğriler kesişme noktalarında (3+ kenar) ve köşelerde bölünür; uçlar birebir çakışıktır.
"""

import math

import bpy

# ================================================================ saf mantık (test edilebilir)


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, k):
    return (a[0] * k, a[1] * k, a[2] * k)


def _len(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _unit(a):
    n = _len(a)
    return None if n < 1e-15 else (a[0] / n, a[1] / n, a[2] / n)


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def build_chains(pos, edges, cos_lim):
    """pos: {köşe: (x,y,z)}, edges: [(a,b)]. Kenarları zincirlere böler.
    Kırılma noktaları: derecesi 2 olmayan köşeler (uç / kesişme) ve keskin köşeler.
    [(köşe listesi, kapalı mı)] döndürür."""
    adj = {}
    for k, (a, b) in enumerate(edges):
        if a == b:
            continue
        adj.setdefault(a, []).append((k, b))
        adj.setdefault(b, []).append((k, a))

    def is_corner(v):
        nb = adj.get(v, [])
        if len(nb) != 2:
            return True
        a, b = nb[0][1], nb[1][1]
        u = _unit(_sub(pos[v], pos[a]))
        w = _unit(_sub(pos[b], pos[v]))
        if u is None or w is None:
            return True
        return _dot(u, w) < cos_lim

    breaks = {v for v in adj if is_corner(v)}
    used = set()
    chains = []

    def walk(start, k, nxt):
        chain = [start]
        used.add(k)
        cur = nxt
        while True:
            chain.append(cur)
            if cur in breaks or cur == start:
                break
            cand = [(k2, o) for k2, o in adj[cur] if k2 not in used]
            if not cand:
                break
            k2, o = cand[0]
            used.add(k2)
            cur = o
        return chain

    for v in sorted(breaks, key=str):
        for k, o in adj[v]:
            if k not in used:
                chains.append((walk(v, k, o), False))
    # kalanlar: kırılma noktası olmayan kapalı halkalar
    for k, (a, b) in enumerate(edges):
        if k in used or a == b:
            continue
        ch = walk(a, k, b)
        if ch[-1] == ch[0]:
            chains.append((ch[:-1], True))
        else:
            chains.append((ch, False))
    # kırılma noktasından başlayıp aynı noktaya dönen zincir: açık ama uçları çakışık
    return chains


def circle_tangent(q, p, r):
    """q, p, r'den geçen çemberin p'deki teğeti (doğrusalsa doğru yönü). Yaylar için kesin."""
    a, b = _sub(p, q), _sub(r, p)
    la, lb = _dot(a, a), _dot(b, b)
    if la < 1e-30 or lb < 1e-30:
        return None
    return _unit(_add(_mul(a, lb), _mul(b, la)))


def _reflect(t, d):
    """t'yi d doğrultusuna göre yansıt (yayın öbür ucundaki teğet)."""
    k = 2.0 * _dot(t, d)
    return _unit(_sub(_mul(d, k), t))


def arc_handle_len(chord_len, t, d):
    """Teğet t ile kiriş d arasındaki açıdan, çember yayını birebir veren tutamaç boyu."""
    c = max(-1.0, min(1.0, abs(_dot(t, d))))
    phi = math.acos(c)
    return chord_len / (3.0 * max(0.5, math.cos(phi / 2.0) ** 2))


def smooth_tangents(pts, cyclic, cos_lim=None):
    """Her nokta için teğet (yoksa None = köşe/düz uç)."""
    n = len(pts)
    ts = [None] * n
    for j in range(n):
        if not cyclic and (j == 0 or j == n - 1):
            continue
        q, p, r = pts[(j - 1) % n], pts[j], pts[(j + 1) % n]
        if cos_lim is not None:
            u, w = _unit(_sub(p, q)), _unit(_sub(r, p))
            if u is None or w is None or _dot(u, w) < cos_lim:
                continue
        ts[j] = circle_tangent(q, p, r)
    if not cyclic and n >= 3:
        # açık uçlar: komşu teğetin kirişe göre yansıması (yay sürekliliği)
        for j, k in ((0, 1), (n - 1, n - 2)):
            if ts[k] is not None:
                d = _unit(_sub(pts[k], pts[j])) if j == 0 else _unit(_sub(pts[j], pts[k]))
                if d is not None:
                    ts[j] = _reflect(ts[k], d)
    return ts


def bezier_handles(pts, cyclic, smooth):
    """Her nokta için (sol tutamaç, sağ tutamaç). Noktalar değişmez."""
    n = len(pts)
    ts = smooth_tangents(pts, cyclic) if smooth else [None] * n
    out = []
    for j in range(n):
        p = pts[j]
        prev = pts[(j - 1) % n] if (cyclic or j > 0) else None
        nxt = pts[(j + 1) % n] if (cyclic or j < n - 1) else None
        t = ts[j]
        if t is None:
            # düz mod / tek kenar: her tutamaç kendi kenarı boyunca (birebir düz)
            left = _add(p, _mul(_sub(prev, p), 1 / 3)) if prev is not None else \
                _sub(p, _mul(_sub(nxt, p), 1 / 3))
            right = _add(p, _mul(_sub(nxt, p), 1 / 3)) if nxt is not None else \
                _sub(p, _mul(_sub(prev, p), 1 / 3))
        else:
            if prev is not None:
                d = _unit(_sub(p, prev))
                left = _sub(p, _mul(t, arc_handle_len(_len(_sub(p, prev)), t, d)))
            else:
                left = _sub(p, _mul(t, _len(_sub(nxt, p)) / 3.0))
            if nxt is not None:
                d = _unit(_sub(nxt, p))
                right = _add(p, _mul(t, arc_handle_len(_len(_sub(nxt, p)), t, d)))
            else:
                right = _add(p, _mul(t, _len(_sub(p, prev)) / 3.0))
        out.append((left, right))
    return out


def max_deviation(pts, handles, cyclic, samples=16):
    """Bezier eğrinin mesh kenarlarından (noktaları birleştiren doğrulardan) en büyük sapması."""
    n = len(pts)
    worst = 0.0
    for j in range(n if cyclic else n - 1):
        a, b = pts[j], pts[(j + 1) % n]
        h1, h2 = handles[j][1], handles[(j + 1) % n][0]
        ab = _sub(b, a)
        L2 = _dot(ab, ab)
        for s in range(1, samples):
            t = s / samples
            u = 1 - t
            q = _add(_add(_mul(a, u ** 3), _mul(h1, 3 * u * u * t)),
                     _add(_mul(h2, 3 * u * t * t), _mul(b, t ** 3)))
            if L2 < 1e-30:
                d = _len(_sub(q, a))
            else:
                tt = max(0.0, min(1.0, _dot(_sub(q, a), ab) / L2))
                d = _len(_sub(q, _add(a, _mul(ab, tt))))
            worst = max(worst, d)
    return worst


# ================================================================ Blender operatörü

class MINICAD_OT_mesh_to_wire(bpy.types.Operator):
    bl_idname = "minicad.mesh_to_wire"
    bl_label = "Seçili Kenarlardan Tel Kafes"
    bl_description = ("Mesh'in seçili kenarlarını, noktaları birebir mesh köşelerinde duran ve "
                      "yüzeylemeye hazır bezier tel kafese çevirir")
    bl_options = {"REGISTER", "UNDO"}

    mode: bpy.props.EnumProperty(
        name="Biçim",
        items=[("SMOOTH", "Pürüzsüz", "Eğri diziler noktalardan geçen pürüzsüz eğri; düz diziler "
                "düz; köşeler keskin"),
               ("STRAIGHT", "Birebir düz", "Her kenar mesh'teki gibi düz çizgi (sıfır sapma)")],
        default="SMOOTH")
    corner: bpy.props.FloatProperty(
        name="Köşe Açısı", description="Bu açıdan keskin kırılmalar köşe kabul edilir",
        default=math.radians(30.0), min=math.radians(1.0), max=math.radians(89.0),
        subtype="ANGLE")
    hide_mesh: bpy.props.BoolProperty(name="Kaynak Mesh'i Gizle", default=False)

    @classmethod
    def poll(cls, context):
        return context.mode == "EDIT_MESH"

    def invoke(self, context, event):
        try:
            self.corner = context.scene.minicad_poly_corner
        except Exception:
            pass
        return self.execute(context)

    def execute(self, context):
        import bmesh
        objs = [o for o in (getattr(context, "objects_in_mode", None) or [context.edit_object])
                if o is not None and o.type == "MESH"]
        pos, edges = {}, []
        for ob in objs:
            bm = bmesh.from_edit_mesh(ob.data)
            mw = ob.matrix_world
            for e in bm.edges:
                if not e.select:
                    continue
                ids = []
                for v in e.verts:
                    key = (ob.name, v.index)
                    if key not in pos:
                        pos[key] = tuple(mw @ v.co)
                    ids.append(key)
                edges.append(tuple(ids))
        if not edges:
            self.report({"WARNING"}, "Seçili kenar yok")
            return {"CANCELLED"}

        # Farklı objelerde aynı konumdaki köşeleri birleştir (tam çakışık uçlar)
        canon = {}
        remap = {}
        for k, p in pos.items():
            ck = (round(p[0], 7), round(p[1], 7), round(p[2], 7))
            remap[k] = canon.setdefault(ck, k)
        edges = [(remap[a], remap[b]) for a, b in edges]

        chains = build_chains(pos, edges, math.cos(self.corner))
        smooth = self.mode == "SMOOTH"
        cu = bpy.data.curves.new("Tel_Kafes", "CURVE")
        cu.dimensions = "3D"
        cu.resolution_u = 24
        worst = 0.0
        for verts, cyclic in chains:
            pts = [pos[v] for v in verts]
            if len(pts) < 2:
                continue
            hs = bezier_handles(pts, cyclic, smooth)
            worst = max(worst, max_deviation(pts, hs, cyclic))
            sp = cu.splines.new("BEZIER")
            sp.bezier_points.add(len(pts) - 1)
            for bp, p, (hl, hr) in zip(sp.bezier_points, pts, hs):
                bp.handle_left_type = "FREE"
                bp.handle_right_type = "FREE"
                bp.co = p
                bp.handle_left = hl
                bp.handle_right = hr
            sp.use_cyclic_u = cyclic
        ob = bpy.data.objects.new("Tel_Kafes", cu)
        context.collection.objects.link(ob)
        if self.hide_mesh:
            for o in objs:
                o.hide_set(True)
        try:
            from .core import fmt_len
            dev = fmt_len(worst)
        except Exception:
            dev = f"{worst * 1000:.3f} mm"
        self.report({"INFO"}, f"'{ob.name}': {len(chains)} eğri, mesh köşelerinde sıfır kayma, "
                    f"kenarlardan en büyük sapma {dev}")
        return {"FINISHED"}


classes = (MINICAD_OT_mesh_to_wire,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
