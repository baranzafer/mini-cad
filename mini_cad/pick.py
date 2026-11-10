"""Kenar seçim modu: fare ile bezier segmentlerinin üzerine gelince vurgular, tıklayınca seçer.

Kısayollar (mod açıkken):
  Sol tık          kenar zincirini (köşeye / kesişmeye kadar) seç / bırak
  Alt + sol tık    tek segmenti seç / bırak
  Enter / F        seçili kenarlardan yüzey oluştur (hedef gövdeye ekler)
  Ctrl+Enter       seçili kenarlarla YENİ bir gövde başlat
  B                seçili kenarlara bevel ekle (ölçü panelden)
  Sarı kenarlar    gövdenin boolean'la oluşan kenarları: tek tek seçilip B ile fillet'lenir
  Backspace        seçimi temizle
  Esc              moddan çık
  Diğer her şey (panel, eğri düzenleme, G/R/S, Tab, geri alma) mod açıkken de çalışır
  Orta tuş, tekerlek, numpad: görünüm gezinmesi normal çalışır
"""

import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader

from . import core

SAMPLES = 24          # bezier segmenti başına örnek nokta
PICK_RADIUS_PX = 10   # seçim yarıçapı (ui ölçeğiyle çarpılır)

COL_HOVER = (1.0, 0.62, 0.1, 1.0)
COL_SELECTED = (0.2, 0.75, 1.0, 1.0)
COL_USED = (0.35, 0.9, 0.45, 0.55)
COL_BEVEL = (0.85, 0.4, 1.0, 0.9)
COL_BODY = (1.0, 0.86, 0.15, 0.85)   # gövde (boolean) kenarları

PASS_KEYS = {
    "MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "TRACKPADPAN", "TRACKPADZOOM",
    "MOUSEROTATE", "MOUSESMARTZOOM", "NDOF_MOTION",
    "NUMPAD_0", "NUMPAD_1", "NUMPAD_2", "NUMPAD_3", "NUMPAD_4", "NUMPAD_5", "NUMPAD_6",
    "NUMPAD_7", "NUMPAD_8", "NUMPAD_9", "NUMPAD_PERIOD", "NUMPAD_PLUS", "NUMPAD_MINUS",
    "NUMPAD_SLASH", "NUMPAD_ASTERIX", "HOME", "Z", "N", "T",
}


def _sample(p):
    if len(p) == 2:
        return np.array([tuple(p[0]), tuple(p[1])], dtype=np.float64)
    p0, p1, p2, p3 = (np.array(tuple(v), dtype=np.float64) for v in p)
    t = np.linspace(0.0, 1.0, SAMPLES)[:, None]
    u = 1.0 - t
    return u ** 3 * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t ** 3 * p3


