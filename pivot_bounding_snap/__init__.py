"""Pivot Bounding Snap

Seçili nesnenin / çoklu seçimin bounding box'unu görünümde çizer. İmleç kutunun etrafında
serbestçe gezdirilir (yüzeyler ve kenarlar üzerinde kayar); köşelere, kenar ortalarına,
yüz merkezlerine ve kutu merkezine yakalanır. Tıklanan nokta yeni pivot olur.

Çoklu seçimde hedef kipleri:
  ORTAK    : bütün nesnelerin pivotu aynı dünya noktasına taşınır
  KENDİ    : noktanın ana kutudaki göreli konumu (ör. sağ-alt kenar ortası) her nesnenin
             kendi bounding box'una uygulanır
  İMLEÇ    : yalnızca 3D imleç o noktaya konur

Tuşlar (modal):
  Sol tık / Enter  : uygula        Sağ tık / Esc : iptal
  Ctrl (basılı)    : yakalamayı geçici kapat (tam serbest)
  S                : yakalama aç / kapa
  M                : hedef kipi değiştir (Ortak / Kendi / İmleç)
  W                : kutu yönü (Yerel = etkin nesnenin dönüşü / Dünya)
"""

import bpy
import blf
import gpu
from bpy.props import EnumProperty, BoolProperty, FloatProperty
from gpu_extras.batch import batch_for_shader
from mathutils import Matrix, Vector
from mathutils.geometry import intersect_line_line
from bpy_extras import view3d_utils

MODES = [
    ('SHARED', "Ortak", "Bütün nesnelere aynı pivot noktası"),
    ('INDIVIDUAL', "Kendi Kutusu", "Aynı göreli konum her nesnenin kendi bounding box'unda"),
    ('CURSOR', "3D İmleç", "Yalnızca 3D imleci o noktaya koy"),
]
SPACES = [
    ('LOCAL', "Yerel", "Kutu etkin nesnenin dönüşüne hizalı"),
    ('WORLD', "Dünya", "Kutu dünya eksenlerine hizalı"),
]

# 8 köşe (x,y,z ∈ {0,1}) ve 12 kenar: köşe indeksleri
_CORNERS = [Vector((x, y, z)) for x in (0, 1) for y in (0, 1) for z in (0, 1)]
_EDGES = [(a, b) for a in range(8) for b in range(a + 1, 8)
          if sum(1 for k in range(3) if _CORNERS[a][k] != _CORNERS[b][k]) == 1]


def _snap_uvws():
    """Göreli (0..1) yakalama noktaları ve türleri."""
    pts = [(c.copy(), "Köşe") for c in _CORNERS]
    pts += [((_CORNERS[a] + _CORNERS[b]) * 0.5, "Kenar ortası") for a, b in _EDGES]
    for k in range(3):
        for v in (0.0, 1.0):
            p = Vector((0.5, 0.5, 0.5))
            p[k] = v
            pts.append((p, "Yüz merkezi"))
    pts.append((Vector((0.5, 0.5, 0.5)), "Merkez"))
    return pts


_SNAPS = _snap_uvws()


def _world_corners(ob):
    mw = ob.matrix_world
    return [mw @ Vector(c) for c in ob.bound_box]


def _aabb(points):
    lo = Vector((min(p[i] for p in points) for i in range(3)))
    hi = Vector((max(p[i] for p in points) for i in range(3)))
    return lo, hi


class Box:
    """frame (dönüş+konum, ölçeksiz) uzayında lo..hi kutusu."""

    def __init__(self, frame, lo, hi):
        self.frame, self.lo, self.hi = frame, lo, hi

    def at(self, uvw):
        size = self.hi - self.lo
        local = Vector(self.lo[i] + uvw[i] * size[i] for i in range(3))
        return self.frame @ local

    def uvw(self, world):
        local = self.frame.inverted_safe() @ world
        size = self.hi - self.lo
        return Vector(((local[i] - self.lo[i]) / size[i]) if abs(size[i]) > 1e-12 else 0.5
                      for i in range(3))

    def corners(self):
        return [self.at(c) for c in _CORNERS]

    def ray_hit(self, o, d):
        """Işının kutu yüzeyine ilk değdiği dünya noktası (yoksa None)."""
        inv = self.frame.inverted_safe()
        o2 = inv @ o
        d2 = inv.to_3x3() @ d
        eps = 1e-6
        t0, t1 = -1e30, 1e30
        for i in range(3):
            lo, hi = self.lo[i] - eps, self.hi[i] + eps
            if abs(d2[i]) < 1e-12:
                if o2[i] < lo or o2[i] > hi:
                    return None
                continue
            a, b = (lo - o2[i]) / d2[i], (hi - o2[i]) / d2[i]
            if a > b:
                a, b = b, a
            t0, t1 = max(t0, a), min(t1, b)
            if t0 > t1:
                return None
        t = t0 if t0 > 0 else t1
        if t <= 0:
            return None
        return self.frame @ (o2 + d2 * t)


