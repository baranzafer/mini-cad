# SPDX-License-Identifier: GPL-3.0-or-later
"""Ölç ve Ölçekle: iki nokta (izdüşümlü olabilir) arası ölçü -> seçimi hedefe ölçekle."""
import math

import bpy
from bpy.types import Operator
from mathutils import Matrix, Vector

from . import draw as D
from . import geom
from .common import (NAV_EVENTS, NUMPAD_CHARS, NUMPAD_NAV, PIVOT_LABEL, TYPE_CHARS,
                     first_window_region, frame_with_axis, region_under_mouse, resolve_pivot,
                     set_status, tag_redraw_all)
from .props import PIVOT_ORDER
from .scaling import Scaler
from .selection import Group, frame_for, group_box
from .snapping import KIND_LABEL, Snap, Snapper
from .units import UnitCtx, safe_parse_target

AXIS_NAMES = "XYZ"
PLANE_NAMES = ("YZ", "XZ", "XY")

SNAP_KEYS = [
    ('ONE', "snap_vert", "Köşe"), ('TWO', "snap_edge", "Kenar"), ('THREE', "snap_mid", "Orta"),
    ('FOUR', "snap_face", "Yüzey"), ('FIVE', "snap_box", "Kutu"), ('SIX', "snap_perp", "Dik"),
    ('SEVEN', "snap_face_center", "Yüz merk."), ('EIGHT', "snap_origin", "Köken"),
]


class Constraint:
    __slots__ = ("kind", "idx", "space", "vec", "color")

    def __init__(self, kind, idx, space, frame):
        self.kind = kind            # 'AXIS' | 'PLANE'
        self.idx = idx
        self.space = space          # 'GLOBAL' | 'LOCAL'
        self.vec = Matrix(frame).col[idx].normalized()
        self.color = D.COL_AXIS[idx]

    @property
    def label(self):
        n = AXIS_NAMES[self.idx] if self.kind == 'AXIS' else PLANE_NAMES[self.idx]
        sp = "yerel" if self.space == 'LOCAL' else "global"
        return f"{n} ({sp})" if self.kind == 'AXIS' else f"{n} düzlemi ({sp})"

    def apply(self, anchor, snap_co, ro, rd):
        a = Vector(anchor)
        d = self.vec
        if self.kind == 'AXIS':
            if snap_co is not None:
                return a + d * (Vector(snap_co) - a).dot(d)
            t = geom.closest_on_line_to_ray(a, d, ro, rd)
            return a + d * (t or 0.0)
        # düzlem: normal = vec
        if snap_co is not None:
            p = Vector(snap_co)
            return p - d * (p - a).dot(d)
        hit = geom.ray_plane(ro, rd, a, d)
        return hit if hit is not None else a.copy()


class Pt:
    """Seçilen nokta. obj+local varsa nesneyle birlikte hareket eder."""
    __slots__ = ("co", "kind", "obj", "local", "raw")

    def __init__(self, co, kind='FREE', obj=None, local=None, raw=None):
        self.co = Vector(co)
        self.kind = kind
        self.obj = obj
        self.local = Vector(local) if local is not None else None
        self.raw = raw            # izdüşüm öncesi yakalama (Pt) ya da None


