# SPDX-License-Identifier: GPL-3.0-or-later
"""Kutu ile Ölçekle: seçimin sınır kutusu tutamaçlarından sürükle / değer yaz."""
import bpy
from bpy.types import Operator
from mathutils import Matrix, Vector

from . import draw as D
from . import geom
from .common import (NAV_EVENTS, NUMPAD_CHARS, NUMPAD_NAV, TYPE_CHARS, region_under_mouse,
                     set_status, tag_redraw_all)
from .scaling import Scaler
from .selection import Group, frame_for, group_box
from .snapping import Snapper
from .units import UnitCtx, safe_parse_target

AX = "XYZ"


def _up_axis(box):
    best, bz, sign = 2, -1.0, 1.0
    for i in range(3):
        z = box.frame.col[i].z
        if abs(z) > bz:
            bz, best, sign = abs(z), i, (1.0 if z >= 0 else -1.0)
    return best, sign


class Handle:
    __slots__ = ("kind", "ax", "side", "u")

    def __init__(self, kind, ax=None, side=None, u=None):
        self.kind = kind      # 'FACE' | 'CORNER'
        self.ax = ax
        self.side = side      # 0 / 1
        self.u = u            # köşe: (0/1, 0/1, 0/1)

    def point(self, box):
        if self.kind == 'FACE':
            u = [0.5, 0.5, 0.5]
            u[self.ax] = self.side
            return box.point(u)
        return box.point(self.u)

    def key(self):
        return (self.kind, self.ax, self.side, self.u)


def _handles():
    hs = [Handle('FACE', a, s) for a in range(3) for s in (0, 1)]
    hs += [Handle('CORNER', u=(x, y, z)) for x in (0, 1) for y in (0, 1) for z in (0, 1)]
    return hs


