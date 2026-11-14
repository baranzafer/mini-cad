"""Operatörler, N paneli ve eklenti tercihleri."""

import os
import sys

import bpy
from bpy_extras.io_utils import ExportHelper

from . import core, kernel


def get_target(context):
    ob = context.active_object
    if ob is not None and ob.cad.is_cad:
        return ob
    t = context.scene.minicad_target
    if t is not None and t.name in context.scene.objects:
        return t
    return None


def _selected_curves(context):
    return [o for o in context.selected_objects if o.type == "CURVE"]


def _edit_curve_objects(context):
    objs = list(getattr(context, "objects_in_mode", None) or [])
    if not objs and context.edit_object is not None:
        objs = [context.edit_object]
    return [o for o in objs if o.type == "CURVE"]


def gather_selection(context):
    """('segs', [(obj, spline, seg)]) edit modunda, ('curves', [obj]) obje modunda."""
    if context.mode == "EDIT_CURVE":
        return "segs", core.selected_segment_refs(_edit_curve_objects(context))
    if context.mode == "OBJECT":
        return "curves", _selected_curves(context)
    return None, []


# ================================================================ çekirdek

class MINICAD_OT_install_kernel(bpy.types.Operator):
    bl_idname = "minicad.install_kernel"
    bl_label = "Çekirdeği Kur (OpenCASCADE)"
    bl_description = "OCP kütüphanesini internetten indirip kurar. Birkaç dakika sürebilir"

    def execute(self, context):
        kernel.start_install()
        self.report({"INFO"}, "Kurulum arka planda başladı")
        return {"FINISHED"}


class MINICAD_OT_check_kernel(bpy.types.Operator):
    bl_idname = "minicad.check_kernel"
    bl_label = "Tekrar Kontrol Et"

    def execute(self, context):
        if kernel.kernel_available(force=True):
            self.report({"INFO"}, "Çekirdek yüklendi")
        else:
            self.report({"WARNING"}, f"Yüklenemedi: {kernel.last_error()}")
        return {"FINISHED"}


class MINICAD_OT_diag(bpy.types.Operator):
    bl_idname = "minicad.diag"
    bl_label = "Tanı Raporu"
    bl_description = "Kurulum bilgisini toplar, panoya kopyalar ve 'MiniCAD_Tani' metnine yazar"

    def execute(self, context):
        from . import diag
        report = diag.build_report()
        print(report)
        context.window_manager.clipboard = report
        txt = bpy.data.texts.get("MiniCAD_Tani") or bpy.data.texts.new("MiniCAD_Tani")
        txt.clear()
        txt.write(report)
        self.report({"INFO"}, "Tanı raporu panoya kopyalandı (Ctrl+V ile yapıştır)")
        return {"FINISHED"}


# ================================================================ model

def _add_patch(cad_ob, kind, items):
    props = cad_ob.cad
    p = props.patches.add()
    p.name = f"Yüzey {len(props.patches)}"
    if kind == "segs":
        for ob, si, i in items:
            r = p.segs.add()
            r.obj, r.spline, r.seg = ob, si, i
    else:
        for c in items:
            p.curves.add().obj = c
    props.active_patch = len(props.patches) - 1
    return p


def apply_surface(context, kind, items, new_body=False):
    """Hedef varsa yüzey ekler, yoksa (veya new_body ise) yeni CAD objesi oluşturur.
    (başarılı mı, mesaj)."""
    target = None if new_body else get_target(context)
    if target is None:
        me = bpy.data.meshes.new("CAD_Govde")
        ob = bpy.data.objects.new("CAD_Govde", me)
        context.collection.objects.link(ob)
        ob.cad.is_cad = True
        core.forget_cache(ob.name)   # aynı adlı eski bir gövdenin önbelleği karışmasın
        _add_patch(ob, kind, items)
        if not core.rebuild(ob):
            msg = ob.cad.status
            bpy.data.objects.remove(ob)
            bpy.data.meshes.remove(me)
            return False, f"Yüzey oluşturulamadı: {msg}"
        context.scene.minicad_target = ob
        if context.view_layer.objects.active is not None and \
                context.view_layer.objects.active.cad.is_cad and context.mode == "OBJECT":
            context.view_layer.objects.active = ob
        return True, f"Yeni gövde '{ob.name}' oluşturuldu ve hedef yapıldı"

    added = 0
    if kind == "segs":
        pool = [r for p in target.cad.patches for r in core.patch_refs(p)]
        try:
            items, added = core.complete_loop(items, pool, target.cad.join_tol)
        except core.CadError as e:
            return False, str(e)
    patch = _add_patch(target, kind, items)
    core.rebuild(target)
    if not patch.ok:
        msg = patch.info
        target.cad.patches.remove(len(target.cad.patches) - 1)
        target.cad.active_patch = max(0, len(target.cad.patches) - 1)
        core.forget_cache(target.name)
        core.rebuild(target)
        return False, f"Yüzey eklenemedi: {msg}"
    extra = f" ({added} kenar komşu yüzeyden tamamlandı)" if added else ""
    return True, f"{target.name}: {len(target.cad.patches)} yüzey{extra}"


