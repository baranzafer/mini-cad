"""BlendCAD arayüzü (v0.27.0, işlevler v0.28.0): sağ üstte 'BlendCAD' başlatıcı düğmesi ve üstte yatay şerit.

- Başlatıcı: 3D görünümün sağ üstünde, gezinme gizmosunun solunda duran 2B gizmo düğmesi
  (Forge v2'deki gibi tek tıkla başlatma). İsteğe bağlı olarak başlık çubuğunda da düğme
  gösterilebilir (Tercihler).
- Şerit: BLENDCAD_OT_workspace kalıcı (modal) operatörü; yalnızca açıldığı 3D görünümde
  çizilir, şerit üzerindeki tık / tekerlek olaylarını tüketir, geri kalan her olay Blender'a
  geçer (PASS_THROUGH).

v0.28.0: düğmeler ribbon_actions.dispatch ile Mini CAD işlevlerine bağlı; düğme durumları
(açık / etkin araç) ribbon_actions.state / active ile Blender'dan okunur. Şerit, görünümün üst
üste binen başlık / araç başlığı bölgelerinin altına yerleşir.
"""

import time

import blf
import bpy
import gpu
from gpu_extras.batch import batch_for_shader

from . import notify, ribbon, ribbon_actions, ribbon_ctx, ribbon_state

_STATE = ribbon_state.STATE
_STATE.setdefault("capture", False)


def _now():
    return time.monotonic()


def prefs():
    try:
        a = bpy.context.preferences.addons.get(__package__)
        return a.preferences if a else None
    except Exception:
        return None


def _pref(name, default):
    p = prefs()
    return getattr(p, name, default) if p is not None else default


def legacy_panels():
    """Eski N panelleri gösterilsin mi (geçiş dönemi seçeneği)."""
    return bool(_pref("legacy_panels", False))


def is_running():
    return _STATE["running"]


# ---------------------------------------------------------------- GPU ressamı

def _round_pts(x0, y0, x1, y1, r, n=4):
    import math
    r = max(0.0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    if r <= 0.5:
        return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -math.pi / 2), (x1 - r, y1 - r, 0.0),
                       (x0 + r, y1 - r, math.pi / 2), (x0 + r, y0 + r, math.pi)):
        for k in range(n + 1):
            a = a0 + (math.pi / 2) * k / n
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


class GPUPainter:
    def __init__(self, region_w, region_h):
        self.vp = (region_w, region_h)
        self._flat = gpu.shader.from_builtin("UNIFORM_COLOR")
        self._line = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")

    def _fan(self, pts, col):
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        verts = [(cx, cy)] + list(pts)
        n = len(pts)
        idx = [(0, 1 + i, 1 + (i + 1) % n) for i in range(n)]
        batch = batch_for_shader(self._flat, "TRIS", {"pos": verts}, indices=idx)
        self._flat.bind()
        self._flat.uniform_float("color", col)
        batch.draw(self._flat)

    def rect(self, x0, y0, x1, y1, col, r=0):
        if x1 <= x0 or y1 <= y0:
            return
        self._fan(_round_pts(x0, y0, x1, y1, r), col)

    def outline(self, x0, y0, x1, y1, col, r=0, width=1.0):
        pts = _round_pts(x0, y0, x1, y1, r)
        seg = []
        for i in range(len(pts)):
            seg += [pts[i], pts[(i + 1) % len(pts)]]
        self.lines(seg, col, width)

    def lines(self, seg, col, width):
        if not seg:
            return
        batch = batch_for_shader(self._line, "LINES", {"pos": [(p[0], p[1], 0.0) for p in seg]})
        self._line.bind()
        self._line.uniform_float("viewportSize", self.vp)
        self._line.uniform_float("lineWidth", width)
        self._line.uniform_float("color", col)
        batch.draw(self._line)

    def tri(self, pts, col):
        batch = batch_for_shader(self._flat, "TRIS", {"pos": list(pts)})
        self._flat.bind()
        self._flat.uniform_float("color", col)
        batch.draw(self._flat)

    def circle(self, cx, cy, r, col):
        import math
        self._fan([(cx + r * math.cos(k * math.pi / 8), cy + r * math.sin(k * math.pi / 8))
                   for k in range(16)], col)

    @staticmethod
    def _size(size):
        try:
            blf.size(0, size)
        except TypeError:
            blf.size(0, size, 72)

    def text(self, x, y, txt, col, size, bold=False):
        self._size(size)
        blf.color(0, *col)
        blf.position(0, x, y, 0)
        blf.draw(0, txt)
        if bold:                              # yazı tipi 0'ın kalını yok: yarım piksel kaydır
            blf.position(0, x + 0.6, y, 0)
            blf.draw(0, txt)

    def measure(self, txt, size, bold=False):
        self._size(size)
        return blf.dimensions(0, txt)


