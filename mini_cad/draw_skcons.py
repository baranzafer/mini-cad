"""Taslak kısıtları (v0.22.0): kısıt / ölçü araçları taslağı Bitir'lemeden taslak çizgilerine
de uygulanır (Inventor'da taslak açıkken olduğu gibi).

  Saklama   self.skc = [{"kind", "refs", "value", "axis"}]; referanslar:
              ("seg" | "pt", "@sk", uid, sıra)       taslak çizgisi (kalıcı kimlik "uid")
              ("seg" | "pt", obje adı, spline, sıra)  kaydedilmiş eğri (taslakta sabit)
  Çözüm     nokta tabanlı kısıtlar taslakta hemen çözülür (solver; kaydedilmiş noktalar
            sabit): AXIS, PARALLEL, PERP, COLLINEAR, EQUAL (doğru), DISTANCE, ANGLE, FIX,
            COINCIDENT, SYMMETRIC, SYMLINE, PTLINE, LINEDIST. Ekleyince, sürükleme bitince ve
            taslak araçlarından (_set_sketch) sonra yeniden çözülür.
            Teğet / Pürüzsüz (v0.25.5) taslakta anında, biçimi bozmadan uygulanır (_skc_geo):
            doğru korunur, yay iki ucunu koruyarak teğet çember yayı olarak yeniden kurulur,
            serbest eğride yalnızca uç tutamacı (G2'de 2. kontrol noktası) ayarlanır.
            Diğer yay kısıtları (RADIUS, CONCENTRIC, CENTERDIST, yaylarda EQUAL) Bitir'de.
  Bitir     uid → yazılan spline; kısıtlar gerçek kısıt olarak eklenir (_skc_finish).
  Kimlik    Taşı / Döndür / Ölçekle / Esnet çizginin kimliğini korur; Kırp / Böl / Yuvarla gibi
            yapıyı değiştiren işlemler korumaz (o çizgiye bağlı taslak kısıtları düşer).

MINICAD_OT_draw (draw.py) bu mixin'den miras alır.
"""
import itertools
import math

import bpy
import numpy as np

from . import constraints
from . import drawmath as dm
from . import sketchmath as sm
from . import solver
from .draw_common import _project, _seg_px_dist

_UID = itertools.count(1)

LIVE = {"AXIS", "PARALLEL", "PERP", "COLLINEAR", "EQUAL", "DISTANCE", "ANGLE", "FIX",
        "COINCIDENT", "SYMMETRIC", "SYMLINE", "PTLINE", "LINEDIST"}
# v0.25.5: taslakta anında, biçimi bozmadan uygulanan geometrik kısıtlar (Inventor gibi)
GEO = {"TANGENT", "SMOOTH"}
RANK = {"line": 1, "arc": 2, "curve": 3}       # hangisi uyar: eğri > yay > doğru


