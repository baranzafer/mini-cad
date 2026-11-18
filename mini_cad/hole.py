"""Delik aracı (v0.33.0, Inventor 'Hole'): gövde yüzüne tıklayarak delik yerleştir.

- Üzerine gelince: deliğin hayaleti (ağız çemberi + eksen + derinlik) imleçteki yüzde.
- Yakalama: kaydedilmiş eskiz noktaları (tek noktalı spline) ve eskiz dairelerinin merkezi
  (ekranda 12 piksel içinde) — Inventor'daki 'eskizden' yerleşim gibi.
- Tık: delik ekler (eksen yüzey normalinin tersi, malzemeye doğru); her tıkta gerçek gövde
  yeniden hesaplanır (önizleme gerçek sonuçtur). Backspace / sağ tık: son deliği geri al.
- Enter / Tamam: bitir. Esc / Vazgeç: bu oturumda eklenenleri geri al (yeni delik
  özelliğiyse onu siler).
- Ayarlar "Delik" penceresinde (tür, vida ölçüsü, çap, derinlik / tümüyle geçen, uç açısı,
  havşa ölçüleri) — değişince delikler canlı güncellenir.
"""

import math

import numpy as np

import bpy

from . import core, ribbon_state

_STATE = {"active": None}
_HANDLES = []


def is_running():
    return _STATE["active"] is not None


def cleanup_all():
    for h in list(_HANDLES):
        try:
            bpy.types.SpaceView3D.draw_handler_remove(h, "WINDOW")
        except Exception:
            pass
    _HANDLES.clear()
    op = _STATE["active"]
    if op is not None:
        op.stop_request = True
    _STATE["active"] = None


def scene_scale():
    try:
        return bpy.context.scene.unit_settings.scale_length or 1.0
    except Exception:
        return 1.0


def default_params(f, body):
    """Yeni deliğin başlangıç ölçüleri: küçük (mekanik ölçekli) gövdede M6 geçme deliği,
    büyük gövdede gövdeye orantılı yuvarlak bir çap."""
    from . import holemath
    try:
        diag = float(max(body.dimensions)) * scene_scale()
    except Exception:
        diag = 0.1
    if diag <= 0.5:
        f.hole_thread = "M6"
        apply_preset(f)
    else:
        d = diag * 0.02
        e = math.floor(math.log10(d))
        f.hole_d = round(d / 10 ** e) * 10 ** e / scene_scale()
        f.hole_cb_d, f.hole_cb_depth = f.hole_d * 1.7, f.hole_d
        f.hole_cs_d = f.hole_d * 2.0
        f.hole_depth = f.hole_d * 3.0
    del holemath


def apply_preset(f):
    """Vida ölçüsünden çap / havşa değerleri (tür değişince de çağrılır)."""
    from . import holemath
    if f.hole_thread == "NONE":
        return
    pr = holemath.preset(f.hole_kind, f.hole_thread, scene_scale())
    f.hole_d = pr["d"]
    if "cb_d" in pr:
        f.hole_cb_d, f.hole_cb_depth = pr["cb_d"], pr["cb_depth"]
    if "cs_d" in pr:
        f.hole_cs_d = pr["cs_d"]
    if not f.hole_through:
        f.hole_depth = max(f.hole_depth, pr["d"] * 2.0)


def new_feature(body, kind="SIMPLE"):
    p = body.cad
    f = p.features.add()
    f.op = "HOLE"
    f.uid = core.new_uid()
    f.name = f"Delik {sum(1 for x in p.features if x.op == 'HOLE')}"
    f.hole_kind = kind
    default_params(f, body)
    return f


def find_feature(body, uid):
    for i, f in enumerate(body.cad.features):
        if f.uid == uid:
            return i, f
    return None, None


# ---------------------------------------------------------------- yakalama