# ---------------------------------------------------------------- bölge yardımcıları

def _scale(context):
    return context.preferences.system.ui_scale


def _reserves(context, area, s):
    """(sol, sağ, üst): görünümün üstüne binen araç çubuğu / N paneli / başlıklar."""
    return ribbon_state.insets(area, context.preferences.system.use_region_overlap)


def _window_region(area):
    for r in area.regions:
        if r.type == "WINDOW":
            return r
    return None


# ---------------------------------------------------------------- şerit operatörü

def _draw_ribbon():
    ctx = bpy.context
    area = ctx.area
    if area is None or _STATE["area"] != area.as_pointer():
        return
    rb = _STATE["ribbon"]
    region = ctx.region
    if rb is None or region is None:
        return
    try:
        s = _scale(ctx)
        rb.s = s
        left, right_ui, top = _reserves(ctx, area, s)
        p = GPUPainter(region.width, region.height)
        lw = 34 * s + p.measure("BlendCAD", int(12 * s))[0]
        right = right_ui + 104 * s + lw + 10 * s if _pref("show_launcher", True) else right_ui
        gpu.state.blend_set("ALPHA")
        rb.draw(p, region.width, region.height, left, right, now=_now(), top_reserve=top)
    except Exception as e:  # pragma: no cover - yalnızca Blender'da
        print("[BlendCAD] şerit çizilemedi:", e)
    finally:
        gpu.state.blend_set("NONE")


