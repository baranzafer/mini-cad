"""BlendCAD şerit düğmelerini Mini CAD işlevlerine bağlar (v0.28.0).

- Çizim araçları ve kısıtlar: açık çizim aracına (minicad.draw) araç değiştirtir; çizim kapalıysa
  önce açar (önce düzlem seçimi, sonra araç — Inventor gibi).
- Operatörler: kenar seçimi, yüzey bölme, mesh → tel kafes, çöz, yenile, STEP, tanı, kayıt.
- Ayar gerektiren işlemler (Boolean, Fillet, Süpürme, Yüzeyler, Simetri, İşlem sırası, Ayarlar,
  Kısıt listesi, Gövde, Çekirdek): eski N paneli içeriği açılır pencerede (wm.call_panel) gösterilir.
- Aç / kapa düğmeleri sahne ayarlarını değiştirir; düğmenin durumu her çizimde ayardan okunur.

dispatch(context, kind, item) kullanıcıya gösterilecek kısa iletiyi (ya da None) döndürür.
"""

import types

import bpy

from . import ribbon_state

# ---------------------------------------------------------------- tablolar

# şerit kimliği -> çizim aracı (minicad.draw self.tool)
DRAW_TOOLS = {k: k for k in (
    "SELECT", "LINE", "ARC3", "TARC", "CARC", "CIRCLE", "CIRCT", "ELLIPSE", "RECT", "RECT3",
    "RECTC", "RECT3C", "POLYGON", "SLOTCC", "SLOTO", "SLOTC", "ARCSLOT", "SLOTARCC", "CV", "FIT",
    "PEN", "POINT", "TEXT", "PROJECT", "EDITSK", "TRIM", "EXTEND", "SPLIT", "OFFSET", "FILLET2D",
    "CHAMFER2D", "MOVE", "COPY", "ROTATE", "SCALE", "STRETCH", "RPAT", "CPAT")}
DRAW_TOOLS["MIRROR2D"] = "MIRROR"

CONS_TOOLS = {"DIM", "AUTODIM", "HORIZ", "VERT", "AXIS", "PARALLEL", "PERP", "COLLINEAR", "EQUAL",
              "COINCIDENT", "FIX", "TANGENT", "SMOOTH", "CONCENTRIC", "SYMLINE", "SYMMETRIC",
              "DISTANCE", "ANGLE", "RADIUS"}

PLANES = {"PL_PICK": "PICK", "PL_AUTO": "AUTO", "PL_XY": "XY", "PL_XZ": "XZ", "PL_YZ": "YZ",
          "PL_VIEW": "VIEW"}

# şerit kimliği -> (panel sınıfı adı, gövde gerekir mi, başlık)
POPUPS = {
    "CONS_LIST": ("MINICAD_PT_constraints", False, "Kısıtlar ve ilişkiler"),
    "SURF_LIST": ("MINICAD_PT_surfaces", True, "Yüzeyler"),
    "BLEND_G0": ("MINICAD_PT_surfaces", True, "Yüzeyler"),
    "BLEND_G1": ("MINICAD_PT_surfaces", True, "Yüzeyler"),
    "SYM_BODY": ("MINICAD_PT_mirror", True, "Ayna simetrisi"),
    "BODY": ("MINICAD_PT_main", False, "Gövde"),
    "SWEEP": ("MINICAD_PT_sweep", True, "Profil süpürme"),
    "BOOL_DIFF": ("MINICAD_PT_boolean", True, "Boolean"),
    "BOOL_UNION": ("MINICAD_PT_boolean", True, "Boolean"),
    "BOOL_INT": ("MINICAD_PT_boolean", True, "Boolean"),
    "FILLET_R": ("MINICAD_PT_fillet", True, "Fillet / pah"),
    "CHAMFER": ("MINICAD_PT_fillet", True, "Fillet / pah"),
    "ORDER": ("MINICAD_PT_order", True, "İşlem sırası"),
    "SETTINGS": ("MINICAD_PT_settings", True, "Ayarlar"),
    "WIRE_MESH": ("MINICAD_PT_select", False, "Mesh'ten tel kafes"),
    "KERNEL": (None, False, "Çekirdek (OpenCASCADE)"),
}