def add_feature(context, refs):
    """Seçili kenarlara yeni bir bevel ekler ve hemen hesaplar. (başarılı mı, mesaj)."""
    target = get_target(context)
    if target is None:
        return False, "Önce yüzey oluştur (hedef CAD objesi yok)"
    props = target.cad
    f = props.features.add()
    props.active_bevel = len(props.features) - 1
    f.name = f"Fillet {len(props.features)}"
    f.size = props.default_bevel
    n_body = 0
    for ref in refs:
        if isinstance(ref, tuple) and len(ref) == 3 and ref[0] == "BODY":
            # gövde kenarı: ("BODY", boolean uid, kenar çizgisi)
            _, src, poly = ref
            g = f.geo_edges.add()
            g.id, g.src, g.data = core.new_uid(), src, core.geo_desc_json(poly)
            n_body += 1
            continue
        ob, si, i = ref
        r = f.segs.add()
        r.obj, r.spline, r.seg = ob, si, i
    core.rebuild(target)
    if not f.ok:
        msg = f.info
        props.features.remove(len(props.features) - 1)
        core.rebuild(target)
        return False, f"Bevel eklenemedi: {msg}"
    extra = f" · {n_body} gövde kenarı" if n_body else ""
    return True, f"{f.name}: {f.info}{extra} · ölçüyü panelden ayarla"


class MINICAD_OT_remove_patch(bpy.types.Operator):
    bl_idname = "minicad.remove_patch"
    bl_label = "Yüzeyi Sil"
    bl_options = {"REGISTER", "UNDO"}

    index: bpy.props.IntProperty()

    def execute(self, context):
        target = get_target(context)
        if target is None or not (0 <= self.index < len(target.cad.patches)):
            return {"CANCELLED"}
        target.cad.patches.remove(self.index)
        core.forget_cache(target.name)
        if len(target.cad.patches):
            core.rebuild(target)
        else:
            target.data.clear_geometry()
            target.cad.status = "Yüzey yok"
        return {"FINISHED"}


class MINICAD_OT_select_patch_curves(bpy.types.Operator):
    bl_idname = "minicad.select_patch_curves"
    bl_label = "Eğrilerini Seç"
    bl_description = "Bu yüzeyi tanımlayan eğrileri seçer"
    bl_options = {"REGISTER", "UNDO"}

    index: bpy.props.IntProperty()

    def execute(self, context):
        target = get_target(context)
        if target is None or not (0 <= self.index < len(target.cad.patches)):
            return {"CANCELLED"}
        context.scene.minicad_target = target
        patch = target.cad.patches[self.index]
        if context.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for o in context.selected_objects:
            o.select_set(False)

        if len(patch.segs):
            objs = []
            for r in patch.segs:
                if r.obj is not None and r.obj not in objs:
                    objs.append(r.obj)
            if not objs:
                return {"CANCELLED"}
            for o in objs:
                o.select_set(True)
            context.view_layer.objects.active = objs[0]
            bpy.ops.object.mode_set(mode="EDIT")
            for o in objs:
                for sp in o.data.splines:
                    if sp.type == "BEZIER":
                        for p in sp.bezier_points:
                            p.select_control_point = False
                            p.select_left_handle = False
                            p.select_right_handle = False
                    else:
                        for p in sp.points:
                            p.select = False
            for r in patch.segs:
                if r.obj is None or r.spline >= len(r.obj.data.splines):
                    continue
                sp = r.obj.data.splines[r.spline]
                pts = sp.bezier_points if sp.type == "BEZIER" else sp.points
                n = len(pts)
                for j in (r.seg % n, (r.seg + 1) % n):
                    if sp.type == "BEZIER":
                        pts[j].select_control_point = True
                    else:
                        pts[j].select = True
            for o in objs:
                o.data.update_tag()
            context.area.tag_redraw() if context.area else None
            return {"FINISHED"}

        last = None
        for r in patch.curves:
            if r.obj is not None:
                r.obj.select_set(True)
                last = r.obj
        if last is not None:
            context.view_layer.objects.active = last
        return {"FINISHED"}


