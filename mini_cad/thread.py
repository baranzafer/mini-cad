"""Diş, vida ve somun — Blender tarafı (v0.36.0).

- Diş ayarları (core.MINICAD_Thread): standarttan doldur, geçme ön ayarı, hesap parametresi.
- Dişli delikten uyumlu vida / somun: yeni BlendCAD gövdesi (part_kind SCREW / NUT). Bağlı
  parça diş tanımını ve toleransı delikten alır: delik değişince vida da yeniden hesaplanır.
- Deliğe yerleştir: vida ekseni deliğin ekseni, baş yüzeyde (kademeli delikte yuva dibinde,
  havşada yüzeyle aynı hizada); somun geçen deliğin çıkış yüzünde.

Hesap (OCC) threadgeo.py'de, saf matematik threadmath.py'de.
"""

import math

import bpy
import numpy as np

from . import core
from . import threadmath as tm


def scene_scale():
    try:
        return bpy.context.scene.unit_settings.scale_length or 1.0
    except Exception:
        return 1.0


def u(mm):
    """mm → sahne birimi."""
    return tm.mm_to_units(mm, scene_scale())


def mm(v):
    return tm.units_to_mm(v, scene_scale())


# ---------------------------------------------------------------- diş ayarları

def fill_standard(thr, family=None, size=None):
    """Standart ve ölçüden diş değerlerini doldur (Özel'de dokunmaz)."""
    family = family or thr.family
    if family == "CUSTOM":
        if thr.family != "CUSTOM":
            thr.family = "CUSTOM"
        return
    names = tm.sizes(family)
    if not names:
        return
    if size is None:
        size = thr.size
    if size not in names:
        # aynı çapa en yakın ölçü (aile değişince)
        dmm = mm(thr.D)
        best = min(names, key=lambda n: abs(tm.standard(family, n)["D"] - dmm))
        size = best
    st = tm.standard(family, size)
    if thr.family != family:
        thr.family = family
    thr.size = size
    thr.profile = st["profile"]
    thr.D, thr.P = u(st["D"]), u(st["P"])
    thr.angle = st["a1"] + st["a2"]
    thr.angle2 = st["a1"]
    thr.depth, thr.crest = u(st["depth"]), u(st["crest"])
    thr.rc, thr.rr = u(st["rc"]), u(st["rr"])
    apply_fit(thr)


def apply_fit(thr):
    """Geçme ön ayarından boşluk (Özel'de elle girilen kalır)."""
    c = tm.fit_clearance(thr.fit, mm(thr.P))
    if c is not None:
        thr.clearance = u(c)


def init_thread(thr, family="ISO_M", size="M6", modeled=True, fit="NOMINAL"):
    thr.inited = True
    thr.modeled = modeled
    thr.fit = fit
    thr.family = family
    fill_standard(thr, family, size)


def set_profile(thr, prof):
    """Profil türü elle değişince (Özel): uygun başlangıç oranları."""
    P = thr.P
    shape = {"TRI": "ISO", "TRAP": "TR", "SQUARE": "SQ", "ROUND": "RD", "BUTT": "BUTT"}.get(prof)
    if shape is None:
        thr.profile = prof
        return
    p, a1, a2, h, c, rc, rr = tm.SHAPES[shape]
    thr.profile = prof
    thr.angle, thr.angle2 = a1 + a2, a1
    thr.depth, thr.crest, thr.rc, thr.rr = h * P, c * P, rc * P, rr * P
    if thr.family != "CUSTOM":
        thr.family = "CUSTOM"


def curve_points(ob, n=10):
    """Profil eğrisinin (ilk spline) yerel XY noktaları."""
    if ob is None or ob.type != "CURVE" or not len(ob.data.splines):
        return None
    sp = ob.data.splines[0]
    out = []
    if sp.type == "BEZIER":
        bp = list(sp.bezier_points)
        segs = len(bp) if sp.use_cyclic_u else len(bp) - 1
        for i in range(segs):
            a, b = bp[i], bp[(i + 1) % len(bp)]
            P = [np.array(a.co), np.array(a.handle_right), np.array(b.handle_left),
                 np.array(b.co)]
            for k in range(n if i < segs - 1 else n + 1):
                t = k / n
                q = ((1 - t) ** 3 * P[0] + 3 * (1 - t) ** 2 * t * P[1] +
                     3 * (1 - t) * t * t * P[2] + t ** 3 * P[3])
                out.append((float(q[0]), float(q[1])))
    else:
        out = [(float(p.co[0]), float(p.co[1])) for p in sp.points]
    return out


