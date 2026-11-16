"""Pivot Bounding Snap

Seçimin bounding box'unu görünümde çizer; imleç kutunun yüzeylerinde ve kenarlarında serbestçe
gezer, köşelere / kenar ortalarına / yüz merkezlerine / kutu merkezine yakalanır. Tıklanan nokta
yeni pivot olur.

Pivot hedefi:
  * En Üst Taşıyıcı (varsayılan): aktif objenin (parlak turuncu seçili) en üstteki ebeveyni,
    ör. Empty taşıyıcı. Ebeveyni yoksa aktif objenin kendisi.
  * Aktif Obje: yalnızca parlak turuncu seçili obje.
Alt objeler: N panelde "Alt Objeler" açık değilse hiçbir alt objenin pivotu değişmez (taşıyıcının
pivotu değişirken alt objeler dünyadaki yerlerinde kalır). Açıksa ya aynı nokta ya da ana kutuda
seçilen göreli konum (ör. Sağ-Alt kenar ortası) her birinin kendi kutusunda uygulanır.

Kısayol: Nesne kipinde Shift+Alt+P (Tercihler > Eklentiler'den değiştirilebilir).
"""

import math

import blf
import bpy
import gpu
from bpy.props import BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, \
    PointerProperty
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from mathutils.geometry import intersect_line_line

OP_ID = "object.pivot_bounding_snap"

# ------------------------------------------------------------------ renkler (Mini CAD ile aynı dil)
COL_BOX = (1.0, 0.62, 0.1, 0.95)        # kutu çizgileri (turuncu)
COL_OWN = (0.25, 0.85, 1.0, 0.45)       # alt objelerin kendi kutuları (mavi)
COL_SNAP = (1.0, 0.85, 0.15, 1.0)       # yakalama işareti / vurgu (sarı)
COL_FACE = (1.0, 0.85, 0.15, 0.13)      # vurgulanan yüz dolgusu
COL_HINT = (1.0, 1.0, 1.0, 0.45)        # yakalanabilir noktaların soluk işaretleri
COL_GUIDE = (0.6, 0.9, 0.6, 0.9)        # kesikli kılavuz
COL_SUB = (0.25, 0.85, 1.0, 1.0)        # alt objelerin yeni pivotları
COL_TEXT = (0.95, 0.95, 0.95, 1.0)
COL_DIM = (0.7, 0.7, 0.72, 1.0)
COL_BG = (0.08, 0.08, 0.08, 0.78)
COL_AX = ((0.95, 0.3, 0.3, 1.0), (0.45, 0.9, 0.3, 1.0), (0.35, 0.55, 1.0, 1.0))

# ------------------------------------------------------------------ seçenekler
TARGETS = [
    ('ROOT', "En Üst Taşıyıcı",
     "Aktif objenin en üstteki ebeveyni (ör. Empty taşıyıcı); ebeveyni yoksa aktif obje", 'OUTLINER', 0),
    ('ACTIVE', "Aktif Obje", "Yalnızca parlak turuncu seçili (aktif) obje", 'OBJECT_DATA', 1),
]
SPACES = [
    ('LOCAL', "Yerel", "Kutu, hedef objenin dönüşüne hizalı", 'ORIENTATION_LOCAL', 0),
    ('WORLD', "Dünya", "Kutu dünya eksenlerine hizalı", 'ORIENTATION_GLOBAL', 1),
]
BOX_SCOPES = [
    ('SELECTION', "Seçim", "Seçili objeler ve onların alt objeleri", 'RESTRICT_SELECT_OFF', 0),
    ('HIERARCHY', "Tüm Hiyerarşi", "Hedefin altındaki bütün objeler de kutuya katılır", 'OUTLINER', 1),
]
SUB_SCOPES = [
    ('SELECTED', "Seçili Diğerleri", "Hedef dışındaki seçili objeler", 'RESTRICT_SELECT_OFF', 0),
    ('HIERARCHY', "Hedefin Altı", "Hedefin bütün alt objeleri (seçili olmasalar da)", 'OUTLINER', 1),
    ('BOTH', "İkisi", "Seçili diğerleri + hedefin bütün alt objeleri", 'GROUP', 2),
]
SUB_MODES = [
    ('SAME', "Aynı Nokta", "Hepsine ana pivotla aynı dünya noktası atanır", 'PIVOT_CURSOR', 0),
    ('OWN', "Kendi Kutusunda",
     "Ana kutuda seçilen göreli konum (ör. Sağ-Alt kenar ortası) her objenin kendi kutusunda "
     "uygulanır", 'PIVOT_INDIVIDUAL', 1),
]

# bound_box'u anlamlı (geometrisi olan) türler
GEOM_TYPES = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META', 'LATTICE', 'ARMATURE', 'GPENCIL',
              'GREASEPENCIL', 'CURVES', 'POINTCLOUD', 'VOLUME'}
# pivotu origin_set ile (geometri yerinde kalarak) taşınan türler; diğerleri (Empty, kamera,
# ışık...) objenin kendisi taşınır, alt objeleri yerinde tutulur
DATA_TYPES = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META', 'LATTICE', 'ARMATURE', 'GPENCIL',
              'GREASEPENCIL', 'CURVES', 'POINTCLOUD'}