class BLENDCAD_OT_workspace(bpy.types.Operator):
    """BlendCAD şeridini aç / kapat"""
    bl_idname = "blendcad.workspace"
    bl_label = "BlendCAD"
    bl_description = "BlendCAD çizim şeridini aç / kapat (CAD araçları üstte yatay panelde)"

    _handle = None
    _hov = None
    _timer = None

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def invoke(self, context, event):
        if _STATE["running"]:
            _STATE["close"] = True
            _redraw_all(context)
            return {"FINISHED"}
        if _STATE["ribbon"] is None:
            _STATE["ribbon"] = ribbon.Ribbon(_scale(context))
        rb = _STATE["ribbon"]
        rb.on_action = self._on_action
        rb.state_fn = ribbon_actions.state
        rb.active_fn = ribbon_actions.active
        _setup_forms(rb)
        rb.hover = None
        rb.fly = None
        _STATE.update(running=True, close=False, area=context.area.as_pointer())
        _migrate_scene(context.scene)
        _hide_text(context.area)
        BLENDCAD_OT_workspace._handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_ribbon, (), "WINDOW", "POST_PIXEL")
        BLENDCAD_OT_workspace._hov = bpy.types.SpaceView3D.draw_handler_add(
            _draw_hover, (), "WINDOW", "POST_VIEW")
        BLENDCAD_OT_workspace._timer = context.window_manager.event_timer_add(
            0.05, window=context.window)
        context.window_manager.modal_handler_add(self)
        _redraw_all(context)
        return {"RUNNING_MODAL"}

    def _on_action(self, kind, item):
        if kind == "CLOSE":
            _STATE["close"] = True
            return None
        return ribbon_actions.dispatch(bpy.context, kind, item)

    def _finish(self, context):
        if BLENDCAD_OT_workspace._handle is not None:
            bpy.types.SpaceView3D.draw_handler_remove(BLENDCAD_OT_workspace._handle, "WINDOW")
            BLENDCAD_OT_workspace._handle = None
        if BLENDCAD_OT_workspace._hov is not None:
            bpy.types.SpaceView3D.draw_handler_remove(BLENDCAD_OT_workspace._hov, "WINDOW")
            BLENDCAD_OT_workspace._hov = None
        ribbon_ctx.clear()
        if _STATE["ribbon"] is not None:
            _STATE["ribbon"].menu.close()
        if BLENDCAD_OT_workspace._timer is not None:
            context.window_manager.event_timer_remove(BLENDCAD_OT_workspace._timer)
            BLENDCAD_OT_workspace._timer = None
        _restore_text(context)
        rb = _STATE["ribbon"]
        if rb is not None:
            rb.forms.close()
        _STATE.update(running=False, close=False, area=None, capture=False)
        _close_tools()
        _redraw_all(context)

    def cancel(self, context):
        self._finish(context)

    def modal(self, context, event):
        rb = _STATE["ribbon"]
        area = ribbon_state.find_area(context, _STATE["area"])
        if _STATE["close"] or rb is None:
            self._finish(context)
            return {"FINISHED"}
        if area is None:
            # alan kapandı / büyütüldü (Ctrl+Space): fare altındaki 3D görünüme taşın
            a = context.area
            if a is not None and a.type == "VIEW_3D":
                _restore_text(context)
                _STATE["area"] = a.as_pointer()
                _hide_text(a)
                area = a
            else:
                return {"PASS_THROUGH"}
        region = _window_region(area)
        if region is None:
            return {"PASS_THROUGH"}
        now = _now()
        if event.type == "TIMER":
            if rb.tick(now):
                area.tag_redraw()
            return {"PASS_THROUGH"}
        mx, my = event.mouse_x - region.x, event.mouse_y - region.y
        inside = 0 <= mx <= region.width and 0 <= my <= region.height
        try:
            return self._modal_events(context, event, rb, area, mx, my, inside, now)
        finally:
            _STATE["capture"] = rb.capturing()

    def _modal_events(self, context, event, rb, area, mx, my, inside, now):
        et, press = event.type, event.value == "PRESS"
        # pencerede sayı yazılıyor / sürükleniyor: klavye ve fare pencerenin
        if rb.capturing():
            if et in ("MOUSEMOVE", "INBETWEEN_MOUSEMOVE"):
                rb.move(mx, my, now, event.shift)
                area.tag_redraw()
                return {"RUNNING_MODAL"}
            if et == "LEFTMOUSE" and not press:
                rb.release(mx, my)
                area.tag_redraw()
                return {"RUNNING_MODAL"}
            if et == "LEFTMOUSE" and press:
                rb.press(mx, my, now)
                area.tag_redraw()
                return {"RUNNING_MODAL"}
            if press and rb.key(et, event.unicode, event.ctrl, event.shift):
                area.tag_redraw()
                return {"RUNNING_MODAL"}
            return {"RUNNING_MODAL"} if et not in ("TIMER", "TIMER_REPORT") else \
                {"PASS_THROUGH"}
        if not inside:
            if rb.leave(now):
                area.tag_redraw()
            return {"PASS_THROUGH"}
        nc = notify.CENTER
        if et in ("MOUSEMOVE", "INBETWEEN_MOUSEMOVE"):
            ch = nc.move(mx, my)
            if rb.move(mx, my, now, event.shift) or ch:
                area.tag_redraw()
            if _idle(context) and not rb.contains(mx, my) and not nc.contains(mx, my):
                region = _window_region(area)
                if ribbon_ctx.hover_update(context, area, region, mx, my):
                    area.tag_redraw()
            elif ribbon_ctx.clear():
                area.tag_redraw()
            return {"PASS_THROUGH"}
        if et == "RIGHTMOUSE":
            if not press:
                if getattr(self, "_eat_rmb", False):
                    self._eat_rmb = False
                    return {"RUNNING_MODAL"}
                return {"RUNNING_MODAL"} if rb.contains(mx, my) else {"PASS_THROUGH"}
            if rb.menu.is_open():
                rb.menu.press(mx, my)
                area.tag_redraw()
                self._eat_rmb = True
                return {"RUNNING_MODAL"}
            if rb.contains(mx, my):
                return {"RUNNING_MODAL"}
            t = ribbon_ctx.HOVER["target"]
            if t is not None and _idle(context) and ribbon_ctx.open_menu(t, mx, my):
                self._eat_rmb = True
                return {"RUNNING_MODAL"}
            return {"PASS_THROUGH"}
        if nc.contains(mx, my) and et in ("LEFTMOUSE", "RIGHTMOUSE", "MIDDLEMOUSE"):
            if et == "LEFTMOUSE" and press:
                nc.press(mx, my)
                area.tag_redraw()
            return {"RUNNING_MODAL"}
        over = rb.contains(mx, my) or rb.fly is not None or rb.forms.drop is not None
        if et == "LEFTMOUSE":
            if press and over:
                used = rb.press(mx, my, now)
                area.tag_redraw()
                if _STATE["close"]:
                    self._finish(context)
                    return {"FINISHED"}
                return {"RUNNING_MODAL"} if used else {"PASS_THROUGH"}
            if not press and rb.release(mx, my):
                area.tag_redraw()
                return {"RUNNING_MODAL"}
            if rb.contains(mx, my):
                return {"RUNNING_MODAL"}
            return {"PASS_THROUGH"}
        if et in ("RIGHTMOUSE", "MIDDLEMOUSE") and rb.contains(mx, my):
            return {"RUNNING_MODAL"}
        if et in ("WHEELUPMOUSE", "WHEELDOWNMOUSE") and rb.contains(mx, my):
            rb.wheel(mx, my, -1 if et == "WHEELUPMOUSE" else 1)
            area.tag_redraw()
            return {"RUNNING_MODAL"}
        if et == "ESC" and press and rb.escape():
            area.tag_redraw()
            return {"RUNNING_MODAL"}
        return {"PASS_THROUGH"}