BOOL_TYPES = {"BOOL_DIFF": "CUT", "BOOL_UNION": "UNION", "BOOL_INT": "INTERSECT"}

# aç / kapa düğmesi -> sahne ayarı (ve açık değeri)
SCENE_TOGGLES = {
    "CONS_SHOW": ("minicad_show_constraints", True),
    "CONS_AUTO": ("minicad_auto_constraints", True),
    "OPT_GRID": ("minicad_grid_snap", True),
    "OPT_LOOK": ("minicad_look_at", True),
    "OPT_FIRST": ("minicad_pick_plane", True),
    "OPT_NEW": ("minicad_draw_target", "NEW"),
}


# ---------------------------------------------------------------- yardımcılar

def _draw_mod():
    from . import draw
    return draw


def draw_op():
    try:
        return _draw_mod()._STATE["active"]
    except Exception:
        return None


def _override(context):
    """Şeridin açık olduğu 3D görünümün bağlamı (operatörler orada çalışsın)."""
    area = ribbon_state.find_area(context, ribbon_state.STATE["area"]) or context.area
    region = ribbon_state.window_region(area) if area is not None else None
    win = context.window
    if area is not None:
        for w in context.window_manager.windows:
            if any(a == area for a in w.screen.areas):
                win = w
                break
    kw = {"window": win, "area": area}
    if region is not None:
        kw["region"] = region
    return context.temp_override(**kw)


def _call(context, fn):
    """Operatörü şeridin görünümünde çağır; poll hatasını okunur iletiye çevir."""
    with _override(context):
        try:
            fn()
            return None
        except RuntimeError as e:
            txt = str(e).strip().splitlines()[-1] if str(e).strip() else "çalıştırılamadı"
            return txt.replace("Error: ", "")


def _ensure_draw(context):
    op = draw_op()
    if op is None:
        err = _call(context, lambda: bpy.ops.minicad.draw("INVOKE_DEFAULT"))
        op = draw_op()
        if op is None:
            raise RuntimeError(err or "Çizim açılamadı")
        return op, True
    return op, False


def _after(context, op):
    for fn in ("_refresh", "_hist_sync"):
        try:
            getattr(op, fn)(context) if fn == "_refresh" else getattr(op, fn)()
        except Exception:
            pass
    try:
        op.area.tag_redraw()
    except Exception:
        pass


def _target(context):
    try:
        from .ui import get_target
        return get_target(context)
    except Exception:
        return None


def _kernel_ready():
    try:
        from . import kernel
        return kernel.kernel_available()
    except Exception:
        return False


def _pick_running():
    try:
        from . import pick
        return pick.is_running()
    except Exception:
        return False


def _split_running():
    try:
        from . import split
        return split.is_running()
    except Exception:
        return False


# ---------------------------------------------------------------- açılır pencereler

def _draw_kernel(self, context):
    from . import core
    from .ui import draw_kernel_box
    layout = self.layout
    draw_kernel_box(layout)
    try:
        layout.label(text="Hesap motoru: " + core._client().describe())
    except Exception:
        pass
    layout.operator("minicad.check_kernel", icon="FILE_REFRESH")


def _make_popup(key, base_name, needs_target, title):
    def draw(self, context):
        from . import panels
        layout = self.layout
        row = layout.row()
        row.label(text=title, icon="TOOL_SETTINGS")
        if base_name is None:
            _draw_kernel(self, context)
            return
        base = getattr(panels, base_name)
        if base_name != "MINICAD_PT_main" and not _kernel_ready():
            from .ui import draw_kernel_box
            draw_kernel_box(layout)
            return
        if needs_target and _target(context) is None:
            col = layout.column(align=True)
            col.label(text="Gövde yok", icon="INFO")
            col.label(text="Yüzey → Sınır yüzeyi ile ilk yüzeyi oluştur")
            col.label(text="(Kenar seçimi: Enter yüzey · Ctrl+Enter yeni gövde)")
            return
        if hasattr(base, "draw_header"):
            hdr = layout.row(align=True)
            hdr.label(text="Açık:")
            base.draw_header(types.SimpleNamespace(layout=hdr), context)
        base.draw(self, context)

    return type(f"BLENDCAD_PT_pop_{key.lower()}", (bpy.types.Panel,), {
        "bl_idname": f"BLENDCAD_PT_pop_{key.lower()}",
        "bl_label": title,
        "bl_space_type": "VIEW_3D",
        "bl_region_type": "HEADER",
        "bl_ui_units_x": 17,
        "draw": draw,
    })