# ------------------------------------------------------------------ kutu topolojisi
CORNERS = [Vector((x, y, z)) for x in (0, 1) for y in (0, 1) for z in (0, 1)]
EDGES = [(a, b) for a in range(8) for b in range(a + 1, 8)
         if sum(CORNERS[a][k] != CORNERS[b][k] for k in range(3)) == 1]
SIDE = (("Sol", "Sağ"), ("Ön", "Arka"), ("Alt", "Üst"))
KIND_NAMES = {'CORNER': "Köşe", 'EDGE_MID': "Kenar ortası", 'FACE': "Yüz merkezi",
              'CENTER': "Merkez"}
BIAS = {'CORNER': 4.0, 'EDGE_MID': 3.0, 'CENTER': 2.0, 'FACE': 0.0}   # px: yakın adaylarda öncelik


def side_name(fixed):
    """{eksen: 0/1} → 'Sağ-Ön-Alt' gibi ad (x, y, z sırasıyla)."""
    return "-".join(SIDE[k][int(v)] for k, v in sorted(fixed.items()))


def edge_fixed(i):
    a, b = EDGES[i]
    return {k: CORNERS[a][k] for k in range(3) if CORNERS[a][k] == CORNERS[b][k]}


def _build_snaps():
    out = []
    for c in CORNERS:
        out.append({'kind': 'CORNER', 'uvw': c.copy(), 'edge': None, 'face': None,
                    'label': side_name({0: c.x, 1: c.y, 2: c.z}) + " köşe"})
    for i, (a, b) in enumerate(EDGES):
        out.append({'kind': 'EDGE_MID', 'uvw': (CORNERS[a] + CORNERS[b]) * 0.5, 'edge': i,
                    'face': None, 'label': side_name(edge_fixed(i)) + " kenar ortası"})
    for k in range(3):
        for s in (0, 1):
            u = Vector((0.5, 0.5, 0.5))
            u[k] = s
            out.append({'kind': 'FACE', 'uvw': u, 'edge': None, 'face': (k, s),
                        'label': SIDE[k][s] + " yüz merkezi"})
    out.append({'kind': 'CENTER', 'uvw': Vector((0.5, 0.5, 0.5)), 'edge': None, 'face': None,
                'label': "Kutu merkezi"})
    return out


SNAPS = _build_snaps()


class Box:
    """frame (dönüş + konum, ölçeksiz) uzayında lo..hi kutusu."""

    def __init__(self, frame, lo, hi):
        self.frame, self.lo, self.hi = frame, lo, hi
        self.inv = frame.inverted_safe()

    def at(self, uvw):
        s = self.hi - self.lo
        return self.frame @ Vector(self.lo[i] + uvw[i] * s[i] for i in range(3))

    def uvw(self, world):
        p = self.inv @ world
        s = self.hi - self.lo
        return Vector(((p[i] - self.lo[i]) / s[i]) if abs(s[i]) > 1e-12 else 0.5 for i in range(3))

    def corners(self):
        return [self.at(c) for c in CORNERS]

    def face_pts(self, face):
        k, s = face
        i, j = [a for a in range(3) if a != k]
        out = []
        for u, v in ((0, 0), (1, 0), (1, 1), (0, 1)):
            w = Vector((0, 0, 0))
            w[k], w[i], w[j] = s, u, v
            out.append(self.at(w))
        return out

    def axes(self):
        m = self.frame.to_3x3()
        return [m.col[i].normalized() for i in range(3)]

    def ray_hit(self, o, d):
        """Işının kutuya ilk değdiği yüz: (dünya noktası, (eksen, yan)) ya da None."""
        o2, d2 = self.inv @ o, self.inv.to_3x3() @ d
        eps = 1e-7
        t0, t1, f0, f1 = -1e30, 1e30, None, None
        for i in range(3):
            lo, hi = self.lo[i] - eps, self.hi[i] + eps
            if abs(d2[i]) < 1e-12:
                if not lo <= o2[i] <= hi:
                    return None
                continue
            a, b = (lo - o2[i]) / d2[i], (hi - o2[i]) / d2[i]
            sa, sb = 0, 1
            if a > b:
                a, b, sa, sb = b, a, 1, 0
            if a > t0:
                t0, f0 = a, (i, sa)
            if b < t1:
                t1, f1 = b, (i, sb)
            if t0 > t1:
                return None
        if t0 > 0 and f0 is not None:
            t, f = t0, f0
        elif t1 > 0 and f1 is not None:
            t, f = t1, f1
        else:
            return None
        return self.frame @ (o2 + d2 * t), f


def frame_of(ob):
    loc, rot, _s = ob.matrix_world.decompose()
    return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()


def make_box(objs, frame):
    pts = [ob.matrix_world @ Vector(c) for ob in objs if ob.type in GEOM_TYPES
           for c in ob.bound_box]
    if not pts:
        pts = [ob.matrix_world.translation.copy() for ob in objs]
    inv = frame.inverted_safe()
    lp = [inv @ p for p in pts]
    lo = Vector(min(p[i] for p in lp) for i in range(3))
    hi = Vector(max(p[i] for p in lp) for i in range(3))
    return Box(frame, lo, hi)


def own_box(ob, space):
    """Alt objenin kendi kutusu: geometrisi varsa kendisi, yoksa (Empty) altındakiler."""
    objs = [ob] if ob.type in GEOM_TYPES else ([c for c in ob.children_recursive] or [ob])
    return make_box(objs, frame_of(ob) if space == 'LOCAL' else Matrix.Identity(4))


