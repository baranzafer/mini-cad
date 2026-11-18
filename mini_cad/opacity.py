"""Gövde saydamlığı (v0.34.0).

Çizime devam ederken katı gövdenin arkasındaki referans görseli görebilmek için gövde
başına saydamlık (cad.opacity) ve isteğe bağlı "çizerken saydam" kipi.

Gövdenin kendi malzemesine dokunulmaz: saydamken ilk malzeme yuvası OBJE bağlantılı
geçici bir malzemeyle (BlendCAD Saydam · <gövde>) örtülür; tam opak olunca yuva eski
(veri) bağlantısına döner. Katı görünümde malzeme rengi alfası, Malzeme önizlemesinde
Principled BSDF alfası ve harmanlanmış yüzey kullanılır; nesne rengi alfası da ayarlanır
(görünüm "Nesne" rengindeyse).
"""
import bpy

PREFIX = "BlendCAD Saydam · "
BASE_RGB = (0.62, 0.66, 0.72)


def _drawing():
    try:
        from . import draw_common
        return draw_common._STATE.get("active") is not None
    except Exception:
        return False


def effective(ob, drawing=None):
    a = float(getattr(ob.cad, "opacity", 1.0))
    sc = bpy.context.scene
    if drawing is None:
        drawing = _drawing()
    if drawing and getattr(sc, "minicad_draw_ghost", False):
        a = min(a, float(getattr(sc, "minicad_draw_opacity", 0.35)))
    return max(0.02, min(1.0, a))


def _material(ob, alpha):
    name = PREFIX + ob.name
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_fake_user = False
        src = None
        if ob.material_slots and ob.material_slots[0].link == "DATA":
            src = ob.material_slots[0].material
        rgb = tuple(src.diffuse_color[:3]) if src is not None else BASE_RGB
        mat.diffuse_color = rgb + (alpha,)
        try:
            mat.use_nodes = True
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf is not None:
                bsdf.inputs["Base Color"].default_value = rgb + (1.0,)
        except Exception:
            pass
    c = mat.diffuse_color
    mat.diffuse_color = (c[0], c[1], c[2], alpha)
    try:
        bsdf = mat.node_tree.nodes.get("Principled BSDF") if mat.node_tree else None
        if bsdf is not None:
            bsdf.inputs["Alpha"].default_value = alpha
    except Exception:
        pass
    for attr, val in (("surface_render_method", "BLENDED"), ("blend_method", "BLEND")):
        try:
            setattr(mat, attr, val)
        except Exception:
            pass
    try:
        mat.show_transparent_back = True
        mat.use_backface_culling = False
    except Exception:
        pass
    return mat


def apply(ob, drawing=None):
    """Gövdenin görünür saydamlığını uygular (malzeme + nesne rengi)."""
    if ob is None or ob.type != "MESH" or not getattr(ob.cad, "is_cad", False):
        return
    a = effective(ob, drawing)
    try:
        c = ob.color
        ob.color = (c[0], c[1], c[2], a)
    except Exception:
        pass
    try:
        ob.show_transparent = a < 0.999
    except Exception:
        pass
    if a >= 0.999:
        if ob.material_slots and ob.material_slots[0].link == "OBJECT" and \
                ob.material_slots[0].material is not None and \
                ob.material_slots[0].material.name.startswith(PREFIX):
            ob.material_slots[0].material = None
            ob.material_slots[0].link = "DATA"
        return
    if not ob.material_slots:
        ob.data.materials.append(None)
    slot = ob.material_slots[0]
    mat = _material(ob, a)
    if slot.link != "OBJECT":
        slot.link = "OBJECT"
    if slot.material is not mat:
        slot.material = mat


def apply_all(drawing=None):
    try:
        objs = list(bpy.context.scene.objects)
    except Exception:
        return
    for ob in objs:
        if ob.type == "MESH" and getattr(ob.cad, "is_cad", False):
            try:
                apply(ob, drawing)
            except Exception:
                pass


def on_change(self, context):
    """cad.opacity güncellemesi (self: MINICAD_ObjectProps)."""
    ob = self.id_data
    try:
        apply(ob)
    except Exception:
        pass


def on_scene_change(self, context):
    apply_all()


def register():
    bpy.types.Scene.minicad_draw_ghost = bpy.props.BoolProperty(
        name="Çizerken saydam", description="Çizim aracı açıkken bütün gövdeler saydam "
        "görünür; arkadaki referans görsele bakarak çizmeye devam edilir", default=False,
        update=on_scene_change)
    bpy.types.Scene.minicad_draw_opacity = bpy.props.FloatProperty(
        name="Çizerken opaklık", description="Çizerken saydam kipinde gövde opaklığı",
        default=0.35, min=0.02, max=1.0, subtype="FACTOR", update=on_scene_change)


def unregister():
    for p in ("minicad_draw_ghost", "minicad_draw_opacity"):
        try:
            delattr(bpy.types.Scene, p)
        except Exception:
            pass