def _idle(context):
    """CAD aracı açık değil ve obje modundayız: boşta üzerine gelme / sağ tık menüsü."""
    return (ribbon_actions.draw_op() is None and ribbon_actions.pick_op() is None and
            ribbon_actions.split_op() is None and ribbon_actions.hole_op() is None and
            ribbon_actions.extrude_op() is None and
            getattr(context, "mode", "") == "OBJECT")


def _draw_hover():
    ctx = bpy.context
    if ctx.area is None or _STATE["area"] != ctx.area.as_pointer():
        return
    try:
        ribbon_ctx.draw_hover(ctx)
    except Exception as e:  # pragma: no cover
        print("[BlendCAD] vurgu çizilemedi:", e)


def _migrate_scene(sc):
    """v0.30.0: eski dosyalarda 'Önce düzlem' açık kaydedilmiş olabilir; araçlar artık otomatik
    düzlemle açılır. Bir kez kapatılır (sonra kullanıcı isterse yeniden açar)."""
    try:
        if not sc.get("blendcad_v30_plane"):
            sc.minicad_pick_plane = False
            sc["blendcad_v30_plane"] = 1
    except Exception:
        pass


# ---------------------------------------------------------------- bildirim merkezi

def body_entries(scene):
    """Görünür CAD gövdelerinin süren hata / uyarıları: [(seviye, metin)]."""
    from .bool_overlay import short_error
    out = []
    for ob in getattr(scene, "objects", ()):
        try:
            props = ob.cad
            if not props.is_cad or not ob.visible_get():
                continue
        except Exception:
            continue
        for pt in props.patches:
            if not pt.enabled:
                continue
            info = pt.info or ""
            if not pt.ok:
                out.append(("error", f"{ob.name} · {pt.name}: {info}"))
            elif "UYARI" in info:
                out.append(("warn", f"{ob.name} · {pt.name}: {info[info.index('UYARI'):]}"))
        for f in props.features:
            if f.enabled and not f.ok:
                out.append(("error", f"{ob.name} · {f.name}: {short_error(f.info)}"))
    return out


def _draw_notify():
    ctx = bpy.context
    area, region = ctx.area, ctx.region
    if area is None or region is None:
        return
    if _STATE["running"] and _STATE["area"] != area.as_pointer():
        return                                   # şerit açıkken yalnız onun görünümünde
    try:
        now = _now()
        c = notify.CENTER
        c.sync("body", body_entries(ctx.scene), now)
        c.expire(now)
        s = ctx.preferences.system.ui_scale
        left, _r, _t = ribbon_state.insets(area, ctx.preferences.system.use_region_overlap)
        bottom = 0.0
        for r in area.regions:      # altta pencereye binen bölgeler (varlık rafı vb.)
            if r.type in ("ASSET_SHELF", "ASSET_SHELF_HEADER", "HEADER", "TOOL_HEADER") and \
                    r.height > 1 and r.y < region.y + region.height * 0.5 and \
                    r.y + r.height > region.y:
                bottom = max(bottom, r.y + r.height - region.y)
        p = GPUPainter(region.width, region.height)
        gpu.state.blend_set("ALPHA")
        _draw_repair_markers(p, ctx, region, s)
        w = min(440, max(260, (region.width - left) / s - 140))
        c.draw(p, s, left + 10 * s, bottom + 10 * s, w, now)
    except Exception as e:  # pragma: no cover
        print("[BlendCAD] bildirimler çizilemedi:", e)
    finally:
        gpu.state.blend_set("NONE")


