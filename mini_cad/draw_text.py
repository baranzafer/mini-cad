"""Metin ve Taslağa al araçları (v0.21.0):

  Metin       yazının sol alt köşesine tıkla, yaz (Tab: yükseklik), Enter: harflerin çizgileri
              taslağa eklenir (Blender yazı nesnesi eğriye çevrilir; her harf çizgisi kapalı
              bir taslak çizgisi). Esc: vazgeç.
  Taslağa al  kaydedilmiş bir eğriye tıkla: o spline taslağa alınır (Inventor "Edit Sketch").
              Bütün taslak araçlarıyla düzenlenir; Bitir'de aynı objeye geri yazılır.
              Ona bağlı yüzey, fillet ve kısıt referansları geçici bir işarete bağlanır ve
              Bitir'de yeni spline sırasına eşlenir (segment sayısı değişmediyse korunur).

MINICAD_OT_draw (draw.py) bu mixin'den miras alır.
"""
import itertools

import bpy
import numpy as np

from . import core
from . import drawmath as dm
from . import sketchmath as sm
from .draw_common import COL_RUBBER, COL_SNAP, _poly, _text, parse_length

_TOKENS = itertools.count(1)


def _token():
    return -1000 - next(_TOKENS)


def segs_from_bezier(pts, cyclic):
    """[(co, hl, hr)] dünya noktalarından taslak segmentleri (doğru / yay / eğri)."""
    n = len(pts)
    m = n if cyclic else n - 1
    segs = []
    g = sm.new_grp()
    for i in range(m):
        a, b = pts[i], pts[(i + 1) % n]
        P = [np.asarray(a[0]), np.asarray(a[2]), np.asarray(b[1]), np.asarray(b[0])]
        if float(np.linalg.norm(P[3] - P[0])) < 1e-12 and float(np.linalg.norm(P[1] - P[0])) \
                < 1e-12:
            continue
        if dm.is_straight_poly(np.array(P)):
            segs.append(dm.line_seg(P[0], P[3]))
        elif dm.arc_of_bezier(P) is not None:
            segs.append({"kind": "arc", "p": tuple(P)})
        else:
            segs.append({"kind": "curve", "p": tuple(P), "grp": g})
    if cyclic and segs:
        segs[-1]["p"] = tuple(segs[-1]["p"][:3]) + (segs[0]["p"][0],)
    return segs