def resolve(context, st):
    """Seçimden hedef, kutu objeleri ve alt objeleri çıkarır."""
    sel = list(context.selected_objects)
    active = context.active_object
    if active is None or (sel and active not in sel):
        active = sel[0] if sel else active
    if active is None:
        return None
    if not sel:
        sel = [active]
    target = active
    if st.target == 'ROOT':
        while target.parent is not None:
            target = target.parent
    box_objs = set(sel)
    for ob in sel:
        box_objs.update(ob.children_recursive)
    if st.box_scope == 'HIERARCHY':
        box_objs.add(target)
        box_objs.update(target.children_recursive)
    subs = set()
    if st.sub_enabled:
        if st.sub_scope in ('SELECTED', 'BOTH'):
            subs.update(sel)
        if st.sub_scope in ('HIERARCHY', 'BOTH'):
            subs.update(target.children_recursive)
        subs.discard(target)
    return {'sel': sel, 'active': active, 'target': target,
            'box_objs': sorted(box_objs, key=lambda o: o.name),
            'subs': sorted(subs, key=lambda o: o.name)}


def build(context, st):
    r = resolve(context, st)
    if r is None:
        return None
    frame = frame_of(r['target']) if st.space == 'LOCAL' else Matrix.Identity(4)
    r['box'] = make_box(r['box_objs'], frame)
    r['own'] = [own_box(ob, st.space) for ob in r['subs']] if st.sub_mode == 'OWN' else []
    return r


def plan(r, st, point):
    """[(obje, yeni pivot dünya noktası)] — önce hedef, sonra alt objeler."""
    out = [(r['target'], point.copy())]
    if not r['subs']:
        return out
    if st.sub_mode == 'OWN':
        uvw = Vector(max(0.0, min(1.0, c)) for c in r['box'].uvw(point))
        out += [(ob, bx.at(uvw)) for ob, bx in zip(r['subs'], r['own'])]
    else:
        out += [(ob, point.copy()) for ob in r['subs']]
    return out


def set_origin(context, ob, p):
    """Objenin pivotunu p'ye taşır; geometri ve alt objeler dünyada yerinde kalır."""
    if ob.library is not None:
        return False
    if ob.type in DATA_TYPES and ob.data is not None:
        context.scene.cursor.location = p
        try:
            with context.temp_override(selected_editable_objects=[ob], selected_objects=[ob],
                                       active_object=ob, object=ob):
                bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
        except RuntimeError:
            return False
        context.view_layer.update()
        return (ob.matrix_world.translation - p).length < 1e-4 * max(1.0, p.length)
    kids = [(c, c.matrix_world.copy()) for c in ob.children]
    mw = ob.matrix_world.copy()
    mw.translation = p
    ob.matrix_world = mw
    context.view_layer.update()
    for c, m in kids:
        c.matrix_world = m
    context.view_layer.update()
    return True


def apply_plan(context, items):
    cur = context.scene.cursor
    saved = (cur.location.copy(), cur.rotation_mode, cur.rotation_euler.copy(),
             cur.rotation_quaternion.copy())
    ok, bad = 0, []
    for ob, p in items:
        if set_origin(context, ob, p):
            ok += 1
        else:
            bad.append(ob.name)
    cur.location, cur.rotation_mode = saved[0], saved[1]
    cur.rotation_euler, cur.rotation_quaternion = saved[2], saved[3]
    return ok, bad


def report_result(op, ok, bad, target):
    if bad:
        op.report({'WARNING'}, f"{ok} pivot ayarlandı; ayarlanamayan: {', '.join(bad[:5])}"
                               f"{' …' if len(bad) > 5 else ''} (bağlı / kilitli veri)")
    elif ok == 1:
        op.report({'INFO'}, f"'{target.name}' pivotu ayarlandı")
    else:
        op.report({'INFO'}, f"'{target.name}' + {ok - 1} alt obje pivotu ayarlandı")


def shortcut_text(context):
    kc = context.window_manager.keyconfigs.user
    km = kc.keymaps.get("Object Mode") if kc else None
    if km:
        for kmi in km.keymap_items:
            if kmi.idname == OP_ID and kmi.active:
                return kmi.to_string()
    return ""


# ------------------------------------------------------------------ çizim yardımcıları
def _shader(name):
    return gpu.shader.from_builtin(name)


def _lines(segs, color, width, region):
    if not segs:
        return
    pts = [tuple(p) if len(p) == 3 else (p[0], p[1], 0.0) for p in segs]
    sh = _shader('POLYLINE_UNIFORM_COLOR')
    sh.bind()
    sh.uniform_float("viewportSize", (region.width, region.height))
    sh.uniform_float("lineWidth", width)
    sh.uniform_float("color", color)
    batch_for_shader(sh, 'LINES', {"pos": pts}).draw(sh)


def _loop(pts, color, width, region):
    seg = []
    for k in range(len(pts)):
        seg += [pts[k], pts[(k + 1) % len(pts)]]
    _lines(seg, color, width, region)


