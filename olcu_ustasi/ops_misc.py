# SPDX-License-Identifier: GPL-3.0-or-later
"""Panelden çalışan tek adımlık işlemler ve canlı seçim boyutu alanları."""
import time

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy.types import Operator
from mathutils import Matrix, Vector

from . import geom
from .common import resolve_pivot, tag_redraw_all
from .scaling import Scaler, apply_scale
from .selection import Group, frame_for, group_box, object_box
from .units import UnitCtx


def _settings(context):
    return context.scene.olcu_ustasi


def _group(context, exclude_active=False):
    s = _settings(context)
    sel = list(context.selected_objects)
    if exclude_active and context.active_object in sel:
        act = context.active_object
        sel = [o for o in sel if o != act]
    return Group(sel, s.include_children)


def _box(context, group):
    s = _settings(context)
    frame = frame_for(s.box_space, group, context)
    return group_box(context.evaluated_depsgraph_get(), group.names, frame)


def _ensure_object_mode(context):
    if context.mode != 'OBJECT' and context.active_object is not None:
        prev = context.object.mode
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
            return prev
        except RuntimeError:
            return None
    return None


def _restore_mode(prev):
    if prev and prev != 'OBJECT':
        try:
            bpy.ops.object.mode_set(mode=prev)
        except RuntimeError:
            pass


def run_scale(op, context, group, M, frame=None, pivot=None):
    s = _settings(context)
    prev = _ensure_object_mode(context)
    try:
        msgs, _e = Scaler(group).finalize(context, M, frame=frame, pivot=pivot,
                                          apply_data=s.apply_data)
    finally:
        _restore_mode(prev)
    invalidate_dims()
    if op is not None and msgs:
        op.report({'INFO'}, " | ".join(msgs))
    return msgs


# ====================================================== canlı boyut alanları

_dims = {"key": None, "box": None, "t": 0.0, "dirty": True}


def invalidate_dims():
    """Kendi işlemlerimizden sonra: bir sonraki okuma kesin yeniden hesaplar."""
    _dims["dirty"] = True
    _dims["t"] = 0.0


@bpy.app.handlers.persistent
def _on_depsgraph(*_args):
    _dims["dirty"] = True


def _dims_key(context):
    s = _settings(context)
    act = context.active_object.name if context.active_object else ""
    return (tuple(sorted(o.name for o in context.selected_objects)), s.box_space,
            s.include_children, act)


def _late_redraw():
    _dims["timer"] = False
    try:
        tag_redraw_all(bpy.context)
    except (AttributeError, ReferenceError):
        pass
    return None


def current_box(context, force=False):
    key = _dims_key(context)
    now = time.monotonic()
    if key == _dims["key"] and not _dims["dirty"]:
        return _dims["box"]
    if not force and key == _dims["key"] and now - _dims["t"] < 0.15:
        # sürükleme sırasında sık hesaplamayı kıs; kısa süre sonra paneli tazele
        if not _dims.get("timer"):
            _dims["timer"] = True
            bpy.app.timers.register(_late_redraw, first_interval=0.2)
        return _dims["box"]
    g = Group(context.selected_objects, _settings(context).include_children)
    box = _box(context, g) if g else None
    _dims.update(key=key, box=box, t=now, dirty=False)
    return box


def _get_dim(i):
    def get(self):
        try:
            b = current_box(bpy.context)
        except (AttributeError, RuntimeError, ReferenceError):
            return 0.0
        return float(b.size[i]) if b is not None else 0.0
    return get


def _set_dim(i):
    def set_(self, value):
        context = bpy.context
        g = Group(context.selected_objects, _settings(context).include_children)
        if not g:
            return
        _dims["dirty"] = True
        box = current_box(context, force=True)
        if box is None:
            return
        old = box.size[i]
        if old < 1e-12 or value <= 1e-12:
            return
        f = value / old
        if abs(f - 1.0) < 1e-12:
            return
        s = _settings(context)
        mode = s.pivot if s.pivot != 'POINT_A' else 'BOX_BOTTOM'
        piv = resolve_pivot(mode, context, box, None, g)
        if s.lock_ratio:
            M = geom.scale_matrix(piv, f)
        else:
            M = geom.axis_scale_matrix(piv, box.axis(i), f)
        run_scale(None, context, g, M, frame=box.frame, pivot=piv)
        tag_redraw_all(context)
    return set_