class OU_OT_measure(Operator):
    bl_idname = "olcu.measure"
    bl_label = "Ölç ve Ölçekle"
    bl_description = ("İki nokta arasını ölç (köşe, kenar, yüzey, sınır kutusu, eksen/düzlem "
                      "izdüşümü) ve seçimi tek bütün olarak hedef boyuta ölçekle")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == 'VIEW_3D'

    # ================================================================ başlat
    def invoke(self, context, event):
        s = context.scene.olcu_ustasi
        self.s = s
        self.area = context.area
        self.prev_mode = None
        if context.mode != 'OBJECT' and context.active_object is not None:
            self.prev_mode = context.object.mode
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except RuntimeError:
                self.prev_mode = None
        self.group = Group(context.selected_objects, s.include_children)
        self.uctx = UnitCtx.from_settings(s, context.scene)
        self.frame = frame_for(s.box_space, self.group, context)
        self.box = None
        self.snapper = Snapper(context, s, self.group if self.group else None)
        self.snapper.xray = _xray(context)
        self._rebuild_box(context)
        self.scaler = Scaler(self.group) if self.group else None

        self.phase = 'A'
        self.A = self.B = self.C = self.D = None
        self.hover = None
        self.hover_raw = None
        self.hover_edge = None
        self.cons = None
        self.typed = ""
        self.error = ""
        self.pivot_mode = s.pivot
        self.axis_only = False
        self.apply_data = s.apply_data
        self.ref_len = None
        self.factor = None
        self.M = None
        self.ctrl = False
        self.view = None
        self.last_msgs = []
        self._fixed_scale = None

        args = (self, context)
        self._h3d = bpy.types.SpaceView3D.draw_handler_add(_draw_3d, args, 'WINDOW', 'POST_VIEW')
        self._h2d = bpy.types.SpaceView3D.draw_handler_add(_draw_2d, args, 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        self._update_hover(context, event)
        self._status(context)
        return {'RUNNING_MODAL'}

    def _rebuild_box(self, context):
        if self.group:
            dg = context.evaluated_depsgraph_get()
            self.box = group_box(dg, self.group.names, self.frame)
        else:
            self.box = None
        self.snapper.box = self.box
        self.snapper.invalidate()

    # ================================================================ yardımcı
    def _anchor(self):
        if self.phase == 'B':
            return self.A.co
        if self.phase == 'REF_D':
            return self.C.co
        return None

    def _update_hover(self, context, event):
        region, rv3d = region_under_mouse(self.area, event)
        if region is None:
            return False
        self.view = geom.View.from_region(region, rv3d)
        mx = event.mouse_x - region.x
        my = event.mouse_y - region.y
        anchor = self._anchor()
        ro, rd = self.view.ray(mx, my)
        snap = None
        if not self.ctrl:
            snap = self.snapper.find(context, self.view, mx, my, ref=anchor)
        else:
            h = self.snapper._cast(context.scene, context.evaluated_depsgraph_get(), ro, rd,
                                   self.s.snap_only_selection)
            if h is not None:
                loc, nor, idx, ob, M, is_inst = h
                snap = Snap(loc, 'FACE', None if is_inst else ob,
                            None if is_inst else M.inverted_safe() @ loc, nor)
        self.hover_edge = snap.edge if snap is not None else None
        raw = None
        if snap is not None:
            raw = Pt(snap.co, snap.kind, snap.obj, snap.local)
        if anchor is not None and self.cons is not None:
            co = self.cons.apply(anchor, snap.co if snap else None, ro, rd)
            kind = self.cons.kind if snap is None else snap.kind
            self.hover = Pt(co, kind, None, None, raw)
        elif raw is not None:
            self.hover = raw
        else:
            base = anchor
            if base is None:
                base = self.box.center if self.box is not None else context.scene.cursor.location
            p = geom.ray_plane(ro, rd, base, self.view.view_dir())
            self.hover = Pt(p if p is not None else base, 'FREE')
        self.hover_raw = raw
        return True

    def _measure_vec(self):
        if self.A is None or self.B is None:
            return None
        return self.B.co - self.A.co

    def _measured(self):
        v = self._measure_vec()
        return v.length if v is not None else 0.0

    def _cycle_cons(self, idx, plane):
        kind = 'PLANE' if plane else 'AXIS'
        c = self.cons
        local = frame_for('LOCAL', self.group, bpy.context) if self.group else None
        if c is None or c.kind != kind or c.idx != idx:
            self.cons = Constraint(kind, idx, 'GLOBAL', Matrix.Identity(3))
        elif c.space == 'GLOBAL' and local is not None:
            self.cons = Constraint(kind, idx, 'LOCAL', local)
        else:
            self.cons = None
        self.axis_only = self.axis_only and self.cons is not None and self.cons.kind == 'AXIS'

    def _pivot(self, context):
        return resolve_pivot(self.pivot_mode, context, self.box,
                             self.A.co if self.A else None, self.group)

    def _compute(self, context):
        """Yazılan hedeften çarpanı ve dönüşümü hesaplar; önizler."""
        self.error = ""
        self.factor = None
        self.M = None
        meas = self._measured()
        if self.ref_len is not None and not self.typed:
            res = ('LENGTH', self.ref_len)
        elif self.typed:
            res = safe_parse_target(self.typed, self.uctx)
            if res is None:
                self.error = "geçersiz değer"
        else:
            res = None
        if res is not None:
            kind, v = res
            f = v if kind == 'FACTOR' else (v / meas if meas > 1e-12 else None)
            if f is None or not (abs(f) > 1e-9):
                self.error = "sıfır olamaz"
            elif f < 0:
                self.error = "negatif çarpan"
            else:
                self.factor = f
        if self.factor is not None and self.scaler is not None:
            piv = self._pivot(context)
            if self.axis_only and self.cons is not None and self.cons.kind == 'AXIS':
                self.M = geom.axis_scale_matrix(piv, self.cons.vec, self.factor)
            else:
                self.M = geom.scale_matrix(piv, self.factor)
            if self.s.live_preview:
                self.scaler.preview(self.M)
        elif self.scaler is not None and self.scaler.current is not None:
            self.scaler.restore()

    def _restore_preview(self):
        if self.scaler is not None and self.scaler.current is not None:
            self.scaler.restore()

    def _back(self, context):
        if self.phase == 'TARGET':
            self._restore_preview()
            self.typed = ""
            self.ref_len = None
            self.B = None
            self.phase = 'B'
        elif self.phase == 'B':
            self.A = None
            self.cons = None
            self.phase = 'A'
        elif self.phase == 'REF_D':
            self.C = None
            self.phase = 'REF_C'
        elif self.phase == 'REF_C':
            self.phase = 'TARGET'
            self._compute(context)
        else:
            return False
        return True

    def _pin(self, context):
        if self.A is None or self.B is None:
            return
        pins = self.s.pins
        p = pins.add()
        a = self.A
        b = self.B.raw if (self.B.raw is not None and self.cons is not None) else self.B
        p.a_obj = a.obj if a.local is not None else None
        p.a_co = a.local if a.local is not None else a.co
        p.b_obj = b.obj if b.local is not None else None
        p.b_co = b.local if b.local is not None else b.co
        if self.cons is not None and self.B.raw is not None:
            p.mode = 'AXIS' if self.cons.kind == 'AXIS' else 'PLANE'
            p.axis = self.cons.vec
        self.s.pin_index = len(pins) - 1

    def _status(self, context):
        msg = {
            'A': "Ölç: ilk noktayı (A) tıkla",
            'B': "Ölç: ikinci noktayı (B) tıkla",
            'TARGET': "Hedef boyutu yaz → Enter",
            'REF_C': "Referans: ilk noktayı tıkla",
            'REF_D': "Referans: ikinci noktayı tıkla",
        }[self.phase]
        if self.phase in ('A', 'B', 'REF_C', 'REF_D'):
            st = ("Sol tık: nokta   X/Y/Z: eksen (2× yerel)   Shift+X/Y/Z: düzlem   "
                  "Ctrl: yapışma kapalı   1-8: yapışma türleri   S: yalnız seçim   "
                  "O: kutu yönü   Sağ tık/Geri: geri   Esc: çık")
        else:
            st = ("Değer: 4.5m · 450 · 1m 20cm · 150% · *2    Enter/Sol tık: uygula   "
                  "R: referansa eşitle   P: pivot   U: tek eksen   A: veriye uygula   "
                  "K: ölçüyü sabitle   Ctrl+C: kopyala   Geri: geri   Esc: iptal")
        set_status(context, self.area, msg, st)

    # ================================================================ modal
    def modal(self, context, event):
        try:
            return self._modal(context, event)
        except Exception:
            self._finish(context, cancel=True)
            raise

    def _modal(self, context, event):
        if self.area is None or not self.area.regions:
            return self._finish(context, cancel=True)
        et, ev = event.type, event.value
        typing = self.phase == 'TARGET'

        if et in NAV_EVENTS or (et in NUMPAD_NAV and not typing):
            return {'PASS_THROUGH'}
        if et in {'LEFT_CTRL', 'RIGHT_CTRL'}:
            self.ctrl = ev == 'PRESS'
            if not typing:
                self._update_hover(context, event)
                self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if et == 'MOUSEMOVE' or et == 'INBETWEEN_MOUSEMOVE':
            if et == 'INBETWEEN_MOUSEMOVE':
                return {'RUNNING_MODAL'}
            self.ctrl = event.ctrl
            region, _ = region_under_mouse(self.area, event)
            if region is None:
                return {'PASS_THROUGH'}
            if not typing:
                self._update_hover(context, event)
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}

        region, _ = region_under_mouse(self.area, event)
        if region is None and et not in {'ESC', 'RET', 'NUMPAD_ENTER'} and not typing:
            return {'PASS_THROUGH'}

        if ev == 'PRESS' and et in {'Z'} and event.ctrl:
            return {'RUNNING_MODAL'}            # modal sırasında geri alma yok

        if et == 'ESC' and ev == 'PRESS':
            return self._finish(context, cancel=True)

        if et == 'RIGHTMOUSE' and ev == 'PRESS':
            if not self._back(context):
                return self._finish(context, cancel=True)
            self._after_change(context, event)
            return {'RUNNING_MODAL'}

        if et == 'BACK_SPACE' and ev == 'PRESS':
            if typing and self.typed:
                self.typed = "" if event.ctrl else self.typed[:-1]
                self._compute(context)
            elif not self._back(context):
                return self._finish(context, cancel=True)
            self._after_change(context, event)
            return {'RUNNING_MODAL'}

        if typing:
            return self._modal_target(context, event)
        return self._modal_pick(context, event)

    def _after_change(self, context, event):
        if self.phase != 'TARGET':
            self._update_hover(context, event)
        self._status(context)
        self.area.tag_redraw()

    def _modal_pick(self, context, event):
        et, ev = event.type, event.value
        if ev != 'PRESS':
            return {'RUNNING_MODAL'}
        s = self.s
        if et in {'LEFTMOUSE', 'RET', 'NUMPAD_ENTER', 'SPACE'}:
            self._update_hover(context, event)
            h = self.hover
            if h is None:
                return {'RUNNING_MODAL'}
            if self.phase == 'A':
                self.A = h
                self.phase = 'B'
            elif self.phase == 'B':
                if (h.co - self.A.co).length < 1e-9:
                    self.report({'INFO'}, "İkinci nokta birinciyle aynı")
                    return {'RUNNING_MODAL'}
                self.B = h
                self.phase = 'TARGET'
                self.typed = ""
                self.ref_len = None
                v = self._measured()
                s.last_value = v
                s.last_text = self.uctx.fmt(v)
                if not self.group:
                    self.report({'INFO'}, f"Ölçüm: {self.uctx.fmt(v)}")
                self._compute(context)
            elif self.phase == 'REF_C':
                self.C = h
                self.phase = 'REF_D'
            elif self.phase == 'REF_D':
                if (h.co - self.C.co).length < 1e-9:
                    return {'RUNNING_MODAL'}
                self.D = h
                self.ref_len = (self.D.co - self.C.co).length
                self.typed = ""
                self.phase = 'TARGET'
                self._compute(context)
            self._after_change(context, event)
            return {'RUNNING_MODAL'}

        if et in {'X', 'Y', 'Z'}:
            if self._anchor() is not None:
                self._cycle_cons("XYZ".index(et), event.shift)
                self._update_hover(context, event)
                self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        for key, attr, _lab in SNAP_KEYS:
            if et == key:
                setattr(s, attr, not getattr(s, attr))
                self.snapper.invalidate()
                self._update_hover(context, event)
                self.area.tag_redraw()
                return {'RUNNING_MODAL'}
        if et == 'S':
            s.snap_only_selection = not s.snap_only_selection
            self.snapper.invalidate()
            self._update_hover(context, event)
        elif et == 'O' and self.group:
            s.box_space = 'LOCAL' if s.box_space == 'WORLD' else 'WORLD'
            self.frame = frame_for(s.box_space, self.group, context)
            self._rebuild_box(context)
            self._update_hover(context, event)
        self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _modal_target(self, context, event):
        et, ev = event.type, event.value
        if ev != 'PRESS':
            return {'RUNNING_MODAL'}
        if et in {'RET', 'NUMPAD_ENTER', 'LEFTMOUSE'}:
            if et == 'LEFTMOUSE':
                region, _ = region_under_mouse(self.area, event)
                if region is None:
                    return {'PASS_THROUGH'}
            return self._confirm(context)
        if et == 'C' and event.ctrl:
            txt = self.uctx.fmt(self._measured())
            context.window_manager.clipboard = txt
            self.report({'INFO'}, f"Panoya kopyalandı: {txt}")
            return {'RUNNING_MODAL'}
        if et == 'V' and event.ctrl:
            clip = context.window_manager.clipboard.strip()
            if clip and len(clip) < 64:
                self.typed += clip
                self._compute(context)
                self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        ch = NUMPAD_CHARS.get(et)
        if ch is None and event.unicode:
            ch = event.unicode.lower()
            if event.ctrl or event.alt or event.oskey:
                ch = None
        cmd_letters = {'p', 'u', 'r', 'a'} | ({'k'} if not self.typed else set())
        if ch and ch in cmd_letters:
            if ch == 'p':
                i = PIVOT_ORDER.index(self.pivot_mode) if self.pivot_mode in PIVOT_ORDER else 0
                self.pivot_mode = PIVOT_ORDER[(i + 1) % len(PIVOT_ORDER)]
            elif ch == 'u':
                if self.cons is not None and self.cons.kind == 'AXIS':
                    self.axis_only = not self.axis_only
                else:
                    self.report({'INFO'}, "Tek eksen ölçeği için ölçümü X/Y/Z kilidiyle yap")
            elif ch == 'a':
                self.apply_data = not self.apply_data
            elif ch == 'r':
                self._restore_preview()
                self.C = self.D = None
                self.phase = 'REF_C'
                self._after_change(context, event)
                return {'RUNNING_MODAL'}
            elif ch == 'k':
                self._pin(context)
                self._restore_preview()
                self.report({'INFO'}, "Ölçü sabitlendi")
                self.A = self.B = None
                self.cons = None
                self.phase = 'A'
                self._after_change(context, event)
                return {'RUNNING_MODAL'}
            self._compute(context)
            self._status(context)
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if ch and (ch in TYPE_CHARS or (ch == 'x' and not self.typed)):
            self.typed += ch
            self.ref_len = None
            self._compute(context)
            self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    # ================================================================ bitir
    def _confirm(self, context):
        s = self.s
        if self.factor is None or self.scaler is None:
            if self.typed or self.ref_len is not None:
                if self.scaler is None:
                    self.report({'WARNING'}, "Ölçeklemek için nesne seç")
                else:
                    self.report({'WARNING'}, f"Değer anlaşılamadı: {self.typed}")
                return {'RUNNING_MODAL'}
            self.report({'INFO'}, f"Ölçüm: {self.uctx.fmt(self._measured())}")
            return self._finish(context, cancel=False)
        piv = self._pivot(context)
        frame = Matrix.Identity(3)
        if self.axis_only and self.cons is not None:
            frame = frame_with_axis(self.cons.vec)
        msgs, _emp = self.scaler.finalize(context, self.M, frame=frame, pivot=piv,
                                          apply_data=self.apply_data)
        meas = self._measured()
        s.last_value = meas * self.factor
        s.last_text = self.uctx.fmt(meas * self.factor)
        n = len(self.group.roots)
        head = f"×{self.factor:.6g} ölçeklendi ({n} kök nesne) · ölçü {self.uctx.fmt(meas)} → " \
               f"{self.uctx.fmt(meas * self.factor)}"
        self.report({'INFO'}, " | ".join([head] + msgs))
        return self._finish(context, cancel=False, keep=True)

    def _finish(self, context, cancel=True, keep=False):
        if cancel or not keep:
            self._restore_preview()
        for h in ("_h3d", "_h2d"):
            hd = getattr(self, h, None)
            if hd is not None:
                try:
                    bpy.types.SpaceView3D.draw_handler_remove(hd, 'WINDOW')
                except (ValueError, ReferenceError):
                    pass
                setattr(self, h, None)
        set_status(context, self.area, None, None)
        if self.prev_mode and self.prev_mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode=self.prev_mode)
            except RuntimeError:
                pass
        tag_redraw_all(context)
        return {'CANCELLED'} if cancel else {'FINISHED'}