def _tris(pts, idx, color):
    sh = _shader('UNIFORM_COLOR')
    sh.bind()
    sh.uniform_float("color", color)
    pts = [tuple(p) if len(p) == 3 else (p[0], p[1], 0.0) for p in pts]
    batch_for_shader(sh, 'TRIS', {"pos": pts}, indices=idx).draw(sh)


def _rect(x0, y0, x1, y1, color):
    _tris([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], [(0, 1, 2), (0, 2, 3)], color)


def _dashed(a, b, color, region, dash=6.0, gap=4.0, width=1.5):
    a, b = Vector((a[0], a[1])), Vector((b[0], b[1]))
    L = (b - a).length
    if L < 1:
        return
    d = (b - a) / L
    seg, s = [], 0.0
    while s < L:
        e = min(s + dash, L)
        seg += [a + d * s, a + d * e]
        s = e + gap
    _lines([(p.x, p.y, 0.0) for p in seg], color, width, region)


def _circle(x, y, r, n=20):
    return [(x + r * math.cos(t), y + r * math.sin(t))
            for t in (2 * math.pi * i / n for i in range(n))]


def _marker(kind, x, y, s, color, width, region):
    """Mini CAD dili: kare köşe, üçgen kenar ortası, elmas yüz merkezi, daire merkez."""
    if kind == 'CORNER':
        _loop([(x - s, y - s), (x + s, y - s), (x + s, y + s), (x - s, y + s)], color, width, region)
    elif kind in ('EDGE_MID',):
        _loop([(x - s, y - s * 0.8), (x + s, y - s * 0.8), (x, y + s)], color, width, region)
    elif kind == 'FACE':
        _loop([(x, y - s), (x + s, y), (x, y + s), (x - s, y)], color, width, region)
    elif kind == 'CENTER':
        _loop(_circle(x, y, s), color, width, region)
        _lines([(x - s * 0.5, y), (x + s * 0.5, y), (x, y - s * 0.5), (x, y + s * 0.5)],
               color, width, region)
    else:   # serbest nokta
        _lines([(x - s, y - s), (x + s, y + s), (x - s, y + s), (x + s, y - s)],
               color, width, region)


def _text(x, y, txt, color=COL_TEXT, size=12):
    blf.size(0, size)
    blf.color(0, *color)
    blf.position(0, x, y, 0)
    blf.draw(0, txt)
    return blf.dimensions(0, txt)


def _label(x, y, txt, color, size, s):
    blf.size(0, size)
    w, h = blf.dimensions(0, txt)
    p = 4 * s
    _rect(x - p, y - p, x + w + p, y + h + p, COL_BG)
    _text(x, y, txt, color, size)