def register_dims():
    for i, n in enumerate("xyz"):
        setattr(bpy.types.Scene, f"olcu_dim_{n}", FloatProperty(
            name="XYZ"[i], unit='LENGTH', subtype='DISTANCE', min=0.0, precision=4,
            get=_get_dim(i), set=_set_dim(i),
            description=f"Seçimin {'XYZ'[i]} boyutu (tek bütün). Değiştirince tüm seçim ölçeklenir"))
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister_dims():
    for n in "xyz":
        try:
            delattr(bpy.types.Scene, f"olcu_dim_{n}")
        except AttributeError:
            pass
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)


# ============================================================== işlemler

class _SelOp:
    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)


class OU_OT_scale_factor(_SelOp, Operator):
    bl_idname = "olcu.scale_factor"
    bl_label = "Çarpanla Ölçekle"
    bl_description = "Seçimi tek bütün olarak verilen çarpanla ölçekle (ilişkiler korunur)"
    bl_options = {'REGISTER', 'UNDO'}

    factor: FloatProperty(name="Çarpan", default=2.0, min=1e-9, precision=6)
    use_setting: BoolProperty(default=False, options={'HIDDEN', 'SKIP_SAVE'})

    def execute(self, context):
        s = _settings(context)
        f = s.quick_factor if self.use_setting else self.factor
        g = _group(context)
        box = _box(context, g)
        mode = s.pivot if s.pivot != 'POINT_A' else 'BOX_BOTTOM'
        piv = resolve_pivot(mode, context, box, None, g)
        run_scale(self, context, g, geom.scale_matrix(piv, f), pivot=piv)
        self.report({'INFO'}, f"×{f:.6g} ölçeklendi ({len(g.roots)} kök)")
        return {'FINISHED'}


class OU_OT_fit(Operator):
    bl_idname = "olcu.fit_to_active"
    bl_label = "Aktif Nesneye Sığdır"
    bl_description = ("Seçili nesneleri (aktif hariç) tek bütün olarak aktif nesnenin kutusuna "
                      "sığdır / eşitle. Örn: aracı bir referans küpün boyuna getir")
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(name="Eşitle", items=[
        ('FIT', "İçine Sığdır", "Hiçbir boyut taşmaz (en küçük oran)"),
        ('FILL', "Kapla", "Kutuyu tamamen doldurur (en büyük oran)"),
        ('X', "X Boyu", "X boyları eşit olur"),
        ('Y', "Y Boyu", "Y boyları eşit olur"),
        ('Z', "Z Boyu", "Z boyları eşit olur"),
        ('STRETCH', "Esnet (her eksen)", "Her eksen ayrı ayrı eşitlenir (oran bozulur)"),
    ], default='FIT')
    align: EnumProperty(name="Hizala", items=[
        ('BOTTOM', "Alt Merkez", "Alt yüz merkezleri çakışır"),
        ('CENTER', "Merkez", "Merkezler çakışır"),
        ('NONE', "Yerinde", "Pivot ayarına göre yerinde ölçekle"),
    ], default='BOTTOM')

    @classmethod
    def poll(cls, context):
        a = context.active_object
        return a is not None and len(context.selected_objects) >= 2 and a.select_get()

    def execute(self, context):
        s = _settings(context)
        act = context.active_object
        g = _group(context, exclude_active=True)
        if not g:
            return {'CANCELLED'}
        if g.contains(act):
            self.report({'WARNING'}, "Aktif nesne, ölçeklenecek grubun alt nesnesi olmamalı")
            return {'CANCELLED'}
        frame = frame_for(s.box_space, Group([act]), context)
        dg = context.evaluated_depsgraph_get()
        tb = object_box(act.evaluated_get(dg), act.matrix_world, frame)
        sb = group_box(dg, g.names, frame)
        if tb is None or sb is None:
            self.report({'WARNING'}, "Kutular hesaplanamadı")
            return {'CANCELLED'}
        ss, ts = sb.size, tb.size
        r = [ts[i] / ss[i] if ss[i] > 1e-12 else None for i in range(3)]
        valid = [x for x in r if x is not None]
        if not valid:
            return {'CANCELLED'}
        if self.mode == 'FIT':
            f = min(valid)
        elif self.mode == 'FILL':
            f = max(valid)
        elif self.mode in ('X', 'Y', 'Z'):
            f = r["XYZ".index(self.mode)]
            if f is None:
                self.report({'WARNING'}, "Bu eksende boyut sıfır")
                return {'CANCELLED'}
        else:
            f = None
        if self.align == 'CENTER':
            src, dst = sb.center, tb.center
        elif self.align == 'BOTTOM':
            src, dst = sb.bottom_center(), tb.bottom_center()
        else:
            mode = s.pivot if s.pivot != 'POINT_A' else 'BOX_BOTTOM'
            src = dst = resolve_pivot(mode, context, sb, None, g)
        if f is not None:
            L = Matrix.Diagonal((f, f, f, 1.0))
        else:
            fs = [x if x is not None else 1.0 for x in r]
            L = (frame @ Matrix.Diagonal(fs) @ frame.transposed()).to_4x4()
        M = Matrix.Translation(dst) @ L @ Matrix.Translation(-src)
        run_scale(self, context, g, M, frame=frame, pivot=dst)
        self.report({'INFO'}, "Sığdırıldı" + (f" (×{f:.6g})" if f else " (esnetildi)"))
        return {'FINISHED'}