def _xray(context):
    try:
        return bool(context.space_data.shading.show_xray)
    except AttributeError:
        return False


# ===================================================================== çizim

def _xf(op, pt):
    """Önizlemede, seçime ait noktalar modelle birlikte hareket eder."""
    if pt is None:
        return None
    co = pt.co
    if op.scaler is not None and op.scaler.current is not None and pt.obj is not None \
            and op.group.contains(pt.obj):
        return op.scaler.current @ co
    if op.scaler is not None and op.scaler.current is not None and pt.kind.startswith('BOX'):
        return op.scaler.current @ co
    return co


def _draw_3d(op, context):
    try:
        if context.area != op.area:
            return
        _draw_3d_impl(op, context)
    except ReferenceError:
        pass


def _draw_3d_impl(op, context):
    s = op.s
    with D.State():
        box = op.box
        if box is not None and s.show_box:
            if op.scaler is not None and op.scaler.current is not None:
                box = box.transformed(op.scaler.current)
            D.lines(D.box_lines(box), D.COL_BOX, 1.5)
        hb = op.snapper.hover_box
        if hb is not None and op.phase != 'TARGET' and s.snap_box and hb is not op.box:
            D.lines(D.box_lines(hb), D.COL_BOX_HOVER, 1.0)
        anchor = op._anchor()
        if op.cons is not None and anchor is not None:
            L = 1e4
            col = op.cons.color
            if op.cons.kind == 'AXIS':
                D.lines([anchor - op.cons.vec * L, anchor + op.cons.vec * L],
                        (col[0], col[1], col[2], 0.6), 1.5)
            else:
                f = frame_with_axis(op.cons.vec)
                u, v = f.col[1], f.col[2]
                g = []
                for k in range(-5, 6):
                    sz = op.view.pixel_size_at(anchor) * 40 if op.view else 0.2
                    g += [anchor + u * k * sz - v * 5 * sz, anchor + u * k * sz + v * 5 * sz,
                          anchor + v * k * sz - u * 5 * sz, anchor + v * k * sz + u * 5 * sz]
                D.lines(g, (col[0], col[1], col[2], 0.25), 1.0)
        if op.hover_edge is not None and op.phase != 'TARGET':
            D.lines(list(op.hover_edge), D.KIND_COLOR['EDGE'], 3.0)
        # ölçü çizgileri
        A, B = _xf(op, op.A), _xf(op, op.B)
        if A is not None:
            end = B if B is not None else (op.hover.co if op.hover and op.phase == 'B' else None)
            if end is not None:
                col = op.cons.color if (op.cons is not None and B is None) else D.COL_MEASURE
                D.lines([A, end], col, 2.5)
        if op.phase in ('REF_C', 'REF_D', 'TARGET') and op.C is not None:
            C = op.C.co
            end = op.D.co if op.D is not None else (op.hover.co if op.hover else None)
            if end is not None:
                D.lines([C, end], D.COL_REF, 2.5)
        if op.hover is not None and op.hover.raw is not None and op.phase in ('B', 'REF_D'):
            D.dashed(op.hover.raw.co, op.hover.co, (1, 1, 1, 0.5), 1.0, 16)
        if op.B is not None and op.B.raw is not None:
            D.dashed(_xf(op, op.B.raw) or op.B.raw.co, B, (1, 1, 1, 0.35), 1.0, 16)