def snap_candidates(context):
    """[(dünya noktası, tür)] — eskiz noktaları ve eskiz dairelerinin merkezleri."""
    out = []
    for ob in context.visible_objects:
        if ob.type != "CURVE":
            continue
        mw = ob.matrix_world
        for sp in ob.data.splines:
            if sp.type == "BEZIER":
                pts = [mw @ b.co for b in sp.bezier_points]
            else:
                pts = [mw @ p.co.xyz for p in sp.points]
            if len(pts) == 1:
                out.append((np.array(pts[0]), "Nokta"))
            elif sp.use_cyclic_u and len(pts) >= 3:
                P = np.array([tuple(q) for q in pts])
                c = P.mean(axis=0)
                rr = np.linalg.norm(P - c, axis=1)
                if rr.mean() > 1e-9 and rr.std() < 0.02 * rr.mean():
                    out.append((c, "Daire merkezi"))
    return out


def _px(region, rv3d, p):
    from bpy_extras.view3d_utils import location_3d_to_region_2d
    from mathutils import Vector
    q = location_3d_to_region_2d(region, rv3d, Vector(tuple(p)))
    return None if q is None else (q.x, q.y)


def _ray(context, region, rv3d, mx, my, body):
    from bpy_extras import view3d_utils
    o = view3d_utils.region_2d_to_origin_3d(region, rv3d, (mx, my))
    d = view3d_utils.region_2d_to_vector_3d(region, rv3d, (mx, my))
    dg = context.evaluated_depsgraph_get()
    ok, loc, n, _idx, ob, _m = context.scene.ray_cast(dg, o, d)
    if not ok or ob is None:
        return None
    try:
        if not ob.cad.is_cad:
            return None
    except Exception:
        return None
    if body is not None and ob != body:
        return None
    if n.dot(d) > 0:                  # içeriden çarptı: normal ışına karşı baksın
        n = -n
    return ob, np.array(loc), np.array(n.normalized())


# ---------------------------------------------------------------- operatör