class MINICAD_OT_remove_feature(bpy.types.Operator):
    bl_idname = "minicad.remove_feature"
    bl_label = "İşlemi Sil"
    bl_options = {"REGISTER", "UNDO"}

    index: bpy.props.IntProperty()

    def execute(self, context):
        target = get_target(context)
        if target is None or not (0 <= self.index < len(target.cad.features)):
            return {"CANCELLED"}
        f = target.cad.features[self.index]
        tool = f.tool if f.op == "BOOLEAN" else None
        target.cad.features.remove(self.index)
        if tool is not None and not any(x.op == "BOOLEAN" and x.tool == tool
                                        for x in target.cad.features):
            tool.display_type = "TEXTURED"
            tool.hide_render = False
        core.rebuild(target)
        return {"FINISHED"}


def _tool_candidates(context, target):
    out = [o for o in context.selected_objects if o.type == "MESH" and o != target]
    act = context.active_object
    if act in out:
        out.remove(act)
        out.insert(0, act)
    return out


BOOL_NAMES = {"CUT": "Kesim", "UNION": "Ekleme", "INTERSECT": "Kesişim"}


class MINICAD_OT_add_boolean(bpy.types.Operator):
    bl_idname = "minicad.add_boolean"
    bl_label = "Boolean Ekle"
    bl_description = ("Paneldeki 'Araç' objesini 'Ana gövde'ye seçili işlemle uygular. Araç kapalı "
                      "bir hacim olmalı (mesh ya da kapalı CAD gövdesi); taşıdıkça sonuç güncellenir")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        sc = context.scene
        t, tool = sc.minicad_target, sc.minicad_bool_tool
        return t is not None and tool is not None and tool != t

    def execute(self, context):
        sc = context.scene
        target, tool = sc.minicad_target, sc.minicad_bool_tool
        props = target.cad
        if any(f.op == "BOOLEAN" and f.tool == tool for f in props.features):
            self.report({"WARNING"}, f"'{tool.name}' zaten bu gövdede araç olarak kullanılıyor")
            return {"CANCELLED"}
        f = props.features.add()
        props.active_bool = len(props.features) - 1
        f.op = "BOOLEAN"
        f.bool_type = sc.minicad_bool_type
        f.tool = tool
        f.name = f"{BOOL_NAMES[f.bool_type]} {len(props.features)}"
        tool.display_type = "WIRE"
        tool.hide_render = True
        core.rebuild(target, preview=False)
        if f.ok:
            self.report({"INFO"}, f"{f.name}: {f.info}")
        else:
            self.report({"WARNING"}, f"{f.name}: {f.info}")
        sc.minicad_bool_tool = None
        return {"FINISHED"}


class MINICAD_OT_pick_bool_tool(bpy.types.Operator):
    bl_idname = "minicad.pick_bool_tool"
    bl_label = "Aktif Objeyi İkincil Yap"
    bl_description = "Viewport'ta aktif (son seçilen) objeyi boolean'ın ikincil parçası yapar"

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return (ob is not None and ob.type == "MESH"
                and ob != context.scene.minicad_target)

    def execute(self, context):
        context.scene.minicad_bool_tool = context.active_object
        return {"FINISHED"}