def _draw_2d(op, context):
    try:
        if context.area != op.area:
            return
        _draw_2d_impl(op, context)
    except ReferenceError:
        pass


def _p2(view, co):
    return view.project(co) if co is not None else None


def _draw_2d_impl(op, context):
    region = context.region
    rv3d = context.region_data
    if region is None or rv3d is None:
        return
    view = geom.View.from_region(region, rv3d)
    u = op.uctx
    s = op.s
    with D.State():
        # pinler bu araçta da görünsün diye ayrı işleyici çizer
        A, B = _xf(op, op.A), _xf(op, op.B)
        if op.hover is not None and op.phase != 'TARGET':
            hp = _p2(view, op.hover.co)
            kind = op.hover.kind
            if op.hover.raw is not None and op.phase in ('B', 'REF_D'):
                D.marker(op.hover.raw.kind, _p2(view, op.hover.raw.co), size=5)
                D.point(hp, op.cons.color if op.cons else D.COL_TEXT, 3.5)
            else:
                D.marker(kind, hp)
            if hp is not None:
                lab = KIND_LABEL.get(op.hover.raw.kind if op.hover.raw else kind, kind)
                if op.cons is not None and op.phase in ('B', 'REF_D'):
                    lab += f" → {op.cons.label}"
                if op.ctrl:
                    lab += "  (yapışma kapalı)"
                D.text(hp.x + 14, hp.y + 10, lab, 11, D.COL_DIM, (0, 0, 0, 0.5), 3)
        for pt, name in ((A, "A"), (B, "B")):
            p = _p2(view, pt)
            if p is not None:
                D.point(p, D.COL_MEASURE, 4.5)
                D.text(p.x - 14, p.y + 8, name, 12, D.COL_MEASURE, None)
        anchor_end = B if B is not None else (op.hover.co if op.hover and op.phase == 'B' else None)
        if A is not None and anchor_end is not None:
            pa, pb = _p2(view, A), _p2(view, anchor_end)
            if pa is not None and pb is not None:
                mid = (pa + pb) * 0.5
                vec = anchor_end - A
                txt = u.fmt(vec.length)
                if op.phase == 'TARGET' and op.factor is not None:
                    orig = op._measured()
                    txt = f"{u.fmt(orig)}  →  {u.fmt(orig * op.factor)}"
                D.text(mid.x, mid.y + 12, txt, 15, D.COL_MEASURE, D.COL_BG, 5, 'CENTER')
        if op.C is not None:
            C = op.C.co
            end = op.D.co if op.D is not None else (op.hover.co if op.hover and op.phase == 'REF_D' else None)
            pc = _p2(view, C)
            if pc is not None:
                D.point(pc, D.COL_REF, 4)
            if end is not None:
                pd = _p2(view, end)
                if pc is not None and pd is not None:
                    D.point(pd, D.COL_REF, 4)
                    mid = (pc + pd) * 0.5
                    D.text(mid.x, mid.y + 12, "Ref " + u.fmt((end - C).length), 13, D.COL_REF,
                           D.COL_BG, 4, 'CENTER')
        _hud(op, context, region, u, s)