# ------------------------------------------------------------------ modal operatör
class PBS_OT_pivot_bounding_snap(bpy.types.Operator):
    """Seçimin bounding box'unda imleçle yeni pivot belirle (köşe / kenar ortası / yüz merkezi /
merkez yakalamalı, yüzey ve kenarlar üzerinde serbest)"""
    bl_idname = OP_ID
    bl_label = "Pivot Belirle"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return bool(context.mode == 'OBJECT' and context.area is not None
                    and context.area.type == 'VIEW_3D'
                    and (context.active_object is not None or context.selected_objects))

    # ---------- kurulum / temizlik
    def invoke(self, context, event):
        self.st = context.scene.pbs
        self.area = context.area
        self.region = next((r for r in self.area.regions if r.type == 'WINDOW'), None)
        self.rv3d = self.area.spaces.active.region_3d
        if self.region is None or self.rv3d is None:
            self.report({'WARNING'}, "3D görünüm bulunamadı")
            return {'CANCELLED'}
        self.ui = context.preferences.system.ui_scale
        self.ctrl = self.shift = False
        self.hover = None
        self.mouse = None
        self.r = build(context, self.st)
        if self.r is None:
            self.report({'WARNING'}, "Seçili obje yok")
            return {'CANCELLED'}
        self._h3 = bpy.types.SpaceView3D.draw_handler_add(self._draw_3d, (), 'WINDOW', 'POST_VIEW')
        self._h2 = bpy.types.SpaceView3D.draw_handler_add(self._draw_2d, (), 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        self._move(event)
        self._header()
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _finish(self):
        bpy.types.SpaceView3D.draw_handler_remove(self._h3, 'WINDOW')
        bpy.types.SpaceView3D.draw_handler_remove(self._h2, 'WINDOW')
        self.area.header_text_set(None)
        self.area.tag_redraw()

    def _rebuild(self, context):
        r = build(context, self.st)
        if r is not None:
            self.r = r
        self._recompute()

    # ---------- imleç → aday nokta
    def _px(self, p):
        return view3d_utils.location_3d_to_region_2d(self.region, self.rv3d, p)

    def _move(self, event):
        mx, my = event.mouse_x - self.region.x, event.mouse_y - self.region.y
        if 0 <= mx < self.region.width and 0 <= my < self.region.height:
            self.mouse = Vector((mx, my))
            self._recompute()
            return True
        return False

    def _recompute(self):
        if self.mouse is not None:
            self.hover = self._pick(self.mouse)

    def _snap_on(self, kind):
        st = self.st
        return {'CORNER': st.snap_corner, 'EDGE_MID': st.snap_edge, 'FACE': st.snap_face,
                'CENTER': st.snap_center}[kind]

    def _pick(self, m):
        box = self.r['box']
        o = view3d_utils.region_2d_to_origin_3d(self.region, self.rv3d, m)
        d = view3d_utils.region_2d_to_vector_3d(self.region, self.rv3d, m)
        R = self.st.snap_px * self.ui
        # 1) noktasal yakalamalar (Ctrl basılıyken kapalı)
        if not self.ctrl:
            best = None
            for sn in SNAPS:
                if not self._snap_on(sn['kind']):
                    continue
                p = box.at(sn['uvw'])
                q = self._px(p)
                if q is None:
                    continue
                dist = (q - m).length
                if dist > R:
                    continue
                score = dist - BIAS[sn['kind']] * self.ui
                if best is None or score < best[0]:
                    best = (score, sn, p)
            if best:
                sn = best[1]
                return {'point': best[2], 'kind': sn['kind'], 'label': sn['label'],
                        'edge': sn['edge'], 'face': sn['face'], 'snap': True}
        # 2) kenarlar: imlece en yakın kenar noktası
        cs = box.corners()
        eb = None
        for i, (a, b) in enumerate(EDGES):
            A, B = cs[a], cs[b]
            ab = B - A
            t = 0.0
            if ab.length_squared > 1e-18:
                hit = intersect_line_line(o, o + d, A, B)
                if hit is not None:
                    t = max(0.0, min(1.0, (hit[1] - A).dot(ab) / ab.length_squared))
            q = self._px(A + ab * t)
            if q is None:
                continue
            dist = (q - m).length
            if eb is None or dist < eb[0]:
                eb = (dist, i, t)
        if eb and eb[0] < R * 0.6:
            return self._edge_hover(eb[1], eb[2])
        # 3) kutu yüzeyi üzerinde serbest
        hit = box.ray_hit(o, d)
        if hit is not None:
            return self._face_hover(*hit)
        # 4) kutunun dışında: en yakın kenar
        if eb:
            return self._edge_hover(eb[1], eb[2])
        return None

    def _edge_hover(self, i, t):
        a, b = EDGES[i]
        step = "  (çeyrek adım)" if self.shift else ""
        if self.shift:
            t = round(t * 4) / 4
        uvw = CORNERS[a].lerp(CORNERS[b], t)
        return {'point': self.r['box'].at(uvw), 'kind': 'FREE', 'edge': i, 'face': None,
                'snap': False,
                'label': f"{side_name(edge_fixed(i))} kenarı · %{t * 100:.0f}{step}"}

    def _face_hover(self, p, face):
        k, s = face
        box = self.r['box']
        if self.shift:
            u = box.uvw(p)
            for a in range(3):
                u[a] = s if a == k else round(max(0.0, min(1.0, u[a])) * 4) / 4
            p = box.at(u)
        step = "  (çeyrek adım)" if self.shift else ""
        return {'point': p, 'kind': 'FREE', 'edge': None, 'face': face, 'snap': False,
                'label': f"{SIDE[k][s]} yüzü · serbest{step}"}

    # ---------- durum çubuğu
    def _header(self):
        st = self.st
        tgt = dict((k, n) for k, n, *_ in TARGETS)[st.target]
        self.area.header_text_set(
            f"Pivot → {self.r['target'].name} ({tgt})   •   Sol tık / Enter: uygula   "
            f"Sağ tık / Esc: iptal   Ctrl: serbest   Shift: çeyrek adım   "
            f"H: hedef  W: kutu yönü  A: alt objeler  M: alt obje ataması  1-4: yakalama türleri")

    # ---------- modal
    def modal(self, context, event):
        self.area.tag_redraw()
        self.ctrl, self.shift = event.ctrl, event.shift
        t, v = event.type, event.value
        st = self.st

        if t in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'TRACKPADPAN', 'TRACKPADZOOM',
                 'MOUSEROTATE', 'MOUSESMARTZOOM'} or t.startswith('NDOF') or \
                (t.startswith('NUMPAD_') and t != 'NUMPAD_ENTER'):
            return {'PASS_THROUGH'}
        if t in {'MOUSEMOVE', 'INBETWEEN_MOUSEMOVE', 'LEFT_CTRL', 'RIGHT_CTRL', 'LEFT_SHIFT',
                 'RIGHT_SHIFT'}:
            if not self._move(event):
                self._recompute()
            return {'RUNNING_MODAL'}
        if v != 'PRESS':
            return {'RUNNING_MODAL'}

        if t in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'}:
            if t == 'LEFTMOUSE' and not self._move(event):
                return {'RUNNING_MODAL'}          # görünüm dışına tıklama: yok say
            if self.hover is None:
                return {'RUNNING_MODAL'}
            self._finish()
            ok, bad = apply_plan(context, plan(self.r, st, self.hover['point']))
            report_result(self, ok, bad, self.r['target'])
            return {'FINISHED'}
        if t in {'RIGHTMOUSE', 'ESC'}:
            self._finish()
            return {'CANCELLED'}

        if t == 'H':
            st.target = 'ACTIVE' if st.target == 'ROOT' else 'ROOT'
        elif t == 'W':
            st.space = 'WORLD' if st.space == 'LOCAL' else 'LOCAL'
        elif t == 'A':
            st.sub_enabled = not st.sub_enabled
        elif t == 'M':
            st.sub_mode = 'OWN' if st.sub_mode == 'SAME' else 'SAME'
        elif t in {'ONE', 'TWO', 'THREE', 'FOUR'}:
            key = {'ONE': 'snap_corner', 'TWO': 'snap_edge', 'THREE': 'snap_face',
                   'FOUR': 'snap_center'}[t]
            setattr(st, key, not getattr(st, key))
        else:
            return {'RUNNING_MODAL'}
        self._rebuild(context)
        self._header()
        return {'RUNNING_MODAL'}

    # ---------- çizim: 3B (kutular, vurgulanan kenar / yüz)
    def _mine(self):
        c = bpy.context
        return c.area is not None and c.area.as_pointer() == self.area.as_pointer() and \
            c.region is not None and c.region.as_pointer() == self.region.as_pointer()

    def _draw_3d(self):
        if not self._mine():
            return
        region = self.region
        gpu.state.depth_test_set('NONE')
        gpu.state.blend_set('ALPHA')
        box = self.r['box']
        if self.r['own']:
            seg = []
            for bx in self.r['own']:
                cs = bx.corners()
                seg += [p for a, b in EDGES for p in (cs[a], cs[b])]
            _lines(seg, COL_OWN, 1.0, region)
        cs = box.corners()
        _lines([p for a, b in EDGES for p in (cs[a], cs[b])], COL_BOX, 1.6 * self.ui, region)
        h = self.hover
        if h is not None:
            if h['face'] is not None:
                fp = box.face_pts(h['face'])
                _tris(fp, [(0, 1, 2), (0, 2, 3)], COL_FACE)
                _loop(fp, COL_SNAP, 1.6 * self.ui, region)
            if h['edge'] is not None:
                a, b = EDGES[h['edge']]
                _lines([cs[a], cs[b]], COL_SNAP, 3.0 * self.ui, region)
        gpu.state.blend_set('NONE')

    # ---------- çizim: 2B (işaretler, kılavuz, etiket, bilgi kutusu)
    def _draw_2d(self):
        if not self._mine():
            return
        region, s = self.region, self.ui
        gpu.state.blend_set('ALPHA')
        box = self.r['box']
        # yakalanabilir noktaların soluk işaretleri
        if not self.ctrl:
            for sn in SNAPS:
                if self._snap_on(sn['kind']):
                    q = self._px(box.at(sn['uvw']))
                    if q is not None:
                        _marker(sn['kind'], q.x, q.y, 3.5 * s, COL_HINT, 1.0, region)
        # mevcut pivot
        tgt = self.r['target']
        cur = self._px(tgt.matrix_world.translation)
        if cur is not None:
            _loop(_circle(cur.x, cur.y, 4 * s, 12), COL_DIM, 1.5, region)
        h = self.hover
        if h is not None:
            p = h['point']
            q = self._px(p)
            if q is not None:
                # alt objelerin yeni pivotları
                for ob, sp in plan(self.r, self.st, p)[1:200]:
                    a, b = self._px(ob.matrix_world.translation), self._px(sp)
                    if b is None:
                        continue
                    if a is not None:
                        _dashed(a, b, (*COL_SUB[:3], 0.5), region, 4, 3, 1.0)
                    _loop(_circle(b.x, b.y, 3.5 * s, 10), COL_SUB, 2.0, region)
                # mevcut → yeni pivot kılavuzu
                if cur is not None:
                    _dashed(cur, q, COL_GUIDE, region)
                # yeni pivotun eksenleri (hedef kutu yönünde)
                for i, ax in enumerate(box.axes()):
                    e = self._px(p + ax * max(1e-3, (box.hi - box.lo).length * 0.01))
                    if e is None or (e - q).length < 1e-3:
                        continue
                    dv = (e - q).normalized() * 30 * s
                    _lines([(q.x, q.y, 0), (q.x + dv.x, q.y + dv.y, 0)], COL_AX[i], 2.0, region)
                # yakalama işareti
                if h['snap']:
                    _marker(h['kind'], q.x, q.y, 7 * s, COL_SNAP, 2.5, region)
                else:
                    _marker('FREE', q.x, q.y, 5 * s, COL_SNAP, 2.0, region)
                _loop(_circle(q.x, q.y, 2 * s, 8), COL_TEXT, 2.0, region)
                _label(q.x + 14 * s, q.y + 12 * s, h['label'], COL_SNAP, int(12 * s), s)
        self._draw_hud(region, s)
        gpu.state.blend_set('NONE')

    def _draw_hud(self, region, s):
        st, r = self.st, self.r
        tname = dict((k, n) for k, n, *_ in TARGETS)[st.target]
        if st.sub_enabled:
            mode = dict((k, n) for k, n, *_ in SUB_MODES)[st.sub_mode]
            sub = f"Açık · {len(r['subs'])} obje · {mode}"
        else:
            sub = "Kapalı (yalnızca hedef)"
        flags = [("1 Köşe", st.snap_corner), ("2 Kenar ortası", st.snap_edge),
                 ("3 Yüz merkezi", st.snap_face), ("4 Merkez", st.snap_center)]
        rows = [
            ("PIVOT BOUNDING SNAP", COL_BOX),
            (f"Hedef: {r['target'].name}  ({tname})   [H]", COL_TEXT),
            (f"Kutu: {'Yerel' if st.space == 'LOCAL' else 'Dünya'}   [W]", COL_TEXT),
            (f"Alt objeler: {sub}   [A] [M]", COL_SUB if st.sub_enabled else COL_DIM),
            ("Yakalama: " + "   ".join(f"{n}{'' if on else ' (kapalı)'}" for n, on in flags),
             COL_TEXT if not self.ctrl else COL_DIM),
            ("Ctrl: serbest   Shift: çeyrek adım   Sol tık: uygula   Sağ tık / Esc: iptal",
             COL_DIM),
        ]
        size = int(11 * s)
        lh = 17 * s
        x0, y0 = 70 * s, 30 * s
        blf.size(0, size)
        w = max(blf.dimensions(0, t)[0] for t, _ in rows)
        _rect(x0 - 8 * s, y0 - 7 * s, x0 + w + 8 * s, y0 + lh * len(rows) - 2 * s, COL_BG)
        for i, (t, c) in enumerate(reversed(rows)):
            _text(x0, y0 + i * lh, t, c, size)


