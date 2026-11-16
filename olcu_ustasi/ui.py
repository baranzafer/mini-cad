# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.types import Panel

from .pins import pin_length
from .units import UnitCtx

CATEGORY = "Ölçü"


class _Base:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = CATEGORY


class OU_PT_tools(_Base, Panel):
    bl_idname = "OU_PT_tools"
    bl_label = "Ölçü Ustası: Araçlar"

    def draw(self, context):
        s = context.scene.olcu_ustasi
        lay = self.layout
        n = len(context.selected_objects)
        col = lay.column(align=True)
        col.scale_y = 1.5
        col.operator("olcu.measure", text="Ölç ve Ölçekle", icon='DRIVER_DISTANCE')
        r = col.row(align=True)
        r.enabled = n > 0
        r.operator("olcu.cage", text="Kutu ile Ölçekle", icon='MOD_LATTICE')
        if n:
            lay.label(text=f"{n} nesne seçili · tek bütün olarak", icon='OUTLINER_OB_GROUP_INSTANCE')
        else:
            lay.label(text="Seçim yok: yalnızca ölçüm yapılır", icon='INFO')
        col = lay.column(align=True)
        col.prop(s, "pivot", text="Pivot")
        col.prop(s, "include_children")
        col.prop(s, "apply_data")
        col.prop(s, "live_preview")


class OU_PT_dims(_Base, Panel):
    bl_idname = "OU_PT_dims"
    bl_label = "Ölçü Ustası: Seçim Boyutu"

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def draw(self, context):
        s = context.scene.olcu_ustasi
        sc = context.scene
        lay = self.layout
        row = lay.row(align=True)
        row.prop(s, "box_space", expand=True)
        row.prop(s, "lock_ratio", text="", icon='LOCKED' if s.lock_ratio else 'UNLOCKED')
        col = lay.column(align=True)
        col.prop(sc, "olcu_dim_x", text="X (genişlik)")
        col.prop(sc, "olcu_dim_y", text="Y (derinlik)")
        col.prop(sc, "olcu_dim_z", text="Z (yükseklik)")
        lay.label(text="Bir boyutu yaz: tüm seçim ölçeklenir", icon='INFO')

        box = lay.box()
        box.label(text="Hızlı Ölçek", icon='FULLSCREEN_ENTER')
        r = box.row(align=True)
        r.prop(s, "quick_factor", text="×")
        op = r.operator("olcu.scale_factor", text="Uygula")
        op.use_setting = True
        g = box.grid_flow(columns=4, align=True, even_columns=True)
        for f, t in ((0.5, "×½"), (2.0, "×2"), (0.1, "×0.1"), (10.0, "×10")):
            g.operator("olcu.scale_factor", text=t).factor = f
        box.label(text="İçe aktarma birim düzeltme:")
        g = box.grid_flow(columns=3, align=True, even_columns=True)
        for f, t in ((0.001, "mm → m"), (0.01, "cm → m"), (0.0254, "in → m"),
                     (0.3048, "ft → m"), (100.0, "m → cm"), (1000.0, "m → mm")):
            g.operator("olcu.scale_factor", text=t).factor = f


class OU_PT_fit(_Base, Panel):
    bl_idname = "OU_PT_fit"
    bl_label = "Ölçü Ustası: Sığdır ve Yerleştir"

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def draw(self, context):
        lay = self.layout
        box = lay.box()
        box.label(text="Aktif nesnenin kutusuna eşitle", icon='SNAP_VOLUME')
        ok = len(context.selected_objects) >= 2 and context.active_object is not None
        col = box.column(align=True)
        col.enabled = ok
        r = col.row(align=True)
        for m, t in (('FIT', "Sığdır"), ('FILL', "Kapla"), ('STRETCH', "Esnet")):
            o = r.operator("olcu.fit_to_active", text=t)
            o.mode = m
        r = col.row(align=True)
        for m in "XYZ":
            o = r.operator("olcu.fit_to_active", text=f"{m} boyu")
            o.mode = m
        if not ok:
            box.label(text="Önce nesneleri, en son referansı seç", icon='INFO')
        col = lay.column(align=True)
        r = col.row(align=True)
        r.operator("olcu.place", text="Zemine İndir", icon='TRIA_DOWN_BAR').target = 'FLOOR'
        r.operator("olcu.place", text="Merkeze", icon='WORLD').target = 'ORIGIN'
        r.operator("olcu.place", text="İmlece", icon='PIVOT_CURSOR').target = 'CURSOR'
        lay.operator("olcu.apply_scale_safe", icon='CHECKMARK')