def _hud(op, context, region, u, s):
    x = 20 * D.ui_scale()
    y = 30 * D.ui_scale()
    lh = 22 * D.ui_scale()
    rows = []
    vec = None
    if op.A is not None:
        end = op.B.co if op.B is not None else (op.hover.co if op.hover and op.phase == 'B' else None)
        if end is not None:
            vec = end - op.A.co
    if op.phase == 'TARGET':
        tv = op.typed if op.typed else (f"= ref {u.fmt(op.ref_len)}" if op.ref_len else "")
        parts = [("Hedef: ", D.COL_DIM), (tv + "▏", D.COL_TEXT)]
        if op.error:
            parts.append(("   " + op.error, D.COL_X))
        elif op.factor is not None:
            parts.append((f"   ×{op.factor:.5g}", D.COL_MEASURE))
        if not op.typed and op.ref_len is None:
            parts.append(("   (örn. 4.5m · 450 · 150% · *2)", D.COL_DIM))
        rows.append(parts)
        mode = "Tek eksen " + AXIS_NAMES[op.cons.idx] if (op.axis_only and op.cons) else "Eşit (oranlı)"
        rows.append([("Pivot [P]: ", D.COL_DIM), (PIVOT_LABEL.get(op.pivot_mode, ""), D.COL_TEXT),
                     ("   Mod [U]: ", D.COL_DIM), (mode, D.COL_TEXT),
                     ("   Veriye uygula [A]: ", D.COL_DIM),
                     ("açık" if op.apply_data else "kapalı",
                      D.COL_Y if op.apply_data else D.COL_DIM)])
        if not op.group:
            rows.append([("Seçim yok: yalnızca ölçüm", D.COL_X)])
    else:
        flags = []
        for key, attr, lab in SNAP_KEYS:
            on = getattr(s, attr)
            n = "12345678"[[k for k, _a, _l in SNAP_KEYS].index(key)]
            flags.append((f"{n}·{lab}  ", D.COL_Y if on else (0.45, 0.45, 0.48, 1)))
        flags.append(("S·Yalnız seçim" if s.snap_only_selection else "S·Tüm sahne", D.COL_TEXT))
        flags.append((f"   O·Kutu: {'Yerel' if s.box_space == 'LOCAL' else 'Dünya'}", D.COL_TEXT))
        rows.append(flags)
        if op.cons is not None:
            rows.append([("Kilit: ", D.COL_DIM), (op.cons.label, op.cons.color)])
    if vec is not None:
        loc = op.cons is not None and op.cons.space == 'LOCAL'
        F = frame_for('LOCAL', op.group, context) if (loc and op.group) else Matrix.Identity(3)
        lv = F.transposed() @ vec
        horiz = Vector((vec.x, vec.y)).length
        ang = math.degrees(math.atan2(vec.z, horiz)) if vec.length > 1e-12 else 0.0
        rows.append([("Mesafe ", D.COL_DIM), (u.fmt(vec.length) + "   ", D.COL_MEASURE),
                     ("Δx ", D.COL_X), (u.fmt(abs(lv.x)) + "  ", D.COL_TEXT),
                     ("Δy ", D.COL_Y), (u.fmt(abs(lv.y)) + "  ", D.COL_TEXT),
                     ("Δz ", D.COL_Z), (u.fmt(abs(lv.z)) + "  ", D.COL_TEXT),
                     (f"eğim {ang:+.1f}°", D.COL_DIM)])
    if op.box is not None:
        sz = op.box.size
        if op.scaler is not None and op.scaler.current is not None:
            sz = op.box.transformed(op.scaler.current).size
        rows.append([("Seçim kutusu  ", D.COL_DIM), (u.fmt(sz.x), D.COL_X), (" × ", D.COL_DIM),
                     (u.fmt(sz.y), D.COL_Y), (" × ", D.COL_DIM), (u.fmt(sz.z), D.COL_Z),
                     (f"   ({len(op.group.objects)} nesne)", D.COL_DIM)])
    title = {"A": "A noktası", "B": "B noktası", "TARGET": "Hedef boyut",
             "REF_C": "Referans C", "REF_D": "Referans D"}[op.phase]
    rows.append([("ÖLÇÜ USTASI  ", D.COL_MEASURE), (title, D.COL_TEXT)])
    for i, parts in enumerate(rows):
        D.rich_line(x, y + i * lh, parts, 12)
