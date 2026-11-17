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

from . import ribbon, ribbon_actions, ribbon_state

_STATE = ribbon_state.STATE


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
        rb.hover = None
        rb.fly = None
        _STATE.update(running=True, close=False, area=context.area.as_pointer())
        _hide_text(context.area)
        BLENDCAD_OT_workspace._handle = bpy.types.SpaceView3D.draw_handler_add(
            _draw_ribbon, (), "WINDOW", "POST_PIXEL")
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
        if BLENDCAD_OT_workspace._timer is not None:
            context.window_manager.event_timer_remove(BLENDCAD_OT_workspace._timer)
            BLENDCAD_OT_workspace._timer = None
        _restore_text(context)
        _STATE.update(running=False, close=False, area=None)
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
        if not inside:
            if rb.leave(now):
                area.tag_redraw()
            return {"PASS_THROUGH"}
        if event.type in ("MOUSEMOVE", "INBETWEEN_MOUSEMOVE"):
            if rb.move(mx, my, now):
                area.tag_redraw()
            return {"PASS_THROUGH"}
        over = rb.contains(mx, my) or rb.fly is not None
        if event.type == "LEFTMOUSE":
            if event.value == "PRESS" and over:
                used = rb.press(mx, my, now)
                area.tag_redraw()
                if _STATE["close"]:
                    self._finish(context)
                    return {"FINISHED"}
                return {"RUNNING_MODAL"} if used else {"PASS_THROUGH"}
            if rb.contains(mx, my):
                return {"RUNNING_MODAL"}
            return {"PASS_THROUGH"}
        if event.type in ("RIGHTMOUSE", "MIDDLEMOUSE") and rb.contains(mx, my):
            return {"RUNNING_MODAL"}
        if event.type in ("WHEELUPMOUSE", "WHEELDOWNMOUSE") and rb.contains(mx, my):
            rb.wheel(mx, my, -1 if event.type == "WHEELUPMOUSE" else 1)
            area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type == "ESC" and event.value == "PRESS" and rb.escape():
            area.tag_redraw()
            return {"RUNNING_MODAL"}
        return {"PASS_THROUGH"}


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
    bpy.types.VIEW3D_HT_header.append(_header_button)
    bpy.app.handlers.load_pre.append(_on_load_pre)


def unregister():
    if _on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load_pre)
    bpy.types.VIEW3D_HT_header.remove(_header_button)
    if BLENDCAD_OT_workspace._handle is not None:
        try:
            bpy.types.SpaceView3D.draw_handler_remove(BLENDCAD_OT_workspace._handle, "WINDOW")
        except Exception:
            pass
        BLENDCAD_OT_workspace._handle = None
    _STATE.update(running=False, close=False, area=None)
    ribbon_actions.unregister()
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