def thread_name(thr):
    if thr.family != "CUSTOM" and thr.size:
        return thr.size
    from .core import fmt_len
    return f"Ø{fmt_len(thr.D)}×{fmt_len(thr.P)}"


def spec(thr):
    """threadmath diş tanımı (sahne biriminde) + kılavuz matkabı ve ad."""
    d = {"D": thr.D, "P": thr.P, "profile": thr.profile, "angle": thr.angle,
         "angle2": thr.angle2, "depth": thr.depth, "crest": thr.crest, "rc": thr.rc,
         "rr": thr.rr, "hand": thr.hand, "starts": thr.starts, "custom_w": thr.custom_w}
    if thr.profile == "CUSTOM":
        d["custom"] = curve_points(thr.custom_obj)
    sp = tm.spec_from(d)
    tap = None
    if thr.family != "CUSTOM":
        try:
            st = tm.standard(thr.family, thr.size)
            if abs(st["D"] - mm(thr.D)) < 1e-6 and abs(st["P"] - mm(thr.P)) < 1e-6:
                tap = u(st["tap"])
        except ValueError:
            tap = None
    if tap is None:
        tap = thr.D - thr.P * (1.5 if thr.profile == "BUTT" else 1.0)
    sp["tap"] = tap
    sp["name"] = thread_name(thr)
    return sp


def offsets(thr):
    """(delik ofseti, vida ofseti) sahne biriminde."""
    return tm.fit_offsets(thr.clearance, thr.share, thr.swell)


def hole_thread_params(f):
    """Dişli deliğin hesap parametresi (core.hole_params'a eklenir): (matkap çapı, thr)."""
    thr = f.thr
    if not thr.inited:
        init_thread(thr, "ISO_M", f.hole_thread if f.hole_thread != "NONE" else "M6",
                    modeled=False)
    sp = spec(thr)
    dh, _ds = offsets(thr)
    th = {"spec": sp, "d_hole": dh, "engage": thr.engage, "modeled": bool(thr.modeled),
          "length": thr.length, "name": sp["name"], "hand": thr.hand,
          "starts": thr.starts}
    if thr.modeled:
        try:
            d = tm.minor_drill(sp, dh, thr.engage)
        except Exception:
            d = sp["tap"]
    else:
        d = sp["tap"] + 2.0 * dh
    return d, th


def check(thr):
    """Diş değerleri denetimi: hata metni | ''."""
    try:
        sp = spec(thr)
        if thr.profile == "CUSTOM" and not sp.get("custom"):
            return "Özel profil için bir eğri seç"
        dh, ds = offsets(thr)
        return tm.check_regions(sp, dh, ds, thr.engage)
    except Exception as e:
        return str(e)


# ---------------------------------------------------------------- parça (vida / somun)

def is_part(ob):
    try:
        return ob is not None and ob.cad.is_cad and ob.cad.part_kind in ("SCREW", "NUT")
    except Exception:
        return False


def linked_feature(ob):
    """Bağlı dişli delik özelliği | None."""
    pt = ob.cad.part
    b = pt.link_obj
    if b is None or not pt.link_uid:
        return None
    for f in b.cad.features:
        if f.uid == pt.link_uid and f.op == "HOLE":
            return f
    return None


def source_thread(ob):
    """Parçanın diş tanımı: bağlı dişli delikten ya da kendisinden."""
    pt = ob.cad.part
    if pt.linked:
        f = linked_feature(ob)
        if f is not None and f.hole_kind == "TAPPED" and f.thr.inited:
            return f.thr
    return pt.thr