class MINICAD_OT_swap_bool(bpy.types.Operator):
    bl_idname = "minicad.swap_bool"
    bl_label = "Gövde ⇄ İkincil"
    bl_description = "Gövde ile ikincil parçanın yerini değiştirir (ikisi de CAD gövdesi olmalı)"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        sc = context.scene
        return sc.minicad_target is not None and sc.minicad_bool_tool is not None

    def execute(self, context):
        sc = context.scene
        body, other = sc.minicad_target, sc.minicad_bool_tool
        if not other.cad.is_cad:
            self.report({"WARNING"}, f"'{other.name}' bir CAD gövdesi değil, gövde yapılamaz "
                        "(gövde tel kafesten oluşturulmuş olmalı)")
            return {"CANCELLED"}
        sc.minicad_bool_tool = None
        sc.minicad_target = other
        sc.minicad_bool_tool = body
        self.report({"INFO"}, f"Gövde: {other.name} · İkincil: {body.name}")
        return {"FINISHED"}


class MINICAD_OT_swap_existing_bool(bpy.types.Operator):
    bl_idname = "minicad.swap_existing_bool"
    bl_label = "Gövde ⇄ İkincil (bu boolean)"
    bl_description = ("Uygulanmış boolean'ı diğer gövdeye taşır: ikincil parça gövde, gövde "
                      "ikincil olur. Her ikisi de CAD gövdesi olmalı")
    bl_options = {"REGISTER", "UNDO"}

    index: bpy.props.IntProperty()

    def execute(self, context):
        body = get_target(context)
        if body is None or not (0 <= self.index < len(body.cad.features)):
            return {"CANCELLED"}
        f = body.cad.features[self.index]
        other = f.tool
        if f.op != "BOOLEAN" or other is None:
            return {"CANCELLED"}
        if not other.cad.is_cad:
            self.report({"WARNING"}, f"'{other.name}' bir CAD gövdesi değil, gövde yapılamaz")
            return {"CANCELLED"}
        if any(x.op == "BOOLEAN" and x.tool == body for x in other.cad.features):
            self.report({"WARNING"}, f"'{other.name}' zaten '{body.name}' ile boolean içeriyor")
            return {"CANCELLED"}
        data = dict(name=f.name, bool_type=f.bool_type, edge_size=f.edge_size,
                    edge_mode=f.edge_mode, mirror_tool=f.mirror_tool, enabled=f.enabled)
        body.cad.features.remove(self.index)
        g = other.cad.features.add()
        g.op = "BOOLEAN"
        for k, v in data.items():
            setattr(g, k, v)
        g.tool = body
        other.cad.active_bool = len(other.cad.features) - 1
        # görünürlük: yeni ikincil tel kafes, yeni gövde katı
        body.display_type = "WIRE"
        body.hide_render = True
        other.display_type = "TEXTURED"
        other.hide_render = False
        context.scene.minicad_target = other
        core.forget_cache(body.name)
        core.forget_cache(other.name)
        core.rebuild(body, preview=False)
        core.rebuild(other, preview=False)
        self.report({"INFO"}, f"Gövde: {other.name} · İkincil: {body.name}")
        return {"FINISHED"}


class MINICAD_OT_set_target_active(bpy.types.Operator):
    bl_idname = "minicad.set_target_active"
    bl_label = "Aktif Gövdeyi Ana Gövde Yap"

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return ob is not None and ob.cad.is_cad

    def execute(self, context):
        sc = context.scene
        sc.minicad_target = context.active_object
        if sc.minicad_bool_tool == context.active_object:
            sc.minicad_bool_tool = None
        return {"FINISHED"}


class MINICAD_OT_move_feature(bpy.types.Operator):
    bl_idname = "minicad.move_feature"
    bl_label = "Sırayı Değiştir"
    bl_description = "İşlemler listedeki sırayla uygulanır (ör. bevel → kesim → yeni kenar bevel'i)"
    bl_options = {"REGISTER", "UNDO"}

    index: bpy.props.IntProperty()
    direction: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        target = get_target(context)
        if target is None:
            return {"CANCELLED"}
        n = len(target.cad.features)
        j = self.index + self.direction
        if not (0 <= self.index < n and 0 <= j < n):
            return {"CANCELLED"}
        target.cad.features.move(self.index, j)
        target.cad.active_order = j
        core.rebuild(target)
        return {"FINISHED"}


