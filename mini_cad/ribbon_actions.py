"""BlendCAD şerit düğmelerini Mini CAD işlevlerine bağlar (v0.28.0; v0.29.0 araç pencereleri).

- Çizim araçları ve kısıtlar: açık çizim aracına (minicad.draw) araç değiştirtir; çizim kapalıysa
  önce açar (önce düzlem seçimi, sonra araç — Inventor gibi).
- Operatörler: kenar seçimi, yüzey bölme, mesh → tel kafes, çöz, yenile, STEP, tanı, kayıt.
- Ayar gerektiren işlemler (Boolean, Fillet, Süpürme, Yüzeyler, Simetri, İşlem sırası, Ayarlar,
  Kısıt listesi, Gövde, Çekirdek, Kenar seçimi, Yüzeyi böl, Mesh → tel kafes): şeridin altına
  açılan BlendCAD araç penceresi (ribbon_forms + ribbon_formspecs).
- Yalnızca kısayolu olan işlemler (G, T, C, F, Q, D, X / Y / Z, Shift+Tab, Ctrl+Z; kenar seçiminde
  Enter / B / P / Backspace / Tab; yüzey bölmede R / K) düğmelerden de çalışır: düğme, açık
  aracın kalıcı operatörüne aynı tuşu gönderir (key_*), yani klavyeyle birebir aynı kod çalışır.
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
DRAW_TOOLS["DELETE"] = "DELETE"
DRAW_TOOLS["DELETE_SK"] = "DELETE"            # Eskiz sekmesindeki kopya (v0.30.0)

CONS_TOOLS = {"DIM", "AUTODIM", "HORIZ", "VERT", "AXIS", "PARALLEL", "PERP", "COLLINEAR", "EQUAL",
              "COINCIDENT", "FIX", "TANGENT", "SMOOTH", "CONCENTRIC", "SYMLINE", "SYMMETRIC",
              "DISTANCE", "ANGLE", "RADIUS"}

PLANES = {"PL_PICK": "PICK", "PL_AUTO": "AUTO", "PL_XY": "XY", "PL_XZ": "XZ", "PL_YZ": "YZ",
          "PL_VIEW": "VIEW"}

BOOL_TYPES = {"BOOL_DIFF": "CUT", "BOOL_UNION": "UNION", "BOOL_INT": "INTERSECT"}

# aç / kapa düğmesi -> sahne ayarı (ve açık değeri)
SCENE_TOGGLES = {
    "CONS_SHOW": ("minicad_show_constraints", True),
    "CONS_AUTO": ("minicad_auto_constraints", True),
    "OPT_GRID": ("minicad_grid_snap", True),
    "OPT_LOOK": ("minicad_look_at", True),
    "OPT_FIRST": ("minicad_pick_plane", True),
    "OPT_NEW": ("minicad_draw_target", "NEW"),
    "OPT_GHOST": ("minicad_draw_ghost", True),
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


def _override(context, **extra):
    if not hasattr(context, "temp_override"):        # test / arka plan bağlamı
        import contextlib
        return contextlib.nullcontext()
    return _override_real(context, **extra)


def _override_real(context, **extra):
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
    kw.update(extra)
    if not hasattr(context, "temp_override"):        # test / arka plan bağlamı
        import contextlib
        return contextlib.nullcontext()
    return context.temp_override(**kw)


def _call(context, fn, **extra):
    """Operatörü şeridin görünümünde çağır; poll hatasını okunur iletiye çevir."""
    with _override(context, **extra):
        try:
            fn()
            return None
        except RuntimeError as e:
            txt = str(e).strip().splitlines()[-1] if str(e).strip() else "çalıştırılamadı"
            return txt.replace("Error: ", "")


def _ensure_draw(context, start_plane="DEFAULT"):
    op = draw_op()
    if op is None:
        err = _call(context, lambda: bpy.ops.minicad.draw("INVOKE_DEFAULT",
                                                          start_plane=start_plane))
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


# ---------------------------------------------------------------- araç pencereleri için

form_state = {}          # pencerelerin oturum içi seçimleri (ör. kısıt listesinde seçili satır)
HOOKS = {"open_form": None, "message": None}


def prefs():
    try:
        a = bpy.context.preferences.addons.get(__package__)
        return a.preferences if a else None
    except Exception:
        return None


def pick_op():
    try:
        from . import pick
        return pick._STATE["active"]
    except Exception:
        return None


def split_op():
    try:
        from . import split
        return split._STATE["active"]
    except Exception:
        return None


def _msg(text):
    if text and HOOKS["message"]:
        HOOKS["message"](text)


def call(opname, invoke=False, _obj=None, **kw):
    """Pencere düğmesinden operatör çağır (şeridin görünümünde); hata bildirime gider.
    _obj: işlemin hedef gövdesi (aktif obje sayılır; sağ tık menüsü)."""
    ns, name = opname.split(".")
    fn = getattr(getattr(bpy.ops, ns), name)
    extra = {"active_object": _obj, "object": _obj} if _obj is not None else {}
    err = _call(bpy.context, (lambda: fn("INVOKE_DEFAULT", **kw)) if invoke else
                (lambda: fn(**kw)), **extra)
    _msg(err)
    return err


class _Ev:
    """Kalıcı operatöre gönderilen yapay tuş olayı (klavyeyle aynı kod yolu)."""

    def __init__(self, etype, mx, my, shift=False, ctrl=False, alt=False):
        self.type, self.value = etype, "PRESS"
        self.shift, self.ctrl, self.alt, self.oskey = shift, ctrl, alt, False
        self.unicode = ""
        self.mouse_x, self.mouse_y = mx, my
        self.is_repeat = False


def send_key(op, etype, shift=False, ctrl=False, alt=False):
    """Açık aracın modal'ına tuş gönder. İmleç olarak aracın son fare konumu (yoksa bölge
    ortası) kullanılır."""
    if op is None:
        return False
    region = getattr(op, "region", None)
    if region is None:
        return False
    m = getattr(op, "mouse", None)
    if not m or (m[0] == 0.0 and m[1] == 0.0):
        m = (region.width / 2, region.height / 2)
    ev = _Ev(etype, region.x + m[0], region.y + m[1], shift, ctrl, alt)
    ctx = bpy.context
    with _override(ctx):
        try:
            op.modal(bpy.context, ev)
        except Exception as e:
            _msg(f"Hata: {e}")
            return False
    try:
        op.area.tag_redraw()
    except Exception:
        pass
    return True


def key_pick(etype, ctrl=False, shift=False):
    op = pick_op()
    if op is None:
        _msg("Kenar seçimi kapalı: önce Kenar seç")
        return False
    return send_key(op, etype, shift=shift, ctrl=ctrl)


def key_split(etype):
    return send_key(split_op(), etype)


def key_draw(context, etype, shift=False, ctrl=False, start=True):
    op = draw_op()
    if op is None:
        if not start:
            _msg("Çizim açık değil (Eskiz başlat)")
            return None
        op, _s = _ensure_draw(context)
    send_key(op, etype, shift=shift, ctrl=ctrl)
    return op


# şerit kimliği -> (tuş, shift, ctrl): çizim aracına gönderilir
DRAW_KEYS = {
    "KEY_G": ("G", False, False), "KEY_T": ("T", False, False), "KEY_C": ("C", False, False),
    "KEY_Q": ("Q", False, False), "KEY_D": ("D", False, False),
    "KEY_COORD": ("TAB", True, False),
    "AX_X": ("X", False, False), "AX_Y": ("Y", False, False), "AX_Z": ("Z", False, False),
    "SK_SURF": ("F", False, False), "SK_SURF_NEW": ("F", False, True),
    "SK_HIST_UNDO": ("Z", False, True), "SK_REDO": ("Z", True, True),
}


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
    if bid == "DELETE_SK":
        return bool(op is not None and getattr(op, "tool", "") == "DELETE")
    if bid == "KEY_COORD":
        return bool(op is not None and getattr(op, "coord_mode", False))
    if bid == "KEY_G":
        return bool(op is not None and getattr(op, "temp", None) is not None)
    if bid == "KEY_T":
        return bool(op is not None and getattr(op, "track", None) is not None)
    if bid == "AXLOCK":
        return bool(op is not None and getattr(op, "axis_lock", None) is not None)
    if bid in EXT_KINDS:
        op = extrude_op()
        f = op.feature() if op is not None else None
        if f is None:
            return False
        return bid == "EXTRUDE" or EXT_KINDS[bid] == f.ext_kind
    if bid in ("HOLE", "TAPPED"):
        op = hole_op()
        f = op.feature() if op is not None else None
        if f is None:
            return False
        return (bid == "TAPPED") == (f.hole_kind == "TAPPED")
    if bid in ("PATCH", "FILLET", "BOOL", "SWEEP", "BODY", "ORDER", "SETTINGS", "CONS_LIST",
               "SURF_LIST", "BLEND", "KERNEL", "WIRE_MESH"):
        return _form_open(bid)
    return None


FORM_BUTTONS = {"FILLET": ("FILLET_R", "CHAMFER"), "BOOL": ("BOOL_DIFF", "BOOL_UNION", "BOOL_INT"),
                "BLEND": ("BLEND_G0", "BLEND_G1")}


def _form_open(bid):
    rb = ribbon_state.STATE.get("ribbon")
    if rb is None or rb.forms.form is None:
        return False
    fid = rb.forms.form["id"]
    return fid == bid or fid in FORM_BUTTONS.get(bid, ())


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
    eop = extrude_op()
    if eop is not None and ident not in EXT_KINDS and ident != "EXT_LIST" and (
            ident in DRAW_TOOLS or ident in CONS_TOOLS or ident in PLANES or ident in DRAW_KEYS
            or ident in HOLE_KINDS
            or ident in ("SK_START", "EDGE_PICK", "PATCH", "PATCH_HOLE", "SPLIT_FACE",
                         "FILLET_R", "CHAMFER", "EDIT_ALL")):
        eop.finish(context)                # ekstrüzyon açıkken başka araç: yapılan kalır
    op = hole_op()
    if op is not None and ident not in HOLE_KINDS and ident != "HOLE_LIST" and (
            ident in DRAW_TOOLS or ident in CONS_TOOLS or ident in PLANES or ident in DRAW_KEYS
            or ident in ("SK_START", "EDGE_PICK", "PATCH", "PATCH_HOLE", "SPLIT_FACE",
                         "FILLET_R", "CHAMFER", "EDIT_ALL")):
        op.finish(context)                 # delik aracı açıkken başka araç: delikler kalır

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
            _ensure_draw(context, "PICK")          # Eskiz başlat: düzlemi açıkça seçtir
            return "Çizim düzlemini seç (eksen düzlemi ya da gövde yüzü)"
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

    # ---- kısayol düğmeleri (tuş aktarımı)
    if ident in DRAW_KEYS:
        k, sh, ct = DRAW_KEYS[ident]
        op = key_draw(context, k, sh, ct, start=ident not in ("SK_HIST_UNDO", "SK_REDO"))
        return None if op is not None else None

    # ---- tel kafes · yüzey
    if ident in ("EDGE_PICK", "PATCH"):
        if not _pick_running():
            err = _call(context, lambda: bpy.ops.minicad.pick_edges("INVOKE_DEFAULT"))
            if err:
                return err
        elif ident == "EDGE_PICK" and _form_is(ident):
            _call(context, lambda: bpy.ops.minicad.pick_edges("INVOKE_DEFAULT"))   # kapat
            _close_form()
            return "Kenar seçimi kapatıldı"
        _open(ident, keep=True)
        return None
    if ident == "PATCH_HOLE":
        op, _s = _ensure_draw(context)
        _after(context, op)
        return "Dış döngüyü ve delikleri aynı düzlemde çiz · F (Yüzey düğmesi): yüzey"
    if ident == "SPLIT_FACE":
        if not _split_running():
            err = _call(context, lambda: bpy.ops.minicad.split_surface("INVOKE_DEFAULT"))
            if err:
                return err
        _open(ident, keep=True)
        return None
    if ident in ("BLEND_G0", "BLEND_G1"):
        t = _target(context)
        if t is not None:
            t.cad.surface_blend = "SHARP" if ident == "BLEND_G0" else "TANGENT"
        _open(ident, keep=True)
        return None

    # ---- ekstrüzyon (v0.34.0)
    if ident in EXT_KINDS:
        return _extrude(context, EXT_KINDS[ident])
    if ident == "EXT_LIST":
        _open("EXTRUDE", keep=True)
        return None
    # ---- delik (v0.33.0)
    if ident in HOLE_KINDS:
        return _hole(context, HOLE_KINDS[ident])
    if ident == "HOLE_LIST":
        _open("HOLE", keep=True)
        return None

    # ---- katı
    if ident in BOOL_TYPES:
        sc.minicad_bool_type = BOOL_TYPES[ident]
        _open(ident, keep=True)
        return None
    if ident in ("FILLET_R", "CHAMFER"):
        if not _pick_running() and _target(context) is not None and _kernel_ready():
            _call(context, lambda: bpy.ops.minicad.pick_edges("INVOKE_DEFAULT"))
        _open(ident)
        return None
    if ident == "REBUILD":
        return _call(context, lambda: bpy.ops.minicad.rebuild())

    # ---- uzun hesap (v0.35.0)
    if ident == "CALC_STOP":
        from . import core
        n = core.cancel_running()
        return f"{n}: hesap durduruldu" if n else "Süren arka plan hesabı yok"
    if ident == "CALC_CONT":
        from . import core
        t = _target(context)
        if t is None:
            return "Önce bir gövde seç"
        return core.continue_full(t.name)

    # ---- araçlar
    if ident == "CONS_SOLVE":
        return _call(context, lambda: bpy.ops.minicad.constraint_solve()) or "Kısıtlar çözüldü"
    if ident == "STEP":
        return _call(context, lambda: bpy.ops.minicad.export_step("INVOKE_DEFAULT"))
    if ident == "DIAG":
        return _call(context, lambda: bpy.ops.minicad.diag())
    if ident == "REC":
        return _call(context, lambda: bpy.ops.minicad.record("INVOKE_DEFAULT"))

    if _forms().get(ident):
        _open(ident)
        return None
    return None


EXT_KINDS = {"EXTRUDE": "", "EXT_LINEAR": "LINEAR", "EXT_THICK": "THICK"}


def extrude_op():
    try:
        from . import extrude
        return extrude._STATE["active"]
    except Exception:
        return None


def _extrude(context, kind, pick=None):
    """Ekstrüzyon aracını başlat. kind '': başlarken türü sor. Açıksa türü değiştirir.
    pick: (dünya nokta, dışa normal) — sağ tık menüsünden gelen yüz."""
    op = extrude_op()
    if op is not None:
        if kind:
            op.set_kind(context, kind)
        _open("EXTRUDE", keep=True)
        return None
    if _target(context) is None:
        return "Önce bir gövde gerekli (Yüzey → Sınır yüzeyi, Ctrl+Enter: yeni gövde)"
    if not _kernel_ready():
        return "Hesap çekirdeği kurulu değil (Araçlar → Çekirdek)"
    kw = {"kind": kind}
    if pick is not None:
        kw.update(pick_co=tuple(pick[0]), pick_nrm=tuple(pick[1]), has_pick=True)
    err = _call(context, lambda: bpy.ops.minicad.extrude("INVOKE_DEFAULT", **kw))
    if err:
        return err
    op = extrude_op()
    form_state["ext_uid"] = op.fuid if op is not None else form_state.get("ext_uid")
    _open("EXTRUDE", keep=True)
    if not kind:
        return "Ekstrüzyon türünü seç: Doğrusal ya da Kalınlaştır"
    return "Yüzeyin üzerine gel (ok belirir) · tıkla · oku sürükle"


HOLE_KINDS = {"HOLE": "SIMPLE", "HOLE_CBORE": "CBORE", "HOLE_CSK": "CSINK", "TAPPED": "TAPPED"}


def hole_op():
    try:
        from . import hole
        return hole._STATE["active"]
    except Exception:
        return None


def _hole(context, kind):
    """Delik aracını başlat (açıksa açık deliğin türünü değiştir) ve pencereyi aç."""
    from . import hole
    op = hole_op()
    if op is not None:
        f = op.feature()
        if f is not None and f.hole_kind != kind:
            f.hole_kind = kind
            if kind == "TAPPED" and f.hole_thread == "NONE":
                f.hole_thread = "M6"
            hole.apply_preset(f)
        _open("HOLE", keep=True)
        return None
    if _target(context) is None:
        return "Delik için önce bir gövde gerekli (Yüzey → Sınır yüzeyi)"
    if not _kernel_ready():
        return "Hesap çekirdeği kurulu değil (Araçlar → Çekirdek)"
    err = _call(context, lambda: bpy.ops.minicad.hole("INVOKE_DEFAULT", kind=kind))
    if err:
        return err
    op = hole_op()
    if op is not None and kind == "TAPPED":
        f = op.feature()
        if f is not None:
            if f.hole_thread == "NONE":
                f.hole_thread = "M6"
            hole.apply_preset(f)
    form_state["hole_uid"] = op.fuid if op is not None else form_state.get("hole_uid")
    _open("HOLE", keep=True)
    return "Yüzeye tıkla: delik yeri · Enter: bitir"


def _forms():
    from . import ribbon_formspecs
    return ribbon_formspecs.FORMS


def _form_is(ident):
    rb = ribbon_state.STATE.get("ribbon")
    return rb is not None and rb.forms.is_open(ident)


def _close_form():
    rb = ribbon_state.STATE.get("ribbon")
    if rb is not None:
        rb.forms.close()


def _open(ident, keep=False):
    """Araç penceresini aç. keep: aynı pencere açıksa kapatma (araç yeniden seçildi)."""
    spec = _forms().get(ident)
    if spec is None or HOOKS["open_form"] is None:
        return
    if keep and _form_is(ident):
        return
    title, icon, fn, width = spec
    HOOKS["open_form"](ident, title, icon, fn, width)


classes = ()


def register():
    pass


def unregister():
    pass