_POPUP_CLASSES = {}
for _k, (_base, _need, _title) in POPUPS.items():
    _key = _base or "KERNEL"
    if _key not in _POPUP_CLASSES:
        _POPUP_CLASSES[_key] = _make_popup(_key.replace("MINICAD_PT_", ""), _base, _need, _title)


def popup_idname(ident):
    base = POPUPS[ident][0] or "KERNEL"
    return _POPUP_CLASSES[base].bl_idname


def _popup(context, ident):
    name = popup_idname(ident)
    return _call(context, lambda: bpy.ops.wm.call_panel(name=name, keep_open=True))


# ---------------------------------------------------------------- durum (düğme açık mı)

def state(btn):
    """Düğmenin Blender'daki durumu; None: şerit kendi durumunu kullanır."""
    ctx = bpy.context
    bid = btn["id"]
    sc = ctx.scene
    if bid in SCENE_TOGGLES:
        prop, on = SCENE_TOGGLES[bid]
        return getattr(sc, prop, None) == on
    op = draw_op()
    if bid == "OPT_SNAP":
        return bool(getattr(op, "snap_on", True)) if op is not None else True
    if bid == "SK_START":
        return op is not None
    if bid == "PLANE":
        return op is not None and getattr(op, "phase", "") in ("PLANE", "OFFSET")
    if bid == "EDGE_PICK":
        return _pick_running()
    if bid == "SPLIT_FACE":
        return _split_running()
    if bid == "SYM_BODY":
        t = _target(ctx)
        return bool(t is not None and t.cad.use_mirror)
    if bid in ("PATCH", "FILLET"):
        return False
    return None


def active():
    """Açık çizim aracının şerit kimliği."""
    op = draw_op()
    if op is None:
        return None
    tool = getattr(op, "tool", None) or ""
    if tool.startswith("C_"):
        return tool[2:]
    if tool == "MIRROR":
        return "MIRROR2D"
    return tool


# ---------------------------------------------------------------- eylemler

def dispatch(context, kind, item):
    if kind == "CLOSE" or item is None:
        return None
    ident = item["id"]
    try:
        return _dispatch(context, kind, ident)
    except RuntimeError as e:
        return str(e)