class SketchConsMixin:
    """Taslak çizgilerine kısıt / ölçü."""

    def _skc_init(self):
        if not hasattr(self, "skc") or self.skc is None:
            self.skc = []
        if not hasattr(self, "_skc_boxes"):
            self._skc_boxes = []

    # ------------------------------------------------------------ kimlik

    def _uid(self, k):
        st = self.sketch[k]
        if st.get("uid") is None:
            st["uid"] = next(_UID)
        return st["uid"]

    def _uid_map(self):
        return {st.get("uid"): k for k, st in enumerate(self.sketch) if st.get("uid") is not None}

    # ------------------------------------------------------------ seçim (taslak)

    def _sk_pick(self, mx, my, is_pt, taken=()):
        """İmlecin altındaki taslak noktası / segmenti: ("pt"|"seg", "@sk", uid, sıra, konum|örnek)
        ve piksel uzaklığı ya da None."""
        if not self.sketch:
            return None
        M = np.array(self.rv3d.perspective_matrix, dtype=np.float64)
        m = np.array([mx, my], dtype=np.float64)
        best = None
        for k, st in enumerate(self.sketch):
            if is_pt:
                P = np.array(sm.stroke_nodes(st))
                px, ok, _ = _project(P, M, self.region)
                d = np.where(ok, np.linalg.norm(px - m, axis=1), np.inf)
                for j in np.argsort(d)[:3]:
                    if d[j] > self.radius * 1.3:
                        break
                    if ("@sk", st.get("uid"), int(j)) in taken:
                        continue
                    if best is None or d[j] < best[0]:
                        best = (float(d[j]), k, int(j), P[j])
                    break
            else:
                for i, sg in enumerate(st["segs"]):
                    S = dm.sample(sg, 2 if sg["kind"] == "line" else 17)
                    px, ok, _ = _project(S, M, self.region)
                    if not ok.all():
                        continue
                    dd, _ = _seg_px_dist(px[:-1], px[1:], m)
                    d = float(dd.min())
                    if d > self.radius or ("@sk", st.get("uid"), i) in taken:
                        continue
                    if best is None or d < best[0]:
                        best = (d, k, i, S)
        if best is None:
            return None
        d, k, i, pos = best
        return ("pt" if is_pt else "seg", "@sk", self._uid(k), i, pos), d

    # ------------------------------------------------------------ geometri

    def _skc_points(self, r):
        """Referansın noktaları: [(anahtar, konum, taslakta mı)] ya da None."""
        if r[1] == "@sk":
            k = self._uid_map().get(r[2])
            if k is None:
                return None
            st = self.sketch[k]
            nodes = sm.stroke_nodes(st)
            if r[0] == "pt":
                if not (0 <= r[3] < len(nodes)):
                    return None
                return [(("@sk", r[2], r[3]), np.asarray(nodes[r[3]]), True)]
            n = len(st["segs"])
            if not (0 <= r[3] < n):
                return None
            j2 = (r[3] + 1) % len(nodes) if st["cyclic"] else r[3] + 1
            return [(("@sk", r[2], r[3]), np.asarray(nodes[r[3]]), True),
                    (("@sk", r[2], j2), np.asarray(nodes[j2]), True)]
        ob = bpy.data.objects.get(r[1])
        pts = constraints.ref_points(ob, r[2], r[3], r[0] == "pt") if ob is not None else None
        if pts is None:
            return None
        return [((o.name, si, pi), constraints._world(o, si, pi), False) for o, si, pi in pts]

    def _skc_seg_bez(self, r):
        """Segment referansının 4 kontrol noktası (taslak ya da kaydedilmiş)."""
        if r[1] == "@sk":
            k = self._uid_map().get(r[2])
            if k is None or not (0 <= r[3] < len(self.sketch[k]["segs"])):
                return None
            return [np.asarray(q, dtype=np.float64) for q in self.sketch[k]["segs"][r[3]]["p"]]
        from .constraints_arcs import seg_bez
        ob = bpy.data.objects.get(r[1])
        try:
            return seg_bez(ob, r[2], r[3])
        except Exception:
            return None

    def _skc_measure(self, kind, refs):
        if kind in ("RADIUS", "CENTERDIST"):
            P = self._skc_seg_bez(refs[0])
            arc = dm.arc_of_bezier(P) if P is not None else None
            if arc is None:
                return None
            if kind == "RADIUS":
                return float(arc[1])
            other = refs[1]
            if other[0] == "seg":
                Q = self._skc_seg_bez(other)
                a2 = dm.arc_of_bezier(Q) if Q is not None else None
                if a2 is not None:
                    return float(np.linalg.norm(arc[0] - a2[0]))
                d = dm.unit(Q[3] - Q[0])
                return float(np.linalg.norm(np.cross(arc[0] - Q[0], d)))
            pts = self._skc_points(other)
            return float(np.linalg.norm(arc[0] - pts[0][1])) if pts else None
        P = []
        for r in refs:
            pts = self._skc_points(r)
            if pts is None:
                return None
            P += [p for _, p, _ in pts]
        return solver.measure(kind, np.array(P))

    # ------------------------------------------------------------ ekle / çöz

    def _pick_any(self, mx, my, is_pt):
        """Kayıtlı eğri ya da taslak: imlece yakın olan."""
        taken = {(r[1], r[2], r[3]) for r in self.c_refs}
        saved = self._pick_entity(mx, my, is_pt)
        sk = self._sk_pick(mx, my, is_pt, taken)
        if sk is None:
            return saved
        if saved is None:
            return sk[0]
        M = np.array(self.rv3d.perspective_matrix, dtype=np.float64)
        m = np.array([mx, my], dtype=np.float64)
        if is_pt:
            px, _ok, _ = _project(np.array([saved[4]]), M, self.region)
            ds = float(np.linalg.norm(px[0] - m))
        else:
            px, _ok, _ = _project(np.asarray(saved[4]), M, self.region)
            dd, _ = _seg_px_dist(px[:-1], px[1:], m)
            ds = float(dd.min())
        return sk[0] if sk[1] <= ds + 1e-6 else saved

    def _sk_smooth_node(self, p):
        k = self._uid_map().get(p[2])
        if k is None:
            return False
        st = self.sketch[k]
        n = len(st["segs"])
        j = p[3]
        if not st["cyclic"] and (j == 0 or j == n):
            return False
        a, b = st["segs"][(j - 1) % n], st["segs"][j % n]
        ta, tb = dm.end_tangent(a), dm.start_tangent(b)
        return ta is not None and tb is not None and float(np.dot(ta, tb)) > 0.9999

    def _skc_apply_value(self, context, i, txt):
        from .draw_common import parse_angle, parse_length
        if not (0 <= i < len(self.skc)) or not txt:
            return
        e = self.skc[i]
        if e["kind"] == "ANGLE":
            v = parse_angle(txt)
            if v is None or not (0.0 <= v <= 180.0):
                self._status(context, "Açı 0–180° olmalı")
                return
        else:
            v = parse_length(txt)
            if v is None:
                self._status(context, "Geçersiz değer")
                return
            if e["kind"] == "RADIUS" and e.get("axis") == 1:
                v /= 2.0
        e["value"] = v
        self._sk_solve()
        self._status(context, "Ölçü uygulandı" if e.get("ok", True) else
                     f"Ölçü sağlanamadı: {e.get('info')}")
        self.area.tag_redraw()

    def _skc_add(self, context, kind, refs, value=None, axis=None):
        """Taslak kısıtı ekler ve (canlıysa) hemen çözer. Sırası."""
        self._skc_init()
        refs = [(r[0], r[1] if isinstance(r[1], str) else r[1].name, r[2], r[3]) for r in refs]
        e = {"kind": kind, "refs": refs, "value": value, "axis": axis, "ok": True, "info": ""}
        if kind == "AXIS" and axis is None:
            pts = self._skc_points(e["refs"][0])
            if pts is None:
                return None
            e["axis"] = int(np.argmax(np.abs(pts[1][1] - pts[0][1])))
        if kind == "FIX":
            pts = self._skc_points(e["refs"][0])
            e["pos"] = tuple(pts[0][1]) if pts else (0.0, 0.0, 0.0)
        if kind in ("DISTANCE", "ANGLE", "PTLINE", "LINEDIST", "RADIUS", "CENTERDIST") and \
                value is None:
            e["value"] = self._skc_measure(kind, e["refs"])
            if e["value"] is None:
                return None
        if kind == "SYMMETRIC":
            pts = [p for r in e["refs"] for _, p, _ in (self._skc_points(r) or [])]
            if len(pts) == 2:
                e["axis"] = int(np.argmax(np.abs(pts[1] - pts[0])))
        if kind == "RADIUS":
            P = self._skc_seg_bez(e["refs"][0])
            k = self._uid_map().get(e["refs"][0][2]) if e["refs"][0][1] == "@sk" else None
            closed = False
            if k is not None:
                st = self.sketch[k]
                ent = sm.entity_of(st, e["refs"][0][3])
                closed = ent is not None and sm.closed_entity(st, ent[0], ent[1])
            e["axis"] = 1 if closed else 0
        self.skc.append(e)
        prefer = {key for key, _, ins in (self._skc_points(e["refs"][0]) or []) if ins}
        self._sk_solve(prefer)
        self.dirty = True
        return len(self.skc) - 1

    def _skc_params(self, e):
        k = e["kind"]
        if k == "AXIS":
            return {"axis": e["axis"]}
        if k in ("DISTANCE", "PTLINE", "LINEDIST"):
            return {"value": e["value"]}
        if k == "ANGLE":
            return {"value": e["value"]}
        if k == "FIX":
            return {"pos": e.get("pos", (0.0, 0.0, 0.0))}
        if k == "SYMMETRIC":
            return {"axis": e.get("axis", 0), "offset": 0.0}
        return {}

    def _sk_solve(self, prefer=None):
        """Canlı taslak kısıtları: önce nokta tabanlılar (solver), sonra teğet / pürüzsüz
        (geometrik, biçimi koruyarak)."""
        ok = self._sk_solve_pts(prefer)
        self._skc_geo_all()
        return ok

    def _sk_solve_pts(self, prefer=None):
        """Nokta tabanlı taslak kısıtlarını taslak noktalarında çözer (kaydedilmiş noktalar
        sabit)."""
        self._skc_init()
        keys, var_of, cons, owners = [], {}, [], []
        pos, fixed = [], []
        for e in self.skc:
            k = e["kind"]
            if k in GEO:
                continue
            if k not in LIVE:
                e["ok"], e["info"] = True, "Bitir'de uygulanır"
                continue
            if k == "EQUAL" and any(self._is_arc_ref(r) for r in e["refs"]):
                e["ok"], e["info"] = True, "Bitir'de uygulanır (yay)"
                continue
            idx = []
            bad = False
            for r in e["refs"]:
                pts = self._skc_points(r)
                if pts is None:
                    bad = True
                    break
                for key, p, ins in pts:
                    if key not in var_of:
                        var_of[key] = len(keys)
                        keys.append(key)
                        pos.append(p)
                        fixed.append(not ins)
                    idx.append(var_of[key])
            if bad:
                e["ok"], e["info"] = False, "referans kayboldu (çizgi yapısı değişti)"
                continue
            cons.append((k, tuple(idx), self._skc_params(e)))
            owners.append(e)
        if not cons:
            return True
        X0 = np.array(pos)
        w = np.ones(len(keys))
        for j, key in enumerate(keys):
            if fixed[j]:
                w[j] = 1e9
            elif prefer and key in prefer:
                w[j] = 1e3
        X, ok, per = solver.solve(X0, cons, w)
        scale = 1.0 + float(np.abs(X0).max())
        for e, r in zip(owners, per):
            e["ok"] = r <= 1e-6 * scale
            e["info"] = "" if e["ok"] else "sağlanamadı: diğer kısıtlarla çelişiyor olabilir"
        umap = self._uid_map()
        for j, key in enumerate(keys):
            if fixed[j] or float(np.linalg.norm(X[j] - X0[j])) <= 1e-12 * scale:
                continue
            k = umap.get(key[1])
            if k is None:
                continue
            st = self.sketch[k]
            sm._move_node(st["segs"], key[2], X[j], st["cyclic"])
        self.dirty = True
        return ok

    # ------------------------------------------------------------ teğet / pürüzsüz (v0.25.5)

    def _skc_ent(self, r):
        """Segment referansının varlığı (doğru / yay / eğri): sözlük ya da None."""
        if r[0] != "seg":
            return None
        if r[1] == "@sk":
            k = self._uid_map().get(r[2])
            if k is None:
                return None
            st = self.sketch[k]
            ent = sm.entity_of(st, r[3])
            if ent is None:
                return None
            i0, i1 = ent
            segs = [np.array([np.asarray(q, dtype=np.float64) for q in st["segs"][i]["p"]])
                    for i in range(i0, i1)]
            closed = sm.closed_entity(st, i0, i1)
            sk = True
        else:
            P = self._skc_seg_bez(r)
            if P is None:
                return None
            segs, k, i0, i1, closed, sk = [np.array(P)], None, None, None, False, False
        decl = {st["segs"][i].get("kind") for i in range(i0, i1)} if sk else set()
        if sk and decl <= {"line", "arc", "curve"} and len(decl) == 1:
            kind = decl.pop()                     # taslakta tür kayıtlı (sürüklenince de yay)
        elif all(dm.is_straight_poly(P) for P in segs):
            kind = "line"
        else:
            arcs = [dm.arc_of_bezier(P) for P in segs]
            kind = "arc" if all(a is not None for a in arcs) and all(
                np.linalg.norm(a[0] - arcs[0][0]) <= 1e-4 * (1 + arcs[0][1]) for a in arcs) \
                else "curve"
        return {"sketch": sk, "k": k, "i0": i0, "i1": i1, "segs": segs, "kind": kind,
                "closed": closed, "S": segs[0][0], "E": segs[-1][3]}

    @staticmethod
    def _leave_dir(ent, at_start):
        """Varlığın ucundan içine doğru (o uçtan ayrılış) yönü."""
        P = ent["segs"][0] if at_start else ent["segs"][-1]
        if at_start:
            d = P[1] - P[0] if np.linalg.norm(P[1] - P[0]) > 1e-12 else P[3] - P[0]
        else:
            d = P[2] - P[3] if np.linalg.norm(P[2] - P[3]) > 1e-12 else P[0] - P[3]
        return dm.unit(d)

    @staticmethod
    def _curvature(ent, at_start):
        """Uçtaki eğrilik (κ, eğrilik normali birim ya da None)."""
        if ent["kind"] == "line":
            return 0.0, None
        P = ent["segs"][0] if at_start else ent["segs"][-1]
        if ent["kind"] == "arc" and dm.arc_of_bezier(P) is not None:
            c, R, _n = dm.arc_of_bezier(P)
            J = P[0] if at_start else P[3]
            return 1.0 / R, dm.unit(c - J)
        if at_start:
            d1, dd = P[1] - P[0], P[2] - 2 * P[1] + P[0]
        else:
            d1, dd = P[3] - P[2], P[3] - 2 * P[2] + P[1]
        L = float(np.linalg.norm(d1))
        if L < 1e-12:
            return 0.0, None
        t = d1 / L
        perp = dd - np.dot(dd, t) * t
        h = float(np.linalg.norm(perp))
        if h < 1e-15:
            return 0.0, None
        # κ = |B' × B''| / |B'|³, B' = 3·d1, B'' = 6·dd
        return float(np.linalg.norm(np.cross(3 * d1, 6 * dd))) / (3 * L) ** 3, perp / h

    def _write_ent(self, ent, segs):
        st = self.sketch[ent["k"]]
        for i, P in zip(range(ent["i0"], ent["i1"]), segs):
            st["segs"][i]["p"] = tuple(np.asarray(q, dtype=np.float64) for q in P)

    def _move_ent_nodes(self, ent, fn):
        """Varlığın düğümlerini fn(eski konum) → yeni konuma taşır (komşu bağlantılar korunur)."""
        st = self.sketch[ent["k"]]
        nodes = sm.stroke_nodes(st)
        last = ent["i1"] if not ent["closed"] else ent["i1"] - 1
        for j in range(ent["i0"], last + 1):
            jj = j % len(st["segs"]) if st["cyclic"] else j
            sm._move_node(st["segs"], jj, fn(np.asarray(nodes[jj], dtype=np.float64)),
                          st["cyclic"])

    def _skc_geo(self, e):
        """Teğet / pürüzsüz kısıtını taslakta uygular. (sağlandı mı, bilgi)"""
        if len(e["refs"]) != 2:
            return False, "iki eğri gerekli"
        A, B = (self._skc_ent(r) for r in e["refs"])
        if A is None or B is None:
            return False, "referans kayboldu (çizgi yapısı değişti)"
        size = max(1.0, float(np.abs(np.vstack(A["segs"] + B["segs"])).max()))
        tol = 1e-6 * size
        joint = None
        if not A["closed"] and not B["closed"]:
            best = None
            for sa, pa in ((True, A["S"]), (False, A["E"])):
                for sb, pb in ((True, B["S"]), (False, B["E"])):
                    d = float(np.linalg.norm(pa - pb))
                    if best is None or d < best[0]:
                        best = (d, sa, sb, pa)
            if best[0] <= 1e-4 * size:
                joint = best[1:]
        movable = [x for x in (A, B) if x["sketch"]]
        if not movable:
            return True, "kaydedilmiş eğriler (Bitir'de)"
        if joint is None:
            return self._skc_tan_free(A, B, tol)
        sa, sb, J = joint
        if len(movable) == 1:
            M = movable[0]
        elif A["kind"] != B["kind"]:
            M = A if RANK[A["kind"]] > RANK[B["kind"]] else B
        else:
            M = B                                    # aynı türde: ikinci seçilen uyar
        O = B if M is A else A
        m_start = sa if M is A else sb
        o_start = sb if M is A else sa
        t = -self._leave_dir(O, o_start)              # M, J'den bu yönde ayrılmalı
        if t is None:
            return False, "teğet yönü bulunamadı"
        cur = self._leave_dir(M, m_start)
        smooth = e["kind"] == "SMOOTH"
        if M["kind"] == "arc":
            F = M["E"] if m_start else M["S"]
            arc = dm.tangent_arc(J, t, F)
            if arc is None:
                return False, "yay bu konumda teğet olamaz (düzleşirdi)"
            n = len(M["segs"])
            th = arc["angle"]
            ctr, R = arc["center"], arc["radius"]
            segs = dm._arc_from_basis(ctr, R, (J - ctr) / R, t, th, J, F,
                                      max_angle=th / n + 1e-9)
            if len(segs) != n:
                return False, "yay yeniden kurulamadı"
            P = [np.array(sg["p"]) for sg in segs]
            if not m_start:
                P = [Q[::-1] for Q in reversed(P)]
            self._write_ent(M, P)
        elif M["kind"] == "line":
            if cur is not None and float(np.dot(cur, t)) > 1 - 1e-12:
                pass
            else:
                self._move_ent_nodes(M, lambda q: J + t * float(np.linalg.norm(q - J)))
        else:                                         # serbest eğri: uçtaki tutamaç
            P = M["segs"][0].copy() if m_start else M["segs"][-1].copy()
            hi = 1 if m_start else 2
            L1 = float(np.linalg.norm(P[hi] - J)) or float(np.linalg.norm(P[3] - P[0])) / 3
            P[hi] = J + t * L1
            if smooth:
                kap, nv = self._curvature(O, o_start)
                ii = 2 if m_start else 1
                base = P[hi]
                along = float(np.dot(P[ii] - base, t))
                h = 1.5 * kap * L1 * L1
                P[ii] = base + t * along + (nv * h if nv is not None else 0.0)
            segs = [Q.copy() for Q in M["segs"]]
            if m_start:
                segs[0] = P
            else:
                segs[-1] = P
            self._write_ent(M, segs)
        if smooth and M["kind"] != "curve":
            return False, ("Pürüzsüz (G2): eğrilik yalnızca serbest eğride eşitlenebilir "
                           "(doğru / yay arasında olamaz) · teğet uygulandı")
        return True, ""

    def _skc_tan_free(self, A, B, tol):
        """Ortak ucu olmayan teğet: doğru–yay (doğru kayar) ve yay–yay (yay kayar)."""
        kinds = {A["kind"], B["kind"]}
        if kinds == {"line", "arc"}:
            L = A if A["kind"] == "line" else B
            C = B if L is A else A
            c, R, _n = dm.arc_of_bezier(C["segs"][0])
            a, b = L["S"], L["E"]
            u = dm.unit(b - a)
            v = c - a
            foot = a + u * float(np.dot(v, u))
            d = float(np.linalg.norm(c - foot))
            if abs(d - R) <= tol:
                return True, ""
            if d < 1e-12:
                return False, "doğru yayın merkezinden geçiyor"
            nh = (c - foot) / d
            if L["sketch"]:
                self._move_ent_nodes(L, lambda q: q + nh * (d - R))
            elif C["sketch"]:
                self._move_ent_nodes(C, lambda q: q - nh * (d - R))
            return True, ""
        if kinds == {"arc"}:
            M = B if B["sketch"] else A
            O = A if M is B else B
            c1, R1, _ = dm.arc_of_bezier(O["segs"][0])
            c2, R2, _ = dm.arc_of_bezier(M["segs"][0])
            d = float(np.linalg.norm(c2 - c1))
            if d < 1e-12:
                return False, "eş merkezli yaylar teğet olamaz"
            want = min((R1 + R2, abs(R1 - R2)), key=lambda x: abs(x - d))
            if abs(want - d) <= tol:
                return True, ""
            shift = (c2 - c1) / d * (want - d)
            self._move_ent_nodes(M, lambda q: q + shift)
            return True, ""
        return False, "ortak uçları yok: bu tür için teğet yalnızca ortak uçta"

    def _skc_geo_all(self):
        for e in self.skc:
            if e["kind"] in GEO:
                try:
                    e["ok"], e["info"] = self._skc_geo(e)
                except Exception as ex:
                    e["ok"], e["info"] = False, f"uygulanamadı: {ex}"
        self.dirty = True

    def _is_arc_ref(self, r):
        if r[0] != "seg":
            return False
        P = self._skc_seg_bez(r)
        return P is not None and not dm.is_straight_poly(np.array(P)) and \
            dm.arc_of_bezier(P) is not None

    # ------------------------------------------------------------ Bitir

    def _skc_finish(self, context, written_uid):
        """written_uid: {uid: (obje, spline)}. Taslak kısıtlarını gerçek kısıt yapar."""
        self._skc_init()
        n = 0
        for e in self.skc:
            refs = []
            for r in e["refs"]:
                if r[1] == "@sk":
                    got = written_uid.get(r[2])
                    if got is None:
                        refs = None
                        break
                    refs.append((r[0], got[0], got[1], r[3]))
                else:
                    ob = bpy.data.objects.get(r[1])
                    if ob is None:
                        refs = None
                        break
                    refs.append((r[0], ob, r[2], r[3]))
            if not refs:
                continue
            k = e["kind"]
            value = e.get("value")
            if k == "AXIS":
                value = e["axis"]
            c = constraints.add(k, refs, value=value, solve=False)
            if c is None:
                continue
            if k == "RADIUS":
                c.axis = e.get("axis", 0)
            if k == "SYMMETRIC":
                c.axis = e.get("axis", 0)
            n += 1
        self.skc = []
        return n

    # ------------------------------------------------------------ çizim

    def _skc_anchor(self, r):
        if r[0] == "pt":
            pts = self._skc_points(r)
            return pts[0][1] if pts else None
        P = self._skc_seg_bez(r)
        return None if P is None else 0.125 * (P[0] + 3 * P[1] + 3 * P[2] + P[3])

    def _skc_draw2d(self, region):
        """Taslak kısıtlarının simgeleri (silik) ve ölçü değerleri; sağ tıkla silinir."""
        self._skc_init()
        self._skc_boxes = []
        if not self.skc or not getattr(bpy.context.scene, "minicad_show_constraints", True):
            return
        from . import core, palette
        from .constraints_glyphs import ICON
        s = self.ui_scale
        size = 13 * s
        stack = {}
        for i, e in enumerate(self.skc):
            a = self._skc_anchor(e["refs"][0])
            p = self._px(a) if a is not None else None
            if p is None:
                continue
            key = (round(p[0] / 4), round(p[1] / 4))
            kk = stack.get(key, 0)
            stack[key] = kk + 1
            x, y = p[0] + 10 * s + kk * (size + 3 * s), p[1] - 22 * s
            col = (0.55, 0.85, 1.0, 0.55) if e.get("ok", True) else (1.0, 0.35, 0.3, 0.75)
            if e["value"] is not None and e["kind"] != "AXIS":
                if e["kind"] == "ANGLE":
                    txt = f"{e['value']:.1f}°"
                elif e["kind"] == "RADIUS":
                    txt = f"Ø{core.fmt_len(e['value'] * 2)}" if e.get("axis") == 1 else \
                        f"R{core.fmt_len(e['value'])}"
                else:
                    txt = core.fmt_len(e["value"])
                w = 8 * s + len(txt) * 6.5 * s
                palette.rect(x, y, x + w, y + size, (0.1, 0.1, 0.12, 0.35))
                palette.text(x + 4 * s, y + 4 * s, txt, col, int(10 * s))
                self._skc_boxes.append((x, y, x + w, y + size, i))
                continue
            palette.rect(x, y, x + size, y + size, (0.1, 0.1, 0.12, 0.3))
            palette.draw_icon(ICON.get(e["kind"], "AXIS"), x + size / 2, y + size / 2,
                              size * 0.75, col, region, 1.3)
            self._skc_boxes.append((x, y, x + size, y + size, i))

    def _skc_at(self, mx, my):
        for x0, y0, x1, y1, i in getattr(self, "_skc_boxes", ()):
            if x0 <= mx <= x1 and y0 <= my <= y1:
                return i
        return None

    def _skc_delete(self, context, i):
        if 0 <= i < len(self.skc):
            k = self.skc.pop(i)["kind"]
            self._status(context, f"Taslak kısıtı silindi: {constraints.NAMES.get(k, k)}")
            self.area.tag_redraw()
