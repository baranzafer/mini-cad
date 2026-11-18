"""Ekstrüzyon aracı (v0.34.0, Inventor 'Extrude' / yüzey kalınlaştırma).

Akış:
1. Başlarken sorar: **Doğrusal** (yüz tek doğrultuda — yüz normali — uzar: prizma) mı,
   **Kalınlaştır** (yüz kendi normalleri boyunca kalınlık kazanır, geometrik şekli korunur;
   eğri yüzeyde her nokta kendi normaline gider — kabuk ekstrüzyonu) mı? (1 / 2 tuşu ya da
   pencere düğmeleri).
2. Yüzeylerin üzerine gelince yüz vurgulanır ve imleçte Inventor'daki gibi bir ok belirir:
   ekstrüzyon yapılmaya hazırdır. Tık: yüzü seçer (Shift+tık: yüz ekler), gövde gerçek
   sonuçla yeniden hesaplanır.
3. Ok tutulup sürüklenince mesafe değişir (ok ekseni boyunca; ızgara adımlarına yapışır,
   Ctrl: serbest). Rakam yazınca mesafe girilir. F: yönü çevir, Tab: tür değiştir.
   Enter / Tamam: bitir · Esc / Vazgeç: geri al.

Ayarlar "Ekstrüzyon" penceresinde (tür, mesafe, yön, iki yönlü, işlem: Birleştir / Kes /
Kesişim, kapsam: seçilen yüz / bütün açık yüzey, aynala).
"""

import math

import numpy as np

import bpy

from . import core, ribbon_state

_STATE = {"active": None}
_HANDLES = []
COL_ARROW = (0.25, 0.75, 1.0, 0.95)
COL_ARROW_HOT = (1.0, 0.8, 0.2, 1.0)


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


def default_dist(body):
    try:
        diag = float(max(body.dimensions))
    except Exception:
        diag = 1.0
    d = max(diag * 0.1, 1e-4)
    e = math.floor(math.log10(d))
    return round(d / 10 ** e) * 10 ** e


def new_feature(body, kind="LINEAR"):
    p = body.cad
    f = p.features.add()
    f.op = "EXTRUDE"
    f.uid = core.new_uid()
    f.name = f"Ekstrüzyon {sum(1 for x in p.features if x.op == 'EXTRUDE')}"
    f.ext_kind = kind if kind in ("LINEAR", "THICK") else "LINEAR"
    f.ext_dist = default_dist(body)
    f.mirror_tool = True
    return f


def find_feature(body, uid):
    for i, f in enumerate(body.cad.features):
        if f.uid == uid:
            return i, f
    return None, None


def direction(f, n):
    """Okun (ekstrüzyonun) dünya doğrultusu: yüz normali; Kes'te içe, Yönü çevir'de ters."""
    sign = -1.0 if f.ext_op == "CUT" else 1.0
    if f.ext_flip:
        sign = -sign
    return np.asarray(n, float) * sign


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
    ok, loc, n, idx, ob, _m = context.scene.ray_cast(dg, o, d)
    if not ok or ob is None:
        return None
    try:
        if not ob.cad.is_cad:
            return None
    except Exception:
        return None
    if body is not None and ob != body:
        return None
    if n.dot(d) > 0:                  # açık yüzeyin arkası: normal bakana dönsün
        n = -n
    return ob, np.array(loc), np.array(n.normalized()), idx


def _closest_on_axis(ro, rd, a, u):
    """Fare ışını (ro, rd) ile a + u·t doğrusunun en yakın noktasındaki t."""
    rd = rd / max(np.linalg.norm(rd), 1e-15)
    w0 = a - ro
    b = float(np.dot(u, rd))
    den = 1.0 - b * b
    if den < 1e-9:
        return None
    return float(b * np.dot(w0, rd) - np.dot(w0, u)) / den


# ---------------------------------------------------------------- operatör

