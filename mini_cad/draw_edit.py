"""Taslak düzenleme: nokta / tutamaç seçme ve sürükleme, pivot, sürüklerken yakalama ve
ızgara, eksen kilidi.

MINICAD_OT_draw (draw.py) bu mixin'den miras alır; metotlar self üzerinden birbirini çağırır.
"""
import math
import numpy as np

from . import drawmath as dm
from .draw_common import (
    AXIS_COLS, COL_GUIDE, COL_RUBBER, COL_TEXT, GRID_PX, GUIDE_PX, MODIFIERS, PASS_KEYS,
    _dashed, _move_handle, _move_node, _poly, _project, _text, parse_angle, parse_length,
)
from . import core


class EditMixin:
    """Taslak düzenleme: nokta / tutamaç seçme ve sürükleme, pivot, sürüklerken yakalama ve
    ızgara, eksen kilidi."""

    def _sketch_items(self):
        """Taslaktaki sürüklenebilir noktalar ve (eğri parçalarında) tutamaçlar."""
        items = []
        for si, st in enumerate(self.sketch):
            segs = st["segs"]
            n = len(segs)
            nodes = n if st["cyclic"] else n + 1
            for j in range(nodes):
                pos = segs[j]["p"][0] if j < n else segs[-1]["p"][3]
                items.append((("pt", si, j, 0), pos))
            for j, sg in enumerate(segs):
                if sg["kind"] != "line":
                    items.append((("h", si, j, 1), sg["p"][1]))
                    items.append((("h", si, j, 2), sg["p"][2]))
        return items

    def _sketch_hit(self, mx, my):
        items = self._sketch_items()
        if not items:
            return None
        M = np.array(self.rv3d.perspective_matrix, dtype=np.float64)
        P = np.array([p for _, p in items])
        px, ok, _ = _project(P, M, self.region)
        d = np.where(ok, np.linalg.norm(px - np.array([mx, my]), axis=1), np.inf)
        r = 8 * self.ui_scale
        best = None
        for i in np.argsort(d)[:6]:
            if d[i] > r:
                break
            key = items[int(i)][0]
            pri = 0 if key[0] == "pt" else 1
            if best is None or (pri, d[i]) < best[0]:
                best = ((pri, d[i]), key, items[int(i)][1])
        return None if best is None else (best[1], best[2])

    def _sketch_event(self, context, event, mx, my, press):
        """Taslak noktası / tutamacı üzerinde: üstüne gelince vurgula, basılı sürükleyince
        düzenle. Sürüklemeden bırakılırsa normal tık olarak çalışır."""
        if not self.sketch or self.tool.startswith("C_"):
            if self.sk_hover is not None:
                self.sk_hover = None
            return False
        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            h = self._sketch_hit(mx, my)
            if (h and h[0]) != (self.sk_hover and self.sk_hover[0]):
                self.sk_hover = h
                self.area.tag_redraw()
            return False
        if event.type == "LEFTMOUSE" and press and self.pen is None:
            axis = self._pivot_hit(mx, my)
            if axis is not None:
                key = self.sk_sel
                pos = self._item_pos(key)
            else:
                h = self._sketch_hit(mx, my)
                if h is None:
                    return False
                key, pos = h
            st = self.sketch[key[1]]
            base = self._cur_plane() or self.tmp_plane or self._make_plane(self.plane_mode, pos)
            self.sk_sel = key
            self.typed, self.field = ["", ""], 0
            self.sk_drag = {"key": key, "press": (mx, my), "moved": axis is not None,
                            "axis": axis, "pivot": axis is not None,
                            "orig": [dict(sg, p=tuple(np.array(q) for q in sg["p"]))
                                     for sg in st["segs"]],
                            "pos": np.asarray(pos, dtype=np.float64).copy(),
                            "plane": base.moved(pos), "event": (mx, my)}
            self.area.tag_redraw()
            return True
        return False

    def _item_pos(self, key):
        try:
            st = self.sketch[key[1]]
            segs = st["segs"]
            if key[0] == "pt":
                j = key[2]
                return segs[j]["p"][0] if j < len(segs) else segs[-1]["p"][3]
            return segs[key[2]]["p"][key[3]]
        except Exception:
            return None

    def _pivot_axes(self):
        """Seçili noktadaki pivotun eksen okları: [(eksen, merkez px, uç px)]."""
        if self.sk_sel is None:
            return []
        pos = self._item_pos(self.sk_sel)
        if pos is None:
            self.sk_sel = None
            return []
        c = self._px(pos)
        if c is None:
            return []
        L = 48.0 * self.ui_scale
        out = []
        for k in range(3):
            ax = np.zeros(3)
            ax[k] = 1.0
            q = self._px(np.asarray(pos) + ax * 50.0 * self.ui_scale * self._px_size(pos))
            if q is None:
                continue
            d = np.array(q) - np.array(c)
            n = float(np.linalg.norm(d))
            if n < 4.0:
                continue                         # bakış doğrultusundaki eksen
            out.append((k, c, (c[0] + d[0] / n * L, c[1] + d[1] / n * L)))
        return out

    def _pivot_hit(self, mx, my):
        for k, c, e in self._pivot_axes():
            a, b = np.array(c), np.array(e)
            ab = b - a
            t = float(np.clip(np.dot(np.array([mx, my]) - a, ab) / max(np.dot(ab, ab), 1e-9),
                              0.0, 1.0))
            if t < 0.2:
                continue                         # merkez: noktanın kendisi
            if float(np.linalg.norm(a + ab * t - np.array([mx, my]))) <= 6 * self.ui_scale:
                return k
        return None

    def _draw_pivot(self, region):
        if self.sk_sel is None:
            return
        pos = self._item_pos(self.sk_sel)
        c = self._px(pos) if pos is not None else None
        if c is None:
            return
        s = self.ui_scale
        lock = self.sk_drag["axis"] if self.sk_drag else None
        for k, c0, e in self._pivot_axes():
            col = AXIS_COLS[k]
            w = 3.0 if lock == k else 2.0
            _poly([c0, e], col, w, region)
            d = np.array(e) - np.array(c0)
            d /= max(float(np.linalg.norm(d)), 1e-9)
            nrm = np.array([-d[1], d[0]])
            tip = np.array(e)
            base = tip - d * 9 * s
            _poly([tuple(base + nrm * 4 * s), tuple(tip), tuple(base - nrm * 4 * s)], col, w,
                  region, closed=True)
            _text(e[0] + 4 * s, e[1] + 2 * s, "XYZ"[k], col, int(10 * s))
        pts = [(c[0] + 7 * s * math.cos(a), c[1] + 7 * s * math.sin(a))
               for a in np.linspace(0, 2 * math.pi, 17)[:-1]]
        _poly(pts, (1.0, 1.0, 1.0, 0.9), 1.5, region, closed=True)
        _poly([(c[0] - 11 * s, c[1]), (c[0] + 11 * s, c[1])], (1, 1, 1, 0.6), 1.0, region)
        _poly([(c[0], c[1] - 11 * s), (c[0], c[1] + 11 * s)], (1, 1, 1, 0.6), 1.0, region)

    def _drag_cancel(self):
        d = self.sk_drag
        if d is not None:
            self.sketch[d["key"][1]]["segs"] = d["orig"]
        self.sk_drag = None
        self.dirty = True
        self.area.tag_redraw()

    def _drag_event(self, context, event, mx, my, press):
        d = self.sk_drag
        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            if not d["moved"] and math.hypot(mx - d["press"][0], my - d["press"][1]) < \
                    4 * self.ui_scale:
                return {"RUNNING_MODAL"}
            if not d["moved"]:
                self._status(context, "Sürükleme · ölçü yaz (uzunluk, Tab: açı) · X/Y/Z: eksen "
                                      "kilidi · bırak / Enter: uygula · sağ tık / Esc: iptal")
            d["moved"] = True
            self._drag_apply(mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if press and self._drag_typing(event, mx, my):
            return {"RUNNING_MODAL"}
        if (event.type == "LEFTMOUSE" and not press) or \
                (event.type in {"RET", "NUMPAD_ENTER"} and press):
            if any(self.typed):
                d["moved"] = True
            self.sk_drag = None
            self.typed, self.field = ["", ""], 0
            if self.tool == "SELECT":
                self.cursor, self.info, self.snap_kind = None, None, None
            if d["moved"]:
                self.dirty = True
                self._status(context, "Taslak düzenlendi · Bitir (Ctrl+Enter) ile kaydet")
            elif self.tool != "SELECT":
                self.sk_sel = None
                self._update(context, mx, my)     # sürüklenmedi: normal tık
                self._place(context)
                self._refresh(context)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type == "RIGHTMOUSE" and press:
            self._drag_cancel()
            return {"RUNNING_MODAL"}
        if event.type in {"X", "Y", "Z"} and press:
            ax = {"X": 0, "Y": 1, "Z": 2}[event.type]
            d["axis"] = None if d["axis"] == ax else ax
            if d["moved"]:
                self._drag_apply(mx, my)
            self._status(context, f"Sürükleme: {'XYZ'[ax] + ' ekseninde' if d['axis'] is not None else 'düzlemde'}"
                                  " · X/Y/Z: eksen kilidi · sağ tık / Esc: iptal")
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type in MODIFIERS:
            self.ctrl = event.ctrl
            return {"RUNNING_MODAL"}
        return {"RUNNING_MODAL"} if event.type not in PASS_KEYS else {"PASS_THROUGH"}

    def _drag_typing(self, event, mx, my):
        """Sürüklerken ölçü yazma (çizimdeki gibi): rakamlar, Tab, Backspace. İşlendiyse True."""
        d = self.sk_drag
        if event.type == "TAB":
            if d["axis"] is None:
                self.field = 1 - self.field
        elif event.type == "BACK_SPACE":
            if not self.typed[self.field]:
                return True
            self.typed[self.field] = self.typed[self.field][:-1]
        else:
            ch = event.unicode or ""
            typing = bool(self.typed[self.field])
            if not ch or event.ctrl or event.type in {"X", "Y", "Z"} or \
                    not (ch in "0123456789.,-+°" or
                         (typing and (ch.isalpha() or ch in "'\""))):
                return False                     # X / Y / Z: eksen kilidi
            self.typed[self.field] += ch
        d["moved"] = True
        self._drag_apply(mx, my)
        self.area.tag_redraw()
        return True

    def _dim_anchor(self):
        """Sürüklemede ölçünün alındığı nokta: tutamaçta bağlı olduğu nokta, noktada
        çizgideki komşu nokta (önceki; yoksa sonraki)."""
        d = self.sk_drag
        if d is None:
            return None
        if d["key"][0] == "h":
            return self._drag_anchor()
        st = self.sketch[d["key"][1]]
        segs = d["orig"]
        n = len(segs)
        j = d["key"][2]
        if j > 0:
            return np.array(segs[j - 1]["p"][0])
        if st["cyclic"] and n > 1:
            return np.array(segs[-1]["p"][0])
        if n >= 1:
            return np.array(segs[0]["p"][3])
        return None

    def _drag_anchor(self):
        """Sürüklenen tutamacın bağlı olduğu nokta (kılavuzlar ona göre)."""
        d = self.sk_drag
        if d is None or d["key"][0] != "h":
            return None
        sg = d["orig"][d["key"][2]]
        return np.array(sg["p"][0] if d["key"][3] == 1 else sg["p"][3])

    def _drag_apply(self, mx, my):
        """Taslak noktası / tutamacı sürükleme: çizimdeki bütün yakalamalar geçerli
        (uç / orta / merkez, yatay / dikey / paralel / dik / hiza / uzantı, ızgara);
        eksen kilidinde eksen boyunca ızgara adımı."""
        self.mouse = (mx, my)
        d = self.sk_drag
        key = d["key"]
        ro, rd = self._ray(mx, my)
        p0 = d["pos"]
        self.info, self.snap_kind = None, None
        no_snap = self.ctrl or not self.snap_on
        if d["axis"] is not None:
            ax = np.zeros(3)
            ax[d["axis"]] = 1.0
            rdn = rd / max(float(np.linalg.norm(rd)), 1e-15)
            w0 = ro - p0
            bb = float(np.dot(rdn, ax))
            den = 1.0 - bb * bb
            t = float(np.dot(w0, ax) - bb * np.dot(w0, rdn)) / den if den > 1e-9 else 0.0
            typed = self._signed_len(self.typed[0]) if self.typed[0] else None
            if typed is not None:
                t = typed
                self.info = {"kind": f"{'XYZ'[d['axis']]} · yazılan"}
            elif self.grid_on and not no_snap:
                q = p0 + ax * t
                gs = self._grid_step(q)
                g = round(float(q[d["axis"]]) / gs) * gs - float(p0[d["axis"]])
                if abs(g - t) <= GRID_PX * self.ui_scale * self._px_size(q):
                    t = g
                    self.info = {"kind": f"{'XYZ'[d['axis']]} · Izgara"}
            new = p0 + ax * t
            if self.info is None:
                self.info = {"kind": f"{'XYZ'[d['axis']]} ekseni"}
        else:
            plane = d["plane"]
            new = plane.ray_hit(ro, rd)
            if new is None:
                return
            anc = self._dim_anchor()
            v0 = parse_length(self.typed[0]) if self.typed[0] else None
            v1 = parse_angle(self.typed[1]) if self.typed[1] else None
            locked = anc is not None and (v0 is not None or v1 is not None)
            if locked:
                new = dm.apply_locks(plane, anc, new, v0, v1)
                new = new - plane.n * plane.dist(new)    # sürüklenen öğenin yüksekliği kalsın
                self.info = {"kind": "Yazılan", "plane": plane}
            elif not no_snap:
                snap = self._point_snap_excluding(mx, my, ro, rd, p0)
                if snap is not None:
                    new = np.asarray(snap[0], dtype=np.float64)
                    self.snap_kind = snap[1]
                else:
                    tol = GUIDE_PX * self.ui_scale * self._px_size(new)
                    anchor = self._drag_anchor()
                    ref_pts, ref_dirs, ref_segs = self._inference_refs(plane, mx, my)
                    ref_pts = [r for r in ref_pts
                               if abs(r[0] - plane.uv(p0)[0]) + abs(r[1] - plane.uv(p0)[1]) > 1e-9]
                    a_uv = plane.uv(anchor) if anchor is not None else None
                    q, info = dm.refine(a_uv, plane.uv(new), ref_dirs, ref_pts, ref_segs, tol,
                                        shift=self.shift)
                    if info is not None:
                        new = plane.xyz(q)
                        info["plane"] = plane
                        self.info = info
                    if self.grid_on:
                        n2, g = self._grid_snap(plane, new, self.info)
                        if g:
                            new = n2
                            if self.info is None:
                                self.info = {"kind": "Izgara", "plane": plane}
                            else:
                                self.info["kind"] += " + Izgara"
        self.cursor = np.asarray(new, dtype=np.float64)
        segs = [dict(sg, p=tuple(np.array(q) for q in sg["p"])) for sg in d["orig"]]
        st = self.sketch[key[1]]
        if key[0] == "pt":
            _move_node(segs, key[2], new, st["cyclic"])
        else:
            _move_handle(segs, key[2], key[3], new, st["cyclic"], d["orig"])
        st["segs"] = segs

    def _draw_sketch3d(self, region):
        for st in self.sketch:
            for sg in st["segs"]:
                _poly([tuple(p) for p in dm.sample(sg, 2 if sg["kind"] == "line" else 20)],
                      (0.55, 0.85, 1.0, 0.95), 2.2, region)

    def _draw_sketch2d(self, region):
        if not self.sketch:
            return
        s = self.ui_scale
        hov = self.sk_hover[0] if self.sk_hover else None
        drag = self.sk_drag["key"] if self.sk_drag else None
        for key, pos in self._sketch_items():
            p = self._px(pos)
            if p is None:
                continue
            on = key == hov or key == drag
            col = COL_RUBBER if on else (0.9, 0.9, 0.9, 0.85)
            if key[0] == "h":
                sg = self.sketch[key[1]]["segs"][key[2]]
                node = sg["p"][0] if key[3] == 1 else sg["p"][3]
                q = self._px(node)
                if q is not None:
                    _poly([q, p], (0.7, 0.7, 0.75, 0.6), 1.0, region)
                pts = [(p[0] + 3.5 * s * math.cos(a), p[1] + 3.5 * s * math.sin(a))
                       for a in np.linspace(0, 2 * math.pi, 11)[:-1]]
                _poly(pts, col, 1.5, region, closed=True)
            else:
                r = 3.5 * s
                _poly([(p[0] - r, p[1] - r), (p[0] + r, p[1] - r), (p[0] + r, p[1] + r),
                       (p[0] - r, p[1] + r)], col, 1.6, region, closed=True)

    def _draw_drag_input(self, region, cur):
        """Sürüklerken dinamik ölçü (çizimdeki gibi): ölçü noktasından uzunluk ve açı,
        imleç yanında ölçü kutusu; yazılan değer kilitler. Eksen kilidinde kaydırma."""
        d = self.sk_drag
        if d is None or not d["moved"] or self.cursor is None:
            return
        sc = self.ui_scale
        size = int(12 * sc)
        if d["axis"] is not None:
            t = float(self.cursor[d["axis"]] - d["pos"][d["axis"]])
            names = ((f"{'XYZ'[d['axis']]} kaydırma", core.fmt_len(t)),)
            a, b = self._px(d["pos"]), self._px(self.cursor)
            if a is not None and b is not None:
                _dashed(a, b, AXIS_COLS[d["axis"]], region)
        else:
            anc = self._dim_anchor()
            if anc is None:
                return
            pl = d["plane"]
            L = float(np.linalg.norm(self.cursor - anc))
            ang = dm.seg_angle(pl, anc, self.cursor)
            ap, cp = self._px(anc), self._px(self.cursor)
            if ap is not None and cp is not None:
                if d["key"][0] == "pt":
                    _dashed(ap, cp, COL_GUIDE, region)
                mid = ((ap[0] + cp[0]) * 0.5, (ap[1] + cp[1]) * 0.5)
                _text(mid[0] + 6 * sc, mid[1] + 6 * sc, core.fmt_len(L), COL_TEXT, size)
                _text(ap[0] + 8 * sc, ap[1] - 16 * sc, f"{ang:.1f}°", COL_TEXT, size)
            names = (("Tutamaç" if d["key"][0] == "h" else "Uzunluk", core.fmt_len(L)),
                     ("Açı", f"{ang:.1f}°"))
        rows = []
        for i, (name, live) in enumerate(names):
            txt = self.typed[i]
            val = (txt + ("_" if i == self.field else "")) if txt else live
            rows.append((name, val, i == self.field))
        self._draw_rows(cur, rows)