# ------------------------------------------------------------------ panelden doğrudan atama
class PBS_OT_preset(bpy.types.Operator):
    """Pivotu kutunun bu noktasına doğrudan ata (imleç gerekmez)"""
    bl_idname = "object.pivot_bounding_preset"
    bl_label = "Pivotu Kutu Noktasına Ata"
    bl_options = {'REGISTER', 'UNDO'}

    uvw: FloatVectorProperty(size=3, default=(0.5, 0.5, 0.5), min=0.0, max=1.0)

    @classmethod
    def poll(cls, context):
        return bool(context.mode == 'OBJECT' and
                    (context.active_object is not None or context.selected_objects))

    def execute(self, context):
        st = context.scene.pbs
        r = build(context, st)
        if r is None:
            return {'CANCELLED'}
        ok, bad = apply_plan(context, plan(r, st, r['box'].at(Vector(self.uvw))))
        report_result(self, ok, bad, r['target'])
        return {'FINISHED'}


# ------------------------------------------------------------------ ayarlar
def _redraw(self, context):
    for a in context.screen.areas if context.screen else ():
        if a.type == 'VIEW_3D':
            a.tag_redraw()


class PBS_Settings(bpy.types.PropertyGroup):
    target: EnumProperty(name="Pivot Hedefi", items=TARGETS, default='ROOT', update=_redraw)
    space: EnumProperty(name="Kutu Yönü", items=SPACES, default='LOCAL')
    box_scope: EnumProperty(name="Kutu Kapsamı", items=BOX_SCOPES, default='SELECTION')
    snap_corner: BoolProperty(name="Köşeler", default=True, description="8 köşe (kare işaret)")
    snap_edge: BoolProperty(name="Kenar Ortaları", default=True,
                            description="12 kenarın ortası (üçgen işaret)")
    snap_face: BoolProperty(name="Yüz Merkezleri", default=True,
                            description="6 yüzün merkezi (elmas işaret)")
    snap_center: BoolProperty(name="Kutu Merkezi", default=True,
                              description="Kutunun tam merkezi (daire işaret)")
    snap_px: FloatProperty(name="Yakalama Mesafesi", default=16.0, min=4.0, max=60.0,
                           subtype='PIXEL', description="İmleç bu kadar yakınsa noktaya yakalanır")
    sub_enabled: BoolProperty(name="Alt Objeler", default=False,
                              description="Kapalıyken yalnızca hedefin pivotu değişir; alt "
                                          "objelerin pivotuna dokunulmaz", update=_redraw)
    sub_scope: EnumProperty(name="Kapsam", items=SUB_SCOPES, default='SELECTED')
    sub_mode: EnumProperty(name="Atama", items=SUB_MODES, default='OWN')