class OU_OT_cage(Operator):
    bl_idname = "olcu.cage"
    bl_label = "Kutu ile Ölçekle"
    bl_description = ("Seçimin dış sınır kutusunu tutamaçlarından sürükleyerek ya da değer yazarak "
                      "ölçekle. Ctrl: başka nesnelere yapış, Shift: tek eksen")
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return (context.area is not None and context.area.type == 'VIEW_3D'
                and bool(context.selected_objects))

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
        if not self.group:
            self.report({'WARNING'}, "Nesne seç")
            return {'CANCELLED'}
        self.frame = frame_for(s.box_space, self.group, context)
        dg = context.evaluated_depsgraph_get()
        self.box0 = group_box(dg, self.group.names, self.frame)
        if self.box0 is None:
            self.report({'WARNING'}, "Seçimin ölçülebilir geometrisi yok")
            return {'CANCELLED'}
        self.uctx = UnitCtx.from_settings(s, context.scene)
        self.scaler = Scaler(self.group)
        self.snapper = Snapper(context, s, None, exclude=self.group)
        self.snapper.xray = _xray(context)
        self.Mc = Matrix.Identity(4)          # onaylanmış toplam
        self.Md = Matrix.Identity(4)          # sürükleme
        self.history = []
        self.handles = _handles()
        self.hover = None
        self.drag = None
        self.typed = ""
        self.error = ""
        self.from_center = False
        self.axis_only = False
        self.keep_ground = True
        self.apply_data = s.apply_data
        self.shift = False
        self.ctrl = False
        self.snap = None
        self.view = None
        self._region = None
        args = (self, context)
        self._h3d = bpy.types.SpaceView3D.draw_handler_add(_draw_3d, args, 'WINDOW', 'POST_VIEW')
        self._h2d = bpy.types.SpaceView3D.draw_handler_add(_draw_2d, args, 'WINDOW', 'POST_PIXEL')
        context.window_manager.modal_handler_add(self)
        self._status(context)
        return {'RUNNING_MODAL'}

    # ---------------------------------------------------------------- yardımcı
    def box(self):
        return self.box0.transformed(self.Md @ self.Mc)

    def box_committed(self):
        return self.box0.transformed(self.Mc)

    def _status(self, context):
        if self.drag is None:
            h = "Kutu: bir tutamaç tut (yüz: eksen, köşe: oranlı)"
        else:
            h = "Sürükle ya da değer yaz → bırak / Enter"
        st = ("Sol tık-sürükle: ölçekle   Değer yaz: tam boyut   Shift/U: tek eksen   "
              "C: merkezden   G: zemini koru   Ctrl: yapış   A: veriye uygula   "
              "Ctrl+Z: son adımı geri al   Enter/Boşluk: bitir   Esc: iptal")
        set_status(context, self.area, h, st)

    def _pick_handle(self, view, m):
        box = self.box()
        best, bd = None, None
        r = 14.0 * D.ui_scale()
        for h in self.handles:
            p = view.project(h.point(box))
            if p is None:
                continue
            d = (p - m).length - (2.0 if h.kind == 'FACE' else 0.0)
            if d <= r and (bd is None or d < bd):
                best, bd = h, d
        return best

    def _pivot_for(self, h, box):
        upi, ups = _up_axis(box)
        if h.kind == 'FACE':
            u = [0.5, 0.5, 0.5]
            if not self.from_center:
                u[h.ax] = 1 - h.side
            if self.keep_ground and upi != h.ax:
                u[upi] = 0.0 if ups > 0 else 1.0
            return box.point(u)
        if self.from_center:
            return box.center
        return box.point(tuple(1 - c for c in h.u))

    def _start_drag(self, context, h, view, m):
        box = self.box_committed()
        hp = h.point(box)
        piv = self._pivot_for(h, box)
        if h.kind == 'FACE':
            d = box.axis(h.ax) * (1.0 if h.side else -1.0)
            L0 = box.size[h.ax]
            # merkezden ölçekte uzunluk her iki yöne değişir
        else:
            d = (hp - piv)
            L0 = d.length
            d = d.normalized() if L0 > 1e-12 else Vector((0, 0, 1))
        self.drag = dict(h=h, hp=hp, piv=piv, dir=d, L0=L0, m0=m.copy(), moved=False, L=L0,
                         lead=(hp - piv).dot(d))
        self.typed = ""
        self.error = ""

    def _drag_len_from_mouse(self, context, view, mx, my):
        dr = self.drag
        ro, rd = view.ray(mx, my)
        self.snap = None
        target = None
        snap_on = self.ctrl
        if snap_on:
            sn = self.snapper.find(context, view, mx, my)
            if sn is not None:
                self.snap = sn
                target = sn.co
        if target is not None:
            t = (target - dr['hp']).dot(dr['dir'])
        else:
            t = geom.closest_on_line_to_ray(dr['hp'], dr['dir'], ro, rd)
            if t is None:
                t = 0.0
        lead = dr['lead']             # tutamacın pivottan uzaklığı (dir boyunca)
        if abs(lead) < 1e-12:
            return dr['L0']
        f = (lead + t) / lead
        return dr['L0'] * f

    def _update_drag(self, context):
        dr = self.drag
        h = dr['h']
        L0 = dr['L0']
        self.error = ""
        L = dr['L']
        if self.typed:
            res = safe_parse_target(self.typed, self.uctx)
            if res is None:
                self.error = "geçersiz değer"
                L = None
            elif res[0] == 'FACTOR':
                L = L0 * res[1]
            else:
                if h.kind == 'CORNER':
                    box = self.box_committed()
                    big = max(box.size)
                    L = L0 * (res[1] / big) if big > 1e-12 else None
                else:
                    L = res[1]
        if L is None or L0 < 1e-12:
            self.Md = Matrix.Identity(4)
        else:
            f = max(L / L0, 1e-6)
            axis = h.kind == 'FACE' and (self.axis_only or self.shift)
            if axis:
                self.Md = geom.axis_scale_matrix(dr['piv'], dr['dir'], f)
            else:
                self.Md = geom.scale_matrix(dr['piv'], f)
            dr['f'] = f
        self.scaler.preview(self.Md @ self.Mc)

    def _commit(self):
        self.history.append(self.Mc.copy())
        self.Mc = self.Md @ self.Mc
        self.Md = Matrix.Identity(4)
        self.drag = None
        self.typed = ""
        self.snap = None

    def _cancel_drag(self):
        self.Md = Matrix.Identity(4)
        self.drag = None
        self.typed = ""
        self.snap = None
        self.scaler.preview(self.Mc)

    # ---------------------------------------------------------------- modal
    def modal(self, context, event):
        try:
            return self._modal(context, event)
        except Exception:
            self._finish(context, cancel=True)
            raise

    def _modal(self, context, event):
        et, ev = event.type, event.value
        typing = self.drag is not None
        if et in NAV_EVENTS or (et in NUMPAD_NAV and not typing):
            return {'PASS_THROUGH'}
        region, rv3d = region_under_mouse(self.area, event)
        if region is None and self.drag is not None and getattr(self, "_region", None) is not None:
            region, rv3d = self._region, self._region.data      # sürüklerken bölge dışı
        if region is not None:
            self._region = region
            self.view = geom.View.from_region(region, rv3d)
            m = Vector((event.mouse_x - region.x, event.mouse_y - region.y))
        else:
            m = None
        self.shift = event.shift
        self.ctrl = event.ctrl

        if et in {'LEFT_SHIFT', 'RIGHT_SHIFT', 'LEFT_CTRL', 'RIGHT_CTRL'}:
            if self.drag is not None and m is not None:
                if not self.typed:
                    self.drag['L'] = self._drag_len_from_mouse(context, self.view, m.x, m.y)
                self._update_drag(context)
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}

        if et == 'MOUSEMOVE':
            if m is None:
                return {'PASS_THROUGH'}
            if self.drag is None:
                self.hover = self._pick_handle(self.view, m)
            elif not self.typed:
                if (m - self.drag['m0']).length > 3:
                    self.drag['moved'] = True
                self.drag['L'] = self._drag_len_from_mouse(context, self.view, m.x, m.y)
                self._update_drag(context)
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if et == 'INBETWEEN_MOUSEMOVE':
            return {'RUNNING_MODAL'}

        if et == 'ESC' and ev == 'PRESS':
            if self.drag is not None:
                self._cancel_drag()
                self._status(context)
                self.area.tag_redraw()
                return {'RUNNING_MODAL'}
            return self._finish(context, cancel=True)
        if et == 'RIGHTMOUSE' and ev == 'PRESS':
            if self.drag is not None:
                self._cancel_drag()
                self._status(context)
                self.area.tag_redraw()
                return {'RUNNING_MODAL'}
            return {'RUNNING_MODAL'}

        if et == 'LEFTMOUSE':
            if m is None:
                return {'PASS_THROUGH'}
            if ev == 'PRESS':
                if self.drag is None:
                    h = self._pick_handle(self.view, m)
                    if h is None:
                        return {'RUNNING_MODAL'}
                    self._start_drag(context, h, self.view, m)
                    self._update_drag(context)
                else:
                    self._commit()
                self._status(context)
            elif ev == 'RELEASE' and self.drag is not None and self.drag['moved'] and not self.typed:
                self._commit()
                self._status(context)
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}

        if ev != 'PRESS':
            return {'RUNNING_MODAL'}

        if et in {'RET', 'NUMPAD_ENTER', 'SPACE'}:
            if self.drag is not None:
                if self.error:
                    return {'RUNNING_MODAL'}
                self._commit()
                self._status(context)
                self.area.tag_redraw()
                return {'RUNNING_MODAL'}
            return self._finish(context, cancel=False)
        if et == 'Z' and event.ctrl:
            if self.drag is None and self.history:
                self.Mc = self.history.pop()
                self.scaler.preview(self.Mc)
                self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if et == 'BACK_SPACE':
            if self.typed:
                self.typed = "" if event.ctrl else self.typed[:-1]
                if self.drag is not None and not self.typed and m is not None:
                    self.drag['L'] = self._drag_len_from_mouse(context, self.view, m.x, m.y)
                if self.drag is not None:
                    self._update_drag(context)
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}

        ch = NUMPAD_CHARS.get(et)
        if ch is None and event.unicode and not (event.ctrl or event.alt or event.oskey):
            ch = event.unicode.lower()
        if ch in ('c', 'u', 'g', 'a') and not (ch == 'c' and self.typed):
            if ch == 'c':
                self.from_center = not self.from_center
            elif ch == 'u':
                self.axis_only = not self.axis_only
            elif ch == 'g':
                self.keep_ground = not self.keep_ground
            elif ch == 'a':
                self.apply_data = not self.apply_data
            if self.drag is not None:
                h = self.drag['h']
                L, typed = self.drag['L'], self.typed
                self._start_drag(context, h, self.view, self.drag['m0'])
                self.drag['L'] = L
                self.drag['moved'] = True
                self.typed = typed
                self._update_drag(context)
            self.area.tag_redraw()
            return {'RUNNING_MODAL'}
        if self.drag is not None and ch and (ch in TYPE_CHARS or (ch == 'x' and not self.typed)):
            self.typed += ch
            self.drag['moved'] = True
            self._update_drag(context)
            self.area.tag_redraw()
        return {'RUNNING_MODAL'}

    def _finish(self, context, cancel):
        msgs = []
        if cancel or geom.matrices_close(self.Mc, Matrix.Identity(4), 1e-9):
            self.scaler.restore()
            done = False
        else:
            M = self.Mc
            piv = M.translation.copy()
            msgs, _e = self.scaler.finalize(context, M, frame=self.box0.frame, pivot=piv,
                                            apply_data=self.apply_data)
            done = True
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
        if done:
            sz = self.box_committed().size
            u = self.uctx
            self.report({'INFO'}, " | ".join(
                [f"Yeni boyut {u.fmt(sz.x)} × {u.fmt(sz.y)} × {u.fmt(sz.z)}"] + msgs))
            return {'FINISHED'}
        return {'CANCELLED'}