def object_box(ob, space):
    if space == 'LOCAL':
        # nesnenin kendi uzayı (ölçek dahil): matrix_world'ü dönüş+konum ve ölçek olarak ayır
        loc, rot, sca = ob.matrix_world.decompose()
        frame = Matrix.Translation(loc) @ rot.to_matrix().to_4x4()
        pts = [Vector(c) for c in ob.bound_box]
        pts = [Vector((p.x * sca.x, p.y * sca.y, p.z * sca.z)) for p in pts]
        lo, hi = _aabb(pts)
        return Box(frame, lo, hi)
    lo, hi = _aabb(_world_corners(ob))
    return Box(Matrix.Identity(4), lo, hi)


def group_box(objs, active, space):
    if space == 'LOCAL' and active is not None:
        loc, rot, _s = active.matrix_world.decompose()
        frame = Matrix.Translation(loc) @ rot.to_matrix().to_4x4()
    else:
        frame = Matrix.Identity(4)
    inv = frame.inverted_safe()
    pts = [inv @ p for ob in objs for p in _world_corners(ob)]
    lo, hi = _aabb(pts)
    return Box(frame, lo, hi)


class PBS_OT_pivot_bounding_snap(bpy.types.Operator):
    """Bounding box üzerinde imleçle yeni pivot belirle (köşe / kenar ortası yakalamalı)"""
    bl_idname = "object.pivot_bounding_snap"
    bl_label = "Pivot Bounding Snap"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(name="Hedef", items=MODES, default='SHARED')
    space: EnumProperty(name="Kutu Yönü", items=SPACES, default='LOCAL')
    snap: BoolProperty(name="Yakalama", default=True)
    snap_px: FloatProperty(name="Yakalama Mesafesi (px)", default=18.0, min=2.0, max=100.0)

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D'
                and context.mode == 'OBJECT' and len(context.selected_objects) > 0)

    # ---------- kurulum ----------
    def invoke(self, context, event):
        st = context.window_manager.pbs_settings
        self.mode, self.space, self.snap = st.mode, st.space, st.snap
        self.objs = list(context.selected_objects)
        self.active = context.active_object if context.active_object in self.objs else self.objs[0]
        self.point = None
        self.label = ""
        self.ctrl = False
        self._rebuild()
        args = (context,)
        self._h3d = bpy.types.SpaceView3D.draw_handler_add(self._draw_3d, args, 'WINDOW', 'POST_VIEW')
        self._h2d = bpy.types.SpaceView3D.draw_handler_add(self._draw_2d, args, 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        self._update(context, event)
        return {'RUNNING_MODAL'}

    def _rebuild(self):
        self.box = group_box(self.objs, self.active, self.space)
        self.own = [object_box(ob, self.space) for ob in self.objs]

    def _cleanup(self, context):
        bpy.types.SpaceView3D.draw_handler_remove(self._h3d, 'WINDOW')
        bpy.types.SpaceView3D.draw_handler_remove(self._h2d, 'WINDOW')
        context.area.header_text_set(None)
        context.area.tag_redraw()

    # ---------- imleç → nokta ----------
    def _update(self, context, event):
        region, rv3d = context.region, context.region_data
        mouse = Vector((event.mouse_region_x, event.mouse_region_y))
        o = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse)
        d = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse)

        def px(p):
            q = view3d_utils.location_3d_to_region_2d(region, rv3d, p)
            return (q - mouse).length if q is not None else 1e9

        use_snap = self.snap and not self.ctrl
        # 1) köşe / kenar ortası / yüz merkezi / merkez
        if use_snap:
            best = None
            for uvw, kind in _SNAPS:
                p = self.box.at(uvw)
                dist = px(p)
                # köşe ve kenar ortalarına öncelik: yüz/merkez biraz daha dar yakalanır
                lim = self.snap_px if kind in ("Köşe", "Kenar ortası") else self.snap_px * 0.7
                if dist < lim and (best is None or dist < best[0]):
                    best = (dist, p, kind)
            if best:
                self.point, self.label = best[1], best[2]
                return

        # kenarlar üzerindeki en yakın nokta (ışın–doğru)
        cs = self.box.corners()
        edge_best = None
        for a, b in _EDGES:
            A, B = cs[a], cs[b]
            if (B - A).length < 1e-12:
                q = A
            else:
                r = intersect_line_line(o, o + d, A, B)
                if r is None:
                    continue
                q = r[1]
                ab = B - A
                t = max(0.0, min(1.0, (q - A).dot(ab) / ab.length_squared))
                q = A + ab * t
            dist = px(q)
            if edge_best is None or dist < edge_best[0]:
                edge_best = (dist, q)

        # 2) kenara yakınsa kenar boyunca kay
        if edge_best and edge_best[0] < self.snap_px * 0.5:
            self.point, self.label = edge_best[1], "Kenar"
            return
        # 3) kutu yüzeyi üzerinde serbest
        hit = self.box.ray_hit(o, d)
        if hit is not None:
            self.point, self.label = hit, "Yüzey (serbest)"
            return
        # 4) kutunun dışında: en yakın kenar noktası
        if edge_best:
            self.point, self.label = edge_best[1], "Kenar (serbest)"

    def _targets(self):
        """[(nesne, dünya noktası)] — kipe göre her nesnenin yeni pivotu."""
        if self.point is None:
            return []
        if self.mode == 'INDIVIDUAL' and len(self.objs) > 1:
            uvw = self.box.uvw(self.point)
            uvw = Vector(max(0.0, min(1.0, c)) for c in uvw)
            return [(ob, bx.at(uvw)) for ob, bx in zip(self.objs, self.own)]
        return [(ob, self.point.copy()) for ob in self.objs]

    def _header(self, context):
        mode = dict((k, n) for k, n, _ in MODES)[self.mode]
        space = dict((k, n) for k, n, _ in SPACES)[self.space]
        snap = "Kapalı" if (not self.snap or self.ctrl) else "Açık"
        context.area.header_text_set(
            f"Pivot: {self.label}   |   [M] Hedef: {mode}   [W] Kutu: {space}   "
            f"[S] Yakalama: {snap} (Ctrl: geçici serbest)   |   Sol tık/Enter: uygula   Sağ tık/Esc: iptal")

    # ---------- modal ----------
    def modal(self, context, event):
        context.area.tag_redraw()
        if event.type in {'LEFT_CTRL', 'RIGHT_CTRL'}:
            self.ctrl = event.value == 'PRESS'
            self._update(context, event)
        elif event.type == 'MOUSEMOVE':
            self.ctrl = event.ctrl
            self._update(context, event)
        elif event.value == 'PRESS' and event.type == 'M':
            keys = [m[0] for m in MODES]
            self.mode = keys[(keys.index(self.mode) + 1) % len(keys)]
            context.window_manager.pbs_settings.mode = self.mode
        elif event.value == 'PRESS' and event.type == 'W':
            self.space = 'WORLD' if self.space == 'LOCAL' else 'LOCAL'
            context.window_manager.pbs_settings.space = self.space
            self._rebuild()
            self._update(context, event)
        elif event.value == 'PRESS' and event.type == 'S':
            self.snap = not self.snap
            context.window_manager.pbs_settings.snap = self.snap
            self._update(context, event)
        elif event.value == 'PRESS' and event.type in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER'}:
            self._cleanup(context)
            if self.point is None:
                return {'CANCELLED'}
            self._apply(context)
            return {'FINISHED'}
        elif event.value == 'PRESS' and event.type in {'RIGHTMOUSE', 'ESC'}:
            self._cleanup(context)
            return {'CANCELLED'}
        elif event.type in {'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE'} or event.type.startswith('NUMPAD_'):
            return {'PASS_THROUGH'}  # görünümü döndürme / yakınlaştırma serbest
        self._header(context)
        return {'RUNNING_MODAL'}

    # ---------- uygula ----------
    def _apply(self, context):
        cursor = context.scene.cursor
        if self.mode == 'CURSOR':
            cursor.location = self.point
            self.report({'INFO'}, "3D imleç pivot noktasına kondu")
            return
        saved = cursor.matrix.copy()
        done, failed = 0, 0
        for ob, p in self._targets():
            cursor.location = p
            try:
                with context.temp_override(selected_editable_objects=[ob], selected_objects=[ob],
                                           active_object=ob, object=ob):
                    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
                done += 1
            except RuntimeError:
                failed += 1
        cursor.matrix = saved
        msg = f"{done} nesnenin pivotu ayarlandı"
        if failed:
            msg += f", {failed} nesne atlandı (çok kullanıcılı / kilitli veri)"
        self.report({'WARNING'} if failed else {'INFO'}, msg)

    # ---------- çizim ----------
    def _lines(self, box):
        cs = box.corners()
        return [p for a, b in _EDGES for p in (cs[a], cs[b])]

    def _draw_3d(self, context):
        region = context.region
        gpu.state.depth_test_set('NONE')
        gpu.state.blend_set('ALPHA')
        line = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        line.bind()
        line.uniform_float("viewportSize", (region.width, region.height))

        multi = len(self.objs) > 1
        if multi:  # nesnelerin kendi kutuları (soluk)
            line.uniform_float("lineWidth", 1.0)
            line.uniform_float("color", (0.6, 0.8, 1.0, 0.35))
            pts = [p for bx in self.own for p in self._lines(bx)]
            batch_for_shader(line, 'LINES', {"pos": pts}).draw(line)
        line.uniform_float("lineWidth", 2.0)
        line.uniform_float("color", (1.0, 0.65, 0.1, 0.9))
        batch_for_shader(line, 'LINES', {"pos": self._lines(self.box)}).draw(line)

        pt = gpu.shader.from_builtin('UNIFORM_COLOR')
        pt.bind()
        snaps = [self.box.at(u) for u, k in _SNAPS if k in ("Köşe", "Kenar ortası")]
        gpu.state.point_size_set(6.0)
        pt.uniform_float("color", (1.0, 1.0, 1.0, 0.8))
        batch_for_shader(pt, 'POINTS', {"pos": snaps}).draw(pt)
        others = [self.box.at(u) for u, k in _SNAPS if k not in ("Köşe", "Kenar ortası")]
        gpu.state.point_size_set(4.0)
        pt.uniform_float("color", (0.8, 0.8, 0.8, 0.5))
        batch_for_shader(pt, 'POINTS', {"pos": others}).draw(pt)

        if self.point is not None:
            if multi and self.mode == 'INDIVIDUAL':
                gpu.state.point_size_set(8.0)
                pt.uniform_float("color", (0.3, 0.9, 1.0, 1.0))
                batch_for_shader(pt, 'POINTS', {"pos": [p for _o, p in self._targets()]}).draw(pt)
            gpu.state.point_size_set(12.0)
            pt.uniform_float("color", (0.2, 1.0, 0.3, 1.0))
            batch_for_shader(pt, 'POINTS', {"pos": [self.point]}).draw(pt)

        gpu.state.point_size_set(1.0)
        gpu.state.blend_set('NONE')

    def _draw_2d(self, context):
        if self.point is None:
            return
        q = view3d_utils.location_3d_to_region_2d(context.region, context.region_data, self.point)
        if q is None:
            return
        font = 0
        blf.size(font, 13)
        blf.color(font, 1.0, 1.0, 1.0, 0.95)
        blf.position(font, q.x + 12, q.y + 10, 0)
        blf.draw(font, self.label)


