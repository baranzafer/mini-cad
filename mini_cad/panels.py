"""N paneli (CAD sekmesi): açılır kapanır modüller ve kompakt listeler.

Bağımsız, "Mini CAD: ..." ön ekli paneller (her biri ayrı açılır/kapanır):
  Gövde · Seçim ve Tel Kafes · Yüzeyler · Simetri [☑] · Boolean [☑] · Fillet [☑] ·
  İşlem Sırası · Ayarlar · Export
"""

import bpy

from . import core, kernel
from .ui import draw_kernel_box, get_target, BOOL_NAMES

CATEGORY = "CAD"


def _status_icon(text):
    if text.startswith(("Tamam", "Önizleme")):
        return "ERROR" if "Hatalı" in text else "CHECKMARK"
    return "ERROR"


def _ready():
    return kernel.kernel_available()


# ================================================================ listeler

class MINICAD_UL_patches(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname,
                  index):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="")
        row.prop(item, "name", text="", emboss=False,
                 icon="CHECKMARK" if item.ok else "ERROR")
        sub = row.row(align=True)
        sub.scale_x = 0.8
        sub.prop(item, "method", text="")


class MINICAD_UL_features(bpy.types.UIList):
    """Aynı koleksiyonu üç yerde gösterir: list_id 'bools', 'bevels' ya da 'order'."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname,
                  index):
        row = layout.row(align=True)
        row.prop(item, "enabled", text="")
        is_bool = item.op == "BOOLEAN"
        if self.list_id == "order":
            row.label(text=f"{index + 1}.")
        row.prop(item, "name", text="", emboss=False,
                 icon="MOD_BOOLEAN" if is_bool else "MOD_BEVEL")
        if is_bool:
            tool = item.tool.name if item.tool else "—"
            row.label(text=f"{BOOL_NAMES.get(item.bool_type, '')} · {tool}")
        else:
            kind = "Fillet" if item.kind == "FILLET" else "Pah"
            n_geo = len(item.geo_edges)
            row.label(text=f"{kind} {core.fmt_len(item.size)}" +
                      (f" · +{n_geo} gövde" if n_geo else ""))
        row.label(text="", icon="CHECKMARK" if item.ok else "ERROR")

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        flags = []
        for f in items:
            if self.list_id == "bools":
                show = f.op == "BOOLEAN"
            elif self.list_id == "bevels":
                show = f.op != "BOOLEAN"
            else:
                show = True
            flags.append(self.bitflag_filter_item if show else 0)
        return flags, []


# ================================================================ ana panel

class MINICAD_PT_main(bpy.types.Panel):
    bl_label = "Mini CAD: Gövde"
    bl_idname = "MINICAD_PT_main"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        _record_row(layout, context)
        if not _ready():
            draw_kernel_box(layout)
            return
        row = layout.row(align=True)
        row.prop(context.scene, "minicad_target", text="Gövde")
        row.operator("minicad.set_target_active", text="", icon="RESTRICT_SELECT_OFF")
        t = get_target(context)
        if t is None:
            layout.label(text="Seçim modunda kenarları seç, Ctrl+Enter: yeni gövde", icon="INFO")
            return
        p = t.cad
        if p.status:
            layout.label(text=p.status, icon=_status_icon(p.status))
        row = layout.row(align=True)
        st = core._stats
        row.label(text=f"Hesaplama {st['count']}", icon="TIME")
        row.operator("minicad.rebuild", text="Yenile", icon="FILE_REFRESH")


def _record_row(layout, context):
    from . import recorder
    row = layout.row(align=True)
    if recorder.is_recording():
        row.alert = True
        row.operator("minicad.record", text=f"Kaydediliyor… {recorder.remaining():.1f} sn "
                                            "(bitir)", icon="REC")
    else:
        row.operator("minicad.record", text="Kayıt → Claude (Ctrl+Alt+R)", icon="REC")
    sub = row.row(align=True)
    sub.scale_x = 0.55
    sub.prop(context.scene, "minicad_rec_seconds", text="")
    row.prop(context.scene, "minicad_rec_shot", text="", icon="IMAGE_DATA")


class _Sub:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = CATEGORY

    @classmethod
    def poll(cls, context):
        return _ready() and get_target(context) is not None


# ================================================================ seçim ve tel kafes

class MINICAD_PT_select(_Sub, bpy.types.Panel):
    bl_label = "Mini CAD: Seçim ve Tel Kafes"
    bl_idname = "MINICAD_PT_select"
    bl_order = 1

    @classmethod
    def poll(cls, context):
        return _ready()

    def draw(self, context):
        layout = self.layout
        from . import pick
        from . import draw
        big = layout.row(align=True)
        big.scale_y = 1.5
        if pick.is_running():
            sub = big.row(align=True)
            sub.alert = True
            sub.operator("minicad.pick_edges", text="Seçimi Kapat", icon="CANCEL")
        else:
            big.operator("minicad.pick_edges", text="Kenar Seç", icon="RESTRICT_SELECT_OFF")
        if draw.is_running():
            sub = big.row(align=True)
            sub.alert = True
            sub.operator("minicad.draw", text="Çizimi Kapat", icon="CANCEL")
        else:
            big.operator("minicad.draw", text="Çiz", icon="CURVE_BEZCURVE")
        col = layout.column(align=True)
        col.scale_y = 0.8
        col.label(text="Tık: zincir · Alt+tık: tek parça")
        col.label(text="Enter: yüzey · Ctrl+Enter: yeni gövde")
        col.label(text="B: fillet · Backspace: temizle · Esc: çık")
        col.label(text="Sarı kenarlar: boolean kenarları (tek tek seçip B)")
        if draw.is_running():
            box = layout.box()
            box.scale_y = 0.8
            box.label(text="Araçlar 3D görünümdeki Çizim penceresinde", icon="CURVE_BEZCURVE")
            box.label(text="Tık: nokta · sağ tık/Enter: çizgiyi taslağa ekle")
            box.label(text="Ctrl+Enter / Bitir: taslağı eğriye kaydet")
            box.label(text="Taslak nokta / tutamaç: sürükle (X/Y/Z eksen kilidi)")
            box.label(text="Tıklanan noktada pivot: oklarından eksende taşı")
            box.label(text="Ctrl+Z / Ctrl+Shift+Z: taslakta geri al / yinele")
            box.label(text="T: iz ile başlangıç noktası (eksen boyunca adım adım)")
            box.prop(context.scene, "minicad_draw_target", expand=True)
            box.label(text="Esc: duraklat (Seç) · ikinci Esc: kapat")
            box.label(text="Rakam yaz: ölçü · Tab: sonraki alan · C: kapat · F: yüzey")
            box.label(text="W seç · L doğru · A teğet yay · E 3 nokta yay · M merkezli")
            box.label(text="O daire · R dikdörtgen · S/K spline · P kalem · Q önceki araç")
            box.label(text="Shift+Q düzlem seç · X/Y/Z/V düzlem · I ızgara · Shift 15°")
            box.prop(context.scene, "minicad_grid_alpha", slider=True)

        box = layout.box()
        row = box.row(align=True)
        row.prop(context.scene, "minicad_poly_smooth")
        sub = row.row(align=True)
        sub.active = context.scene.minicad_poly_smooth
        sub.prop(context.scene, "minicad_poly_corner", text="")
        if context.mode == "EDIT_MESH":
            r = box.row()
            r.scale_y = 1.3
            r.operator("minicad.mesh_to_wire", icon="CURVE_BEZCURVE")
        else:
            box.label(text="Mesh → tel kafes: mesh edit modunda kenar seç", icon="INFO")


# ================================================================ kısıtlar

class MINICAD_PT_constraints(_Sub, bpy.types.Panel):
    bl_label = "Mini CAD: Kısıtlar"
    bl_idname = "MINICAD_PT_constraints"
    bl_order = 2
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return _ready()

    def draw(self, context):
        from . import constraints
        layout = self.layout
        sc = context.scene
        row = layout.row(align=True)
        row.prop(sc, "minicad_auto_constraints", toggle=True)
        row.prop(sc, "minicad_show_constraints", toggle=True)
        row = layout.row(align=True)
        row.operator("minicad.constraint_solve", text="Çöz", icon="CON_TRACKTO")
        op = row.operator("minicad.constraint_clear", text="Otomatikleri Sil", icon="X")
        op.auto_only = True
        op = row.operator("minicad.constraint_clear", text="", icon="TRASH")
        op.auto_only = False
        items = list(constraints.all_constraints(sc))
        if not items:
            layout.label(text="Kısıt yok · Çiz penceresinden KISIT araçlarını kullan",
                         icon="INFO")
            return
        bad = sum(1 for _, _, c in items if c.enabled and not c.ok)
        layout.label(text=f"{len(items)} kısıt" + (f" · {bad} sağlanamadı" if bad else ""),
                     icon="ERROR" if bad else "CHECKMARK")
        col = layout.column(align=True)
        for ob, i, c in items[:60]:
            r = col.row(align=True)
            r.prop(c, "enabled", text="")
            name = constraints.NAMES.get(c.kind, c.kind)
            if c.kind == "AXIS":
                name += " " + "XYZ"[c.axis]
            r.label(text=f"{name}{' (oto)' if c.auto else ''}",
                    icon="CHECKMARK" if c.ok or not c.enabled else "ERROR")
            if c.kind == "DISTANCE":
                r.prop(c, "length", text="")
            elif c.kind == "ANGLE":
                r.prop(c, "angle", text="")
            else:
                r.label(text=constraints.describe(c))
            op = r.operator("minicad.constraint_remove", text="", icon="X")
            op.obj, op.index = ob.name, i
        if len(items) > 60:
            col.label(text=f"… {len(items) - 60} kısıt daha")


# ================================================================ yüzeyler

class MINICAD_PT_surfaces(_Sub, bpy.types.Panel):
    bl_label = "Mini CAD: Yüzeyler"
    bl_idname = "MINICAD_PT_surfaces"
    bl_order = 2

    def draw_header(self, context):
        t = get_target(context)
        self.layout.label(text=f"({len(t.cad.patches)})")

    def draw(self, context):
        layout = self.layout
        p = get_target(context).cad
        layout.template_list("MINICAD_UL_patches", "", p, "patches", p, "active_patch", rows=4)
        i = p.active_patch
        if 0 <= i < len(p.patches):
            patch = p.patches[i]
            box = layout.box()
            if patch.info:
                box.label(text=patch.info, icon="NONE" if patch.ok else "ERROR")
            row = box.row(align=True)
            op = row.operator("minicad.select_patch_curves", text="Eğrilerini Seç",
                              icon="RESTRICT_SELECT_OFF")
            op.index = i
            op = row.operator("minicad.remove_patch", text="Sil", icon="TRASH")
            op.index = i
        layout.prop(p, "make_solid")


# ================================================================ simetri

class MINICAD_PT_mirror(_Sub, bpy.types.Panel):
    bl_label = "Mini CAD: Simetri"
    bl_idname = "MINICAD_PT_mirror"
    bl_order = 3
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(get_target(context).cad, "use_mirror", text="")

    def draw(self, context):
        layout = self.layout
        p = get_target(context).cad
        layout.active = p.use_mirror
        row = layout.row(align=True)
        row.prop(p, "mirror_x", toggle=True)
        row.prop(p, "mirror_y", toggle=True)
        row.prop(p, "mirror_z", toggle=True)
        layout.prop(p, "mirror_center")


# ================================================================ boolean

class MINICAD_PT_boolean(_Sub, bpy.types.Panel):
    bl_label = "Mini CAD: Boolean"
    bl_idname = "MINICAD_PT_boolean"
    bl_order = 4
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(get_target(context).cad, "use_booleans", text="")

    def draw(self, context):
        layout = self.layout
        sc = context.scene
        t = get_target(context)
        p = t.cad
        layout.operator("minicad.rebuild", text="Yenile (baştan hesapla)", icon="FILE_REFRESH")
        layout.active = p.use_booleans

        box = layout.box()
        split = box.row(align=True)
        col = split.column(align=True)
        r = col.row(align=True)
        r.label(text="", icon="COLORSET_04_VEC")
        r.prop(sc, "minicad_target", text="Gövde")
        r.operator("minicad.set_target_active", text="", icon="RESTRICT_SELECT_OFF")
        r = col.row(align=True)
        r.label(text="", icon="COLORSET_02_VEC")
        r.prop(sc, "minicad_bool_tool", text="İkincil")
        r.operator("minicad.pick_bool_tool", text="", icon="RESTRICT_SELECT_OFF")
        sw = split.column(align=True)
        sw.prop(sc, "minicad_bool_highlight", text="", emboss=False,
                icon="HIDE_OFF" if sc.minicad_bool_highlight else "HIDE_ON")
        sw.operator("minicad.swap_bool", text="", icon="UV_SYNC_SELECT")

        box.row(align=True).prop(sc, "minicad_bool_type", expand=True)
        rr = box.row()
        rr.scale_y = 1.2
        rr.operator("minicad.add_boolean", icon="ADD")
        tool = sc.minicad_bool_tool
        if tool is not None and tool.cad.is_cad and "Kapalı katı" not in tool.cad.status:
            box.label(text="İkincil gövde kapalı katı değil", icon="ERROR")
        if "Kapalı katı" not in p.status:
            box.label(text="Ana gövde kapalı katı değil", icon="ERROR")

        if not any(f.op == "BOOLEAN" for f in p.features):
            return
        layout.template_list("MINICAD_UL_features", "bools", p, "features", p, "active_bool",
                             rows=3)
        i = p.active_bool
        if 0 <= i < len(p.features) and p.features[i].op == "BOOLEAN":
            f = p.features[i]
            box = layout.box()
            box.row(align=True).prop(f, "bool_type", expand=True)
            box.prop(f, "tool")
            row = box.row(align=True)
            row.prop(f, "edge_size")
            if f.edge_size > 0:
                row.prop(f, "edge_mode", text="")
            if p.use_mirror and (p.mirror_x or p.mirror_y or p.mirror_z):
                box.prop(f, "mirror_tool")
            if f.info:
                box.label(text=f.info, icon="CHECKMARK" if f.ok else "ERROR")
            row = box.row(align=True)
            op = row.operator("minicad.swap_existing_bool", text="Gövde ⇄ İkincil",
                              icon="UV_SYNC_SELECT")
            op.index = i
            op = row.operator("minicad.remove_feature", text="Sil", icon="TRASH")
            op.index = i
        else:
            layout.label(text="Ayrıntı için listeden bir boolean seç")


# ================================================================ fillet

class MINICAD_PT_fillet(_Sub, bpy.types.Panel):
    bl_label = "Mini CAD: Fillet"
    bl_idname = "MINICAD_PT_fillet"
    bl_order = 5
    bl_options = {"DEFAULT_CLOSED"}

    def draw_header(self, context):
        self.layout.prop(get_target(context).cad, "use_bevels", text="")

    def draw(self, context):
        layout = self.layout
        p = get_target(context).cad
        layout.operator("minicad.rebuild", text="Yenile (baştan hesapla)", icon="FILE_REFRESH")
        layout.active = p.use_bevels
        col = layout.column(align=True)
        col.prop(p, "corner_mode", text="Köşe")
        if p.corner_mode == "TRANSITION":
            col.prop(p, "transition_factor")
        if p.corner_mode != "EDGEWISE":
            col.prop(p, "smooth_corners")
        layout.prop(p, "default_bevel", text="Yeni fillet ölçüsü")
        row = layout.row(align=True)
        row.prop(p, "ghost_bevel", icon="GHOST_ENABLED")
        row.prop(p, "preview_bevel", text="Önizlemede gerçek")

        if not any(f.op != "BOOLEAN" for f in p.features):
            layout.label(text="Kenar seçiminde kenarları seç, B'ye bas", icon="INFO")
            return
        layout.template_list("MINICAD_UL_features", "bevels", p, "features", p, "active_bevel",
                             rows=4)
        i = p.active_bevel
        if 0 <= i < len(p.features) and p.features[i].op != "BOOLEAN":
            f = p.features[i]
            box = layout.box()
            row = box.row(align=True)
            row.prop(f, "kind", text="")
            row.prop(f, "size")
            if len(f.geo_edges):
                box.label(text=f"{len(f.segs)} tel kafes + {len(f.geo_edges)} gövde kenarı "
                               "(boolean'dan)", icon="EDGESEL")
            if f.info:
                box.label(text=f.info, icon="NONE" if f.ok else "ERROR")
            op = box.operator("minicad.remove_feature", text="Fillet'i Sil", icon="TRASH")
            op.index = i
        else:
            layout.label(text="Ayrıntı için listeden bir fillet seç")


# ================================================================ işlem sırası

class MINICAD_PT_order(_Sub, bpy.types.Panel):
    bl_label = "Mini CAD: İşlem Sırası"
    bl_idname = "MINICAD_PT_order"
    bl_order = 6
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        p = get_target(context).cad
        if not len(p.features):
            layout.label(text="Henüz fillet ya da boolean yok")
            return
        layout.label(text="Yukarıdan aşağı uygulanır (ör. fillet → kesim → fillet)")
        row = layout.row()
        row.template_list("MINICAD_UL_features", "order", p, "features", p, "active_order",
                          rows=4)
        col = row.column(align=True)
        i = p.active_order
        op = col.operator("minicad.move_feature", text="", icon="TRIA_UP")
        op.index, op.direction = i, -1
        op = col.operator("minicad.move_feature", text="", icon="TRIA_DOWN")
        op.index, op.direction = i, 1
        col.separator()
        op = col.operator("minicad.remove_feature", text="", icon="X")
        op.index = i


# ================================================================ ayarlar

class MINICAD_PT_settings(_Sub, bpy.types.Panel):
    bl_label = "Mini CAD: Ayarlar"
    bl_idname = "MINICAD_PT_settings"
    bl_order = 7
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        p = get_target(context).cad
        col = layout.column(align=True)
        col.prop(p, "live")
        col.prop(p, "preview")
        col.prop(p, "preview_bevel")
        col.prop(p, "ghost_bevel")
        if hasattr(context.scene, "minicad_grid_alpha"):
            col.prop(context.scene, "minicad_grid_alpha", slider=True)
        col = layout.column(align=True)
        col.prop(p, "lin_defl")
        col.prop(p, "ang_defl")
        col.prop(p, "join_tol")
        box = layout.box()
        c = core._client()
        try:
            prefs = context.preferences.addons[__package__].preferences
            box.prop(prefs, "background")
        except Exception:
            pass
        box.label(text=c.describe(), icon="CHECKMARK" if c.mode == "process" else "INFO")
        layout.operator("minicad.diag", icon="INFO")


# ================================================================ export

class MINICAD_PT_export(_Sub, bpy.types.Panel):
    bl_label = "Mini CAD: Export"
    bl_idname = "MINICAD_PT_export"
    bl_order = 8
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        r = layout.row()
        r.scale_y = 1.3
        r.operator("minicad.export_step", icon="EXPORT")
        layout.label(text="Bevel ve boolean'lar dahil, birim: mm")


classes = (
    MINICAD_UL_patches,
    MINICAD_UL_features,
    MINICAD_PT_main,
    MINICAD_PT_select,
    MINICAD_PT_constraints,
    MINICAD_PT_surfaces,
    MINICAD_PT_mirror,
    MINICAD_PT_boolean,
    MINICAD_PT_fillet,
    MINICAD_PT_order,
    MINICAD_PT_settings,
    MINICAD_PT_export,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