def head_dims(pt, D):
    """Baş ölçüleri (sahne birimi)."""
    if pt.auto_head:
        h = tm.head_dims(pt.head, mm(D))
        out = {k: (u(v) if k != "angle" else v) for k, v in h.items()}
        if pt.head == "CSK":
            out.setdefault("angle", 90.0)
        return out
    out = {"dk": pt.head_dk, "k": pt.head_k, "s": pt.drive_s, "t": pt.drive_t}
    if pt.head == "CSK":
        out["angle"] = 90.0
        out["k"] = 0.5 * (pt.head_dk - D)
    return out


def nut_dims(pt, D):
    if pt.auto_head:
        n = tm.nut_dims(mm(D))
        return u(n["s"]), u(n["m"])
    return pt.nut_s, pt.nut_m


def primitive(ob):
    """gather için parça tanımı (hesap sürecine gider)."""
    props = ob.cad
    pt = props.part
    thr = source_thread(ob)
    sp = spec(thr)
    dh, ds = offsets(thr)
    mw = ob.matrix_world
    mat = [[float(mw[i][j]) for j in range(4)] for i in range(4)]
    if props.part_kind == "SCREW":
        hd = head_dims(pt, thr.D)
        p = {"kind": "SCREW", "spec": sp, "d": ds,
             "sp": {"head": pt.head, "drive": pt.drive, "L": pt.length,
                    "thread_len": pt.thr.length,
                    "tip_chamfer": pt.tip_chamfer and thr.lead_in,
                    "modeled": bool(thr.modeled), "head_dims": hd},
             "label": f"vida {sp['name']}×{core.fmt_len(pt.length)}"}
    else:
        s, m = nut_dims(pt, thr.D)
        p = {"kind": "NUT", "spec": sp, "d": dh, "engage": thr.engage, "s": s, "m": m,
             "modeled": bool(thr.modeled), "label": f"somun {sp['name']}"}
    p["matrix"] = mat
    p["key"] = (repr({k: v for k, v in p.items() if k != "key"}),)
    return p


def part_key(ob):
    try:
        return primitive(ob)["key"]
    except Exception as e:
        return ("err", str(e))


# ---------------------------------------------------------------- yerleştirme

def _frame(origin, zaxis):
    from mathutils import Matrix, Vector
    z = Vector(zaxis).normalized()
    a = Vector((1, 0, 0)) if abs(z.x) < 0.9 else Vector((0, 1, 0))
    x = a.cross(z).normalized()
    y = z.cross(x)
    m = Matrix.Identity(4)
    for i in range(3):
        m[i][0], m[i][1], m[i][2], m[i][3] = x[i], y[i], z[i], origin[i]
    return m


def hole_world(body, f, idx):
    """(dünya yeri, malzemeye doğru birim eksen) | None."""
    from mathutils import Vector
    if idx < 0 or idx >= len(f.hole_pts):
        return None
    h = f.hole_pts[idx]
    mw = body.matrix_world
    co = mw @ Vector(tuple(h.co))
    d = (mw.to_3x3() @ Vector(tuple(h.nrm)))
    if d.length < 1e-12:
        return None
    return co, d.normalized()


def exit_depth(body, f, idx):
    """Delik ekseni boyunca gövde kalınlığı (deliğin dışından, radyal kaydırılmış ışınla) |
    None."""
    from mathutils import Vector
    hw = hole_world(body, f, idx)
    if hw is None:
        return None
    co, d = hw
    R = 0.5 * max(f.hole_d, f.hole_cb_d if f.hole_kind == "CBORE" else 0.0,
                  f.hole_cs_d if f.hole_kind == "CSINK" else 0.0,
                  f.thr.D if f.hole_kind == "TAPPED" else 0.0, f.hole_mouth_d)
    a = Vector((1, 0, 0)) if abs(d.x) < 0.9 else Vector((0, 1, 0))
    side = a.cross(d).normalized()
    inv = body.matrix_world.inverted()
    best = None
    eps = R * 1e-3 + 1e-7
    for sgn in (1, -1):
        start = co + side * (R * 1.6 * sgn) + d * eps
        o = inv @ start
        dl = (inv.to_3x3() @ d).normalized()
        try:
            ok, loc, _n, _i = body.ray_cast(o, dl)
        except Exception:
            ok = False
        if ok:
            dist = (body.matrix_world @ loc - start).length + eps
            best = dist if best is None else min(best, dist)
    return best