class OU_PT_snap(_Base, Panel):
    bl_idname = "OU_PT_snap"
    bl_label = "Ölçü Ustası: Yakalama"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.olcu_ustasi
        lay = self.layout
        g = lay.grid_flow(columns=2, align=True, even_columns=True)
        for attr, icon in (("snap_vert", 'SNAP_VERTEX'), ("snap_edge", 'SNAP_EDGE'),
                           ("snap_mid", 'SNAP_MIDPOINT'), ("snap_face", 'SNAP_FACE'),
                           ("snap_box", 'SNAP_VOLUME'), ("snap_perp", 'SNAP_PERPENDICULAR'),
                           ("snap_face_center", 'SNAP_FACE_CENTER'), ("snap_origin", 'OBJECT_ORIGIN')):
            g.prop(s, attr, toggle=True, icon=icon)
        col = lay.column(align=True)
        col.prop(s, "snap_only_selection")
        col.prop(s, "show_box")
        col.prop(s, "snap_radius")


class OU_PT_units(_Base, Panel):
    bl_idname = "OU_PT_units"
    bl_label = "Ölçü Ustası: Birim"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        s = context.scene.olcu_ustasi
        lay = self.layout
        lay.row(align=True).prop(s, "display_unit", expand=True)
        lay.prop(s, "precision")
        if s.last_value > 0:
            r = lay.row(align=True)
            r.label(text=f"Son: {s.last_text or UnitCtx.from_settings(s, context.scene).fmt(s.last_value)}",
                    icon='DRIVER_DISTANCE')
            r.operator("olcu.copy_last", text="", icon='COPYDOWN')


class OU_PT_pins(_Base, Panel):
    bl_idname = "OU_PT_pins"
    bl_label = "Ölçü Ustası: Sabit Ölçüler"
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        self.layout.prop(context.scene.olcu_ustasi, "show_pins", text="")

    def draw(self, context):
        s = context.scene.olcu_ustasi
        lay = self.layout
        if not len(s.pins):
            lay.label(text="Ölçerken K ile ölçüyü sabitle", icon='INFO')
            return
        u = UnitCtx.from_settings(s, context.scene)
        col = lay.column(align=True)
        for i, p in enumerate(s.pins):
            r = col.row(align=True)
            r.prop(p, "visible", text="", icon='HIDE_OFF' if p.visible else 'HIDE_ON', emboss=False)
            tag = {"AXIS": " (eksen)", "PLANE": " (düzlem)"}.get(p.mode, "")
            r.label(text=f"#{i + 1}  {u.fmt(pin_length(p))}{tag}")
            r.operator("olcu.pin_remove", text="", icon='X', emboss=False).index = i
        lay.operator("olcu.pin_remove", text="Tümünü Sil", icon='TRASH').index = -1


def _menu(self, context):
    lay = self.layout
    lay.separator()
    lay.operator("olcu.measure", icon='DRIVER_DISTANCE')
    if context.selected_objects:
        lay.operator("olcu.cage", icon='MOD_LATTICE')


def _menu_transform(self, context):
    lay = self.layout
    lay.separator()
    lay.operator("olcu.measure", icon='DRIVER_DISTANCE')
    lay.operator("olcu.cage", icon='MOD_LATTICE')
    lay.operator("olcu.apply_scale_safe", icon='CHECKMARK')


classes = (OU_PT_tools, OU_PT_dims, OU_PT_fit, OU_PT_snap, OU_PT_units, OU_PT_pins)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.VIEW3D_MT_object_context_menu.append(_menu)
    bpy.types.VIEW3D_MT_transform_object.append(_menu_transform)


def unregister():
    bpy.types.VIEW3D_MT_transform_object.remove(_menu_transform)
    bpy.types.VIEW3D_MT_object_context_menu.remove(_menu)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