def _dispatch(context, kind, ident):
    sc = context.scene

    # ---- aç / kapa
    if ident in SCENE_TOGGLES:
        prop, on = SCENE_TOGGLES[ident]
        cur = getattr(sc, prop)
        if isinstance(on, bool):
            setattr(sc, prop, not cur)
        else:
            setattr(sc, prop, "ACTIVE" if cur == on else on)
        op = draw_op()
        if op is not None:
            if ident == "OPT_GRID":
                op.grid_on = bool(sc.minicad_grid_snap)
            _after(context, op)
        return None
    if ident == "OPT_SNAP":
        op = draw_op()
        if op is None:
            return "Yakalama çizim açıkken değiştirilir"
        op.snap_on = not op.snap_on
        _after(context, op)
        return None

    # ---- çizim araçları ve kısıtlar
    if ident in DRAW_TOOLS or ident in CONS_TOOLS:
        tool = DRAW_TOOLS.get(ident) or ("C_" + ident)
        op, started = _ensure_draw(context)
        op._set_tool(context, tool)
        _after(context, op)
        if started and getattr(op, "phase", "") == "PLANE":
            return "Önce çizim düzlemini seç (eksen düzlemi ya da gövde yüzü)"
        return None
    if ident in PLANES:
        dm = _draw_mod().dm
        name = PLANES[ident]
        op, _started = _ensure_draw(context)
        if name in dm.AXIS_PLANES and op.phase == "PLANE":
            op._start_offset(context, name, dm.Plane.axis(name, (0.0, 0.0, 0.0)))
        else:
            op._set_plane(name)
        _after(context, op)
        return None

    # ---- eskiz
    if ident == "SK_START":
        op = draw_op()
        if op is None:
            _ensure_draw(context)
            return None
        op._set_plane("PICK")
        _after(context, op)
        return "Düzlemi yeniden seç"
    if ident in ("SK_FINISH", "SK_UNDO", "SK_CLOSE"):
        op = draw_op()
        if op is None:
            return "Çizim açık değil (Eskiz başlat)"
        if ident == "SK_FINISH":
            op._finish_sketch(context)
        elif ident == "SK_UNDO":
            op._undo_last(context)
        else:
            return _call(context, lambda: bpy.ops.minicad.draw("INVOKE_DEFAULT")) or \
                "Çizim kaydedildi ve kapatıldı"
        _after(context, op)
        return None
    if ident == "EDIT_ALL":
        err = _call(context, lambda: bpy.ops.minicad.edit_sketch("EXEC_DEFAULT"))
        return "Önce düzenlenecek çizimi (eğri objesi) seç" if err else None

    # ---- tel kafes · yüzey
    if ident in ("EDGE_PICK", "PATCH"):
        if ident == "PATCH" and _pick_running():
            return "Kenar seçimi açık: döngüyü seç · Enter: yüzey · Ctrl+Enter: yeni gövde"
        err = _call(context, lambda: bpy.ops.minicad.pick_edges("INVOKE_DEFAULT"))
        if err:
            return err
        if ident == "PATCH":
            return "Döngünün kenarlarını seç · Enter: yüzey · Ctrl+Enter: yeni gövde"
        return None
    if ident == "PATCH_HOLE":
        op, _s = _ensure_draw(context)
        _after(context, op)
        return "Dış döngüyü ve delikleri aynı düzlemde çiz · F: yüzey · Ctrl+F: yeni gövde"
    if ident == "SPLIT_FACE":
        return _call(context, lambda: bpy.ops.minicad.split_surface("INVOKE_DEFAULT"))
    if ident == "WIRE_MESH":
        if context.mode == "EDIT_MESH":
            return _call(context, lambda: bpy.ops.minicad.mesh_to_wire("INVOKE_DEFAULT"))
        return _popup(context, ident) or "Mesh düzenleme modunda kenarları seçip tekrar bas"
    if ident in ("BLEND_G0", "BLEND_G1"):
        t = _target(context)
        if t is not None:
            t.cad.surface_blend = "SHARP" if ident == "BLEND_G0" else "TANGENT"
        return _popup(context, ident)

    # ---- katı
    if ident in BOOL_TYPES:
        sc.minicad_bool_type = BOOL_TYPES[ident]
        return _popup(context, ident)
    if ident in ("FILLET_R", "CHAMFER"):
        msg = None
        if not _pick_running() and _target(context) is not None:
            msg = _call(context, lambda: bpy.ops.minicad.pick_edges("INVOKE_DEFAULT"))
        return _popup(context, ident) or msg or "Kenarları seç · B: uygula"
    if ident == "REBUILD":
        return _call(context, lambda: bpy.ops.minicad.rebuild())

    # ---- araçlar
    if ident == "CONS_SOLVE":
        return _call(context, lambda: bpy.ops.minicad.constraint_solve()) or "Kısıtlar çözüldü"
    if ident == "STEP":
        return _call(context, lambda: bpy.ops.minicad.export_step("INVOKE_DEFAULT"))
    if ident == "DIAG":
        return _call(context, lambda: bpy.ops.minicad.diag())
    if ident == "REC":
        return _call(context, lambda: bpy.ops.minicad.record("INVOKE_DEFAULT"))

    if ident in POPUPS:
        return _popup(context, ident)
    return None


classes = tuple(_POPUP_CLASSES.values())


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