def seat_offset(f):
    """Vida başının oturduğu düzlemin yüzeyden derinliği."""
    if f.hole_kind == "CBORE":
        return f.hole_cb_depth
    if f.hole_kind == "CSINK":
        return f.hole_cs_head
    return 0.0


def place(ob):
    """Bağlı parçayı deliğe yerleştir. True / False."""
    pt = ob.cad.part
    body = pt.link_obj
    f = linked_feature(ob)
    if body is None or f is None:
        return False
    hw = hole_world(body, f, pt.link_pt)
    if hw is None:
        return False
    co, d = hw
    if ob.cad.part_kind == "SCREW":
        origin = co + d * seat_offset(f)
        ob.matrix_world = _frame(origin, -d)
    else:
        t = exit_depth(body, f, pt.link_pt)
        if t is None:
            t = f.hole_depth
        ob.matrix_world = _frame(co + d * t, d)
    return True


def default_length(body, f, idx, kind_head):
    """Deliğe uyan standart vida boyu (sahne birimi)."""
    t = exit_depth(body, f, idx)
    through = f.hole_through or f.hole_kind != "TAPPED"
    if f.hole_kind == "TAPPED":
        if f.hole_through:
            avail = t if t else f.hole_depth
        else:
            avail = f.hole_depth - 0.5 * f.thr.P
            if f.thr.length > 0:
                avail = min(avail, f.thr.length + 0.5 * f.thr.P)
    else:
        avail = (t if t else f.hole_depth) - seat_offset(f)
        if through:
            D = u(_nominal_mm(f))
            avail += u(tm.nut_dims(mm(D))["m"]) + 0.3 * D
    L = u(tm.std_length(max(mm(avail), 2.0)))
    if kind_head == "CSK":
        L += 0.0
    return L


def _nominal_mm(f):
    if f.hole_kind == "TAPPED" and f.thr.inited:
        return mm(f.thr.D)
    from . import holemath
    if f.hole_thread in holemath.ISO_COARSE:
        return holemath.ISO_COARSE[f.hole_thread][0]
    return mm(f.hole_d) / 1.1


def _nominal_size(f):
    """Geçme deliğinin metrik ölçüsü (vida için)."""
    if f.hole_thread != "NONE":
        return f.hole_thread
    dmm = mm(f.hole_d)
    names = tm.sizes("ISO_M")
    return min(names, key=lambda n: abs(tm.standard("ISO_M", n)["D"] * 1.1 - dmm))


def new_part_object(context, kind, name):
    me = bpy.data.meshes.new(name)
    ob = bpy.data.objects.new(name, me)
    context.collection.objects.link(ob)
    ob.cad.is_cad = True
    ob.cad.part_kind = kind
    core.forget_cache(ob.name)
    return ob


def tune_mesh(ob, thr):
    """Parçada üçgenleme ölçüsü dişe göre (sahne genelindeki küçük sapma helisel dişte
    yüz binlerce üçgen veriyordu)."""
    ob.cad.lin_defl = max(min(thr.P * 0.04, thr.D * 0.005), 1e-7)
    ob.cad.ang_defl = math.radians(8.0)