def _xray(context):
    try:
        return bool(context.space_data.shading.show_xray)
    except AttributeError:
        return False


# ===================================================================== çizim

def _draw_3d(op, context):
    try:
        if context.area != op.area:
            return
        with D.State():
            box = op.box()
            D.lines(D.box_lines(box), (1.0, 0.62, 0.2, 0.85), 2.0)
            if op.drag is not None:
                dr = op.drag
                D.dashed(dr['piv'], op.drag['h'].point(box), (1, 1, 1, 0.45), 1.0, 20)
            if op.snap is not None and op.snap.edge is not None:
                D.lines(list(op.snap.edge), D.KIND_COLOR['EDGE'], 3.0)
    except ReferenceError:
        pass


def _draw_2d(op, context):
    try:
        if context.area != op.area:
            return
        region, rv3d = context.region, context.region_data
        if region is None or rv3d is None:
            return
        view = geom.View.from_region(region, rv3d)
        u = op.uctx
        with D.State():
            box = op.box()
            active = op.drag['h'].key() if op.drag else None
            hov = op.hover.key() if op.hover else None
            for h in op.handles:
                p = view.project(h.point(box))
                if p is None:
                    continue
                k = h.key()
                big = k == active or (active is None and k == hov)
                s = (6.5 if big else 4.5) * D.ui_scale()
                col = D.COL_AXIS[h.ax] if h.kind == 'FACE' else (1, 1, 1, 1)
                D.rect(p.x - s - 1.5, p.y - s - 1.5, 2 * s + 3, 2 * s + 3, (0, 0, 0, 0.7))
                D.rect(p.x - s, p.y - s, 2 * s, 2 * s, col)
            # boyut etiketleri: bir köşeden çıkan üç kenarın ortası
            sz = box.size
            for ax in range(3):
                uu = [0.0, 0.0, 0.0]
                uu[ax] = 0.5
                p = view.project(box.point(uu))
                if p is None:
                    continue
                hl = op.drag is not None and op.drag['h'].kind == 'FACE' and op.drag['h'].ax == ax
                D.text(p.x, p.y - 18, f"{AX[ax]} {u.fmt(sz[ax])}", 13 if hl else 11,
                       D.COL_AXIS[ax], D.COL_BG, 3, 'CENTER')
            if op.snap is not None:
                D.marker(op.snap.kind, view.project(op.snap.co))
            _hud(op, u, box)
    except ReferenceError:
        pass