class OU_OT_place(_SelOp, Operator):
    bl_idname = "olcu.place"
    bl_label = "Yerleştir"
    bl_description = "Seçimi tek bütün olarak taşı"
    bl_options = {'REGISTER', 'UNDO'}

    target: EnumProperty(items=[
        ('FLOOR', "Zemine İndir", "Kutunun altı Z=0 olur"),
        ('ORIGIN', "Merkeze Al", "Kutu alt merkezi dünya orijinine gelir"),
        ('CURSOR', "İmlece Al", "Kutu alt merkezi 3B imlece gelir"),
    ], default='FLOOR')

    def execute(self, context):
        g = _group(context)
        box = group_box(context.evaluated_depsgraph_get(), g.names, Matrix.Identity(3))
        if box is None:
            return {'CANCELLED'}
        bc = box.bottom_center()
        if self.target == 'FLOOR':
            d = Vector((0, 0, -box.lo.z))
        elif self.target == 'ORIGIN':
            d = -bc
        else:
            d = context.scene.cursor.location - bc
        M = Matrix.Translation(d)
        prev = _ensure_object_mode(context)
        try:
            msgs, _e = Scaler(g).finalize(context, M)
        finally:
            _restore_mode(prev)
        invalidate_dims()
        if msgs:
            self.report({'INFO'}, " | ".join(msgs))
        return {'FINISHED'}


class OU_OT_apply_safe(_SelOp, Operator):
    bl_idname = "olcu.apply_scale_safe"
    bl_label = "Ölçeği Güvenle Uygula"
    bl_description = ("Seçimin tüm hiyerarşisinde ölçeği 1 yap: ölçek veriye, eğri kalınlıklarına ve "
                      "değiştirici değerlerine aktarılır; görünüm değişmez, paylaşılan veri bir kez "
                      "dönüştürülür, alt nesne ilişkileri korunur")
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        g = Group(context.selected_objects, True)
        prev = _ensure_object_mode(context)
        try:
            rep = apply_scale(context, g.hierarchy)
        finally:
            _restore_mode(prev)
        invalidate_dims()
        self.report({'INFO'}, " | ".join(rep.messages()))
        return {'FINISHED'}


class OU_OT_pin_remove(Operator):
    bl_idname = "olcu.pin_remove"
    bl_label = "Sabit Ölçüyü Sil"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
    index: IntProperty(default=-1)

    def execute(self, context):
        s = _settings(context)
        if self.index < 0:
            s.pins.clear()
        elif self.index < len(s.pins):
            s.pins.remove(self.index)
        tag_redraw_all(context)
        return {'FINISHED'}


class OU_OT_copy_last(Operator):
    bl_idname = "olcu.copy_last"
    bl_label = "Son Ölçümü Kopyala"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        s = _settings(context)
        context.window_manager.clipboard = s.last_text or UnitCtx.from_settings(
            s, context.scene).fmt(s.last_value)
        return {'FINISHED'}


classes = (OU_OT_scale_factor, OU_OT_fit, OU_OT_place, OU_OT_apply_safe, OU_OT_pin_remove,
           OU_OT_copy_last)