def create_for_hole(context, body, f, idx=0, kind="SCREW"):
    """Delikten uyumlu vida / somun. (obje, mesaj)."""
    if f is None or f.op != "HOLE":
        return None, "Delik seçili değil"
    if not len(f.hole_pts):
        return None, "Deliğin yeri yok: önce yüzeye tıklayarak yer ver"
    idx = min(max(idx, 0), len(f.hole_pts) - 1)
    tapped = f.hole_kind == "TAPPED"
    if tapped and not f.thr.inited:
        init_thread(f.thr, "ISO_M", f.hole_thread if f.hole_thread != "NONE" else "M6",
                    modeled=False)
    if kind == "NUT" and tapped:
        return None, "Dişli deliğe somun gerekmez (vida doğrudan deliğe girer)"
    if tapped:
        nm = thread_name(f.thr)
    else:
        nm = _nominal_size(f)
    label = "Vida" if kind == "SCREW" else "Somun"
    ob = new_part_object(context, kind, f"{label} {nm}")
    pt = ob.cad.part
    pt.link_obj = body
    pt.link_uid = f.uid
    pt.link_pt = idx
    if tapped:
        pt.linked = True
        init_thread(pt.thr, f.thr.family, f.thr.size, modeled=f.thr.modeled, fit=f.thr.fit)
    else:
        pt.linked = False                   # geçme deliği: diş vidanın kendisinde
        init_thread(pt.thr, "ISO_M", nm, modeled=True, fit="NOMINAL")
    if kind == "SCREW":
        pt.head = {"CBORE": {"SOCKET": "SOCKET", "LOWHEAD": "SOCKET", "HEX": "HEX",
                             "BUTTON": "BUTTON"}.get(f.hole_head, "SOCKET"),
                   "CSINK": "CSK"}.get(f.hole_kind, "SOCKET")
        if pt.head == "CSK" and f.hole_csk in ("ISO7046", "DIN74"):
            pt.drive = "CROSS"
        pt.length = default_length(body, f, idx, pt.head)
        if f.hole_kind == "CBORE" and f.hole_head == "LOWHEAD":
            pt.auto_head = False
            hd = tm.head_dims("LOWHEAD", mm(source_thread(ob).D))
            pt.head_dk, pt.head_k = u(hd["dk"]), u(hd["k"])
            pt.drive_s, pt.drive_t = u(hd["s"]), u(hd["t"])
    tune_mesh(ob, source_thread(ob))
    place(ob)
    ok = core.rebuild(ob)
    msg = f"{ob.name}: {ob.cad.status}" if ok else f"{ob.name}: {ob.cad.status}"
    return ob, msg


def create_free(context, kind="SCREW", size="M6"):
    """Bağımsız vida / somun (3B imlecinde, Z ekseninde)."""
    ob = new_part_object(context, kind, f"{'Vida' if kind == 'SCREW' else 'Somun'} {size}")
    pt = ob.cad.part
    pt.linked = False
    init_thread(pt.thr, "ISO_M", size, modeled=True, fit="NOMINAL")
    pt.length = u(16.0)
    from mathutils import Matrix
    ob.matrix_world = Matrix.Translation(context.scene.cursor.location)
    tune_mesh(ob, pt.thr)
    core.rebuild(ob)
    return ob


def parts_linked_to(body):
    out = []
    for ob in bpy.data.objects:
        try:
            if is_part(ob) and ob.cad.part.link_obj == body:
                out.append(ob)
        except Exception:
            pass
    return out


# ---------------------------------------------------------------- operatörler

class MINICAD_OT_part_from_hole(bpy.types.Operator):
    """Dişli delikten uyumlu vida (ya da geçme deliğine vida / somun) oluşturur"""
    bl_idname = "minicad.part_from_hole"
    bl_label = "Uyumlu vida"
    bl_options = {"REGISTER", "UNDO"}

    body: bpy.props.StringProperty(options={"HIDDEN"})
    uid: bpy.props.StringProperty(options={"HIDDEN"})
    index: bpy.props.IntProperty(default=0, options={"HIDDEN"})
    kind: bpy.props.StringProperty(default="SCREW", options={"HIDDEN"})

    def execute(self, context):
        body = bpy.data.objects.get(self.body)
        f = None
        if body is not None:
            f = next((x for x in body.cad.features if x.uid == self.uid), None)
        ob, msg = create_for_hole(context, body, f, self.index, self.kind)
        if ob is None:
            self.report({"WARNING"}, msg)
            return {"CANCELLED"}
        self.report({"INFO"}, msg)
        return {"FINISHED"}


classes = (MINICAD_OT_part_from_hole,)


def register():
    for c in classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