class _Scene:
    """Görünür eğri objelerinin segmentlerini örnekler ve hızlı seçim için diziler hazırlar."""

    def __init__(self, context):
        self.refs = []       # [(ob, si, i)]
        self.keys = []       # [(ob.name, si, i)]
        self.polys = []      # her segmentin örnek noktaları (K,3)
        self.ends = []       # (başlangıç düğümü, bitiş düğümü, başlangıç yönü, bitiş yönü)
        self.nodes = {}      # düğüm -> segment indeksleri
        a_list, b_list, owner = [], [], []
        for ob in context.visible_objects:
            if ob.type != "CURVE":
                continue
            mw = ob.matrix_world
            for si, sp in enumerate(ob.data.splines):
                if sp.type not in ("BEZIER", "POLY"):
                    continue
                for i in range(core._seg_count(sp)):
                    s = core._spline_segment(ob, si, sp, i, mw)
                    if s is None:
                        continue
                    pts = _sample(s["p"])
                    idx = len(self.refs)
                    self.refs.append((ob, si, i))
                    self.keys.append((ob.name, si, i))
                    self.polys.append(pts)
                    self._add_ends(idx, s["p"])
                    a_list.append(pts[:-1])
                    b_list.append(pts[1:])
                    owner.append(np.full(len(pts) - 1, idx))
        # Gövdenin boolean'la oluşan kenarları (tel kafeste karşılığı olmayanlar)
        self.kinds = ["wire"] * len(self.refs)
        self.body_used = set()
        try:
            target = core_target(context)
            vis = target is not None and target.visible_get()
        except Exception:
            target, vis = None, False
        if vis:
            for uid, poly, used in core._display.get(target.name, {}).get("bool_edges", ()):
                P = np.asarray(poly, dtype=np.float64)
                if len(P) < 2:
                    continue
                key = ("@body", uid) + tuple(np.round(P.mean(axis=0), 4).tolist()) + \
                    (round(float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum()), 4),)
                if key in self.keys:
                    continue
                idx = len(self.refs)
                self.refs.append(("BODY", uid, P))
                self.keys.append(key)
                self.polys.append(P)
                self.kinds.append("body")
                self._add_ends(idx, P)
                a_list.append(P[:-1])
                b_list.append(P[1:])
                owner.append(np.full(len(P) - 1, idx))
                if used:
                    self.body_used.add(key)
        if a_list:
            self.A = np.vstack(a_list)
            self.B = np.vstack(b_list)
            self.owner = np.concatenate(owner)
        else:
            self.A = self.B = np.zeros((0, 3))
            self.owner = np.zeros(0, dtype=int)

    @staticmethod
    def _node(v):
        return (round(v[0], 5), round(v[1], 5), round(v[2], 5))

    @staticmethod
    def _unit(v):
        n = float(np.linalg.norm(v))
        return v / n if n > 1e-12 else None

    def _add_ends(self, idx, p):
        P = np.array([tuple(q) for q in p], dtype=np.float64)
        d0 = self._unit(P[1] - P[0]) if len(P) > 1 else None
        d1 = self._unit(P[-1] - P[-2]) if len(P) > 1 else None
        if d0 is None:
            d0 = self._unit(P[-1] - P[0])
        if d1 is None:
            d1 = self._unit(P[-1] - P[0])
        k0, k1 = self._node(P[0]), self._node(P[-1])
        self.ends.append((k0, k1, d0, d1))
        self.nodes.setdefault(k0, []).append(idx)
        self.nodes.setdefault(k1, []).append(idx)

    def chain(self, h, cos_lim):
        """h segmentinden iki yöne, köşeye ya da kesişme noktasına (3+ eğri) kadar uzanan
        kesintisiz zincir."""
        out = [h]
        seen = {h}
        for side in (1, 0):                       # önce bitiş ucu, sonra başlangıç ucu
            cur = h
            k0, k1, d0, d1 = self.ends[cur]
            node = k1 if side == 1 else k0
            d = d1 if side == 1 else (-d0 if d0 is not None else None)
            while d is not None:
                kinds = getattr(self, "kinds", None)
                nb = [j for j in self.nodes.get(node, [])
                      if j != cur and (kinds is None or kinds[j] == kinds[h])]
                if len(nb) != 1:
                    break                          # uç nokta ya da kesişme
                nxt = nb[0]
                a0, a1, e0, e1 = self.ends[nxt]
                if a0 == node:
                    nd, nnode, exitd = e0, a1, e1
                else:
                    nd = -e1 if e1 is not None else None
                    nnode, exitd = a0, (-e0 if e0 is not None else None)
                if nd is None or float(np.dot(d, nd)) < cos_lim or nxt in seen:
                    break
                out.append(nxt)
                seen.add(nxt)
                cur, node, d = nxt, nnode, exitd
        return out

    def pick(self, region, rv3d, mx, my, radius):
        if len(self.owner) == 0:
            return None
        P = np.array(rv3d.perspective_matrix, dtype=np.float64)

        def project(X):
            h = np.hstack([X, np.ones((len(X), 1))]) @ P.T
            w = h[:, 3:4]
            ok = w[:, 0] > 1e-6
            w = np.where(np.abs(w) < 1e-9, 1e-9, w)
            ndc = h[:, :3] / w
            px = (ndc[:, 0] + 1.0) * 0.5 * region.width
            py = (ndc[:, 1] + 1.0) * 0.5 * region.height
            return np.stack([px, py], axis=1), ndc[:, 2], ok

        a, za, oka = project(self.A)
        b, zb, okb = project(self.B)
        m = np.array([mx, my], dtype=np.float64)
        ab = b - a
        denom = np.einsum("ij,ij->i", ab, ab)
        denom = np.where(denom < 1e-12, 1e-12, denom)
        t = np.clip(np.einsum("ij,ij->i", m - a, ab) / denom, 0.0, 1.0)
        closest = a + ab * t[:, None]
        d = np.linalg.norm(closest - m, axis=1)
        z = za + (zb - za) * t
        d = np.where(oka & okb, d, np.inf)
        dmin = d.min()
        if not np.isfinite(dmin) or dmin > radius:
            return None
        # Üst üste binen kenarlarda kameraya en yakın olanı seç
        near = np.where(d <= dmin + 2.0)[0]
        best = near[np.argmin(z[near])]
        return int(self.owner[best])


