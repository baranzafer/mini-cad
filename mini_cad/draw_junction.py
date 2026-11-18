"""Kesişim (birleşim) noktasını eğriler üzerinde kaydırma — çizim aracı tarafı (v0.34.0).

Tel kafeste birden çok eğrinin buluştuğu noktanın üzerine gelinince işaretlenir; basılı
tutup sürükleyince nokta o eğrilerin ÜZERİNDE ve DOĞRULTUSUNDA kayar (slide.py). Hem
taslaktaki çizgiler hem kaydedilmiş tel kafes eğrileri (Blender eğri objeleri) desteklenir;
noktada ucu olan öbür eğriler yeni konuma taşınır, bağlantı kopmaz.

Sürüklerken: yol üzerindeki uç / orta / merkez noktalarına ve öbür eğrilerle kesişimlere
yapışır (Ctrl: yakalama kapalı), rakam yazınca eğri boyunca o uzunlukta durur, E: serbest
sürükleme (görünüş düzleminde) ↔ eğri üzerinde, bırak / Enter: uygula, sağ tık / Esc: iptal.

MINICAD_OT_draw (draw.py) bu mixin'den miras alır.
"""
import math
import traceback

import bpy
import numpy as np
from mathutils import Vector

from . import core
from . import slide as sl
from .draw_common import (
    COL_GUIDE, COL_RUBBER, COL_SNAP, COL_TEXT, MODIFIERS, PASS_KEYS, _dashed, _marker, _poly,
    _project, _text, parse_length,
)

TOL = 1e-5            # aynı nokta sayılma uzaklığı (dünya birimi)
COL_JN = (1.0, 0.45, 0.85, 1.0)


def _arr(v):
    return np.array(tuple(v), dtype=np.float64)


# ------------------------------------------------------------------ kaynak okuma / yazma
def _spline_chain(ob, si, sp):
    """Kaydedilmiş spline → (segs dünya, lines, cyclic) ya da None."""
    mw = ob.matrix_world
    if sp.type == "BEZIER":
        bp = sp.bezier_points
        n = len(bp)
        if n < 2:
            return None
        nseg = n if sp.use_cyclic_u else n - 1
        segs, lines = [], []
        for i in range(nseg):
            a, b = bp[i], bp[(i + 1) % n]
            P = np.array([_arr(mw @ a.co), _arr(mw @ a.handle_right),
                          _arr(mw @ b.handle_left), _arr(mw @ b.co)])
            if np.linalg.norm(P[3] - P[0]) < 1e-12:
                return None                     # sıfır uzunluk: önce Öneriler onarsın
            segs.append(P)
            lines.append(a.handle_right_type == "VECTOR" and b.handle_left_type == "VECTOR"
                         or sl._is_straight(P))
        return segs, lines, bool(sp.use_cyclic_u)
    if sp.type == "POLY":
        pts = sp.points
        n = len(pts)
        if n < 2:
            return None
        nseg = n if sp.use_cyclic_u else n - 1
        segs = []
        for i in range(nseg):
            a, b = _arr(mw @ pts[i].co.xyz), _arr(mw @ pts[(i + 1) % n].co.xyz)
            if np.linalg.norm(b - a) < 1e-12:
                return None
            segs.append(sl._line_bez(a, b))
        return segs, [True] * nseg, bool(sp.use_cyclic_u)
    return None