class TextMixin:
    """Metin aracı ve kaydedilmiş eğriyi taslağa alma."""

    def _txt_init(self):
        if not hasattr(self, "txt"):
            self.txt = None
        if not hasattr(self, "text_h"):
            self.text_h = None

    # ------------------------------------------------------------ metin

    def _font_splines(self, context, text, size):
        """Blender yazı nesnesinden eğriler: [([(co, hl, hr) yerel 2B], kapalı mı)]."""
        cu = bpy.data.curves.new("MC_tmp_text", "FONT")
        ob = bpy.data.objects.new("MC_tmp_text", cu)
        out = []
        try:
            cu.body = text
            cu.size = size
            context.scene.collection.objects.link(ob)
            dg = context.evaluated_depsgraph_get()
            ev = ob.evaluated_get(dg)
            cc = ev.to_curve(dg)
            for sp in cc.splines:
                if sp.type != "BEZIER" or len(sp.bezier_points) < 2:
                    continue
                pts = [(tuple(b.co)[:2], tuple(b.handle_left)[:2], tuple(b.handle_right)[:2])
                       for b in sp.bezier_points]
                out.append((pts, bool(sp.use_cyclic_u)))
            try:
                ev.to_curve_clear()
            except Exception:
                pass
        finally:
            try:
                context.scene.collection.objects.unlink(ob)
            except Exception:
                pass
            try:
                bpy.data.objects.remove(ob)
                bpy.data.curves.remove(cu)
            except Exception:
                pass
        return out

    def _txt_strokes(self, context):
        t = self.txt
        if not t or not t["text"].strip():
            return []
        h = parse_length(t["htyped"]) if t["htyped"] else t["h"]
        if h is None or h <= 0:
            return []
        pl = t["plane"]
        base = pl.uv(t["pos"])
        hh = pl.dist(t["pos"])
        strokes = []
        for pts, cyc in self._font_splines(context, t["text"], h):
            W = [tuple(pl.xyz((base[0] + q[0], base[1] + q[1])) + pl.n * hh for q in p)
                 for p in pts]
            segs = segs_from_bezier(W, cyc)
            if segs:
                strokes.append({"segs": segs, "cyclic": cyc, "node_ids": {}, "start_tan": None})
        return strokes

    def _txt_start(self, context, cur):
        self._txt_init()
        pl = (self.plane or self.tmp_plane or self._make_plane(self.plane_mode, cur)).moved(cur)
        h = self.text_h or round(self._grid_step(cur) * 2.0, 9)
        self.txt = {"pos": np.asarray(cur, dtype=np.float64).copy(), "plane": pl, "text": "",
                    "h": h, "htyped": "", "field": 0, "prev": []}
        self._status(context, "Metin: yaz · Tab: yükseklik · Enter: taslağa ekle · Esc: vazgeç")

    def _txt_event(self, context, event):
        """Metin yazılırken bütün tuşlar metne gider. İşlendiyse sonuç, değilse None."""
        t = self.txt
        et = event.type
        if et in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE", "TIMER", "TIMER_REPORT", "NONE",
                  "MIDDLEMOUSE", "WHEELUPMOUSE", "WHEELDOWNMOUSE", "TRACKPADPAN",
                  "TRACKPADZOOM"}:
            return None
        if event.value != "PRESS":
            return {"RUNNING_MODAL"}
        if et == "ESC":
            self.txt = None
            self._status(context, "Metin iptal edildi")
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if et in {"RET", "NUMPAD_ENTER"}:
            strokes = self._txt_strokes(context)
            if t["htyped"]:
                v = parse_length(t["htyped"])
                if v:
                    self.text_h = v
            self.txt = None
            if strokes:
                self._set_sketch(context, self.sketch + strokes,
                                 f"Metin taslağa eklendi: {len(strokes)} çizgi")
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if et == "TAB":
            t["field"] = 1 - t["field"]
        elif et == "BACK_SPACE":
            key = "text" if t["field"] == 0 else "htyped"
            t[key] = t[key][:-1]
        else:
            ch = event.unicode or ""
            if ch and not event.ctrl and ch.isprintable():
                if t["field"] == 0:
                    t["text"] += ch
                else:
                    t["htyped"] += ch
            else:
                return {"RUNNING_MODAL"}
        try:
            t["prev"] = self._txt_strokes(context)
        except Exception as e:
            t["prev"] = []
            self._status(context, f"Metin çizilemedi: {e}")
        self.area.tag_redraw()
        return {"RUNNING_MODAL"}

    # ------------------------------------------------------------ taslağa al

    def _edit_load(self, context, name, si):
        """Kaydedilmiş spline'ı taslağa alır. Başarılı mı."""
        ob = bpy.data.objects.get(name)
        if ob is None or ob.type != "CURVE":
            return False
        sps = ob.data.splines
        if not (0 <= si < len(sps)) or sps[si].type != "BEZIER" or \
                len(sps[si].bezier_points) < 2:
            self._status(context, "Taslağa al: yalnızca bezier eğriler")
            return False
        sp = sps[si]
        mw = ob.matrix_world
        pts = [tuple(np.array(mw @ v, dtype=np.float64) for v in (b.co, b.handle_left,
                                                                  b.handle_right))
               for b in sp.bezier_points]
        cyc = bool(sp.use_cyclic_u)
        segs = segs_from_bezier(pts, cyc)
        if not segs:
            return False
        tok = _token()
        core.remap_splines(ob, lambda s_, r=si, t_=tok: t_ if s_ == r else (s_ - 1 if s_ > r
                                                                             else s_))
        sps.remove(sp)
        try:
            ob.data.update_tag()
        except Exception:
            pass
        self.sketch.append({"segs": segs, "cyclic": cyc, "node_ids": {}, "start_tan": None,
                            "edit_src": {"obj": ob.name, "token": tok}})
        self.dirty = True
        self._hist_reset()               # spline objeden çıktı: öncesine taslakta dönülmez
        self._refs_sync(context)         # çıkan spline'lar yakalama / sınır olmasın
        self._status(context, f"Taslağa alındı: '{ob.name}' spline {si} · düzenle, Bitir "
                              "(Ctrl+Enter) ile geri yazılır")
        return True

    def _edit_load_all(self, context, name):
        """v0.23.0: bir eğri objesinin (çizimin) bütün bezier spline'larını taslağa alır
        (Outliner'dan "Çizimi Düzenle"). Spline sırası korunur: Bitir'de aynı sırayla geri
        yazılır. Tek noktalı (Nokta) ve bezier olmayan spline'lar objede kalır. Çizim
        düzlemselse çizim düzlemi o düzleme kilitlenir. Alınan çizgi sayısı."""
        ob = bpy.data.objects.get(name)
        if ob is None or ob.type != "CURVE":
            self._status(context, "Çizimi düzenle: eğri objesi değil")
            return 0
        sps = ob.data.splines
        idx = [i for i, sp in enumerate(sps)
               if sp.type == "BEZIER" and len(sp.bezier_points) >= 2]
        if not idx:
            self._status(context, f"Çizimi düzenle: '{ob.name}' içinde düzenlenecek çizgi yok")
            return 0
        mw = ob.matrix_world
        loaded = []                                      # (spline, segs, kapalı)
        for i in idx:
            sp = sps[i]
            pts = [tuple(np.array(mw @ v, dtype=np.float64) for v in (b.co, b.handle_left,
                                                                      b.handle_right))
                   for b in sp.bezier_points]
            cyc = bool(sp.use_cyclic_u)
            segs = segs_from_bezier(pts, cyc)
            if segs:
                loaded.append((i, segs, cyc))
        if not loaded:
            return 0
        toks = {i: _token() for i, _s, _c in loaded}
        gone = sorted(toks)

        def fn(s_, toks=toks, gone=gone):
            if s_ in toks:
                return toks[s_]
            return s_ - sum(1 for g in gone if g < s_)
        core.remap_splines(ob, fn)
        for i in reversed(gone):
            sps.remove(sps[i])
        try:
            ob.data.update_tag()
        except Exception:
            pass
        for i, segs, cyc in loaded:
            self.sketch.append({"segs": segs, "cyclic": cyc, "node_ids": {}, "start_tan": None,
                                "edit_src": {"obj": ob.name, "token": toks[i]}})
        self.edit_obj = ob.name                          # yeni çizgiler de bu çizime yazılır
        self.dirty = True
        self._hist_reset()               # spline'lar objeden çıktı: öncesine taslakta dönülmez
        self._refs_sync(context)         # çıkan spline'lar yakalama / sınır olmasın
        pl = self._edit_plane(loaded)
        if pl is not None:
            self._lock_plane(context, pl.name, pl)
        msg = (f"Çizim düzenleniyor: '{ob.name}' · {len(loaded)} çizgi taslakta · Bitir "
               "(Ctrl+Enter) ile geri yazılır")
        self._status(context, msg)
        try:
            from . import recorder
            recorder.log("çiz", msg)
        except Exception:
            pass
        return len(loaded)

    @staticmethod
    def _edit_plane(loaded):
        """Taslağa alınan çizgilerin ortak düzlemi (eksen düzlemiyse o), yoksa None."""
        P = np.array([p for _i, segs, _c in loaded for sg in segs for p in sg["p"]],
                     dtype=np.float64)
        if len(P) < 3:
            return None
        o = P.mean(axis=0)
        ext = float(np.ptp(P, axis=0).max())
        if ext < 1e-9:
            return None
        _u, s, vt = np.linalg.svd(P - o)
        if s[1] < 1e-9 * max(ext, 1.0) * len(P) ** 0.5:
            return None                                   # tek doğru: düzlem belirsiz
        n = vt[2]
        if float(np.abs((P - o) @ n).max()) > 1e-6 * max(ext, 1.0):
            return None                                   # düzlemsel değil
        for name in ("XY", "XZ", "YZ"):
            ax = dm.Plane.axis(name, o)
            if abs(float(np.dot(ax.n, n))) > 1.0 - 1e-9:
                return ax
        return dm.Plane.from_normal(o, n, "FACE")

    # ------------------------------------------------------------ çizim

    def _txt_draw3d(self, region):
        t = getattr(self, "txt", None)
        if not t:
            return
        for st in t.get("prev") or ():
            for sg in st["segs"]:
                _poly([tuple(p) for p in dm.sample(sg, 2 if sg["kind"] == "line" else 12)],
                      COL_RUBBER, 1.8, region)

    def _txt_draw2d(self, region):
        t = getattr(self, "txt", None)
        if not t:
            return
        from . import core as _c
        s = self.ui_scale
        p = self._px(t["pos"])
        if p is None:
            return
        h = t["htyped"] + "_" if t["field"] == 1 else (t["htyped"] or _c.fmt_len(t["h"]))
        rows = [("Metin", t["text"] + ("_" if t["field"] == 0 else ""), t["field"] == 0),
                ("Yükseklik", h, t["field"] == 1)]
        self._draw_rows(p, rows)
        _text(p[0] + 14 * s, p[1] + 12 * s, "Metin: Enter ekle · Esc vazgeç", COL_SNAP,
              int(11 * s))