# ------------------------------------------------------------------ N panel
class PBS_PT_main(bpy.types.Panel):
    bl_label = "Pivot Bounding Snap"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pivot"

    def draw(self, context):
        st = context.scene.pbs
        lay = self.layout
        col = lay.column()
        col.scale_y = 1.6
        sc = shortcut_text(context)
        col.operator(OP_ID, text=f"Pivot Belirle   ({sc})" if sc else "Pivot Belirle",
                     icon='PIVOT_BOUNDBOX')

        r = resolve(context, st) if context.mode == 'OBJECT' else None
        box = lay.box()
        if r is None:
            box.label(text="Nesne kipinde bir obje seçin", icon='INFO')
            return
        t = r['target']
        col = box.column(align=True)
        col.label(text=f"Hedef: {t.name}", icon='OUTLINER_OB_' + t.type
                  if t.type in {'MESH', 'EMPTY', 'CURVE', 'CAMERA', 'LIGHT', 'FONT', 'ARMATURE'}
                  else 'OBJECT_DATA')
        if t is not r['active']:
            col.label(text=f"   (aktif '{r['active'].name}' objesinin en üst taşıyıcısı)")
        col.label(text=f"Kutu: {len(r['box_objs'])} obje", icon='PIVOT_BOUNDBOX')
        if st.sub_enabled:
            col.label(text=f"Alt objeler: {len(r['subs'])} objeye de atanacak", icon='GROUP')
        else:
            col.label(text="Alt objelerin pivotu değişmez", icon='LOCKED')

        lay.label(text="Doğrudan ata:")
        row = lay.row(align=True)
        for txt, uvw, ic in (("Alt", (0.5, 0.5, 0.0), 'TRIA_DOWN'),
                             ("Merkez", (0.5, 0.5, 0.5), 'PIVOT_MEDIAN'),
                             ("Üst", (0.5, 0.5, 1.0), 'TRIA_UP')):
            row.operator(PBS_OT_preset.bl_idname, text=txt, icon=ic).uvw = uvw


