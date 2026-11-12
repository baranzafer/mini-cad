"""Değiştir araçları (Inventor 2D gibi), taslak üzerinde çalışır:

  Kırp (B)      imlecin üzerindeki parçayı en yakın iki kesişim arasında siler; kesişim
                yoksa nesnenin tamamı silinir. Basılı tutup sürükleyince geçtiği her
                nesneyi kırpar. Shift basılıyken Uzat gibi çalışır.
  Uzat          nesnenin imlece yakın ucunu en yakın sınıra uzatır (doğru / yay).
                Shift basılıyken Kırp gibi çalışır.
  Böl           nesneyi imlece en yakın kesişimde ikiye böler.
  Ötele         çizgiye tıkla (Shift+tık: sadece o nesne), fareyle ya da yazarak mesafe ver,
                tıkla / Enter.
  Köşe yuvarla  köşeye tıkla; yarıçap yazılır (Tab yok), önizleme gösterilir.
  Pah           köşeye tıkla; 1. mesafe, Tab ile 2. mesafe (boşsa eşit).

Matematik sketchmath.py'de. MINICAD_OT_draw (draw.py) bu mixin'den miras alır.
"""
import math
import numpy as np

from . import drawmath as dm
from . import sketchmath as sm
from .draw_common import (
    COL_ACTIVE, COL_GUIDE, COL_RUBBER, COL_SNAP, MODIFY_TOOLS, XFORM_TOOLS, _dashed, _marker, _poly, _project,
    _seg_px_dist, _text, parse_length,
)

COL_CUT = (1.0, 0.3, 0.3, 0.95)

MOD_HELP = {
    "TRIM": "Kırp: parçanın üzerine gel, tıkla (sürükleyerek çoklu) · Shift: Uzat",
    "EXTEND": "Uzat: nesnenin ucuna yakın gel, tıkla · Shift: Kırp",
    "SPLIT": "Böl: nesneyi kesişim noktasından ikiye ayır",
    "OFFSET": "Ötele: çizgiye tıkla (Shift+tık: tek nesne) · mesafe yaz ya da fareyle ver · "
              "tık / Enter",
    "FILLET2D": "Köşe yuvarla: yarıçap yaz · köşeye tıkla",
    "CHAMFER2D": "Pah: mesafe yaz (Tab: 2. mesafe) · köşeye tıkla",
}


