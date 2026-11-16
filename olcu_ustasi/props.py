# SPDX-License-Identifier: GPL-3.0-or-later
import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       FloatVectorProperty, IntProperty, PointerProperty, StringProperty)
from bpy.types import PropertyGroup

UNIT_ITEMS = [
    ('SCENE', "Sahne", "Sahnenin birim ayarlarını kullan"),
    ('MM', "mm", "Milimetre"),
    ('CM', "cm", "Santimetre"),
    ('M', "m", "Metre"),
    ('IN', "in", "İnç"),
    ('FT', "ft", "Fit"),
]

PIVOT_ITEMS = [
    ('BOX_BOTTOM', "Kutu Altı", "Seçim kutusunun alt yüz merkezi: model zeminde kalır", 'TRIA_DOWN', 0),
    ('BOX_CENTER', "Kutu Merkezi", "Seçim kutusunun merkezi", 'PIVOT_BOUNDBOX', 1),
    ('POINT_A', "A Noktası", "Ölçümün ilk noktası sabit kalır", 'PIVOT_INDIVIDUAL', 2),
    ('CURSOR', "3B İmleç", "3B imleç etrafında", 'PIVOT_CURSOR', 3),
    ('ACTIVE', "Aktif Köken", "Aktif nesnenin kökeni", 'PIVOT_ACTIVE', 4),
    ('WORLD', "Dünya Merkezi", "Dünya orijini", 'WORLD', 5),
]

PIVOT_ORDER = [i[0] for i in PIVOT_ITEMS]


def _redraw(self, context):
    for win in context.window_manager.windows:
        for area in win.screen.areas:
            if area.type in ('VIEW_3D', 'PROPERTIES'):
                area.tag_redraw()


class OU_Pin(PropertyGroup):
    a_obj: PointerProperty(type=bpy.types.Object)
    a_co: FloatVectorProperty(size=3)
    b_obj: PointerProperty(type=bpy.types.Object)
    b_co: FloatVectorProperty(size=3)
    mode: StringProperty(default="")          # '', 'X', 'Y', 'Z' ... (izdüşüm etiketi)
    axis: FloatVectorProperty(size=3)         # izdüşüm ekseni (mode varsa)
    visible: BoolProperty(name="Görünür", default=True, update=_redraw)


class OU_Settings(PropertyGroup):
    display_unit: EnumProperty(name="Birim", items=UNIT_ITEMS, default='SCENE', update=_redraw)
    precision: EnumProperty(
        name="Hassasiyet",
        items=[(str(i), "0." + "0" * i if i else "0", f"{i} ondalık") for i in range(6)],
        default='2', update=_redraw)

    # yakalama
    snap_vert: BoolProperty(name="Köşe", default=True)
    snap_edge: BoolProperty(name="Kenar", default=True)
    snap_mid: BoolProperty(name="Kenar Ortası", default=True)
    snap_face: BoolProperty(name="Yüzey", default=True)
    snap_face_center: BoolProperty(name="Yüz Merkezi", default=False)
    snap_box: BoolProperty(name="Sınır Kutusu", default=True,
                           description="Seçimin ve imleç altındaki nesnenin dış sınırlarına yapış")
    snap_origin: BoolProperty(name="Köken / İmleç", default=False)
    snap_perp: BoolProperty(name="Dik", default=True,
                            description="A noktasından kenara dik ayak")
    snap_only_selection: BoolProperty(name="Yalnız Seçime", default=False,
                                      description="Yalnızca seçili nesnelere yapış (önündekileri yok say)")
    snap_radius: IntProperty(name="Yakalama Yarıçapı", default=16, min=6, max=48, subtype='PIXEL')

    # seçim
    include_children: BoolProperty(name="Alt Nesneleri Dahil Et", default=True,
                                   description="Seçili nesnelerin alt nesneleri de bütünün parçasıdır")
    box_space: EnumProperty(
        name="Kutu Yönü",
        items=[('WORLD', "Dünya", "Dünya eksenlerine hizalı kutu"),
               ('LOCAL', "Yerel", "Aktif nesnenin eksenlerine hizalı kutu")],
        default='WORLD', update=_redraw)
    pivot: EnumProperty(name="Pivot", items=PIVOT_ITEMS, default='BOX_BOTTOM')
    apply_data: BoolProperty(
        name="Ölçeği Veriye Uygula", default=False,
        description="Bitince ölçek 1 olsun: ölçek, veriye ve değiştirici değerlerine güvenle aktarılır "
                    "(paylaşılan veriler bir kez dönüştürülür)")
    show_box: BoolProperty(name="Kutuyu Göster", default=True)
    live_preview: BoolProperty(name="Canlı Önizleme", default=True,
                               description="Değer yazarken model anında ölçeklensin")

    # panel
    lock_ratio: BoolProperty(name="Oranı Koru", default=True,
                             description="Bir boyut değişince diğerleri orantılı değişir")
    quick_factor: FloatProperty(name="Çarpan", default=2.0, min=1e-6, soft_min=0.001, soft_max=1000,
                                precision=4)

    pins: CollectionProperty(type=OU_Pin)
    pin_index: IntProperty(default=0)
    show_pins: BoolProperty(name="Sabit Ölçüleri Göster", default=True, update=_redraw)

    last_value: FloatProperty(name="Son Ölçüm", default=0.0, unit='LENGTH')
    last_text: StringProperty(default="")


classes = (OU_Pin, OU_Settings)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.olcu_ustasi = PointerProperty(type=OU_Settings)


def unregister():
    del bpy.types.Scene.olcu_ustasi
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
