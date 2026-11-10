"""Taslak: nokta koyma, çizgi / şekil tamamlama, taslağı hafızada tutma, Bitir ile hedef
eğriye yazma, oto kısıtlar, yüzey, taslak geri al / yinele geçmişi.

MINICAD_OT_draw (draw.py) bu mixin'den miras alır; metotlar self üzerinden birbirini çağırır.
"""
import bpy
import copy
import math
import numpy as np
import traceback
from mathutils import Vector

from . import constraints
from . import core
from . import drawmath as dm
from .draw_common import AXIS_OF, SHAPE_TOOLS, _LAST, parse_length


class SketchMixin:
    """Taslak: nokta koyma, çizgi / şekil tamamlama, taslağı hafızada tutma, Bitir ile hedef
    eğriye yazma, oto kısıtlar, yüzey, taslak geri al / yinele geçmişi."""

    def _finalize_stage(self):
        """Çok noktalı spline'ı zincire ekler (araç değişince / Enter'da)."""
        if self.tool in ("CV", "FIT") and self.stage and self._anchor() is not None:
            pts = [self._anchor()] + self.stage
            segs = dm.bspline_bezier(pts) if self.tool == "CV" else dm.fit_bezier(pts)
            self._grp += 1
            for sg in segs:
                sg["grp"] = self._grp
            self.segs += segs
            self.out_h = None
        self.stage = []
        self.shape_plane = None
        self.pen = None

    def _auto_for(self, seg_index, typed_len):
        """Doğru parçası için çizerken yakalanan kısıtlar."""
        out = []
        info = self.info or {}
        kind = (info.get("kind") or "").split(" + ")[0]
        pl = info.get("plane") or self.plane
        if kind in AXIS_OF and pl is not None and pl.name in AXIS_OF[kind]:
            out.append(("AXIS", AXIS_OF[kind][pl.name]))
        elif kind in ("Paralel", "Dik") and isinstance(info.get("ref_seg"), int):
            j = info["ref_seg"]
            if 0 <= j < len(self._cur_chords) and self._cur_chords[j][2] is not None:
                out.append(("REF", "PARALLEL" if kind == "Paralel" else "PERP",
                            self._cur_chords[j][2]))
        elif kind in ("Doğrusal", "Dik (önceki)") and seg_index > 0 and \
                self.segs[seg_index - 1]["kind"] == "line":
            out.append(("REF", "COLLINEAR" if kind == "Doğrusal" else "PERP",
                        ("chain", seg_index - 1)))
        if typed_len is not None:
            out.append(("DIST", typed_len))
        return out

    def _place(self, context):
        if self.cursor is None:
            return
        t = self.tool
        cur = self.cursor.copy()
        anchor = self._anchor()
        try:
            from . import recorder
            recorder.log("çiz", f"{t} tık {recorder.fmt_pt(cur)} · yakalama={self.snap_kind} · "
                                f"kılavuz={(self.info or {}).get('kind')} · yazılan={self.typed}")
        except Exception:
            pass
        if t in SHAPE_TOOLS:
            if not self.stage:
                self.stage = [cur]
                base = self.plane or self.tmp_plane or self._make_plane(self.plane_mode, cur)
                self.shape_plane = base.moved(cur)
                self.typed, self.field = ["", ""], 0
                return
            if not self.preview:
                return
            pl = self.shape_plane
            autos = []
            if t == "RECT":
                if pl.name in dm.AXIS_PLANES:
                    ax_u = {"XY": 0, "XZ": 0, "YZ": 1}[pl.name]
                    ax_v = {"XY": 1, "XZ": 2, "YZ": 2}[pl.name]
                    autos = [[("AXIS", ax_u)], [("AXIS", ax_v)], [("AXIS", ax_u)],
                             [("AXIS", ax_v)]]
                else:
                    autos = [[], [("REF", "PERP", ("chain", 0))], [("REF", "PARALLEL",
                                                                     ("chain", 0))],
                             [("REF", "PARALLEL", ("chain", 1))]]
            segs = [dict(s) for s in self.preview]
            for s, a in zip(segs, autos):
                s["auto"] = a
            self._write_shape(context, segs)
            self.stage, self.shape_plane = [], None
            self.typed, self.field = ["", ""], 0
            return
        if anchor is None:
            if t == "CARC" and not self.stage:
                self.stage = [cur]                # önce merkez
                base = self.tmp_plane or self._make_plane(self.plane_mode, cur)
                self.plane = base.moved(cur)
                return
            self.start = cur
            self.node_ids = {0: self.snap_id} if self.snap_id else {}
            self.start_tan = self._end_tangent_of(self.snap_id) if self.snap_id else None
            if self.plane is None:
                self.plane = (self.tmp_plane or self._make_plane(self.plane_mode, cur)).moved(cur)
            else:
                self.plane = self.plane.moved(cur)
            self.out_h = None
            self._status(context, "")
            return
        tarc3 = t == "TARC" and self._prev_tangent() is None
        if (t in ("ARC3", "CARC") or tarc3) and not self.stage:
            self.stage = [cur]
            return
        if t in ("CV", "FIT"):
            if np.linalg.norm(cur - (self.stage[-1] if self.stage else anchor)) > 1e-12:
                self.stage.append(cur)
                self.typed, self.field = ["", ""], 0
                if self.snap_kind == "Başlangıç" and len(self.stage) >= 2:
                    self._finalize_stage()
                    self._commit(context, cyclic=True)
            return
        if not self.preview or self.preview[0]["kind"] == "guide":
            return
        closing = self.snap_kind == "Başlangıç" and (
            len(self.segs) >= 2 or any(sg["kind"] != "line" for sg in self.preview))
        typed_len = parse_length(self.typed[0]) if t == "LINE" and self.typed[0] else None
        self._grp += 1
        new = [dict(s) for s in self.preview]
        for sg in new:
            sg["grp"] = self._grp
        if t == "LINE" and len(new) == 1:
            new[0]["auto"] = self._auto_for(len(self.segs), typed_len)
        self.segs += new
        if self.snap_id and not closing:
            self.node_ids[len(self.segs)] = self.snap_id
        self.stage = []
        self.out_h = None
        self.typed = ["", ""]
        self.field = 0
        if closing:
            self._commit(context, cyclic=True)
            return
        self.plane = self.plane.moved(self.segs[-1]["p"][3])
        self.preview = []

    def _pen_release(self, context):
        pen, self.pen = self.pen, None
        if pen is None:
            return
        co, h = pen["co"], pen["h"]
        anchor = self._anchor()
        if anchor is None:
            self.start = co
            self.node_ids = {0: pen.get("id")} if pen.get("id") else {}
            self.plane = (self.plane or self.tmp_plane or
                          self._make_plane(self.plane_mode, co)).moved(co)
            self.out_h = h
            return
        if np.linalg.norm(co - anchor) <= 1e-12:
            self.out_h = h
            return
        closing = pen.get("kind") == "Başlangıç" and len(self.segs) >= 1
        self._grp += 1
        seg = dm.pen_seg(anchor, self.out_h, co, h)
        seg["grp"] = self._grp
        self.segs.append(seg)
        if pen.get("id") and not closing:
            self.node_ids[len(self.segs)] = pen["id"]
        self.out_h = h
        if closing:
            self._commit(context, cyclic=True)
            return
        self.plane = self.plane.moved(co)

    def _close(self, context):
        self._finalize_stage()
        if len(self.segs) < 2 or self.start is None:
            self._status(context, "Kapatmak için en az iki parça gerekli")
            return
        anchor = self._anchor()
        t0 = self._prev_tangent()
        arc = dm.tangent_arc(anchor, t0, self.start) if self.tool == "TARC" and t0 is not None \
            else None
        self.segs += arc["segs"] if arc is not None else [dm.line_seg(anchor, self.start)]
        self._commit(context, cyclic=True)

    def _target_curve(self, context):
        # Eski sürümlerde eğri objesinin TAMAMIYLA tanımlanmış yüzeyler var: o eğrilere spline
        # eklemek o yüzeyleri bozar, bu yüzden onlar hedef alınmaz.
        whole = set()
        try:
            for o in bpy.data.objects:
                if o.type == "MESH" and o.cad.is_cad:
                    for p in o.cad.patches:
                        whole.update(r.obj.name for r in p.curves if r.obj is not None)
        except Exception:
            pass

        def ok(o):
            return o is not None and o.type == "CURVE" and o.name not in whole

        act = context.active_object
        if ok(act):
            return act
        last = bpy.data.objects.get(_LAST["curve"]) if _LAST["curve"] else None
        if ok(last) and last.name in context.scene.objects:
            return last
        try:
            from .ui import get_target
            t = get_target(context)
            if t is not None:
                for w in core.wire_objects(t.cad):
                    if ok(w):
                        return w
        except Exception:
            pass
        cu = bpy.data.curves.new("CAD_TelKafes", "CURVE")
        cu.dimensions = "3D"
        ob = bpy.data.objects.new("CAD_TelKafes", cu)
        context.collection.objects.link(ob)
        return ob

    def _write_spline(self, context, ob, segs, cyclic):
        pts = dm.bezier_points(segs, cyclic)
        was_edit = ob.mode == "EDIT"
        if was_edit:
            bpy.ops.object.mode_set(mode="OBJECT")
        try:
            cu = ob.data
            if cu.dimensions != "3D":
                cu.dimensions = "3D"
            mwi = ob.matrix_world.inverted()

            def loc(p):
                return mwi @ Vector(tuple(float(x) for x in p))

            sp = cu.splines.new("BEZIER")
            bps = sp.bezier_points
            bps.add(len(pts) - 1)
            for b, p in zip(bps, pts):
                b.handle_left_type = "FREE"
                b.handle_right_type = "FREE"
                b.co = loc(p["co"])
                b.handle_left = loc(p["hl"])
                b.handle_right = loc(p["hr"])
            for b, p in zip(bps, pts):
                b.handle_left_type = p["tl"]
                b.handle_right_type = p["tr"]
            sp.use_cyclic_u = cyclic
            cu.update_tag()
            return len(cu.splines) - 1
        finally:
            if was_edit:
                try:
                    bpy.ops.object.mode_set(mode="EDIT")
                except Exception:
                    pass

    def _auto_constraints(self, context, ob, si, segs, cyclic, node_ids, solve=True):
        if not getattr(context.scene, "minicad_auto_constraints", True):
            return 0
        n_pts = len(segs) if cyclic else len(segs) + 1
        made = 0
        for j, sg in enumerate(segs):
            for a in sg.get("auto", ()):
                refs = None
                kind, value = None, None
                if a[0] == "AXIS":
                    kind, value, refs = "AXIS", a[1], [("seg", ob, si, j)]
                elif a[0] == "DIST":
                    kind, value, refs = "DISTANCE", a[1], [("seg", ob, si, j)]
                elif a[0] == "REF":
                    kind, rid = a[1], a[2]
                    if rid[0] == "chain":
                        other = ("seg", ob, si, rid[1])
                    else:
                        o2 = bpy.data.objects.get(rid[1])
                        other = ("seg", o2, rid[2], rid[3]) if o2 is not None else None
                    if other is not None:
                        refs = [other, ("seg", ob, si, j)]
                if refs:
                    c = constraints.add(kind, refs, auto=True, value=value, solve=False)
                    if c is None:
                        continue
                    if not constraints.satisfied(c):     # taslakta düzenlenip bozulduysa
                        constraints.remove_last(c)
                        continue
                    made += 1
        for k, pid in (node_ids or {}).items():
            o2 = bpy.data.objects.get(pid[0])
            if o2 is None or (o2 == ob and pid[1] == si):
                continue
            node = k % n_pts
            c = constraints.add("COINCIDENT", [("pt", o2, pid[1], pid[2]), ("pt", ob, si, node)],
                                auto=True, solve=False)
            if c is None:
                continue
            if not constraints.satisfied(c):
                constraints.remove_last(c)
                continue
            made += 1
        if made and solve:
            constraints.solve_all(context.scene, force=True)
        return made

    def _write_shape(self, context, segs):
        """Daire / dikdörtgen: taslağa kapalı çizgi olarak eklenir."""
        self.sketch.append({"segs": segs, "cyclic": True, "node_ids": {}, "start_tan": None})
        self.last_closed = ("sketch", len(self.sketch) - 1)
        self.dirty = True
        self._status(context, f"Kapalı şekil taslağa eklendi · taslak: {len(self.sketch)} çizgi"
                              " · Bitir (Ctrl+Enter) ile kaydet · F: yüzey")

    def _commit(self, context, cyclic=False):
        """Çizgiyi bitirir ve TASLAĞA ekler (henüz eğri objesine yazılmaz; noktaları ve
        tutamaçları sürüklenerek düzenlenebilir). Bitir ile eğriye kaydedilir."""
        self._finalize_stage()
        segs = self.segs
        node_ids = dict(self.node_ids)
        self.segs, self.start, self.plane, self.preview = [], None, None, []
        self.typed, self.field = ["", ""], 0
        self.node_ids, self.out_h = {}, None
        start_tan, self.start_tan = self.start_tan, None
        if not segs:
            return
        self.sketch.append({"segs": segs, "cyclic": cyclic, "node_ids": node_ids,
                            "start_tan": start_tan})
        if cyclic:
            self.last_closed = ("sketch", len(self.sketch) - 1)
        self.dirty = True
        try:
            from . import recorder
            recorder.log("çiz", f"taslağa çizgi eklendi: {len(segs)} parça · kapalı={cyclic} · "
                                f"taslak {len(self.sketch)} çizgi")
        except Exception:
            pass
        msg = f"Taslağa eklendi ({len(self.sketch)} çizgi) · noktaları / tutamaçları " \
              "sürükleyerek düzenle · Bitir (Ctrl+Enter) ile kaydet"
        if cyclic:
            msg += " · F: yüzey"
        self._status(context, msg)

    def _new_curve(self, context):
        cu = bpy.data.curves.new("CAD_TelKafes", "CURVE")
        cu.dimensions = "3D"
        ob = bpy.data.objects.new("CAD_TelKafes", cu)
        context.collection.objects.link(ob)
        return ob

    def _finish_sketch(self, context):
        """Taslaktaki bütün çizgileri eğri objesine yazar (Inventor'daki Bitir gibi).
        {taslak indeksi: (obje adı, spline, segment sayısı)} döndürür."""
        self._finalize_stage()
        if self.segs:
            self._commit(context)
        strokes, self.sketch = self.sketch, []
        self.sk_hover = self.sk_drag = None
        if not strokes:
            return {}
        try:
            if getattr(context.scene, "minicad_draw_target", "ACTIVE") == "NEW":
                ob = self._new_curve(context)
            else:
                ob = self._target_curve(context)
        except Exception as e:
            self.report({"ERROR"}, f"Eğri objesi bulunamadı: {e}")
            self.sketch = strokes
            return {}
        out, n_auto = {}, 0
        written = []
        for i, st in enumerate(strokes):
            try:
                si = self._write_spline(context, ob, st["segs"], st["cyclic"])
            except Exception as e:
                self.report({"ERROR"}, f"Çizgi yazılamadı: {e}")
                continue
            out[i] = (ob.name, si, len(st["segs"]))
            written.append((st, si))
        _LAST["curve"] = ob.name
        self.created += 1
        for st, si in written:
            try:
                n_auto += self._auto_constraints(context, ob, si, st["segs"], st["cyclic"],
                                                 st["node_ids"], solve=False)
                n_auto += self._auto_tangent(context, ob, si, st)
            except Exception:
                traceback.print_exc()
        try:
            n_auto += self._auto_joints(context, ob, written)
        except Exception:
            traceback.print_exc()
        if n_auto:
            constraints.solve_all(context.scene, force=True)
        try:
            bpy.ops.ed.undo_push(message="Mini CAD: Çizimi Bitir")
        except Exception:
            pass
        self.dirty = True
        msg = f"Bitti: '{ob.name}' içine {len(written)} çizgi kaydedildi"
        if n_auto:
            msg += f" · {n_auto} kısıt"
        try:
            from . import recorder
            recorder.log("çiz", msg)
        except Exception:
            pass
        self._status(context, msg)
        if self.last_closed is not None and self.last_closed[0] == "sketch":
            self.last_closed = out.get(self.last_closed[1])
        self.sk_sel = None
        self._hist_reset()                       # kaydedildi: geri alma artık Blender'da
        return out

    def _auto_tangent(self, context, ob, si, st):
        start_tan = st.get("start_tan")
        segs = st["segs"]
        if start_tan is None or not segs or not segs[0].get("tan_start") or \
                not getattr(context.scene, "minicad_auto_constraints", True):
            return 0
        t = dm.start_tangent(segs[0])
        if t is None or float(np.dot(t, start_tan[0])) < math.cos(math.radians(1.0)):
            return 0                              # taslakta düzenlenip teğetlik bozulmuş
        o2 = bpy.data.objects.get(start_tan[1][0])
        if o2 is not None and constraints.add(
                "TANGENT", [("seg", o2, start_tan[1][1], start_tan[1][2]), ("seg", ob, si, 0)],
                auto=True, solve=False) is not None:
            return 1
        return 0

    def _auto_joints(self, context, ob, written):
        """Aynı taslakta uç uca çizilmiş çizgileri Çakışık kısıtla bağlar."""
        if not getattr(context.scene, "minicad_auto_constraints", True):
            return 0
        nodes = []
        for st, si in written:
            segs = st["segs"]
            if st["cyclic"]:
                continue
            nodes.append((si, 0, segs[0]["p"][0]))
            nodes.append((si, len(segs), segs[-1]["p"][3]))
        made = 0
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                a, b = nodes[i], nodes[j]
                if a[0] == b[0]:
                    continue
                tol = 1e-7 * (1.0 + float(np.abs(a[2]).max()))
                if float(np.linalg.norm(a[2] - b[2])) <= tol:
                    if constraints.add("COINCIDENT", [("pt", ob, a[0], a[1]),
                                                      ("pt", ob, b[0], b[1])],
                                       auto=True, solve=False) is not None:
                        made += 1
        return made

    def _surface(self, context, new_body):
        try:
            from . import recorder
            recorder.log("çiz", f"F yüzey (yeni gövde={new_body}) · son kapalı={self.last_closed}")
        except Exception:
            pass
        if self.last_closed is None:
            self._status(context, "Önce kapalı bir çizgi ya da şekil çiz (C ile kapat)")
            return
        if self.last_closed[0] == "sketch":
            self._finish_sketch(context)          # yüzey için taslak önce kaydedilir
            if self.last_closed is None or self.last_closed[0] == "sketch":
                return
        name, si, n = self.last_closed
        ob = bpy.data.objects.get(name)
        if ob is None:
            return
        from .ui import apply_surface
        ok, msg = apply_surface(context, "segs", [(ob, si, i) for i in range(n)],
                                new_body=new_body)
        if ok:
            self.last_closed = None
            try:
                bpy.ops.ed.undo_push(message="Mini CAD: Yüzey")
            except Exception:
                pass
        self.report({"INFO"} if ok else {"ERROR"}, msg)
        self._status(context, msg)

    def _undo_last(self, context):
        if self.stage:
            self.stage.pop()
            if not self.stage:
                self.shape_plane = None
            return
        if self.segs:
            last = self.segs.pop()
            while self.segs and last.get("grp") is not None and \
                    self.segs[-1].get("grp") == last.get("grp"):
                self.segs.pop()
            for k in [k for k in self.node_ids if k > len(self.segs)]:
                del self.node_ids[k]
            a = self._anchor()
            if a is not None and self.plane is not None:
                self.plane = self.plane.moved(a)
            self.out_h = None
        elif self.start is not None:
            self.start, self.plane = None, None
            self.node_ids = {}
            self.start_tan = None
        elif self.sketch:
            self.sketch.pop()
            self.dirty = True
            self._status(context, f"Taslaktan son çizgi silindi ({len(self.sketch)} kaldı)")

    def _state_sig(self):
        vals = []
        for st in self.sketch:
            vals.append(len(st["segs"]) + (0.5 if st["cyclic"] else 0.0))
            for sg in st["segs"]:
                for q in sg["p"]:
                    vals.extend(q)
        vals.append(-1.0)
        for sg in self.segs:
            for q in sg["p"]:
                vals.extend(q)
        vals.append(-2.0)
        if self.start is not None:
            vals.extend(self.start)
        for q in self.stage:
            vals.extend(q)
        return hash(tuple(round(float(v), 9) for v in vals))

    def _snapshot(self):
        return copy.deepcopy({
            "sketch": self.sketch, "segs": self.segs, "start": self.start,
            "node_ids": self.node_ids, "start_tan": self.start_tan, "stage": self.stage,
            "out_h": self.out_h, "plane": self.plane, "shape_plane": self.shape_plane,
            "last_closed": self.last_closed})

    def _hist_sync(self):
        """Durum değiştiyse önceki durumu geçmişe ekler (fare hareketlerinde çağrılmaz)."""
        if self.sk_drag is not None:
            return
        sig = self._state_sig()
        if self._hsig is None:
            self._hsnap, self._hsig = self._snapshot(), sig
            return
        if sig != self._hsig:
            self.hist.append(self._hsnap)
            del self.hist[:-100]
            self.redo.clear()
            self._hsnap, self._hsig = self._snapshot(), sig

    def _hist_reset(self):
        self.hist.clear()
        self.redo.clear()
        self._hsnap, self._hsig = self._snapshot(), self._state_sig()

    def _hist_step(self, context, src, dst, msg):
        dst.append(self._snapshot())
        snap = src.pop()
        for k, v in copy.deepcopy(snap).items():
            setattr(self, k, v)
        self._hsnap, self._hsig = snap, self._state_sig()
        self.sk_sel = self.sk_hover = None
        self.preview = []
        self.dirty = True
        self._refresh(context)
        self._status(context, f"{msg} · taslak: {len(self.sketch)} çizgi")

    def _pen_drag(self, mx, my):
        pen = self.pen
        ro, rd = self._ray(mx, my)
        pl = (self.plane or self.tmp_plane or dm.Plane.axis("XY", pen["co"])).moved(pen["co"])
        hit = pl.ray_hit(ro, rd)
        if hit is None:
            return
        h = hit - pen["co"]
        if float(np.linalg.norm(h)) < 3 * self.ui_scale * self._px_size(pen["co"]):
            h = None
        pen["h"] = h
        self.cursor = pen["co"]
        self._make_preview(pl)
