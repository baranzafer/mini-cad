"""Düzenle ve Desen araçları (Inventor 2D gibi), taslak üzerinde çalışır:

  Seçim (bütün araçlar)  çizgiye tıkla: seç / bırak · boşlukta sürükle: kutu
                         (soldan sağa: tamamen içindekiler, sağdan sola: değenler) ·
                         Enter / sağ tık: devam
  Taşı / Kopyala         temel nokta → hedef nokta (yakalama, kılavuz, ızgara; uzunluk /
                         açı yazılabilir)
  Döndür                 merkez → açı (fare ya da yazarak; Shift: 15°) · C: kopya
  Ölçekle                temel nokta → ölçek (fare ya da yazarak) · C: kopya
  Esnet                  kutuyla nokta seç → temel → hedef: seçili noktalar taşınır, bağlı
                         parçalar esner
  Dikdörtgen desen       temel → 1. yön (adet, aralık) → 2. yön (isteğe bağlı; Enter: atla)
  Dairesel desen         merkez → adet, açı (varsayılan 6 adet, 360°)
  Ayna                   ayna çizgisinin iki noktası; kopyalar eklenir

İşlem bitince seçim korunur ve temel nokta adımına dönülür (aynı seçimle devam edilebilir).
Matematik sketchmath.py'de. MINICAD_OT_draw (draw.py) bu mixin'den miras alır.
"""
import math
import numpy as np

from . import drawmath as dm
from . import sketchmath as sm
from .draw_common import (
    COL_ACTIVE, COL_GUIDE, COL_RUBBER, COL_SNAP, XFORM_TOOLS, _dashed, _marker, _poly,
    _project, _text, parse_angle, parse_length,
)

XF_HELP = {
    "MOVE": "Taşı", "COPY": "Kopyala", "ROTATE": "Döndür", "SCALE": "Ölçekle",
    "STRETCH": "Esnet", "RPAT": "Dikdörtgen desen", "CPAT": "Dairesel desen",
    "MIRROR": "Ayna",
}
XF_BASE = {
    "MOVE": "temel noktaya tıkla", "COPY": "temel noktaya tıkla",
    "ROTATE": "dönme merkezine tıkla", "SCALE": "temel noktaya tıkla",
    "STRETCH": "temel noktaya tıkla", "RPAT": "desenin başlangıç noktasına tıkla",
    "CPAT": "desen merkezine tıkla", "MIRROR": "ayna çizgisinin ilk noktasına tıkla",
}
XF_TGT = {
    "MOVE": "hedef noktaya tıkla (uzunluk / açı yazılabilir)",
    "COPY": "hedef noktaya tıkla (uzunluk / açı yazılabilir)",
    "ROTATE": "açıyı fareyle ver ya da yaz (Shift: 15°) · C: kopya",
    "SCALE": "ölçeği fareyle ver ya da yaz · C: kopya",
    "STRETCH": "hedef noktaya tıkla (uzunluk / açı yazılabilir)",
    "RPAT": "1. yön: fareyle yön ve aralık · Adet / Aralık yaz (Tab)",
    "CPAT": "Adet / Açı yaz (Tab) · tık / Enter: uygula",
    "MIRROR": "ayna çizgisinin ikinci noktasına tıkla",
}
COL_SEL = (1.0, 0.75, 0.25, 0.95)