class PBS_PT_target(bpy.types.Panel):
    bl_label = "Ana Pivot"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pivot"
    bl_parent_id = "PBS_PT_main"

    def draw(self, context):
        st = context.scene.pbs
        lay = self.layout
        lay.label(text="Pivotu değişecek obje:")
        lay.row().prop(st, "target", expand=True)
        lay.separator()
        lay.label(text="Kutu yönü:")
        lay.row().prop(st, "space", expand=True)
        lay.label(text="Kutuya katılanlar:")
        lay.row().prop(st, "box_scope", expand=True)


class PBS_PT_snap(bpy.types.Panel):
    bl_label = "Yakalama Noktaları"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pivot"
    bl_parent_id = "PBS_PT_main"

    def draw(self, context):
        st = context.scene.pbs
        col = self.layout.column(align=True)
        col.prop(st, "snap_corner", text="1  Köşeler  □", toggle=True)
        col.prop(st, "snap_edge", text="2  Kenar Ortaları  △", toggle=True)
        col.prop(st, "snap_face", text="3  Yüz Merkezleri  ◇", toggle=True)
        col.prop(st, "snap_center", text="4  Kutu Merkezi  ○", toggle=True)
        self.layout.prop(st, "snap_px")


class PBS_PT_sub(bpy.types.Panel):
    bl_label = "Alt Objeler"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pivot"
    bl_parent_id = "PBS_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        self.layout.prop(context.scene.pbs, "sub_enabled", text="")

    def draw(self, context):
        st = context.scene.pbs
        lay = self.layout
        lay.active = st.sub_enabled
        lay.label(text="Hangi objeler:")
        lay.column(align=True).prop(st, "sub_scope", expand=True)
        lay.separator()
        lay.label(text="Nasıl atansın:")
        lay.row().prop(st, "sub_mode", expand=True)
        col = lay.column(align=True)
        col.scale_y = 0.8
        if st.sub_mode == 'OWN':
            col.label(text="Ana kutuda seçilen konum (ör. Sağ-Alt")
            col.label(text="kenar ortası) her objenin kendi")
            col.label(text="kutusundaki aynı konuma atanır.")
        else:
            col.label(text="Hepsinin pivotu ana pivotla")
            col.label(text="aynı noktaya taşınır.")


class PBS_PT_keys(bpy.types.Panel):
    bl_label = "Tuşlar"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pivot"
    bl_parent_id = "PBS_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        col = self.layout.column(align=True)
        col.scale_y = 0.85
        for k, d in ((shortcut_text(context) or "-", "başlat (nesne kipinde)"),
                     ("Sol tık / Enter", "uygula"), ("Sağ tık / Esc", "iptal"),
                     ("Ctrl (basılı)", "yakalamasız serbest"),
                     ("Shift (basılı)", "kenar / yüzeyde çeyrek adım"),
                     ("H", "hedef: en üst taşıyıcı / aktif"), ("W", "kutu: yerel / dünya"),
                     ("A", "alt objeler aç / kapa"), ("M", "alt obje ataması"),
                     ("1 2 3 4", "köşe / kenar ortası / yüz / merkez")):
            row = col.row()
            row.label(text=k)
            row.label(text=d)
        self.layout.label(text="Kısayol, Tercihler > Eklentiler'den değişir", icon='PREFERENCES')


# ------------------------------------------------------------------ tercihler (kısayol)
class PBS_AddonPrefs(bpy.types.AddonPreferences):
    bl_idname = __package__

    def draw(self, context):
        import rna_keymap_ui
        lay = self.layout
        lay.label(text="Kısayol (nesne kipinde):")
        kc = context.window_manager.keyconfigs.user
        km = kc.keymaps.get("Object Mode")
        if km:
            for kmi in km.keymap_items:
                if kmi.idname == OP_ID:
                    rna_keymap_ui.draw_kmi(["ADDON", "USER", "DEFAULT"], kc, km, kmi, lay, 0)


def _menu(self, context):
    self.layout.separator()
    self.layout.operator(OP_ID, icon='PIVOT_BOUNDBOX')


_classes = (PBS_Settings, PBS_OT_pivot_bounding_snap, PBS_OT_preset, PBS_PT_main, PBS_PT_target,
            PBS_PT_snap, PBS_PT_sub, PBS_PT_keys, PBS_AddonPrefs)
_keymaps = []


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.pbs = PointerProperty(type=PBS_Settings)
    bpy.types.VIEW3D_MT_object.append(_menu)
    bpy.types.VIEW3D_MT_object_context_menu.append(_menu)
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="Object Mode", space_type='EMPTY')
        kmi = km.keymap_items.new(OP_ID, 'P', 'PRESS', shift=True, alt=True)
        _keymaps.append((km, kmi))


def unregister():
    for km, kmi in _keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    _keymaps.clear()
    bpy.types.VIEW3D_MT_object_context_menu.remove(_menu)
    bpy.types.VIEW3D_MT_object.remove(_menu)
    del bpy.types.Scene.pbs
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