def _draw_repair_markers(p, ctx, region, s):
    """Yüzey onarımı bekliyorsa sorun noktalarında halka."""
    from . import health, repair
    pts = repair.marker_points() + [("H" + lv, q) for lv, q in health.marker_points()]
    if not pts or ctx.region_data is None:
        return
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    from mathutils import Vector
    col = notify.COL_ERR
    for kind, w in pts:
        q = location_3d_to_region_2d(region, ctx.region_data, Vector(tuple(w)))
        if q is None:
            continue
        c = col if kind in ("BRANCH", "Herror") else \
            ((0.55, 0.72, 1.0, 1.0) if kind == "Hhint" else (1.0, 0.66, 0.22, 1.0))
        for r in (9 * s, 10.5 * s):
            seg = []
            import math
            for k in range(24):
                a0, a1 = k * math.pi / 12, (k + 1) * math.pi / 12
                seg += [(q.x + r * math.cos(a0), q.y + r * math.sin(a0)),
                        (q.x + r * math.cos(a1), q.y + r * math.sin(a1))]
            p.lines(seg, c, 1.6)


def _notify_tick():
    try:
        if notify.CENTER.expire(_now()):
            _redraw_all(bpy.context)
    except Exception:
        pass
    return 1.0


_NOTIFY = {"handle": None}


def _close_tools():
    """BlendCAD kapanınca CAD araçları da kapanır: taslak kaydedilir (eski palete / panele
    düşülmez)."""
    for mod in ("draw", "pick", "split", "hole", "extrude"):
        try:
            m = __import__(f"{__package__}.{mod}", fromlist=["cleanup_all"])
            m.cleanup_all()
        except Exception as e:  # pragma: no cover
            print(f"[BlendCAD] {mod} kapatılamadı:", e)


# ---------------------------------------------------------------- araç pencereleri

def _rna_meta(owner, name):
    from .ribbon_forms import Meta
    rna = owner.bl_rna.properties[name]
    t = rna.type
    if t == "ENUM":
        return Meta("ENUM", rna.name, rna.description,
                    items=[(i.identifier, i.name, i.description) for i in rna.enum_items])
    if t in ("FLOAT", "INT"):
        return Meta(t, rna.name, rna.description, min=rna.hard_min, max=rna.hard_max,
                    soft_min=rna.soft_min, soft_max=rna.soft_max, step=float(rna.step),
                    precision=getattr(rna, "precision", 0), unit=getattr(rna, "unit", "NONE"))
    return Meta(t, rna.name, rna.description)


def _fmt(meta, v):
    from .ribbon_forms import default_fmt
    us = bpy.context.scene.unit_settings
    if meta.type == "FLOAT" and meta.unit == "LENGTH" and us.system != "NONE":
        return bpy.utils.units.to_string(us.system, "LENGTH", v * us.scale_length,
                                         precision=max(3, meta.precision or 3),
                                         split_unit=False, compatible_unit=False)
    if meta.type == "FLOAT" and meta.unit == "ROTATION" and us.system_rotation == "RADIANS":
        return f"{v:.4f}"
    return default_fmt(meta, v)


def _parse(meta, text):
    from .ribbon_forms import default_parse
    us = bpy.context.scene.unit_settings
    if meta.type == "FLOAT" and meta.unit == "LENGTH" and us.system != "NONE":
        try:
            return bpy.utils.units.to_value(us.system, "LENGTH", text) / (us.scale_length or 1.0)
        except Exception:
            pass
    return default_parse(meta, text)


def _undo_push(text):
    try:
        bpy.ops.ed.undo_push(message=f"BlendCAD: {text}")
    except Exception:
        pass


def _setup_forms(rb):
    f = rb.forms
    f.meta_fn, f.fmt_fn, f.parse_fn = _rna_meta, _fmt, _parse
    f.ctx_fn = lambda: bpy.context
    f.on_commit = _undo_push

    def message(text):
        rb.toast = (text, _now())
        notify.CENTER.push(notify.level_of(text), text, _now())
        _redraw_all(bpy.context)
    f.on_message = message
    rb.notify = lambda text: notify.CENTER.push(notify.level_of(text), text, _now())
    ribbon_actions.HOOKS["message"] = message
    ribbon_actions.HOOKS["open_form"] = lambda fid, title, icon, spec, width: \
        rb.open_form(fid, title, icon, spec, width)