def _hud(op, u, box):
    x = 20 * D.ui_scale()
    y = 30 * D.ui_scale()
    lh = 22 * D.ui_scale()
    rows = []
    if op.drag is not None:
        dr = op.drag
        h = dr['h']
        what = f"{AX[h.ax]} boyu" if h.kind == 'FACE' else "en büyük boyut (oranlı)"
        parts = [(f"{what}: ", D.COL_DIM), ((op.typed or "") + "▏", D.COL_TEXT)]
        if op.error:
            parts.append(("  " + op.error, D.COL_X))
        elif 'f' in dr:
            parts.append((f"   ×{dr['f']:.5g}", D.COL_MEASURE))
        if op.snap is not None:
            parts.append((f"   yapış: {op.snap.label}", D.KIND_COLOR.get(op.snap.kind, D.COL_TEXT)))
        rows.append(parts)
    mode = "Tek eksen" if (op.axis_only or op.shift) else "Oranlı"
    rows.append([("Mod [U/Shift]: ", D.COL_DIM), (mode, D.COL_TEXT),
                 ("   Pivot [C]: ", D.COL_DIM), ("merkez" if op.from_center else "karşı yüz", D.COL_TEXT),
                 ("   Zemin [G]: ", D.COL_DIM), ("korunur" if op.keep_ground else "serbest", D.COL_TEXT),
                 ("   Veriye uygula [A]: ", D.COL_DIM),
                 ("açık" if op.apply_data else "kapalı", D.COL_Y if op.apply_data else D.COL_DIM)])
    sz = box.size
    rows.append([("Boyut  ", D.COL_DIM), (u.fmt(sz.x), D.COL_X), (" × ", D.COL_DIM),
                 (u.fmt(sz.y), D.COL_Y), (" × ", D.COL_DIM), (u.fmt(sz.z), D.COL_Z),
                 (f"   adım: {len(op.history)}", D.COL_DIM)])
    rows.append([("ÖLÇÜ USTASI  ", D.COL_MEASURE), ("Kutu ile Ölçekle", D.COL_TEXT)])
    for i, parts in enumerate(rows):
        D.rich_line(x, y + i * lh, parts, 12)