class MINICAD_OT_extrude(bpy.types.Operator):
    """Ekstrüzyon: gövde yüzünü doğrusal uzat ya da normalleri boyunca kalınlaştır"""
    bl_idname = "minicad.extrude"
    bl_label = "Ekstrüzyon"
    bl_description = ("Yüzeyin üzerine gel (ok belirir), tıkla, oku sürükle: doğrusal "
                      "ekstrüzyon ya da şekli koruyarak normaller boyunca kalınlaştırma")
    bl_options = {"REGISTER"}

    kind: bpy.props.StringProperty(default="", options={"HIDDEN", "SKIP_SAVE"})
    uid: bpy.props.StringProperty(default="", options={"HIDDEN", "SKIP_SAVE"})
    pick_co: bpy.props.FloatVectorProperty(size=3, options={"HIDDEN", "SKIP_SAVE"})
    pick_nrm: bpy.props.FloatVectorProperty(size=3, options={"HIDDEN", "SKIP_SAVE"})
    has_pick: bpy.props.BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"})

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    def invoke(self, context, event):
        if _STATE["active"] is not None:
            cleanup_all()
            return {"CANCELLED"}
        for mod in ("draw", "pick", "split", "hole"):
            try:
                __import__(f"{__package__}.{mod}", fromlist=["cleanup_all"]).cleanup_all()
            except Exception:
                pass
        from .ui import get_target
        body = get_target(context)
        if body is None:
            self.report({"WARNING"}, "Ekstrüzyon için önce bir gövde gerekli")
            return {"CANCELLED"}
        self.area = context.area
        self.region = next((r for r in self.area.regions if r.type == "WINDOW"), None)
        self.rv3d = self.area.spaces.active.region_3d
        self.body_name = body.name
        self.stop_request = False
        self.hover = None              # (nokta, normal, üçgenler | None)
        self.hot = False               # ok üzerinde mi
        self.drag = None               # {"t0", "d0"}
        self.typed = ""
        self.mouse = (0.0, 0.0)
        self.created = False
        if self.uid:
            _i, f = find_feature(body, self.uid)
            if f is None:
                self.report({"WARNING"}, "Ekstrüzyon bulunamadı")
                return {"CANCELLED"}
            self.asking = False
        else:
            f = new_feature(body, self.kind or "LINEAR")
            self.created = True
            self.asking = self.kind not in ("LINEAR", "THICK")    # başlangıçta sor
        self.fuid = f.uid
        self.start = self._snapshot(f)
        if self.has_pick:
            self.add_pick(context, np.array(self.pick_co), np.array(self.pick_nrm), rebuild=not
                          self.asking)
        _STATE["active"] = self
        _HANDLES.append(bpy.types.SpaceView3D.draw_handler_add(_draw3d, (), "WINDOW",
                                                               "POST_VIEW"))
        _HANDLES.append(bpy.types.SpaceView3D.draw_handler_add(_draw2d, (), "WINDOW",
                                                               "POST_PIXEL"))
        context.window_manager.modal_handler_add(self)
        self._status(context)
        return {"RUNNING_MODAL"}

    # ------------------------------------------------------------ yardımcılar
    def body(self):
        return bpy.data.objects.get(self.body_name)

    def feature(self):
        b = self.body()
        return None if b is None else find_feature(b, self.fuid)[1]

    @staticmethod
    def _snapshot(f):
        return {"pts": [(tuple(h.co), tuple(h.nrm)) for h in f.ext_pts],
                "vals": {k: getattr(f, k) for k in ("ext_kind", "ext_dist", "ext_flip",
                                                     "ext_sym", "ext_scope", "ext_op")}}

    def _status(self, context, msg=""):
        f = self.feature()
        if self.asking:
            txt = ("EKSTRÜZYON TÜRÜ: 1 — Doğrusal (tek yön, prizma) · 2 — Kalınlaştır (yüzey "
                   "normalleri boyunca, şekli korur) · Esc: vazgeç")
        else:
            n = len(f.ext_pts) if f else 0
            k = "Doğrusal" if f and f.ext_kind == "LINEAR" else "Kalınlaştır"
            txt = (f"Ekstrüzyon ({k}, {n} yüz): yüzeye tıkla · Shift+tık: yüz ekle · oku "
                   "sürükle / ölçü yaz: mesafe · F: yönü çevir · Tab: tür · Enter: bitir · "
                   "Esc: vazgeç")
        if msg:
            txt = msg + "  —  " + txt
        try:
            context.workspace.status_text_set(txt)
        except Exception:
            pass

    def set_kind(self, context, kind):
        f = self.feature()
        if f is None:
            return
        self.asking = False
        f.ext_kind = kind
        if len(f.ext_pts):
            core.rebuild(self.body())
        self._status(context, "Doğrusal ekstrüzyon" if kind == "LINEAR" else
                     "Kalınlaştırma (normaller boyunca)")
        self.area.tag_redraw()

    def anchor(self):
        """Okun dibi ve doğrultusu (ilk seçilen yüz) | None."""
        body, f = self.body(), self.feature()
        if body is None or f is None or not len(f.ext_pts):
            return None
        from mathutils import Vector
        mw = body.matrix_world
        h = f.ext_pts[0]
        a = np.array(tuple(mw @ Vector(tuple(h.co))))
        n = mw.to_3x3().inverted_safe().transposed() @ Vector(tuple(h.nrm))
        n = np.array(tuple(n.normalized()))
        return a, direction(f, n)

    def arrow_len(self, f):
        d = float(self.drag["cur"]) if self.drag else f.ext_dist
        return d

    def _update_hover(self, context, mx, my):
        body = self.body()
        hit = _ray(context, self.region, self.rv3d, mx, my, body)
        self.hot = False
        anc = self.anchor()
        if anc is not None and not self.asking:
            a, u = anc
            L = self.arrow_len(self.feature())
            pa, pb = _px(self.region, self.rv3d, a), _px(self.region, self.rv3d, a + u * L)
            if pa is not None and pb is not None:
                A, B, m = np.array(pa), np.array(pb), np.array([mx, my])
                AB = B - A
                t = float(np.clip(np.dot(m - A, AB) / max(np.dot(AB, AB), 1e-9), 0.0, 1.0))
                s = context.preferences.system.ui_scale
                self.hot = float(np.linalg.norm(A + AB * t - m)) < 10 * s or \
                    float(np.linalg.norm(B - m)) < 14 * s
        if hit is None:
            self.hover = None
            return
        ob, loc, n, idx = hit
        key = self.hover[3] if self.hover else None
        tris = self.hover[2] if self.hover else None
        try:
            from . import ribbon_ctx
            lab = ribbon_ctx._label(ob, idx)
            k = (ob.name, lab)
            if k != key:
                tris = None
                if lab is not None and lab >= 0:
                    g = ribbon_ctx._patch_geom(context, {"obj": ob.name, "patch": lab})
                    tris = None if g is None else g[1]
                key = k
        except Exception:
            tris, key = None, None
        self.hover = (loc, n, tris, key)

    def add_pick(self, context, loc, n, add=False, rebuild=True):
        body, f = self.body(), self.feature()
        if body is None or f is None:
            return
        from mathutils import Vector
        mw = body.matrix_world
        inv = mw.inverted()
        if not add:
            f.ext_pts.clear()
        h = f.ext_pts.add()
        h.co = tuple(inv @ Vector(tuple(loc)))
        nl = mw.to_3x3().transposed() @ Vector(tuple(n))       # normal: ters-devrik matris
        h.nrm = tuple(nl.normalized())
        if rebuild:
            core.rebuild(body)
            self._status(context, f"{len(f.ext_pts)} yüz: {f.info}")

    def undo_pick(self, context):
        body, f = self.body(), self.feature()
        if f is not None and len(f.ext_pts):
            f.ext_pts.remove(len(f.ext_pts) - 1)
            core.rebuild(body)
            self._status(context, "Son yüz geri alındı")

    def set_dist(self, context, v):
        f = self.feature()
        if f is None:
            return
        if v < 0:
            f.ext_flip = not f.ext_flip
            v = -v
        f.ext_dist = max(float(v), 1e-6)
        core.rebuild(self.body())
        self._status(context, f"Mesafe {core.fmt_len(f.ext_dist)} · {f.info}")

    def finish(self, context, cancel=False):
        body, f = self.body(), self.feature()
        if body is not None and f is not None:
            if cancel:
                if self.created:
                    i, _f = find_feature(body, self.fuid)
                    body.cad.features.remove(i)
                else:
                    f.ext_pts.clear()
                    for co, nrm in self.start["pts"]:
                        h = f.ext_pts.add()
                        h.co, h.nrm = co, nrm
                    for k, v in self.start["vals"].items():
                        setattr(f, k, v)
                core.forget_cache(body.name)
                core.rebuild(body)
            elif not len(f.ext_pts) and f.ext_scope != "BODY" and self.created:
                i, _f = find_feature(body, self.fuid)
                body.cad.features.remove(i)
                core.rebuild(body)
            else:
                try:
                    bpy.ops.ed.undo_push(message="BlendCAD: Ekstrüzyon")
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

    def _snap_dist(self, v):
        if self.ctrl:
            return v
        try:
            vd = float(self.rv3d.view_distance)
        except Exception:
            vd = 1.0
        step = 10 ** math.floor(math.log10(max(vd * 0.02, 1e-9)))
        return round(v / step) * step

    # ------------------------------------------------------------ olaylar
    def modal(self, context, event):
        if self.stop_request or _STATE["active"] is not self:
            cleanup_all() if _STATE["active"] is self else None
            return {"CANCELLED"}
        if self.feature() is None:
            self.finish(context, cancel=False)
            return {"CANCELLED"}
        self.ctrl = event.ctrl
        if self.drag is None and ribbon_state.over_ribbon(event):
            return {"PASS_THROUGH"}
        r = self.region
        mx, my = event.mouse_x - r.x, event.mouse_y - r.y
        inside = 0 <= mx < r.width and 0 <= my < r.height
        et, press = event.type, event.value == "PRESS"
        f = self.feature()
        if self.asking:
            if press and et in ("ONE", "NUMPAD_1"):
                self.set_kind(context, "LINEAR")
                return {"RUNNING_MODAL"}
            if press and et in ("TWO", "NUMPAD_2"):
                self.set_kind(context, "THICK")
                return {"RUNNING_MODAL"}
            if press and et == "ESC":
                self.finish(context, cancel=True)
                return {"CANCELLED"}
            return {"PASS_THROUGH"}
        if et in ("MOUSEMOVE", "INBETWEEN_MOUSEMOVE"):
            if not inside and self.drag is None:
                return {"PASS_THROUGH"}
            self.mouse = (mx, my)
            if self.drag is not None:
                from bpy_extras import view3d_utils
                ro = np.array(view3d_utils.region_2d_to_origin_3d(r, self.rv3d, (mx, my)))
                rd = np.array(view3d_utils.region_2d_to_vector_3d(r, self.rv3d, (mx, my)))
                a, u = self.drag["a"], self.drag["u"]
                t = _closest_on_axis(ro, rd, a, u)
                if t is not None:
                    v = self.drag["d0"] + (t - self.drag["t0"])
                    self.drag["cur"] = self._snap_dist(v)
                    self.drag["moved"] = True
                self.area.tag_redraw()
                return {"RUNNING_MODAL"}
            self._update_hover(context, mx, my)
            self.area.tag_redraw()
            return {"PASS_THROUGH"}
        if et == "LEFTMOUSE" and not press and self.drag is not None:
            d = self.drag
            self.drag = None
            if d.get("moved"):
                self.set_dist(context, d["cur"])
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if not inside:
            return {"PASS_THROUGH"}
        if et == "LEFTMOUSE" and press and not (event.alt or event.ctrl):
            anc = self.anchor()
            if self.hot and anc is not None:
                from bpy_extras import view3d_utils
                ro = np.array(view3d_utils.region_2d_to_origin_3d(r, self.rv3d, (mx, my)))
                rd = np.array(view3d_utils.region_2d_to_vector_3d(r, self.rv3d, (mx, my)))
                a, u = anc
                t0 = _closest_on_axis(ro, rd, a, u)
                self.drag = {"a": a, "u": u, "t0": t0 if t0 is not None else f.ext_dist,
                             "d0": f.ext_dist, "cur": f.ext_dist, "moved": False}
                self._status(context, "Mesafe: oku sürükle (Ctrl: serbest) · bırak: uygula")
                return {"RUNNING_MODAL"}
            if self.hover is None:
                return {"PASS_THROUGH"}
            loc, n, _t, _k = self.hover
            self.add_pick(context, loc, n, add=event.shift)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if et == "LEFTMOUSE":
            return {"RUNNING_MODAL"} if (self.hover is not None or self.hot) else \
                {"PASS_THROUGH"}
        if press and et == "RIGHTMOUSE" and self.drag is not None:
            self.drag = None
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if press and et == "BACK_SPACE":
            if self.typed:
                self.typed = self.typed[:-1]
                self.area.tag_redraw()
                return {"RUNNING_MODAL"}
            if len(f.ext_pts):
                self.undo_pick(context)
                self.area.tag_redraw()
                return {"RUNNING_MODAL"}
            return {"PASS_THROUGH"}
        if press and et == "F" and not (event.ctrl or event.alt):
            f.ext_flip = not f.ext_flip
            self._status(context, "Yön çevrildi")
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if press and et == "TAB":
            self.set_kind(context, "THICK" if f.ext_kind == "LINEAR" else "LINEAR")
            return {"RUNNING_MODAL"}
        ch = (event.unicode or "") if press else ""
        if press and ch and not event.ctrl and (ch in "0123456789.,-+" or
                                                (self.typed and ch.isalpha())):
            self.typed += ch
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if press and et in ("RET", "NUMPAD_ENTER"):
            if self.typed:
                from .draw_common import parse_length
                v = parse_length(self.typed)
                self.typed = ""
                if v is not None:
                    self.set_dist(context, v)
                self.area.tag_redraw()
                return {"RUNNING_MODAL"}
            self.finish(context)
            return {"FINISHED"}
        if press and et == "ESC":
            if self.typed:
                self.typed = ""
                self.area.tag_redraw()
                return {"RUNNING_MODAL"}
            self.finish(context, cancel=True)
            return {"CANCELLED"}
        return {"PASS_THROUGH"}