def _write_spline(ob, si, segs, lines, orig):
    """Kaydırılmış zinciri spline'a geri yazar (yalnız değişen noktalar)."""
    sp = ob.data.splines[si]
    inv = ob.matrix_world.inverted()

    def L(v):
        return inv @ Vector(tuple(v))

    if sp.type == "POLY":
        pts = sp.points
        n = len(pts)
        for i, P in enumerate(segs):
            for k, q in ((i, P[0]), ((i + 1) % n, P[3])):
                v = L(q)
                pts[k].co = (v.x, v.y, v.z, pts[k].co[3])
        return
    bp = sp.bezier_points
    n = len(bp)
    for i, P in enumerate(segs):
        if np.allclose(P, orig[i], atol=1e-12):
            continue
        a, b = bp[i], bp[(i + 1) % n]
        typ = "VECTOR" if lines[i] else "FREE"
        for pt, side in ((a, "right"), (b, "left")):
            if getattr(pt, f"handle_{side}_type") != typ:
                # karşı tutamaç da serbest kalsın: hizalı / otomatik tip onu da değiştirmesin
                other = "left" if side == "right" else "right"
                if getattr(pt, f"handle_{other}_type") in ("AUTO", "ALIGNED"):
                    setattr(pt, f"handle_{other}_type", "FREE")
                setattr(pt, f"handle_{side}_type", typ)
    for i, P in enumerate(segs):
        if np.allclose(P, orig[i], atol=1e-12):
            continue
        a, b = bp[i], bp[(i + 1) % n]
        a.co, b.co = L(P[0]), L(P[3])
        a.handle_right, b.handle_left = L(P[1]), L(P[2])