class PBS_Settings(bpy.types.PropertyGroup):
    mode: EnumProperty(name="Hedef", items=MODES, default='SHARED')
    space: EnumProperty(name="Kutu Yönü", items=SPACES, default='LOCAL')
    snap: BoolProperty(name="Yakalama", default=True)


class PBS_PT_panel(bpy.types.Panel):
    bl_label = "Pivot Bounding Snap"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Pivot"

    def draw(self, context):
        st = context.window_manager.pbs_settings
        col = self.layout.column()
        col.prop(st, "mode", text="Hedef")
        col.prop(st, "space", text="Kutu")
        col.prop(st, "snap")
        col.separator()
        col.operator(PBS_OT_pivot_bounding_snap.bl_idname, icon='PIVOT_BOUNDBOX')


def _menu(self, context):
    self.layout.separator()
    self.layout.operator(PBS_OT_pivot_bounding_snap.bl_idname, icon='PIVOT_BOUNDBOX')


_classes = (PBS_Settings, PBS_OT_pivot_bounding_snap, PBS_PT_panel)
_keymaps = []


def register():
    for c in _classes:
        bpy.utils.register_class(c)
    bpy.types.WindowManager.pbs_settings = bpy.props.PointerProperty(type=PBS_Settings)
    bpy.types.VIEW3D_MT_object.append(_menu)
    bpy.types.VIEW3D_MT_object_context_menu.append(_menu)
    kc = bpy.context.window_manager.keyconfigs.addon
    if kc:  # Nesne kipinde Ctrl+Alt+Shift+P
        km = kc.keymaps.new(name="Object Mode", space_type='EMPTY')
        kmi = km.keymap_items.new(PBS_OT_pivot_bounding_snap.bl_idname, 'P', 'PRESS',
                                  ctrl=True, alt=True, shift=True)
        _keymaps.append((km, kmi))


def unregister():
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()
    bpy.types.VIEW3D_MT_object_context_menu.remove(_menu)
    bpy.types.VIEW3D_MT_object.remove(_menu)
    del bpy.types.WindowManager.pbs_settings
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)