def is_body_ref(r):
    """Seçim modundaki gövde kenarı referansı mı: ("BODY", boolean uid, çizgi)."""
    return isinstance(r, tuple) and len(r) == 3 and isinstance(r[0], str) and r[0] == "BODY"


def _lines(polys):
    coords = []
    for pts in polys:
        for k in range(len(pts) - 1):
            coords.append(tuple(pts[k]))
            coords.append(tuple(pts[k + 1]))
    return coords


_STATE = {"active": None}   # çalışan tek seçim modu örneği
_HANDLES = []               # eklenmiş bütün çizim tutamaçları (kalıntı temizliği için)


def is_running():
    return _STATE["active"] is not None


def _remove_handle(h):
    try:
        bpy.types.SpaceView3D.draw_handler_remove(h, "WINDOW")
    except Exception:
        pass
    if h in _HANDLES:
        _HANDLES.remove(h)


def cleanup_all():
    """Bütün seçim modu çizimlerini kaldırır ve çalışan modu durdurur."""
    for h in list(_HANDLES):
        _remove_handle(h)
    op = _STATE["active"]
    if op is not None:
        op.stop_request = True
    _STATE["active"] = None
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    except Exception:
        pass


class MINICAD_OT_pick_edges(bpy.types.Operator):
    bl_idname = "minicad.pick_edges"
    bl_label = "Kenar Seçim Modu"
    bl_description = ("Eğri kenarlarını fareyle seç (hover + tık). Enter/F: yüzey oluştur, "
                      "Backspace: temizle, Esc: çık")
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    # ------------------------------------------------------------ yardımcılar

    def _refresh_used(self, context):
        self.used = set()
        self.beveled = set()
        target = core_target(context)
        if target is not None:
            for p in target.cad.patches:
                for ob, si, i in core.patch_refs(p):
                    self.used.add((ob.name, si, i))
            for f in target.cad.features:
                if f.enabled:
                    for r in f.segs:
                        if r.obj is not None:
                            self.beveled.add((r.obj.name, r.spline, r.seg))

    def _status(self, context, msg=""):
        n = len(self.selected)
        txt = (f"Kenar seçimi: {n} seçili  |  Tık: zinciri seç/bırak  |  Alt+tık: tek parça  |  "
               f"Enter: yüzey  |  "
               f"Ctrl+Enter: YENİ gövde  |  B: fillet (sarı = gövde kenarları)  |  "
               f"Backspace: temizle  |  Esc: çık")
        if msg:
            txt = f"{msg}   —   {txt}"
        try:
            context.workspace.status_text_set(txt)
        except Exception:
            pass

    def _draw(self):
        if _STATE["active"] is not self or getattr(self, "stop_request", False):
            return
        try:
            sc = self.scene
            shader = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
            region = bpy.context.region
            vp = (region.width, region.height) if region else (1000, 1000)
            gpu.state.blend_set("ALPHA")
            gpu.state.depth_test_set("NONE")

            def draw(polys, color, width):
                if not polys:
                    return
                batch = batch_for_shader(shader, "LINES", {"pos": _lines(polys)})
                shader.bind()
                shader.uniform_float("viewportSize", vp)
                shader.uniform_float("lineWidth", width)
                shader.uniform_float("color", color)
                batch.draw(shader)

            used = [sc.polys[i] for i, k in enumerate(sc.keys)
                    if k in self.used and k not in self.selected and k not in self.beveled]
            draw(used, COL_USED, 2.0)
            body = [sc.polys[i] for i, k in enumerate(sc.keys)
                    if sc.kinds[i] == "body" and k not in self.selected
                    and k not in sc.body_used]
            draw(body, COL_BODY, 2.5)
            bev = [sc.polys[i] for i, k in enumerate(sc.keys)
                   if (k in self.beveled or k in sc.body_used) and k not in self.selected]
            draw(bev, COL_BEVEL, 3.5)

            draw([sc.polys[sc.keys.index(k)] for k in self.selected if k in sc.keys],
                 COL_SELECTED, 5.0)
            if self.hover is not None:
                draw([sc.polys[i] for i in self.hover_set], COL_HOVER, 6.0)
            gpu.state.blend_set("NONE")
        except Exception as e:  # çizim hatası eklentiyi kilitlemesin
            print("[Mini CAD] çizim hatası:", e)

    def _finish(self, context):
        if self._handle is not None:
            _remove_handle(self._handle)
            self._handle = None
        if _STATE["active"] is self:
            _STATE["active"] = None
        try:
            context.workspace.status_text_set(None)
        except Exception:
            pass
        if self.area is not None:
            self.area.tag_redraw()

    # ------------------------------------------------------------ yaşam döngüsü

    def invoke(self, context, event):
        if _STATE["active"] is not None:
            # Mod zaten açık: butona tekrar basmak kapatır
            cleanup_all()
            self.report({"INFO"}, "Kenar seçimi kapatıldı")
            return {"CANCELLED"}
        try:
            from . import draw
            draw.cleanup_all()                 # çizim aracıyla aynı anda çalışmasın
        except Exception:
            pass
        self.stop_request = False
        self.area = context.area
        self.region = next((r for r in self.area.regions if r.type == "WINDOW"), None)
        self.rv3d = self.area.spaces.active.region_3d
        if self.region is None or self.rv3d is None:
            self.report({"ERROR"}, "3D görünüm bulunamadı")
            return {"CANCELLED"}
        self.scene = _Scene(context)
        try:
            # Açılmış bir dosyada boolean kenarları henüz hesaplanmadıysa bir kez hesaplat
            t = core_target(context)
            if t is not None and any(f.op == "BOOLEAN" and f.enabled for f in t.cad.features) \
                    and "bool_edges" not in core._display.get(t.name, {}):
                core.schedule(t, preview=False)
        except Exception:
            pass
        if not self.scene.refs:
            self.report({"WARNING"}, "Görünür bezier eğrisi yok")
            return {"CANCELLED"}
        self.selected = []    # sıralı anahtar listesi
        self.hover_set = []
        self.dirty = False
        self.hover = None
        self.created = 0
        self.radius = PICK_RADIUS_PX * context.preferences.system.ui_scale
        self._refresh_used(context)
        self._handle = bpy.types.SpaceView3D.draw_handler_add(self._draw, (), "WINDOW",
                                                              "POST_VIEW")
        _HANDLES.append(self._handle)
        _STATE["active"] = self
        context.window_manager.modal_handler_add(self)
        self._status(context)
        self.area.tag_redraw()
        return {"RUNNING_MODAL"}

    OVERLAY_REGIONS = {"UI", "TOOLS", "HEADER", "TOOL_HEADER", "ASSET_SHELF",
                       "ASSET_SHELF_HEADER", "NAVIGATION_BAR", "HUD", "FOOTER"}
    MOVE_EVENTS = {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE", "TIMER", "TIMER_REPORT",
                   "TIMERREGION", "NONE", "WINDOW_DEACTIVATE"}

    def _mouse_in_region(self, event):
        r = self.region
        x, y = event.mouse_x - r.x, event.mouse_y - r.y
        inside = 0 <= x < r.width and 0 <= y < r.height
        if inside:
            # Yan panel, araç çubuğu, başlık vb. 3D görünümün üstüne biniyorsa oraya bırak
            for o in self.area.regions:
                if o.type in self.OVERLAY_REGIONS and o.width > 1 and o.height > 1:
                    ox, oy = event.mouse_x - o.x, event.mouse_y - o.y
                    if 0 <= ox < o.width and 0 <= oy < o.height:
                        inside = False
                        break
        return inside, x, y

    def _ensure_scene(self, context):
        """Mod dışında bir şey değiştiyse (eğri düzenleme, geri alma...) eğrileri yeniden oku."""
        if not self.dirty:
            return
        try:
            self.scene = _Scene(context)
        except Exception:
            return
        self.selected = [k for k in self.selected if k in self.scene.keys]
        self.hover = None
        self._refresh_used(context)
        self.dirty = False

    def _chain(self, h, event):
        """Alt basılıysa tek segment, değilse köşeye/kesişmeye kadar uzanan zincir."""
        if event.alt:
            return [h]
        try:
            import math
            cos_lim = math.cos(bpy.context.scene.minicad_poly_corner)
        except Exception:
            cos_lim = 0.866
        try:
            return self.scene.chain(h, cos_lim)
        except Exception:
            return [h]

    def _refs(self):
        return [self.scene.refs[self.scene.keys.index(k)] for k in self.selected]

    def _after_action(self, context, ok, msg, undo_msg):
        try:
            from . import recorder
            recorder.log("seç", f"{undo_msg}: {'OK' if ok else 'HATA'} · {msg} · seçim "
                                f"{self.selected[:8]}")
        except Exception:
            pass
        if ok:
            self.created += 1
            self.selected.clear()
            self._refresh_used(context)
            try:
                bpy.ops.ed.undo_push(message=undo_msg)
            except Exception:
                pass
        self.report({"INFO"} if ok else {"ERROR"}, msg)
        self._status(context, msg)
        self.area.tag_redraw()

    def modal(self, context, event):
        if getattr(self, "stop_request", False) or _STATE["active"] is not self:
            self._finish(context)
            return {"CANCELLED"}
        try:
            self.area.regions[0]
        except Exception:
            self._finish(context)            # alan kapandı / ekran değişti
            return {"CANCELLED"}
        inside, mx, my = self._mouse_in_region(event)
        press = event.value == "PRESS"

        if event.type == "ESC" and press:
            self._finish(context)
            return {"FINISHED"} if self.created else {"CANCELLED"}

        # Mod, Blender'ı kilitlemez: kendi işlemediği her olayı Blender'a bırakır
        if not inside or event.type in PASS_KEYS:
            if event.type == "MOUSEMOVE" and self.hover is not None:
                self.hover = None
                self.area.tag_redraw()
            if event.type not in self.MOVE_EVENTS:
                self.dirty = True
            return {"PASS_THROUGH"}

        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            self._ensure_scene(context)
            h = self.scene.pick(self.region, self.rv3d, mx, my, self.radius)
            hs = self._chain(h, event) if h is not None else []
            if h != self.hover or hs != self.hover_set:
                self.hover, self.hover_set = h, hs
                self.area.tag_redraw()
            return {"PASS_THROUGH"}

        if event.type == "LEFTMOUSE" and press:
            self._ensure_scene(context)
            h = self.scene.pick(self.region, self.rv3d, mx, my, self.radius)
            if h is None:
                self.dirty = True          # boşluğa tık: Blender seçsin / gizmo çalışsın
                return {"PASS_THROUGH"}
            ks = [self.scene.keys[i] for i in self._chain(h, event)]
            if all(k in self.selected for k in ks):
                for k in ks:
                    self.selected.remove(k)
            else:
                self.selected += [k for k in ks if k not in self.selected]
            self._status(context)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type in {"BACK_SPACE", "DEL"} and press and self.selected:
            self.selected.clear()
            self._status(context)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}

        if event.type == "B" and press and self.selected and not (event.ctrl or event.alt):
            self._ensure_scene(context)
            from .ui import add_feature
            ok, msg = add_feature(context, self._refs())
            self._after_action(context, ok, msg, "Mini CAD: Bevel")
            return {"RUNNING_MODAL"}

        if (event.type in {"RET", "NUMPAD_ENTER"} or
                (event.type == "F" and self.selected and not event.alt)) and press:
            if not self.selected:
                self._status(context, "Önce kenar seç")
                return {"RUNNING_MODAL"}
            self._ensure_scene(context)
            refs = [r for r in self._refs() if not is_body_ref(r)]
            if not refs:
                self._status(context, "Gövde (sarı) kenarlarından yüzey yapılamaz; onlara "
                                      "sadece B ile fillet verilir")
                return {"RUNNING_MODAL"}
            from .ui import apply_surface
            ok, msg = apply_surface(context, "segs", refs, new_body=event.ctrl)
            self._after_action(context, ok, msg, "Mini CAD: Yüzey")
            return {"RUNNING_MODAL"}

        if event.type not in self.MOVE_EVENTS:
            self.dirty = True
        return {"PASS_THROUGH"}


def core_target(context):
    from .ui import get_target
    return get_target(context)


classes = (MINICAD_OT_pick_edges,)


def _on_result():
    """Yeni hesap sonucu geldi: seçim modu gövde kenarlarını yeniden okusun."""
    op = _STATE["active"]
    if op is not None:
        op.dirty = True


@bpy.app.handlers.persistent
def _on_load_pre(_dummy):
    cleanup_all()


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.app.handlers.load_pre.append(_on_load_pre)
    if _on_result not in core._result_hooks:
        core._result_hooks.append(_on_result)


def unregister():
    if _on_result in core._result_hooks:
        core._result_hooks.remove(_on_result)
    cleanup_all()
    if _on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load_pre)
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