class MINICAD_OT_export_step(bpy.types.Operator, ExportHelper):
    bl_idname = "minicad.export_step"
    bl_label = "STEP Olarak Dışa Aktar"
    bl_description = "Gövdeyi (bevel'ler dahil) STEP dosyası olarak kaydeder (birim: mm)"

    filename_ext = ".step"
    filter_glob: bpy.props.StringProperty(default="*.step;*.stp", options={"HIDDEN"})

    @classmethod
    def poll(cls, context):
        return get_target(context) is not None

    def invoke(self, context, event):
        t = get_target(context)
        folder = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.expanduser("~")
        self.filepath = os.path.join(folder, f"{t.name}.step")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        t = get_target(context)
        try:
            core.export_step(t, self.filepath)
        except core.CadError as e:
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self.report({"INFO"}, f"STEP kaydedildi: {self.filepath}")
        return {"FINISHED"}


class MINICAD_OT_rebuild(bpy.types.Operator):
    bl_idname = "minicad.rebuild"
    bl_label = "Yeniden Hesapla"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return get_target(context) is not None

    def execute(self, context):
        target = get_target(context)
        if getattr(target.data, "is_editmode", False) is True:
            # gövde mesh'i düzenleme modundayken sonuç yazılamaz (v0.25.9)
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass
        core.forget_cache(target.name)
        for f in target.cad.features:            # ikincil parçaları da yeniden oku
            if f.op == "BOOLEAN" and f.tool is not None:
                core.forget_tool(f.tool.name)
        ok = core.rebuild(target, preview=False)
        self.report({"INFO"} if ok else {"WARNING"}, target.cad.status)
        return {"FINISHED"}


# ================================================================ arayüz

def draw_kernel_box(layout):
    st = kernel.install_state()
    box = layout.box()
    if st["running"]:
        box.label(text="Kuruluyor...", icon="TIME")
        box.label(text=st["last"])
        return
    if kernel.kernel_available():
        row = box.row()
        row.label(text="Çekirdek: OpenCASCADE hazır", icon="CHECKMARK")
        row.operator(MINICAD_OT_diag.bl_idname, text="", icon="INFO")
        return
    box.label(text="Çekirdek yüklü değil", icon="ERROR")
    if kernel.last_error().startswith("Uyumsuz"):
        box.label(text=kernel.last_error())
    if st["last"]:
        box.label(text=st["last"])
    if st["log_path"]:
        box.label(text=st["log_path"])
    box.operator(MINICAD_OT_install_kernel.bl_idname, icon="IMPORT")
    box.operator(MINICAD_OT_check_kernel.bl_idname, icon="FILE_REFRESH")
    box.operator(MINICAD_OT_diag.bl_idname, icon="INFO")


def _status_icon(text):
    return "CHECKMARK" if text.startswith(("Tamam", "Önizleme")) else "ERROR"


def _on_background_pref(self, context):
    core.configure_engine()


class MINICAD_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    background: bpy.props.BoolProperty(
        name="Arka Planda Hesapla",
        description="Ağır OCC hesaplarını (fillet, boolean) ayrı bir süreçte yapar: Blender "
        "donmaz, OCC çökerse Blender kapanmaz. Kapalıysa her şey Blender içinde hesaplanır",
        default=True, update=_on_background_pref)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "background")
        layout.label(text="Hesap motoru: " + core._client().describe())
        layout.label(text=f"Blender Python: {sys.version.split()[0]}")
        layout.label(text=f"Kütüphane klasörü: {kernel.site_dir()}")
        draw_kernel_box(layout)
        if not kernel.kernel_available() and kernel.last_error():
            layout.label(text=f"Son hata: {kernel.last_error()[:200]}")


classes = (
    MINICAD_OT_install_kernel,
    MINICAD_OT_check_kernel,
    MINICAD_OT_diag,
    MINICAD_OT_remove_patch,
    MINICAD_OT_select_patch_curves,
    MINICAD_OT_remove_feature,
    MINICAD_OT_add_boolean,
    MINICAD_OT_pick_bool_tool,
    MINICAD_OT_set_target_active,
    MINICAD_OT_swap_bool,
    MINICAD_OT_swap_existing_bool,
    MINICAD_OT_move_feature,
    MINICAD_OT_export_step,
    MINICAD_OT_rebuild,
    MINICAD_Preferences,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