def _hide_text(area):
    """Görünüm adı / istatistik yazısı GPU çizimlerinin üstüne çizilir ve şeridin üstüne biner:
    şerit açıkken gizlenir, kapanınca eski hâline döner (tercihe bağlı)."""
    _STATE["text"] = None
    if not _pref("hide_view_text", True):
        return
    try:
        ov = area.spaces.active.overlay
        _STATE["text"] = (area.as_pointer(), bool(ov.show_text))
        ov.show_text = False
    except Exception:
        _STATE["text"] = None


def _restore_text(context):
    saved = _STATE.get("text")
    _STATE["text"] = None
    if not saved:
        return
    area = ribbon_state.find_area(context, saved[0])
    if area is None:
        return
    try:
        area.spaces.active.overlay.show_text = saved[1]
    except Exception:
        pass


def _redraw_all(context):
    try:
        for win in context.window_manager.windows:
            for a in win.screen.areas:
                if a.type == "VIEW_3D":
                    a.tag_redraw()
    except Exception:
        pass


# ---------------------------------------------------------------- başlatıcı gizmo

def _launcher_geom(context, p=None):
    region = context.region
    s = _scale(context)
    _left, right, top = _reserves(context, context.area, s)
    if p is None:
        GPUPainter._size(int(12 * s))
        tw = blf.dimensions(0, "BlendCAD")[0]
    else:
        tw = p.measure("BlendCAD", int(12 * s))[0]
    return region, s, right, ribbon.launcher_rect(region.width, region.height, s, right, tw, top)


class BLENDCAD_GT_launcher(bpy.types.Gizmo):
    bl_idname = "BLENDCAD_GT_launcher"

    def draw(self, context):
        region = context.region
        s = _scale(context)
        _left, right, top = _reserves(context, context.area, s)
        p = GPUPainter(region.width, region.height)
        gpu.state.blend_set("ALPHA")
        try:
            ribbon.draw_launcher(p, region.width, region.height, s, right,
                                 hover=self.is_highlight, active=is_running(), top_reserve=top)
        finally:
            gpu.state.blend_set("NONE")

    def test_select(self, context, location):
        _r, _s, _right, (x0, y0, x1, y1) = _launcher_geom(context)
        return 0 if (x0 <= location[0] <= x1 and y0 <= location[1] <= y1) else -1


class BLENDCAD_GGT_launcher(bpy.types.GizmoGroup):
    bl_idname = "BLENDCAD_GGT_launcher"
    bl_label = "BlendCAD başlatıcı"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"PERSISTENT"}           # '3D' yok: bölge piksellerinde 2B gizmo

    @classmethod
    def poll(cls, context):
        return bool(_pref("show_launcher", True))

    def setup(self, context):
        gz = self.gizmos.new(BLENDCAD_GT_launcher.bl_idname)
        gz.target_set_operator(BLENDCAD_OT_workspace.bl_idname)
        gz.use_draw_modal = True
        self.gz = gz


def _header_button(self, context):
    if not _pref("header_button", False):
        return
    row = self.layout.row(align=True)
    row.operator(BLENDCAD_OT_workspace.bl_idname, text="BlendCAD", icon="MESH_CUBE",
                 depress=is_running())


@bpy.app.handlers.persistent
def _on_load_pre(*_a):
    if _STATE["running"]:
        _STATE["close"] = True


classes = (BLENDCAD_OT_workspace, BLENDCAD_GT_launcher, BLENDCAD_GGT_launcher)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    ribbon_actions.register()
    _NOTIFY["handle"] = bpy.types.SpaceView3D.draw_handler_add(_draw_notify, (), "WINDOW",
                                                               "POST_PIXEL")
    if not bpy.app.timers.is_registered(_notify_tick):
        bpy.app.timers.register(_notify_tick, first_interval=1.0, persistent=True)
    bpy.types.VIEW3D_HT_header.append(_header_button)
    bpy.app.handlers.load_pre.append(_on_load_pre)


def unregister():
    if _on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load_pre)
    bpy.types.VIEW3D_HT_header.remove(_header_button)
    if _NOTIFY["handle"] is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(_NOTIFY["handle"], "WINDOW")
        except Exception:
            pass
        _NOTIFY["handle"] = None
    if bpy.app.timers.is_registered(_notify_tick):
        bpy.app.timers.unregister(_notify_tick)
    for attr in ("_handle", "_hov"):
        h = getattr(BLENDCAD_OT_workspace, attr)
        if h is not None:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(h, "WINDOW")
            except Exception:
                pass
            setattr(BLENDCAD_OT_workspace, attr, None)
    _STATE.update(running=False, close=False, area=None)
    ribbon_actions.unregister()
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