class MINICAD_OT_hole(bpy.types.Operator):
    """Delik: gövde yüzüne tıklayarak delik yerleştir"""
    bl_idname = "minicad.hole"
    bl_label = "Delik"
    bl_description = ("Gövde yüzüne tıklayarak düz, havşa başlı, havşalı ya da dişli delik "
                      "açar (Inventor Delik). Eskiz noktalarına ve daire merkezlerine yakalar")
    bl_options = {"REGISTER"}

    kind: bpy.props.StringProperty(default="SIMPLE", options={"HIDDEN", "SKIP_SAVE"})
    uid: bpy.props.StringProperty(default="", options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def invoke(self, context, event):
        if _STATE["active"] is not None:
            cleanup_all()
            return {"CANCELLED"}
        for mod in ("draw", "pick", "split"):
            try:
                __import__(f"{__package__}.{mod}", fromlist=["cleanup_all"]).cleanup_all()
            except Exception:
                pass
        from .ui import get_target
        body = get_target(context)
        if body is None:
            self.report({"WARNING"}, "Delik için önce bir gövde gerekli")
            return {"CANCELLED"}
        self.area = context.area
        self.region = next((r for r in self.area.regions if r.type == "WINDOW"), None)
        self.rv3d = self.area.spaces.active.region_3d
        self.body_name = body.name
        self.stop_request = False
        self.hover = None              # (nokta, normal, yakalama türü)
        self.mouse = (0.0, 0.0)
        self.created = False
        if self.uid:
            _i, f = find_feature(body, self.uid)
            if f is None:
                self.report({"WARNING"}, "Delik bulunamadı")
                return {"CANCELLED"}
        else:
            f = new_feature(body, self.kind or "SIMPLE")
            self.created = True
        self.fuid = f.uid
        self.start_pts = [(tuple(h.co), tuple(h.nrm)) for h in f.hole_pts]
        self.cands = snap_candidates(context)
        _STATE["active"] = self
        _HANDLES.append(bpy.types.SpaceView3D.draw_handler_add(_draw3d, (), "WINDOW",
                                                               "POST_VIEW"))
        context.window_manager.modal_handler_add(self)
        self._status(context)
        return {"RUNNING_MODAL"}

    # ------------------------------------------------------------ yardımcılar
    def body(self):
        return bpy.data.objects.get(self.body_name)

    def feature(self):
        b = self.body()
        return None if b is None else find_feature(b, self.fuid)[1]

    def _status(self, context, msg=""):
        f = self.feature()
        n = len(f.hole_pts) if f else 0
        txt = (f"Delik: yüzeye tıkla ({n} delik) · eskiz noktası / daire merkezine yakalar · "
               "Backspace / sağ tık: son deliği geri al · Enter: bitir · Esc: vazgeç")
        if msg:
            txt = msg + "  —  " + txt
        try:
            context.workspace.status_text_set(txt)
        except Exception:
            pass

    def _update_hover(self, context, mx, my):
        body = self.body()
        s = context.preferences.system.ui_scale
        best = None
        for p, kind in self.cands:
            q = _px(self.region, self.rv3d, p)
            if q is None:
                continue
            d = math.hypot(q[0] - mx, q[1] - my)
            if d < 12 * s and (best is None or d < best[0]):
                best = (d, p, kind, q)
        if best is not None:
            hit = _ray(context, self.region, self.rv3d, best[3][0], best[3][1], body)
            if hit is not None:
                _ob, loc, n = hit
                # nokta yüzeyin üstündeyse tam onu kullan; değilse yüzeye düşen yeri
                use = best[1] if np.linalg.norm(best[1] - loc) < 1e-3 * max(
                    1e-9, float(max(body.dimensions))) + 1e-6 else loc
                self.hover = (use, n, best[2])
                return
        hit = _ray(context, self.region, self.rv3d, mx, my, body)
        self.hover = None if hit is None else (hit[1], hit[2], None)

    def add_point(self, context, loc, n):
        body, f = self.body(), self.feature()
        if body is None or f is None:
            return
        mw = body.matrix_world
        inv = mw.inverted()
        from mathutils import Vector
        h = f.hole_pts.add()
        h.co = tuple(inv @ Vector(tuple(loc)))
        dl = inv.to_3x3() @ Vector(tuple(-n))
        h.nrm = tuple(dl.normalized())
        core.rebuild(body)
        self._status(context, f"{len(f.hole_pts)}. delik: {f.info}")

    def undo_point(self, context):
        body, f = self.body(), self.feature()
        if f is not None and len(f.hole_pts):
            f.hole_pts.remove(len(f.hole_pts) - 1)
            core.rebuild(body)
            self._status(context, "Son delik geri alındı")

    def finish(self, context, cancel=False):
        body, f = self.body(), self.feature()
        if body is not None and f is not None:
            if cancel:
                if self.created:
                    i, _f = find_feature(body, self.fuid)
                    body.cad.features.remove(i)
                else:
                    f.hole_pts.clear()
                    for co, nrm in self.start_pts:
                        h = f.hole_pts.add()
                        h.co, h.nrm = co, nrm
                core.forget_cache(body.name)
                core.rebuild(body)
            elif not len(f.hole_pts) and self.created:
                i, _f = find_feature(body, self.fuid)
                body.cad.features.remove(i)
                core.rebuild(body)
            else:
                try:
                    bpy.ops.ed.undo_push(message="BlendCAD: Delik")
                except Exception:
                    pass
        try:
            context.workspace.status_text_set(None)
        except Exception:
            pass
        cleanup_all()
        try:
            self.area.tag_redraw()
        except Exception:
            pass

    # ------------------------------------------------------------ olaylar
    def modal(self, context, event):
        if self.stop_request or _STATE["active"] is not self:
            cleanup_all() if _STATE["active"] is self else None
            return {"CANCELLED"}
        if self.feature() is None:
            self.finish(context, cancel=False)
            return {"CANCELLED"}
        if ribbon_state.over_ribbon(event):
            return {"PASS_THROUGH"}
        r = self.region
        mx, my = event.mouse_x - r.x, event.mouse_y - r.y
        inside = 0 <= mx < r.width and 0 <= my < r.height
        et, press = event.type, event.value == "PRESS"
        if et in ("MOUSEMOVE", "INBETWEEN_MOUSEMOVE"):
            if inside:
                self.mouse = (mx, my)
                self._update_hover(context, mx, my)
                self.area.tag_redraw()
            return {"PASS_THROUGH"}
        if not inside:
            return {"PASS_THROUGH"}
        if et == "LEFTMOUSE" and press and not (event.alt or event.ctrl):
            if self.hover is None:
                return {"PASS_THROUGH"}          # boşluk: Blender (gezinme / seçim)
            loc, n, _k = self.hover
            self.add_point(context, loc, n)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if et == "LEFTMOUSE":
            return {"RUNNING_MODAL"} if self.hover is not None else {"PASS_THROUGH"}
        if press and et in ("BACK_SPACE", "RIGHTMOUSE"):
            f = self.feature()
            if f is not None and len(f.hole_pts):
                self.undo_point(context)
                self.area.tag_redraw()
                return {"RUNNING_MODAL"}
            return {"PASS_THROUGH"}
        if press and et in ("RET", "NUMPAD_ENTER"):
            self.finish(context)
            return {"FINISHED"}
        if press and et == "ESC":
            self.finish(context, cancel=True)
            return {"CANCELLED"}
        return {"PASS_THROUGH"}


# ---------------------------------------------------------------- hayalet

def _circle(c, n, r, k=40):
    n = n / max(np.linalg.norm(n), 1e-15)
    a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(n, a)
    u /= np.linalg.norm(u)
    v = np.cross(n, u)
    t = np.linspace(0, 2 * math.pi, k + 1)
    return [tuple(c + r * (math.cos(x) * u + math.sin(x) * v)) for x in t]


def _draw3d():
    op = _STATE["active"]
    ctx = bpy.context
    if op is None or ctx.area is None or ctx.area != op.area or op.hover is None:
        return
    f = op.feature()
    body = op.body()
    if f is None or body is None:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    from .ribbon import COL_ACCENT
    loc, n, kind = op.hover
    d = -n                                          # malzemeye doğru
    sc = float(max(body.dimensions)) or 1.0
    R = 0.5 * f.hole_d
    depth = f.hole_depth if not f.hole_through else sc * 0.6
    seg = []

    def ring(c, r):
        P = _circle(c, d, r)
        for i in range(len(P) - 1):
            seg.extend([P[i], P[i + 1]])
    ring(loc, R)
    ring(loc + d * depth, R)
    if f.hole_kind == "CBORE":
        ring(loc, 0.5 * f.hole_cb_d)
        ring(loc + d * f.hole_cb_depth, 0.5 * f.hole_cb_d)
    elif f.hole_kind == "CSINK":
        ring(loc, 0.5 * f.hole_cs_d)
    a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(d, a)
    u /= np.linalg.norm(u)
    for sgn in (1, -1):                             # iki yan çizgi + eksen
        seg += [tuple(loc + u * R * sgn), tuple(loc + u * R * sgn + d * depth)]
    seg += [tuple(loc - d * R), tuple(loc + d * (depth + R))]
    region = ctx.region
    sh = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    gpu.state.blend_set("ALPHA")
    gpu.state.depth_test_set("NONE")
    b = batch_for_shader(sh, "LINES", {"pos": seg})
    sh.bind()
    sh.uniform_float("viewportSize", (region.width, region.height))
    sh.uniform_float("lineWidth", 2.0)
    col = (0.35, 0.85, 0.5, 0.95) if kind else (COL_ACCENT[0], COL_ACCENT[1], COL_ACCENT[2], 0.95)
    sh.uniform_float("color", col)
    b.draw(sh)
    gpu.state.blend_set("NONE")


classes = (MINICAD_OT_hole,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    cleanup_all()
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