# ---------------------------------------------------------------- çizim

def _basis(n):
    n = n / max(np.linalg.norm(n), 1e-15)
    a = np.array([1.0, 0, 0]) if abs(n[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(n, a)
    u /= np.linalg.norm(u)
    return u, np.cross(n, u)


def arrow_lines(a, u, L, size):
    """Inventor tarzı ok: gövde çizgisi + dört kanatlı uç (3B çizgi çiftleri)."""
    u = np.asarray(u, float)
    u = u / max(np.linalg.norm(u), 1e-15)
    tip = a + u * L
    e1, e2 = _basis(u)
    h = size
    seg = [tuple(a), tuple(tip)]
    base = tip - u * h * 2.2
    ring = [base + (math.cos(t) * e1 + math.sin(t) * e2) * h * 0.8
            for t in np.linspace(0, 2 * math.pi, 13)]
    for i in range(12):
        seg += [tuple(ring[i]), tuple(ring[i + 1])]
    for k in (0, 3, 6, 9):
        seg += [tuple(ring[k]), tuple(tip)]
    return seg


def _lines(seg, col, width, region):
    import gpu
    from gpu_extras.batch import batch_for_shader
    sh = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    b = batch_for_shader(sh, "LINES", {"pos": seg})
    sh.bind()
    sh.uniform_float("viewportSize", (region.width, region.height))
    sh.uniform_float("lineWidth", width)
    sh.uniform_float("color", col)
    b.draw(sh)


def _draw3d():
    op = _STATE["active"]
    ctx = bpy.context
    if op is None or ctx.area is None or ctx.area != op.area or op.asking:
        return
    f = op.feature()
    body = op.body()
    if f is None or body is None:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    region = ctx.region
    gpu.state.blend_set("ALPHA")
    try:
        try:
            vd = float(op.rv3d.view_distance)
        except Exception:
            vd = 1.0
        size = 0.012 * vd
        if op.hover is not None:
            loc, n, tris, _k = op.hover
            if tris is not None and len(tris):
                gpu.state.depth_test_set("LESS_EQUAL")
                sh = gpu.shader.from_builtin("UNIFORM_COLOR")
                b = batch_for_shader(sh, "TRIS", {"pos": [tuple(q + n * 0.0015 * vd)
                                                          for q in tris]})
                sh.bind()
                sh.uniform_float("color", (0.25, 0.75, 1.0, 0.22))
                b.draw(sh)
            gpu.state.depth_test_set("NONE")
            if not op.hot:               # hazır oku: üzerine gelinen yüzde
                u = direction(f, n)
                _lines(arrow_lines(loc, u, 0.08 * vd, size * 0.8),
                       (COL_ARROW[0], COL_ARROW[1], COL_ARROW[2], 0.55), 1.6, region)
        gpu.state.depth_test_set("NONE")
        anc = op.anchor()
        if anc is not None:
            a, u = anc
            L = op.arrow_len(f)
            col = COL_ARROW_HOT if (op.hot or op.drag) else COL_ARROW
            _lines(arrow_lines(a, u, max(L, size * 3), size), col, 2.6, region)
            if f.ext_kind == "THICK":    # kalınlaştırma: normale dik kısa izler
                e1, e2 = _basis(u)
                seg = []
                for t in np.linspace(0.25, 1.0, 4):
                    c = a + u * L * t
                    seg += [tuple(c - e1 * size * 1.6), tuple(c + e1 * size * 1.6)]
                _lines(seg, (col[0], col[1], col[2], 0.5), 1.2, region)
            if f.ext_sym:
                _lines([tuple(a), tuple(a - u * L * 0.5)], (col[0], col[1], col[2], 0.45),
                       1.6, region)
    finally:
        gpu.state.blend_set("NONE")


def _draw2d():
    op = _STATE["active"]
    ctx = bpy.context
    if op is None or ctx.area is None or ctx.area != op.area:
        return
    f = op.feature()
    if f is None:
        return
    import blf
    s = ctx.preferences.system.ui_scale
    if op.asking:
        txt = ["Ekstrüzyon türü (pencereden ya da tuşla seç):",
               "1  Doğrusal — tek yönde (yüz normali) prizma",
               "2  Kalınlaştır — yüzey normalleri boyunca, şekli korur"]
        x, y = op.mouse[0] + 18 * s, op.mouse[1] + 10 * s
        blf.size(0, int(12 * s))
        for i, t in enumerate(txt):
            blf.color(0, 1, 1, 1, 1 if i else 0.9)
            blf.position(0, x, y - i * 17 * s, 0)
            blf.draw(0, t)
        return
    anc = op.anchor()
    if anc is None:
        return
    a, u = anc
    L = op.arrow_len(f)
    p = _px(op.region, op.rv3d, a + u * L)
    if p is None:
        return
    lab = ("Doğrusal" if f.ext_kind == "LINEAR" else "Kalınlaştır") + " · " + core.fmt_len(L)
    if op.typed:
        lab += f"   [{op.typed}_]"
    blf.size(0, int(13 * s))
    blf.color(0, 1.0, 0.85, 0.3, 1.0)
    blf.position(0, p[0] + 12 * s, p[1] + 8 * s, 0)
    blf.draw(0, lab)


classes = (MINICAD_OT_extrude,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    cleanup_all()
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