class JunctionMixin:
    """Birleşim noktası üzerine gelme, eğriler üzerinde kaydırma, geri yazma."""

    # ------------------------------------------------------------- birleşim bulma
    def _jn_sources(self, context):
        """Taslak + kaydedilmiş eğri zincirleri: [(kaynak, segs, lines, cyclic)]."""
        out = []
        for si, st in enumerate(self.sketch or ()):
            segs = [np.array([_arr(q) for q in sg["p"]]) for sg in st["segs"]]
            if not segs:
                continue
            out.append((("sk", si), segs, [sg["kind"] == "line" for sg in st["segs"]],
                        bool(st["cyclic"])))
        for ob in context.visible_objects:
            if ob.type != "CURVE":
                continue
            for si, sp in enumerate(ob.data.splines):
                try:
                    ch = _spline_chain(ob, si, sp)
                except Exception:
                    ch = None
                if ch is not None:
                    out.append((("ob", ob.name, si),) + ch)
        return out

    def _jn_gather(self, context, pos):
        """pos'taki birleşim: (zincirler, düğümler, geçenler) — birleşim değilse None."""
        pos = np.asarray(pos, float)
        chains, nodes, passing = [], [], []
        for src, segs, lines, cyc in self._jn_sources(context):
            n = len(segs)
            hit = []
            for j in range(n if cyc else n + 1):
                if np.linalg.norm(sl.node_of(segs, j, cyc) - pos) < TOL:
                    hit.append(j)
            if hit:
                ci = len(chains)
                chains.append((src, segs, lines, cyc))
                nodes += [(ci, j) for j in hit]
                continue
            for P in segs:
                lo = P.min(axis=0) - TOL
                hi = P.max(axis=0) + TOL
                if np.any(pos < lo) or np.any(pos > hi):
                    continue
                t, d = sl.closest_param(P, pos)
                if d < TOL and 1e-4 < t < 1 - 1e-4:
                    passing.append((P, t))
        if not nodes:
            return None
        owners = {c[0] for c in chains}
        if len(nodes) < 2 and not passing and len(owners) < 2:
            return None                    # tek eğrinin sıradan noktası: birleşim değil
        return chains, nodes, passing

    def _jn_candidates(self, context):
        """Kaydedilmiş tel kafesteki birleşim noktaları (önbellekli: refs başına)."""
        key = id(self.refs)
        cache = getattr(self, "_jn_cache", None)
        if cache is not None and cache[0] == key:
            return cache[1]
        pts = {}
        for (name, si, k), p in self.refs.wpts:
            pts.setdefault(tuple(np.round(p, 5)), set()).add((name, si))
        cands = [np.array(k) for k, v in pts.items() if len(v) >= 2]
        lone = [np.array(k) for k, v in pts.items() if len(v) == 1]
        if lone and self.refs.wsegs:                       # T birleşimi: uç, öbür eğrinin içinde
            Q = np.array(lone)
            for name, si, i, S in self.refs.wsegs:
                S = np.asarray(S, float)
                if len(S) < 2:
                    continue
                d = sl._poly_dist(Q, S)
                for qi in np.nonzero(d < TOL * 10)[0]:
                    q = Q[qi]
                    if min(np.linalg.norm(q - S[0]), np.linalg.norm(q - S[-1])) > TOL * 10:
                        cands.append(q)
        self._jn_cache = (key, cands)
        return cands

    def _jn_hit(self, context, mx, my):
        cands = self._jn_candidates(context)
        if not cands:
            return None
        M = np.array(self.rv3d.perspective_matrix, dtype=np.float64)
        P = np.array(cands)
        px, ok, _ = _project(P, M, self.region)
        d = np.where(ok, np.linalg.norm(px - np.array([mx, my]), axis=1), np.inf)
        i = int(np.argmin(d))
        return P[i] if d[i] <= 8 * self.ui_scale else None

    # ------------------------------------------------------------- oturum
    def _jn_start(self, context, pos, mx, my, armed=True):
        g = self._jn_gather(context, pos)
        if g is None:
            return False
        chains, nodes, passing = g
        ext = max(float(self.rv3d.view_distance) * 0.25, 1e-3)
        S = sl.Slider([(c[1], c[2], c[3]) for c in chains], nodes, passing, ext_len=ext)
        try:
            pts = np.asarray(self.refs.P, float)
            S.add_snap_points(pts, list(self.refs.kinds), TOL * 10)
            S.add_crossings([w[3] for w in self.refs.wsegs], self._px_size(pos) * 3.0)
        except Exception:
            traceback.print_exc()
        self.jn_drag = {"chains": chains, "slider": S, "pos": np.asarray(pos, float),
                        "press": (mx, my), "moved": not armed, "free": False,
                        "out": None, "new": np.asarray(pos, float), "bi": None, "par": None,
                        "snap": None, "typed": ""}
        self.jn_hover = None
        return True

    def _jn_free(self, mx, my):
        d = self.jn_drag
        ro, rd = self._ray(mx, my)
        n = self._view_dir()
        den = float(np.dot(rd, n))
        if abs(den) < 1e-12:
            return None
        t = float(np.dot(d["pos"] - ro, n)) / den
        new = ro + rd * t
        d["snap"] = None
        if not self.ctrl and self.snap_on:
            s = self._point_snap_excluding(mx, my, ro, rd, d["pos"])
            if s is not None:
                new, d["snap"] = np.asarray(s[0], float), s[1]
        S = d["slider"]
        out = [(list(sg), list(ln)) for sg, ln, _cy in S.chains]
        for ci, jj in S.nodes:
            sg, ln = out[ci]
            out[ci] = (sl.move_node(sg, ln, jj, S.chains[ci][2], new), ln)
        return out, new

    def _jn_apply(self, mx, my):
        d = self.jn_drag
        S = d["slider"]
        self.mouse = (mx, my)
        if d["free"]:
            r = self._jn_free(mx, my)
            if r is not None:
                d["out"], d["new"] = r
                d["bi"] = None
            return
        if not S.branches:
            return
        M = np.array(self.rv3d.perspective_matrix, dtype=np.float64)
        m = np.array([mx, my], dtype=np.float64)
        best = None
        for bi, (b, _j) in enumerate(S.branches):
            px, ok, _ = _project(b.path, M, self.region)
            if not np.any(ok):
                continue
            A, B = px[:-1], px[1:]
            AB = B - A
            L2 = np.maximum(np.sum(AB * AB, axis=1), 1e-12)
            t = np.clip(np.sum((m - A) * AB, axis=1) / L2, 0.0, 1.0)
            C = A + t[:, None] * AB
            dd = np.linalg.norm(C - m, axis=1)
            dd = np.where(ok[:-1] & ok[1:], dd, np.inf)
            k = int(np.argmin(dd))
            if best is None or dd[k] < best[0]:
                par = b.params[k] + (b.params[k + 1] - b.params[k]) * t[k]
                best = (dd[k], bi, par)
        if best is None:
            return
        _, bi, par = best
        d["snap"] = None
        typed = parse_length(d["typed"]) if d["typed"] else None
        b = S.branches[bi][0]
        if typed is not None:
            par, _p = b.at(abs(typed))
            d["snap"] = "Yazılan"
        elif not self.ctrl and self.snap_on:
            q = self._px(b.point(par))
            bestd = self.radius
            for sbi, spar, kind in S.snaps:
                p = self._px(S.branches[sbi][0].point(spar))
                if p is None or q is None:
                    continue
                dist = math.hypot(p[0] - mx, p[1] - my)
                if dist < bestd:
                    bestd, bi, par, d["snap"] = dist, sbi, spar, kind
        d["bi"], d["par"] = bi, par
        try:
            d["out"], d["new"] = S.apply(bi, par)
        except Exception:
            traceback.print_exc()

    def _jn_commit(self, context):
        d = self.jn_drag
        self.jn_drag = None
        if d is None or d["out"] is None:
            return False
        S = d["slider"]
        wrote = []
        for ci, (src, segs0, lines0, cyc) in enumerate(d["chains"]):
            segs, lines = d["out"][ci]
            if all(np.allclose(a, b, atol=1e-12) for a, b in zip(segs, segs0)):
                continue
            if src[0] == "sk":
                st = self.sketch[src[1]]
                new = []
                for i, (sg, P) in enumerate(zip(st["segs"], segs)):
                    kind = sg["kind"]
                    if lines[i]:
                        kind = "line"
                    elif kind == "line" or (kind == "arc" and not
                                            np.allclose(P, segs0[i], atol=1e-12) and
                                            not _same_circle(segs0[i], P)):
                        kind = "curve"
                    new.append(dict(sg, kind=kind, p=tuple(np.array(q) for q in P)))
                st["segs"] = new
                self.dirty = True
                wrote.append("taslak")
            else:
                ob = bpy.data.objects.get(src[1])
                if ob is None:
                    continue
                try:
                    _write_spline(ob, src[2], segs, lines, segs0)
                    ob.data.update_tag()
                    ob.update_tag()
                    wrote.append(ob.name)
                except Exception:
                    traceback.print_exc()
        del S
        if not wrote:
            return False
        names = sorted({w for w in wrote if w != "taslak"})
        for nm in names:
            try:
                from . import health
                health.schedule_curve(nm)
            except Exception:
                pass
        if names:
            try:
                bpy.ops.ed.undo_push(message="BlendCAD: kesişim noktası kaydırma")
            except Exception:
                pass
        try:
            context.view_layer.update()
        except Exception:
            pass
        from .draw_common import _Refs
        self.refs = _Refs(context, self.sketch, getattr(self, "sk_points", None) or ())
        self._jn_cache = None
        self._status(context, "Kesişim noktası kaydırıldı" +
                     (f" · {', '.join(names)}" if names else "") + " · Ctrl+Z: geri al")
        return True

    # ------------------------------------------------------------- olaylar
    def _jn_event(self, context, event, mx, my, press):
        """Birleşim üzerine gelme / basma. İşlendiyse True."""
        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            h = self._jn_hit(context, mx, my)
            old = getattr(self, "jn_hover", None)
            if (h is None) != (old is None) or (h is not None and not np.allclose(h, old)):
                self.jn_hover = h
                self.area.tag_redraw()
                if h is not None:
                    self._status(context, "Kesişim noktası · basılı tutup sürükle: eğriler "
                                          "üzerinde kaydır")
            return False
        if event.type == "LEFTMOUSE" and press and getattr(self, "jn_hover", None) is not None \
                and self.pen is None and not self.segs:
            return self._jn_start(context, self.jn_hover, mx, my, armed=True)
        return False

    def _jn_drag_event(self, context, event, mx, my, press):
        d = self.jn_drag
        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            if not d["moved"] and math.hypot(mx - d["press"][0], my - d["press"][1]) < \
                    4 * self.ui_scale:
                return {"RUNNING_MODAL"}
            if not d["moved"]:
                self._status(context, "Kesişim kaydırma · eğri üzerinde kayar, noktalara / "
                                      "kesişimlere yapışır · ölçü yaz: eğri boyunca uzunluk · "
                                      "E: serbest · Ctrl: yakalama kapalı · bırak / Enter: uygula"
                                      " · sağ tık / Esc: iptal")
            d["moved"] = True
            self._jn_apply(mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if (event.type == "LEFTMOUSE" and not press) or \
                (event.type in {"RET", "NUMPAD_ENTER"} and press):
            if not d["moved"] and not d["typed"]:
                self.jn_drag = None                     # sürüklenmedi: normal tık
                if self.tool != "SELECT":
                    self._update(context, mx, my)
                    self._place(context)
                    self._refresh(context)
                return {"RUNNING_MODAL"}
            self._jn_commit(context)
            self._refresh(context)
            return {"RUNNING_MODAL"}
        if (event.type == "RIGHTMOUSE" and press) or (event.type == "ESC" and press):
            self.jn_drag = None
            self._status(context, "Kesişim kaydırma iptal edildi")
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type == "E" and press:
            d["free"] = not d["free"]
            d["moved"] = True
            self._jn_apply(mx, my)
            self._status(context, "Serbest sürükleme (görünüş düzleminde) · E: eğri üzerine dön"
                         if d["free"] else "Eğri üzerinde kaydırma · E: serbest")
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if press and event.type == "BACK_SPACE":
            d["typed"] = d["typed"][:-1]
            self._jn_apply(mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        ch = (event.unicode or "") if press else ""
        if press and ch and not event.ctrl and (ch in "0123456789.,-+" or
                                                (d["typed"] and ch.isalpha())):
            d["typed"] += ch
            d["moved"] = True
            self._jn_apply(mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type in MODIFIERS:
            self.ctrl = event.ctrl
            if d["moved"]:
                self._jn_apply(*self.mouse)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        return {"RUNNING_MODAL"} if event.type not in PASS_KEYS else {"PASS_THROUGH"}

    # ------------------------------------------------------------- çizim
    def _jn_draw3d(self, region):
        d = getattr(self, "jn_drag", None)
        if d is None or not d["moved"]:
            return
        S = d["slider"]
        if not d["free"]:
            for bi, (b, _j) in enumerate(S.branches):
                col = COL_SNAP if bi == d["bi"] else (COL_GUIDE[0], COL_GUIDE[1], COL_GUIDE[2],
                                                      0.45)
                _poly([tuple(p) for p in b.path], col, 3.0 if bi == d["bi"] else 1.4, region)
        if d["out"] is not None:
            for sg, _ln in d["out"]:
                for P in sg:
                    _poly([tuple(p) for p in sl.sample(P, 20)], COL_RUBBER, 2.4, region)

    def _jn_draw2d(self, region):
        s = self.ui_scale
        h = getattr(self, "jn_hover", None)
        d = getattr(self, "jn_drag", None)
        if d is None and h is not None:
            p = self._px(h)
            if p is not None:
                r = 7 * s
                pts = [(p[0], p[1] - r), (p[0] + r, p[1]), (p[0], p[1] + r), (p[0] - r, p[1])]
                _poly(pts, COL_JN, 2.2, region, closed=True)
                _text(p[0] + 12 * s, p[1] + 10 * s, "Kesişim · sürükle: eğri üzerinde kaydır",
                      COL_JN, int(11 * s))
            return
        if d is None or not d["moved"]:
            return
        p = self._px(d["new"])
        o = self._px(d["pos"])
        if p is None:
            return
        if o is not None:
            _dashed(o, p, COL_GUIDE, region)
        _marker(d["snap"] or "Uç", p[0], p[1], 6 * s, region)
        label = "Serbest" if d["free"] else "Eğri üzerinde"
        if d["snap"]:
            label += f" · {d['snap']}"
        if not d["free"] and d["bi"] is not None:
            b = d["slider"].branches[d["bi"]][0]
            L = b.length_at(d["par"])
            label += f" · {core.fmt_len(L)}"
        if d["typed"]:
            label += f"  [{d['typed']}_]"
        _text(p[0] + 12 * s, p[1] + 10 * s, label, COL_TEXT, int(12 * s))


def _same_circle(P0, P1):
    """Kırpılmış yay hâlâ aynı çember üzerinde mi (yay türü korunsun)."""
    try:
        from . import drawmath as dm
        a, b = dm.arc_of_bezier(np.asarray(P0)), dm.arc_of_bezier(np.asarray(P1))
        return a is not None and b is not None and np.linalg.norm(a[0] - b[0]) < 1e-6 and \
            abs(a[1] - b[1]) < 1e-6
    except Exception:
        return False