class TransformMixin:
    """Taşı / Kopyala / Döndür / Ölçekle / Esnet / Dikdörtgen ve dairesel desen / Ayna."""

    # ------------------------------------------------------------ durum

    def _xf_init(self):
        if not hasattr(self, "xsel"):
            self.xsel = set()
        if not hasattr(self, "xnodes"):
            self.xnodes = set()
        if not hasattr(self, "xf"):
            self.xf = None
        if not hasattr(self, "xprev"):
            self.xprev = []
        if not hasattr(self, "xpts"):
            self.xpts = set()            # seçili taslak noktaları (sk_points sırası)

    def _xf_begin(self, context, tool, keep):
        """Araç seçilince: seçim (önceki düzenle aracından) korunur."""
        self._xf_init()
        if not keep:
            self.xsel, self.xnodes, self.xpts = set(), set(), set()
        self._xf_valid()
        step = "BASE" if self._xf_any() else "SEL"
        self.xf = {"step": step, "copy": tool == "COPY", "box0": None, "box1": None}
        self.xprev = []
        self.typed, self.field = ["", ""], 0
        return self._xf_msg()

    def _xf_any(self):
        return bool(self.xsel or self.xnodes or getattr(self, "xpts", None))

    def _pts(self):
        return getattr(self, "sk_points", None) or []

    def _xf_valid(self):
        self.xpts = {i for i in getattr(self, "xpts", set()) if 0 <= i < len(self._pts())}
        n = len(self.sketch)
        self.xsel = {k for k in self.xsel if 0 <= k < n}
        self.xnodes = {(k, j) for k, j in self.xnodes if 0 <= k < n and
                       0 <= j < len(sm.stroke_nodes(self.sketch[k]))}

    def _xf_msg(self):
        xf = self.xf
        name = XF_HELP.get(self.tool, self.tool)
        if xf is None:
            return name
        n = len(self.xsel)
        sel = f"{n} çizgi" + (f", {len(self.xnodes)} düğüm" if self.xnodes else "") + \
            (f", {len(self.xpts)} nokta" if self.xpts else "")
        if xf["step"] == "SEL":
            what = "noktaları kutuyla seç (çizgiye tık: tamamı)" if self.tool == "STRETCH" \
                else "çizgilere tıkla ya da kutuyla seç"
            return f"{name}: {what} · seçili {sel} · Enter / sağ tık: devam"
        if xf["step"] == "BASE":
            return f"{name}: {XF_BASE[self.tool]} · seçili {sel} · sağ tık: seçime dön"
        if xf["step"] == "DIR2":
            return f"{name}: 2. yön (isteğe bağlı) · Adet / Aralık yaz · Enter / sağ tık: " \
                   "sadece 1. yön"
        extra = ""
        if self.tool in ("ROTATE", "SCALE"):
            extra = f" · kopya {'açık' if xf['copy'] else 'kapalı'}"
        return f"{name}: {XF_TGT[self.tool]}{extra} · sağ tık: temel noktaya dön"

    # ------------------------------------------------------------ nokta (çizimdeki yakalama)

    def _xf_point(self, context, mx, my, anchor=None, use_typed=False):
        """Çizim aracının bütün yakalama / kılavuz / ızgara / kilit mantığıyla nokta: araç
        geçici olarak Doğru, başlangıç 'anchor' sayılır."""
        saved = (self.tool, self.start, self.plane, self.segs, self.stage, self.typed)
        try:
            self.tool, self.segs, self.stage = "LINE", [], []
            self.start = None if anchor is None else np.asarray(anchor, dtype=np.float64)
            if anchor is not None:
                base = self.xf.get("plane") or self.tmp_plane or \
                    self._make_plane(self.plane_mode, anchor)
                self.plane = base.moved(anchor)
            else:
                self.plane = None
            if not use_typed:
                self.typed = ["", ""]
            self._update(context, mx, my)
        finally:
            self.tool, self.start, self.plane, self.segs, self.stage, self.typed = saved
        return self.cursor

    def _xf_plane(self):
        return self.xf.get("plane") or self._cur_plane() or self.tmp_plane

    # ------------------------------------------------------------ önizleme

    def _xf_transform(self, context, mx, my):
        """Hedef adımında (dönüşüm, ek bilgi) — dönüşüm None olabilir."""
        xf = self.xf
        t = self.tool
        base = xf["base"]
        n = xf["n"]
        if t in ("MOVE", "COPY", "STRETCH", "MIRROR"):
            p = self._xf_point(context, mx, my, base, use_typed=True)
            if p is None or np.linalg.norm(p - base) < 1e-12:
                return None, {}
            if t == "MIRROR":
                return sm.T_mirror(base, p, n), {"p": p}
            return sm.T_move(p - base), {"p": p, "d": p - base}
        if t == "ROTATE":
            p = self._xf_point(context, mx, my, base)
            typed = parse_angle(self.typed[0]) if self.typed[0] else None
            if typed is not None:
                ang = typed
            else:
                if p is None:
                    return None, {}
                pl = self._xf_plane()
                ang = dm.seg_angle(pl, base, p) - xf["ref_ang"]
                if self.shift:
                    ang = round(ang / 15.0) * 15.0
                ang = (ang + 180.0) % 360.0 - 180.0
            sgn = 1.0 if float(np.dot(self._xf_plane().n, n)) >= 0 else -1.0
            return sm.T_rotate(base, n, math.radians(ang) * sgn), {"p": p, "ang": ang}
        if t == "SCALE":
            p = self._xf_point(context, mx, my, base)
            typed = None
            if self.typed[0]:
                try:
                    typed = float(self.typed[0].replace(",", "."))
                except ValueError:
                    typed = None
            if typed is not None and typed > 0:
                s = typed
            else:
                if p is None or xf["ref_d"] < 1e-12:
                    return None, {}
                s = float(np.linalg.norm(p - base)) / xf["ref_d"]
            if s < 1e-9:
                return None, {}
            return sm.T_scale(base, s), {"p": p, "s": s}
        return None, {}

    def _xf_count(self, txt, default):
        try:
            v = int(float(txt.replace(",", "."))) if txt else default
        except ValueError:
            v = default
        return max(1, v)

    def _xf_pattern(self, context, mx, my):
        """Desen dönüşümleri ve ek bilgi."""
        xf = self.xf
        base = xf["base"]
        if self.tool == "CPAT":
            cnt = self._xf_count(self.typed[0], 6)
            ang = parse_angle(self.typed[1]) if self.typed[1] else 360.0
            p = self._xf_point(context, mx, my, base)
            xf["pdef"] = {"kind": "CPAT", "center": base, "axis": xf["n"], "n1": cnt,
                          "angle": ang}
            return sm.circ_pattern(base, xf["n"], cnt, ang), {"p": p, "n": cnt, "ang": ang}
        p = self._xf_point(context, mx, my, base)
        if p is None or np.linalg.norm(p - base) < 1e-12:
            return [], {}
        d = p - base
        L = float(np.linalg.norm(d))
        typed_L = parse_length(self.typed[1]) if self.typed[1] else None
        if typed_L is not None:
            d = d / L * typed_L
            L = typed_L
        if xf["step"] == "TGT":
            cnt = self._xf_count(self.typed[0], 3)
            return sm.rect_pattern(d, cnt), {"p": p, "n": cnt, "L": L, "d": d}
        cnt = self._xf_count(self.typed[0], 2)
        xf["pdef"] = self._rpat_def(xf["d1"], xf["n1"], d, cnt)
        return sm.rect_pattern(xf["d1"], xf["n1"], d, cnt), {"p": p, "n": cnt, "L": L, "d": d}

    def _rpat_def(self, d1, n1, d2=None, n2=1):
        d1 = np.asarray(d1, dtype=np.float64)
        L1 = float(np.linalg.norm(d1))
        if d2 is None or n2 <= 1:
            d2, n2 = np.zeros(3), 1
        d2 = np.asarray(d2, dtype=np.float64)
        L2 = float(np.linalg.norm(d2))
        return {"kind": "RPAT", "dir1": d1 / L1 if L1 > 1e-15 else d1, "s1": L1, "n1": int(n1),
                "dir2": d2 / L2 if L2 > 1e-15 else d2, "s2": L2, "n2": int(n2)}

    def _tag_pattern(self, n_before, ks, fns):
        """Desen kaynaklarını ve kopyalarını ilişki için etiketler (Bitir'de kayda dönüşür)."""
        pdef = (self.xf or {}).get("pdef")
        if pdef is None or not ks:
            return
        if not hasattr(self, "sk_pats") or self.sk_pats is None:
            self.sk_pats = {}
        pid = max(self.sk_pats.keys(), default=0) + 1
        self.sk_pats[pid] = dict(pdef, nsrc=len(ks), ninst=len(fns))
        for j, k in enumerate(ks):
            self.sketch[k]["pat"] = (pid, "src", 0, j)
        for m in range(len(fns) * len(ks)):
            st = self.sketch[n_before + m]
            st["pat"] = (pid, "copy", m // len(ks) + 1, m % len(ks))

    def _mirror_line(self, a, b):
        """Ayna noktaları gerçek bir doğrunun iki ucuysa o doğru (simetri kısıtı için)."""
        tol = 1e-7 * (1.0 + float(max(np.abs(a).max(), np.abs(b).max())))
        for A, B in self.refs.chords:
            A, B = np.asarray(A), np.asarray(B)
            if (np.linalg.norm(A - a) <= tol and np.linalg.norm(B - b) <= tol) or \
                    (np.linalg.norm(A - b) <= tol and np.linalg.norm(B - a) <= tol):
                return A, B
        return None

    def _xf_update(self, context, mx, my):
        self._xf_init()
        self.mouse = (mx, my)
        xf = self.xf
        if xf is None:
            return
        self._xf_valid()
        self.xprev, self.mod = [], None
        step = xf["step"]
        if step == "SEL":
            self.cursor, self.preview, self.info, self.snap_kind = None, [], None, None
            if xf.get("box0") is not None:
                xf["box1"] = (mx, my)
                return
            hit = self._pick_seg(mx, my) if self.sketch else None
            xf["hover"] = None if hit is None else hit[0]
            return
        if step == "BASE":
            self._xf_point(context, mx, my)
            self.preview = []
            return
        ks = sorted(self.xsel)
        P = [self._pts()[i] for i in sorted(self.xpts)]
        xf["ptprev"] = []
        if self.tool in ("RPAT", "CPAT"):
            fns, info = self._xf_pattern(context, mx, my)
            xf["info"] = info
            xf["fns"] = fns
            self.xprev = [sm.xform_stroke(self.sketch[k], f) for f in fns for k in ks]
            xf["ptprev"] = [f(p) for f in fns for p in P]
            return
        f, info = self._xf_transform(context, mx, my)
        xf["info"] = info
        xf["fn"] = f
        if f is None:
            return
        xf["ptprev"] = [f(p) for p in P]
        if self.tool == "STRETCH":
            new = sm.stretch(self.sketch, self._xf_nodes(), info["d"])
            touched = {k for k, _ in self._xf_nodes()}
            self.xprev = [new[k] for k in sorted(touched)]
        else:
            self.xprev = [sm.xform_stroke(self.sketch[k], f) for k in ks]

    def _xf_nodes(self):
        out = set(self.xnodes)
        for k in self.xsel:
            out |= {(k, j) for j in range(len(sm.stroke_nodes(self.sketch[k])))}
        return out

    # ------------------------------------------------------------ seçim

    def _xf_box_points(self, inside, M):
        P = self._pts()
        if not P:
            return
        px, ok, _ = _project(np.array(P), M, self.region)
        for i in np.where(inside(px) & ok)[0]:
            self.xpts.add(int(i))

    def _xf_point_at(self, mx, my):
        P = self._pts()
        if not P:
            return None
        M = np.array(self.rv3d.perspective_matrix, dtype=np.float64)
        px, ok, _ = _project(np.array(P), M, self.region)
        d = np.where(ok, np.linalg.norm(px - np.array([mx, my]), axis=1), np.inf)
        i = int(np.argmin(d))
        return i if d[i] <= self.radius else None

    def _xf_box_select(self, x0, y0, x1, y1):
        crossing = x1 < x0               # sağdan sola: değenler (Inventor / AutoCAD gibi)
        lo_x, hi_x = min(x0, x1), max(x0, x1)
        lo_y, hi_y = min(y0, y1), max(y0, y1)
        M = np.array(self.rv3d.perspective_matrix, dtype=np.float64)

        def inside(px):
            return (px[:, 0] >= lo_x) & (px[:, 0] <= hi_x) & (px[:, 1] >= lo_y) & \
                (px[:, 1] <= hi_y)
        self._xf_box_points(inside, M)
        if self.tool == "STRETCH":
            for k, st in enumerate(self.sketch):
                P = np.array(sm.stroke_nodes(st))
                px, ok, _ = _project(P, M, self.region)
                for j in np.where(inside(px) & ok)[0]:
                    self.xnodes.add((k, int(j)))
            return
        for k, st in enumerate(self.sketch):
            S = np.vstack([dm.sample(sg, 17) for sg in st["segs"]])
            px, ok, _ = _project(S, M, self.region)
            ins = inside(px) & ok
            if (ins.any() if crossing else ins.all()):
                self.xsel.add(k)

    # ------------------------------------------------------------ uygula

    def _xf_apply(self, context):
        xf = self.xf
        t = self.tool
        ks = sorted(self.xsel)
        name = XF_HELP[t]
        pts = self._pts()
        P = [pts[i] for i in sorted(self.xpts)]
        new_pts = None
        if t in ("RPAT", "CPAT"):
            fns = xf.get("fns") or []
            if not fns:
                self._status(context, f"{name}: en az 2 adet gerekli")
                return False
            new = sm.apply_many(self.sketch, ks, fns)
            new_pts = list(pts) + [f(p) for f in fns for p in P]
            msg = f"{name}: {len(fns)} kopya eklendi"
            n_before = len(self.sketch)
        else:
            f = xf.get("fn")
            if f is None:
                return False
            if t == "STRETCH":
                new = sm.stretch(self.sketch, self._xf_nodes(), xf["info"]["d"])
                msg = "Esnetildi"
                cp = False
            elif t == "MIRROR":
                new = sm.apply_xform(self.sketch, ks, f, copy_=True)
                msg = f"Ayna: {len(ks)} çizgi kopyalandı"
                cp = True
                line = self._mirror_line(xf["base"], (xf.get("info") or {}).get("p"))
                if line is not None:              # Inventor gibi: simetri kısıtları
                    if not hasattr(self, "sk_cons") or self.sk_cons is None:
                        self.sk_cons = []
                    A, B = line
                    n0 = len(self.sk_cons)
                    srcs = [q for k in ks for q in sm.stroke_nodes(self.sketch[k])] + list(P)
                    seen = []
                    for q in srcs:
                        q = np.asarray(q, dtype=np.float64)
                        r = f(q)
                        tol = 1e-7 * (1.0 + float(np.abs(q).max()))
                        if np.linalg.norm(r - q) <= tol or any(np.linalg.norm(q - z) <= tol
                                                               for z in seen):
                            continue              # ayna çizgisi üzerindeki / tekrar eden
                        seen.append(q)
                        self.sk_cons.append({"kind": "SYMLINE", "refs": [
                            ("pt", q), ("pt", r), ("seg", A, B, None)]})
                    msg += f" · {len(self.sk_cons) - n0} simetri kısıtı Bitir'de yazılır"
                else:
                    msg += " · simetri kısıtı için ayna çizgisi olarak bir doğrunun uçlarını seç"
            else:
                cp = t == "COPY" or (t in ("ROTATE", "SCALE") and xf["copy"])
                new = sm.apply_xform(self.sketch, ks, f, copy_=cp)
                msg = f"{name}: {len(ks)} çizgi" + (" (kopya)" if cp and t != "COPY" else "")
            if P:
                if cp:
                    new_pts = list(pts) + [f(p) for p in P]
                else:
                    new_pts = [f(p) if i in self.xpts else p for i, p in enumerate(pts)]
        if new_pts is not None:
            self.sk_points = [np.asarray(p, dtype=np.float64) for p in new_pts]
            if P:
                msg += f" · {len(P)} nokta"
        self._set_sketch(context, new, msg)
        if t in ("RPAT", "CPAT"):
            self._tag_pattern(n_before, ks, fns)
        xf.update(step="BASE", fn=None, fns=None)
        self.xprev = []
        self.typed, self.field = ["", ""], 0
        return True

    # ------------------------------------------------------------ olaylar

    def _xf_event(self, context, event, mx, my, press):
        self._xf_init()
        xf = self.xf
        if xf is None:
            xf = self.xf = {"step": "SEL", "copy": False, "box0": None, "box1": None}
        et = event.type
        if et in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            self._xf_update(context, mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        step = xf["step"]
        if et == "LEFTMOUSE":
            if not press:
                if step == "SEL" and xf.get("box0") is not None:
                    x0, y0 = xf["box0"]
                    xf["box0"] = xf["box1"] = None
                    if math.hypot(mx - x0, my - y0) > 4 * self.ui_scale:
                        self._xf_box_select(x0, y0, mx, my)
                    else:
                        if not event.shift:
                            self.xsel, self.xnodes, self.xpts = set(), set(), set()
                    self._status(context, self._xf_msg())
                    self.area.tag_redraw()
                return {"RUNNING_MODAL"}
            if step == "SEL":
                pi = self._xf_point_at(mx, my)
                if pi is not None:                # taslak noktası
                    if pi in self.xpts:
                        self.xpts.discard(pi)
                    else:
                        self.xpts.add(pi)
                    self._status(context, self._xf_msg())
                    self.area.tag_redraw()
                    return {"RUNNING_MODAL"}
                hit = self._pick_seg(mx, my) if self.sketch else None
                if hit is None:
                    xf["box0"], xf["box1"] = (mx, my), (mx, my)
                else:
                    k = hit[0]
                    if k in self.xsel:
                        self.xsel.discard(k)
                    else:
                        self.xsel.add(k)
                    self._status(context, self._xf_msg())
            elif step == "BASE":
                p = self._xf_point(context, mx, my)
                if p is None:
                    return {"RUNNING_MODAL"}
                pl = self._cur_plane() or self.tmp_plane or self._make_plane(self.plane_mode, p)
                xf.update(base=np.asarray(p, dtype=np.float64).copy(), plane=pl.moved(p),
                          n=pl.n, step="TGT")
                pts = [q for k in sorted(self.xsel) for q in sm.stroke_nodes(self.sketch[k])]
                pts += [sm.stroke_nodes(self.sketch[k])[j] for k, j in self.xnodes]
                pts += [self._pts()[i] for i in sorted(self.xpts)]
                c = np.mean(np.array(pts), axis=0) if pts else p
                far = max((float(np.linalg.norm(q - p)) for q in pts), default=0.0)
                xf["ref_d"] = far
                v = c - p
                xf["ref_ang"] = dm.seg_angle(pl, p, c) if np.linalg.norm(
                    v - pl.n * float(np.dot(v, pl.n))) > 1e-9 else 0.0
                self.typed, self.field = ["", ""], 0
                self._status(context, self._xf_msg())
                self._xf_update(context, mx, my)
            elif step == "TGT" and self.tool == "RPAT":
                self._xf_update(context, mx, my)
                info = xf.get("info") or {}
                if info.get("d") is not None:
                    xf.update(d1=info["d"], n1=info["n"], step="DIR2")
                    self.typed, self.field = ["", ""], 0
                    self._status(context, self._xf_msg())
                    self._xf_update(context, mx, my)
            else:
                self._xf_update(context, mx, my)
                self._xf_apply(context)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if not press:
            return {"RUNNING_MODAL"} if et == "RIGHTMOUSE" else None
        if et in {"RIGHTMOUSE", "RET", "NUMPAD_ENTER", "SPACE"} and not event.ctrl:
            if step == "SEL":
                if self._xf_any():
                    xf["step"] = "BASE"
                else:
                    self._status(context, f"{XF_HELP[self.tool]}: önce seç")
                    return {"RUNNING_MODAL"}
            elif step == "BASE":
                xf["step"] = "SEL"
            elif step == "DIR2":
                if et == "RIGHTMOUSE":
                    xf["fns"] = sm.rect_pattern(xf["d1"], xf["n1"])
                    xf["pdef"] = self._rpat_def(xf["d1"], xf["n1"])
                else:
                    self._xf_update(context, mx, my)
                self._xf_apply(context)
            elif et == "RIGHTMOUSE":
                xf["step"] = "BASE"
                self.xprev = []
                self.typed, self.field = ["", ""], 0
            else:                                  # Enter: yazılan değerle uygula
                if self.tool == "RPAT":
                    self._xf_update(context, mx, my)
                    info = xf.get("info") or {}
                    if info.get("d") is not None:
                        xf.update(d1=info["d"], n1=info["n"], step="DIR2")
                        self.typed, self.field = ["", ""], 0
                else:
                    self._xf_update(context, mx, my)
                    self._xf_apply(context)
            self._status(context, self._xf_msg())
            self._xf_update(context, mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if et == "C" and not event.ctrl and not event.alt and self.tool in ("ROTATE", "SCALE"):
            xf["copy"] = not xf["copy"]
            self._status(context, self._xf_msg())
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if et == "TAB" and event.shift:
            self.coord_mode = not getattr(self, "coord_mode", False)
            self.typed, self.field = ["", ""], 0
            self._xf_update(context, mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if et == "TAB":
            self.field = 1 - self.field
            self._xf_update(context, mx, my)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if et == "BACK_SPACE":
            if self.typed[self.field]:
                self.typed[self.field] = self.typed[self.field][:-1]
                self._xf_update(context, mx, my)
                self.area.tag_redraw()
                return {"RUNNING_MODAL"}
            return None
        ch = event.unicode or ""
        typing = bool(self.typed[self.field])
        if ch and not event.ctrl and (ch in "0123456789.,-+°" or
                                      (typing and (ch.isalpha() or ch in "'\""))):
            if step in ("TGT", "DIR2"):
                self.typed[self.field] += ch
                self._xf_update(context, mx, my)
                self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        return None

    # ------------------------------------------------------------ çizim

    def _xf_draw3d(self, region):
        self._xf_init()
        xf = self.xf
        for k in sorted(self.xsel):
            if k < len(self.sketch):
                for sg in self.sketch[k]["segs"]:
                    _poly([tuple(p) for p in dm.sample(sg, 2 if sg["kind"] == "line" else 20)],
                          COL_SEL, 3.0, region)
        if xf is not None and xf.get("step") == "SEL" and xf.get("hover") is not None and \
                xf["hover"] < len(self.sketch) and xf.get("box0") is None:
            for sg in self.sketch[xf["hover"]]["segs"]:
                _poly([tuple(p) for p in dm.sample(sg, 2 if sg["kind"] == "line" else 20)],
                      COL_RUBBER, 2.0, region)
        for st in self.xprev:
            for sg in st["segs"]:
                _poly([tuple(p) for p in dm.sample(sg, 2 if sg["kind"] == "line" else 20)],
                      COL_RUBBER, 2.0, region)
        if xf is not None and self.tool == "MIRROR" and xf.get("step") == "TGT":
            p = (xf.get("info") or {}).get("p")
            if p is not None:
                d = p - xf["base"]
                _poly([tuple(xf["base"] - d * 2.0), tuple(xf["base"] + d * 3.0)], COL_GUIDE, 1.5,
                      region)

    def _xf_draw2d(self, region):
        self._xf_init()
        xf = self.xf
        if xf is None:
            return
        s = self.ui_scale
        from . import core
        for i in sorted(getattr(self, "xpts", ())):
            if i < len(self._pts()):
                p = self._px(self._pts()[i])
                if p is not None:
                    _marker("Kesişim", p[0], p[1], 7 * s, region)
        for q in xf.get("ptprev") or ():
            p = self._px(q)
            if p is not None:
                _marker("Nokta", p[0], p[1], 5 * s, region)
        for k, j in self.xnodes:
            if k < len(self.sketch):
                nodes = sm.stroke_nodes(self.sketch[k])
                if j < len(nodes):
                    p = self._px(nodes[j])
                    if p is not None:
                        _marker("Uç", p[0], p[1], 5 * s, region)
        if xf.get("box0") is not None and xf.get("box1") is not None:
            (x0, y0), (x1, y1) = xf["box0"], xf["box1"]
            pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
            if x1 < x0:
                for a, b in zip(pts[:-1], pts[1:]):
                    _dashed(a, b, COL_GUIDE, region)
            else:
                _poly(pts, COL_ACTIVE, 1.2, region)
        if xf.get("base") is not None and xf["step"] in ("TGT", "DIR2"):
            p = self._px(xf["base"])
            if p is not None:
                _marker("Merkez" if self.tool in ("ROTATE", "CPAT") else "Uç", p[0], p[1],
                        6 * s, region)
        mx, my = self.mouse
        info = xf.get("info") or {}
        rows = []
        if xf["step"] in ("TGT", "DIR2"):
            t = self.tool
            if t in ("MOVE", "COPY", "STRETCH", "MIRROR"):
                d = info.get("d") if t != "MIRROR" else (
                    info["p"] - xf["base"] if info.get("p") is not None else None)
                if d is not None and getattr(self, "coord_mode", False):
                    pl = self._xf_plane()
                    du = float(np.dot(d, pl.u))
                    dv = float(np.dot(d, pl.v))
                    rows = [("ΔX", self.typed[0] + ("_" if self.field == 0 else "")
                             if self.typed[0] else core.fmt_len(du), self.field == 0),
                            ("ΔY", self.typed[1] + ("_" if self.field == 1 else "")
                             if self.typed[1] else core.fmt_len(dv), self.field == 1)]
                elif d is not None:
                    L = float(np.linalg.norm(d))
                    ang = dm.seg_angle(self._xf_plane(), xf["base"], xf["base"] + d)
                    rows = [("Uzunluk", self.typed[0] + ("_" if self.field == 0 else "")
                             if self.typed[0] else core.fmt_len(L), self.field == 0),
                            ("Açı", self.typed[1] + ("_" if self.field == 1 else "")
                             if self.typed[1] else f"{ang:.1f}°", self.field == 1)]
            elif t == "ROTATE":
                rows = [("Açı", self.typed[0] + "_" if self.typed[0] else
                         f"{info.get('ang', 0.0):.1f}°", True),
                        ("Kopya", "açık (C)" if xf["copy"] else "kapalı (C)", False)]
            elif t == "SCALE":
                rows = [("Ölçek", self.typed[0] + "_" if self.typed[0] else
                         f"{info.get('s', 1.0):.4g}", True),
                        ("Kopya", "açık (C)" if xf["copy"] else "kapalı (C)", False)]
            elif t == "CPAT":
                rows = [("Adet", self.typed[0] + ("_" if self.field == 0 else "")
                         if self.typed[0] else str(info.get("n", 6)), self.field == 0),
                        ("Açı", self.typed[1] + ("_" if self.field == 1 else "")
                         if self.typed[1] else f"{info.get('ang', 360.0):.1f}°", self.field == 1)]
            elif t == "RPAT":
                rows = [("Adet", self.typed[0] + ("_" if self.field == 0 else "")
                         if self.typed[0] else str(info.get("n", 3 if xf["step"] == "TGT" else 2)),
                         self.field == 0),
                        ("Aralık", self.typed[1] + ("_" if self.field == 1 else "")
                         if self.typed[1] else core.fmt_len(info.get("L", 0.0)), self.field == 1)]
        label = {"SEL": f"{XF_HELP[self.tool]}: seç ({len(self.xsel)})",
                 "BASE": f"{XF_HELP[self.tool]}: {XF_BASE[self.tool]}"}.get(xf["step"], "")
        if label and not self.snap_kind:
            _text(mx + 14 * s, my + 12 * s, label, COL_SNAP, int(11 * s))
        if rows:
            self._draw_rows((mx, my), rows)