class ModifyMixin:
    """Kırp / Uzat / Böl / Ötele / Köşe yuvarla / Pah (taslak üzerinde)."""

    # ------------------------------------------------------------ yardımcılar

    def _mod_init(self):
        if not hasattr(self, "mod"):
            self.mod = None
        if not hasattr(self, "off_sel"):
            self.off_sel = None
        if not hasattr(self, "mod_drag"):
            self.mod_drag = False
        if not hasattr(self, "fillet_r"):
            self.fillet_r = None
        if not hasattr(self, "chamfer_d"):
            self.chamfer_d = None
        if not hasattr(self, "_drag_last"):
            self._drag_last = None
        if not hasattr(self, "fl_sel"):
            self.fl_sel = None           # köşe araçlarında seçilen ilk doğru (çizgi, segment, t)

    def _mod_tool(self):
        """Etkin değiştirme aracı (Shift ile Kırp ⇄ Uzat)."""
        t = self.tool
        if self.shift and t == "TRIM":
            return "EXTEND"
        if self.shift and t == "EXTEND":
            return "TRIM"
        return t

    def _extra_polys(self):
        """Taslak dışındaki sınırlar: görünür tel kafes eğrileri."""
        try:
            return [S for (_n, _s, _i, S) in self.refs.wsegs]
        except Exception:
            return []

    def _pick_seg(self, mx, my):
        """İmlecin altındaki taslak segmenti: (çizgi, segment, t, nokta) ya da None."""
        M = np.array(self.rv3d.perspective_matrix, dtype=np.float64)
        m = np.array([mx, my], dtype=np.float64)
        best = None
        for k, st in enumerate(self.sketch):
            for i, sg in enumerate(st["segs"]):
                n = 2 if sg["kind"] == "line" else 33
                S = dm.sample(sg, n)
                t = np.linspace(0.0, 1.0, n)
                px, ok, _ = _project(S, M, self.region)
                if not ok.all():
                    continue
                d, w = _seg_px_dist(px[:-1], px[1:], m)
                j = int(np.argmin(d))
                if best is None or d[j] < best[0]:
                    tt = float(t[j] + (t[j + 1] - t[j]) * w[j])
                    best = (float(d[j]), k, i, tt)
        if best is None or best[0] > self.radius:
            return None
        _d, k, i, t = best
        return k, i, t, sm.seg_point(self.sketch[k]["segs"][i], t)

    def _set_sketch(self, context, new, msg):
        self.sketch = new
        self.dirty = True
        if getattr(self, "skc", None):
            self._sk_solve()                     # taslak kısıtları korunur
        self.mod = None
        self.sk_sel = self.sk_hover = None
        try:
            from . import recorder
            recorder.log("çiz", f"{self.tool}: {msg} · taslak {len(self.sketch)} çizgi")
        except Exception:
            pass
        self._status(context, msg)

    # ------------------------------------------------------------ hover

    def _mod_update(self, context, mx, my):
        # Değiştir araçları _update'ten geçmez: kaydedilmiş eğri değiştiyse (ör. Taslağa al)
        # sınırlar burada yenilenmeli, yoksa objeden çıkan spline'lar sınır sanılır (v0.23.1)
        self._refs_sync(context)
        if self.tool in ("CIRCT", "PROJECT", "EDITSK"):
            self._pk_update(context, mx, my)
            return
        if self.tool in XFORM_TOOLS:
            self._xf_update(context, mx, my)
            return
        self._mod_init()
        self.mouse = (mx, my)
        self.cursor, self.preview, self.info, self.snap_kind = None, [], None, None
        tool = self._mod_tool()
        self.mod = None
        if not self.sketch:
            return
        if tool == "OFFSET":
            self._ofs_update(context, mx, my)
            return
        if tool in ("FILLET2D", "CHAMFER2D"):
            self._corner_update(mx, my)
            return
        hit = self._pick_seg(mx, my)
        if hit is None:
            return
        k, i, t, pos = hit
        st = self.sketch[k]
        ent = sm.entity_of(st, i)
        if ent is None:
            return
        i0, i1 = ent
        u = (i - i0) + t
        extra = self._extra_polys()
        scale = sm.sketch_scale(self.sketch, extra)
        if tool == "TRIM":
            cuts = sm.entity_cuts(self.sketch, k, i0, i1, extra, scale)
            spans = sm.trim_span(st, i0, i1, u, cuts)
            prev = []
            for a, b in spans:
                prev += sm.ent_sub(st["segs"], i0, i1, a, b)
            self.mod = {"kind": "TRIM", "k": k, "i0": i0, "i1": i1, "u": u, "cuts": cuts,
                        "prev": prev, "pos": pos}
        elif tool == "SPLIT":
            cuts = sm.entity_cuts(self.sketch, k, i0, i1, extra, scale)
            if sm.closed_entity(st, i0, i1):
                pts = [sm.ent_point(st, i0, i1, c) for c in cuts]
                ok = len(cuts) >= 2
                self.mod = {"kind": "SPLIT", "k": k, "i0": i0, "i1": i1, "u": u, "cuts": cuts,
                            "pts": pts, "ok": ok, "pos": pos}
            else:
                if not cuts:
                    self.mod = {"kind": "SPLIT", "k": k, "i0": i0, "i1": i1, "ok": False,
                                "pts": [], "pos": pos, "why": "Kesişim yok"}
                    return
                c = min(cuts, key=lambda c: float(np.linalg.norm(
                    sm.ent_point(st, i0, i1, c) - pos)))
                self.mod = {"kind": "SPLIT", "k": k, "i0": i0, "i1": i1, "u": c, "cuts": cuts,
                            "pts": [sm.ent_point(st, i0, i1, c)], "ok": True, "pos": pos}
        elif tool == "EXTEND":
            ends = self._extend_end(st, i0, i1, u, pos)
            if ends is None:
                self.mod = {"kind": "EXTEND", "ok": False, "pos": pos,
                            "why": "Bu uç başka bir parçaya bağlı"}
                return
            res, why = sm.extend_preview(self.sketch, k, ends, extra, scale)
            self.mod = {"kind": "EXTEND", "k": k, "end": ends, "ok": res is not None,
                        "why": why, "pos": pos}
            if res is not None:
                old = st["segs"][-1] if ends == 1 else sm.reverse_seg(st["segs"][0])
                tip0 = np.asarray(old["p"][3])
                self.mod["from"], self.mod["tip"] = tip0, res["tip"]
                n_old = len(st["segs"])
                self.mod["prev"] = res["segs"][n_old:] if len(res["segs"]) > n_old else []

    def _extend_end(self, st, i0, i1, u, pos):
        """Uzatılacak uç: 1 son, 0 baş; imlecin üzerindeki nesne uçta değilse None."""
        if st["cyclic"]:
            return None
        ents = sm.entities(st)
        first, last = ents[0] == (i0, i1), ents[-1] == (i0, i1)
        if first and last:
            n = i1 - i0
            return 0 if u < n / 2.0 else 1
        if last:
            return 1
        if first:
            return 0
        return None

    # ------------------------------------------------------------ ötele

    def _ofs_plane(self, sel):
        pts = [q for sg in sel["segs"] for q in sm._P(sg)]
        pl = sm.fit_plane(pts)
        if pl is None:
            pl0 = self._cur_plane() or self.tmp_plane
            if pl0 is None:
                return None
            n = pl0.n
            c = np.mean(np.array(pts), axis=0)
            if float(np.abs((np.array(pts) - c) @ n).max()) > 1e-6 * (1.0 + float(
                    np.abs(c).max())):
                return None
            return c, n
        c, n = pl
        cp = self._cur_plane() or self.tmp_plane
        if cp is not None and float(np.dot(n, cp.n)) < 0:
            n = -n
        return c, n

    def _ofs_update(self, context, mx, my):
        sel = self.off_sel
        if sel is None:
            hit = self._pick_seg(mx, my)
            if hit is not None:
                k = hit[0]
                self.mod = {"kind": "OFFSET_PICK", "k": k, "i": hit[1]}
            return
        c, n = sel["plane"]
        ro, rd = self._ray(mx, my)
        pl = dm.Plane.from_normal(c, n, "OFF")
        p = pl.ray_hit(ro, rd)
        if p is None:
            return
        d, q = sm.offset_distance(sel, p, n)
        typed = parse_length(self.typed[0]) if self.typed[0] else None
        if typed is not None:
            d = math.copysign(typed, d if d != 0 else 1.0)
        if abs(d) < 1e-12:
            return
        new, why = sm.offset(sel, d, n)
        self.mod = {"kind": "OFFSET", "d": d, "new": new, "why": why, "q": q, "p": p}

    def _ofs_click(self, context, mx, my):
        if self.off_sel is None:
            hit = self._pick_seg(mx, my)
            if hit is None:
                return
            k, i = hit[0], hit[1]
            st = self.sketch[k]
            if self.shift:                       # sadece imlecin altındaki nesne
                i0, i1 = sm.entity_of(st, i)
                segs = [dict(s) for s in st["segs"][i0:i1]]
                sel = {"segs": segs, "cyclic": sm.closed_entity(st, i0, i1)}
            else:                                # bütün çizgi (Inventor: döngü seçimi)
                sel = {"segs": [dict(s) for s in st["segs"]], "cyclic": st["cyclic"]}
            pl = self._ofs_plane(sel)
            if pl is None:
                self._status(context, "Ötele: çizgi tek bir düzlemde değil")
                return
            sel["plane"] = pl
            self.off_sel = sel
            self.typed, self.field = ["", ""], 0
            self._status(context, "Ötele: fareyle mesafe ver ya da yaz · tık / Enter: uygula · "
                                  "sağ tık: seçimi bırak")
            self._mod_update(context, mx, my)
            return
        self._mod_update(context, mx, my)
        m = self.mod
        if m is None or m.get("new") is None:
            if m is not None and m.get("why"):
                self._status(context, f"Ötele: {m['why']}")
            return
        new = m["new"]
        self.off_sel = None
        self.typed, self.field = ["", ""], 0
        from . import core
        self._set_sketch(context, self.sketch + [new],
                         f"Ötelendi: {core.fmt_len(abs(m['d']))} · taslak {len(self.sketch) + 1}"
                         " çizgi")

    # ------------------------------------------------------------ köşe

    def _corner_candidates(self):
        """[(konum, ("node", k, j) | ("pair", k1, e1, k2, e2))]"""
        out = []
        ends = []
        for k, st in enumerate(self.sketch):
            for j in sm.corners(st):
                out.append((sm.node_pos(st, j), ("node", k, j)))
            if not st["cyclic"] and st["segs"]:
                ends.append((np.asarray(st["segs"][0]["p"][0]), k, 0))
                ends.append((np.asarray(st["segs"][-1]["p"][3]), k, 1))
        for a in range(len(ends)):
            for b in range(a + 1, len(ends)):
                pa, ka, ea = ends[a]
                pb, kb, eb = ends[b]
                if ka == kb:
                    continue
                if np.linalg.norm(pa - pb) <= 1e-7 * (1.0 + float(np.abs(pa).max())):
                    out.append((pa, ("pair", ka, ea, kb, eb)))
        return out

    def _corner_value(self):
        if self.tool == "FILLET2D":
            v = parse_length(self.typed[0]) if self.typed[0] else self.fillet_r
            return v, None
        v1 = parse_length(self.typed[0]) if self.typed[0] else (
            self.chamfer_d[0] if self.chamfer_d else None)
        v2 = parse_length(self.typed[1]) if self.typed[1] else (
            None if self.typed[0] else (self.chamfer_d[1] if self.chamfer_d else None))
        return v1, v2

    def _corner_compute(self, cand, v1, v2):
        """(çalışma taslağı, çizgi sırası, düğüm, sonuç, sebep)"""
        kind = cand[0]
        sketch = self.sketch
        if kind == "lines":                       # ayrı iki doğru: kesişime uzat / kırp
            sketch, k, j = sm.lines_corner(sketch, cand[1], cand[2])
            if sketch is None:
                return None, None, None, None, k, v1
        elif kind == "pair":
            _, k1, e1, k2, e2 = cand
            sketch, k, j = sm.join_ends(sketch, k1, e1, k2, e2)
        else:
            _, k, j = cand
        st = sketch[k]
        if v1 is None:
            seg_a, seg_b = st["segs"][(j - 1) % len(st["segs"])], st["segs"][j % len(st["segs"])]
            L = min(sm.seg_length(seg_a), sm.seg_length(seg_b))
            v1 = round(L * 0.2, 6)
        if self.tool == "FILLET2D":
            res, why = sm.fillet_at(st, j, v1)
        else:
            res, why = sm.chamfer_at(st, j, v1, v2)
        return sketch, k, j, res, why, v1

    def _corner_update(self, mx, my):
        M = np.array(self.rv3d.perspective_matrix, dtype=np.float64)
        cands = self._corner_candidates()
        if not cands:
            self._corner_lines_update(mx, my)
            return
        P = np.array([c[0] for c in cands])
        px, ok, _ = _project(P, M, self.region)
        d = np.where(ok, np.linalg.norm(px - np.array([mx, my]), axis=1), np.inf)
        i = int(np.argmin(d))
        if d[i] > self.radius * 1.5:
            self._corner_lines_update(mx, my)
            return
        v1, v2 = self._corner_value()
        sketch, k, j, res, why, used = self._corner_compute(cands[i][1], v1, v2)
        self.mod = {"kind": "CORNER", "cand": cands[i][1], "pos": cands[i][0], "res": res,
                    "why": why, "value": used, "v2": v2}

    def _corner_lines_update(self, mx, my):
        """Köşe değilse: doğru seçimi (Inventor gibi iki ayrı doğru da yuvarlanır / pah
        kırılır; doğrular kesişime uzatılır / kırpılır)."""
        hit = self._pick_seg(mx, my)
        if hit is None:
            return
        k, i, t, pos = hit
        if self.sketch[k]["segs"][i]["kind"] != "line":
            return
        if self.fl_sel is not None and self.fl_sel[0] != k:
            v1, v2 = self._corner_value()
            cand = ("lines", self.fl_sel, (k, i, t))
            sketch, kk, j, res, why, used = self._corner_compute(cand, v1, v2)
            self.mod = {"kind": "CORNER", "cand": cand, "pos": pos, "res": res,
                        "why": why, "value": used, "v2": v2}
            return
        self.mod = {"kind": "LINEPICK", "k": k, "i": i, "t": t, "pos": pos}

    def _corner_click(self, context, mx, my):
        self._corner_update(mx, my)
        m = self.mod
        if m is None:
            return
        if m["kind"] == "LINEPICK":
            self.fl_sel = (m["k"], m["i"], m["t"])
            self._status(context, "İkinci doğruya tıkla (doğrular kesişime uzatılır / kırpılır)"
                                  " · sağ tık: bırak")
            return
        if m["res"] is None:
            self._status(context, m["why"])
            return
        v1, v2 = self._corner_value()
        sketch, k, j, res, why, used = self._corner_compute(m["cand"], v1, v2)
        if res is None:
            self._status(context, why)
            return
        new = sm.apply_corner(sketch, k, j, res)
        self.fl_sel = None
        from . import core
        if self.tool == "FILLET2D":
            # Inventor gibi: aynı oturumda aynı yarıçapla yapılanlar ilkine "eşit" bağlanır
            g = res["mids"][0]["p"]
            desc = ("seg", g[0], g[3], 0.125 * (np.asarray(g[0]) + 3 * np.asarray(g[1]) +
                                                3 * np.asarray(g[2]) + np.asarray(g[3])))
            eq = getattr(self, "fillet_eq", None)
            if eq and abs(eq[0] - used) <= 1e-12 * (1.0 + used):
                if not hasattr(self, "sk_cons") or self.sk_cons is None:
                    self.sk_cons = []
                self.sk_cons.append({"kind": "EQUAL", "refs": [eq[1], desc]})
            elif not eq or abs(eq[0] - used) > 1e-12 * (1.0 + used):
                self.fillet_eq = (used, desc)
            self.fillet_r = used
            msg = f"Köşe yuvarlandı: R {core.fmt_len(used)} (aynı yarıçapla devam edebilirsin)"
        else:
            self.chamfer_d = (used, v2)
            msg = f"Pah kırıldı: {core.fmt_len(used)}" + (
                f" × {core.fmt_len(v2)}" if v2 else "")
        self.typed, self.field = ["", ""], 0
        self._set_sketch(context, new, msg)

    # ------------------------------------------------------------ uygula

    def _mod_apply(self, context):
        m = self.mod
        if m is None:
            return False
        kind = m["kind"]
        if kind == "TRIM":
            new = sm.trim(self.sketch, m["k"], m["i0"], m["i1"], m["u"], m["cuts"])
            self._set_sketch(context, new, "Kırpıldı")
            return True
        if kind == "SPLIT":
            if not m["ok"]:
                self._status(context, "Böl: " + m.get("why", "kapalı nesne için iki kesişim "
                                                           "gerekli"))
                return False
            new = sm.split(self.sketch, m["k"], m["i0"], m["i1"], m["u"], m["cuts"])
            if new is None:
                self._status(context, "Böl: bu noktada bölünemez")
                return False
            self._set_sketch(context, new, "Bölündü")
            return True
        if kind == "EXTEND":
            if not m["ok"]:
                self._status(context, "Uzat: " + (m.get("why") or "sınır yok"))
                return False
            new, why = sm.extend(self.sketch, m["k"], m["end"], self._extra_polys())
            if new is None:
                self._status(context, "Uzat: " + why)
                return False
            self._set_sketch(context, new, "Uzatıldı")
            return True
        return False

    # ------------------------------------------------------------ olaylar

    def _mod_event(self, context, event, mx, my, press):
        """Değiştir araçlarının olayları; işlenmediyse None (genel işleyiciye gider)."""
        if self.tool in XFORM_TOOLS:
            return self._xf_event(context, event, mx, my, press)
        if self.tool in ("CIRCT", "PROJECT", "EDITSK"):
            return self._pk_event(context, event, mx, my, press)
        self._mod_init()
        et = event.type
        if et in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            self._mod_update(context, mx, my)
            if self.mod_drag and self.mod is not None and self._drag_last is not None and \
                    math.hypot(mx - self._drag_last[0], my - self._drag_last[1]) > \
                    2.0 * self.radius:
                # sürükleyerek çoklu: farenin geçtiği her nesne (aynı yerde tekrar değil)
                if self._mod_apply(context):
                    self._drag_last = (mx, my)
                    self._mod_update(context, mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if et == "LEFTMOUSE":
            if not press:
                self.mod_drag = False
                return {"RUNNING_MODAL"}
            tool = self._mod_tool()
            if tool == "OFFSET":
                self._ofs_click(context, mx, my)
            elif tool in ("FILLET2D", "CHAMFER2D"):
                self._corner_click(context, mx, my)
            else:
                self._mod_update(context, mx, my)
                self._mod_apply(context)
                self._mod_update(context, mx, my)
                self.mod_drag = tool in ("TRIM", "EXTEND")
                self._drag_last = (mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if not press:
            return {"RUNNING_MODAL"} if et == "RIGHTMOUSE" else None
        if et == "RIGHTMOUSE":
            self.fl_sel = None
            if self.off_sel is not None:
                self.off_sel = None
                self.typed, self.field = ["", ""], 0
                self._status(context, MOD_HELP["OFFSET"])
            self._mod_update(context, mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if et in {"RET", "NUMPAD_ENTER"} and not event.ctrl:
            if self.tool == "OFFSET" and self.off_sel is not None:
                self._ofs_click(context, mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if et == "TAB":
            if self.tool == "CHAMFER2D":
                self.field = 1 - self.field
            self._mod_update(context, mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if et == "BACK_SPACE":
            if self.typed[self.field]:
                self.typed[self.field] = self.typed[self.field][:-1]
                self._mod_update(context, mx, my)
                self.area.tag_redraw()
                return {"RUNNING_MODAL"}
            return None                           # taslakta geri al (genel)
        ch = event.unicode or ""
        typing = bool(self.typed[self.field])
        if ch and not event.ctrl and (ch in "0123456789.,+" or
                                      (typing and (ch.isalpha() or ch in "'\""))):
            if self.tool in ("OFFSET", "FILLET2D", "CHAMFER2D"):
                self.typed[self.field] += ch
                self._mod_update(context, mx, my)
                self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        return None

    # ------------------------------------------------------------ çizim

    def _draw_modify3d(self, region):
        if self.tool in ("CIRCT", "PROJECT", "EDITSK"):
            self._pk_draw3d(region)
            return
        if self.tool in XFORM_TOOLS:
            self._xf_draw3d(region)
            return
        self._mod_init()
        sel = self.off_sel
        if sel is not None:
            for sg in sel["segs"]:
                _poly([tuple(p) for p in dm.sample(sg, 2 if sg["kind"] == "line" else 20)],
                      COL_ACTIVE, 3.0, region)
        m = self.mod
        if m is None:
            return
        kind = m["kind"]
        if kind == "TRIM":
            for sg in m["prev"]:
                _poly([tuple(p) for p in dm.sample(sg, 2 if sg["kind"] == "line" else 24)],
                      COL_CUT, 3.5, region)
        elif kind == "EXTEND" and m.get("ok"):
            if m.get("prev"):
                for sg in m["prev"]:
                    _poly([tuple(p) for p in dm.sample(sg, 24)], COL_GUIDE, 3.0, region)
            else:
                _poly([tuple(m["from"]), tuple(m["tip"])], COL_GUIDE, 3.0, region)
        elif kind == "OFFSET_PICK":
            st = self.sketch[m["k"]]
            for sg in st["segs"]:
                _poly([tuple(p) for p in dm.sample(sg, 2 if sg["kind"] == "line" else 20)],
                      COL_RUBBER, 3.0, region)
        elif kind == "OFFSET" and m.get("new") is not None:
            for sg in m["new"]["segs"]:
                _poly([tuple(p) for p in dm.sample(sg, 2 if sg["kind"] == "line" else 20)],
                      COL_RUBBER, 2.2, region)
        elif kind == "LINEPICK":
            sg = self.sketch[m["k"]]["segs"][m["i"]]
            _poly([tuple(sg["p"][0]), tuple(sg["p"][3])], COL_RUBBER, 3.0, region)
        if self.fl_sel is not None and self.fl_sel[0] < len(self.sketch) and \
                self.fl_sel[1] < len(self.sketch[self.fl_sel[0]]["segs"]):
            sg = self.sketch[self.fl_sel[0]]["segs"][self.fl_sel[1]]
            _poly([tuple(sg["p"][0]), tuple(sg["p"][3])], COL_GUIDE, 4.0, region)
        if kind == "CORNER" and m.get("res") is not None:
            r = m["res"]
            for sg in [r["a"]] + r["mids"] + [r["b"]]:
                _poly([tuple(p) for p in dm.sample(sg, 2 if sg["kind"] == "line" else 20)],
                      COL_RUBBER, 2.5, region)

    def _draw_modify2d(self, region):
        if self.tool in ("CIRCT", "PROJECT", "EDITSK"):
            self._pk_draw2d(region)
            return
        if self.tool in XFORM_TOOLS:
            self._xf_draw2d(region)
            return
        self._mod_init()
        s = self.ui_scale
        mx, my = self.mouse
        m = self.mod
        label, rows = "", []
        if m is not None:
            kind = m["kind"]
            if kind == "TRIM":
                label = "Kırp" if m["cuts"] else "Kırp: kesişim yok, tamamı silinir"
            elif kind == "EXTEND":
                label = "Uzat" if m.get("ok") else f"Uzat: {m.get('why') or 'sınır yok'}"
                if m.get("ok"):
                    p = self._px(m["tip"])
                    if p is not None:
                        _marker("Kesişim", p[0], p[1], 6 * s, region)
            elif kind == "SPLIT":
                for q in m.get("pts", ()):
                    p = self._px(q)
                    if p is not None:
                        _marker("Kesişim", p[0], p[1], 6 * s, region)
                label = "Böl" if m.get("ok") else f"Böl: {m.get('why') or 'iki kesişim gerekli'}"
            elif kind == "OFFSET_PICK":
                label = "Ötele: çizgiyi seç (Shift: tek nesne)"
            elif kind == "OFFSET":
                from . import core
                val = self.typed[0] + "_" if self.typed[0] else core.fmt_len(abs(m["d"]))
                rows = [("Mesafe", val, True)]
                a, b = self._px(m["q"]), self._px(m["p"])
                if a is not None and b is not None:
                    _dashed(a, b, COL_GUIDE, region)
                label = m.get("why") or ""
            elif kind == "CORNER":
                from . import core
                p = self._px(m["pos"])
                if p is not None:
                    _marker("Uç", p[0], p[1], 6 * s, region)
                v = core.fmt_len(m["value"]) if m.get("value") else "—"
                if self.tool == "FILLET2D":
                    rows = [("Yarıçap", self.typed[0] + "_" if self.typed[0] else v, True)]
                else:
                    v2 = self.typed[1] + ("_" if self.field == 1 else "") if self.typed[1] \
                        else ("eşit" if not m.get("v2") else core.fmt_len(m["v2"]))
                    rows = [("Mesafe 1", self.typed[0] + ("_" if self.field == 0 else "")
                             if self.typed[0] else v, self.field == 0),
                            ("Mesafe 2", v2, self.field == 1)]
                if m.get("res") is None:
                    label = m.get("why") or ""
        elif self.tool in ("FILLET2D", "CHAMFER2D") and (self.typed[0] or self.typed[1]):
            rows = [("Değer", self.typed[0] + "_", True)]
        if label:
            _text(mx + 14 * s, my + 12 * s, label, COL_SNAP, int(11 * s))
        if rows:
            self._draw_rows((mx, my), rows)
