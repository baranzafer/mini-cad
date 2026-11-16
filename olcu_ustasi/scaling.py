# SPDX-License-Identifier: GPL-3.0-or-later
"""Seçimi tek bütün olarak, aralarındaki ilişkileri bozmadan ölçekleme.

Temel kural: dünya dönüşümü M yalnızca KÖK nesnelere uygulanır
    W_kök' = M @ W_kök
Alt nesneler ebeveynleri üzerinden aynı dönüşümü alır; ebeveyn ilişkisi,
ebeveyn ters matrisi, kısıtlar, değiştiriciler, veri paylaşımı hiç değişmez.

Kök başına yöntem:
  DIRECT : matrix_world ataması (eşit ölçekte her zaman kesin)
  FCURVE : dönüşümü anahtarlanmış, ebeveynsiz kök -> anahtarlar afin dönüştürülür
  EMPTY  : başka yol kesin değilse (eşit olmayan ölçek + dönük nesne, ebeveynli
           animasyon ...) köklerin üstüne bir 'Olcek_Koku' Empty eklenir; kökün
           yerel değerleri ve animasyonu olduğu gibi kalır.
"""
import bpy
from mathutils import Matrix, Vector

from . import geom
from .selection import (ancestors, depth, descendants, has_transform_anim,
                        transform_fcurves)

ROOT_EMPTY_NAME = "Olcek_Koku"


class Scaler:
    def __init__(self, group):
        self.group = group
        # bağlı (linked, düzenlenemez) nesneler taşınamaz; alt nesneleri ebeveynle gelir
        self.locked = [o for o in group.roots if o.library is not None]
        self.roots = [o for o in group.roots if o.library is None]
        self.orig = {o.name: o.matrix_world.copy() for o in self.roots}
        self.current = None

    # ---------------------------------------------------------------- önizleme
    def preview(self, M):
        self.current = M
        for o in self.roots:
            o.matrix_world = M @ self.orig[o.name]

    def restore(self):
        self.current = None
        for o in self.roots:
            try:
                o.matrix_world = self.orig[o.name]
            except ReferenceError:
                pass

    # ------------------------------------------------------------------ bitir
    def finalize(self, context, M, frame=None, pivot=None, apply_data=False):
        """M: 4x4 dünya dönüşümü. Döndürür: (mesajlar listesi, oluşturulan empty'ler)."""
        self.restore()
        msgs = []
        if self.locked:
            msgs.append(f"Bağlı (linked) {len(self.locked)} nesne atlandı: önce yerel yap / override")
        lin = M.to_3x3()
        uniform = _is_uniform(lin)
        s = lin.median_scale if uniform else None
        frame = Matrix(frame) if frame is not None else Matrix.Identity(3)
        if pivot is None:
            pivot = M.translation.copy()

        methods = {}
        for o in self.roots:
            if has_transform_anim(o):
                ad = o.animation_data
                simple = (o.parent is None and uniform and not len(ad.nla_tracks)
                          and not any(d.data_path in ("location", "scale", "delta_location",
                                                      "delta_scale") for d in ad.drivers))
                methods[o.name] = 'FCURVE' if simple else 'EMPTY'
            else:
                methods[o.name] = 'DIRECT'

        # eşit olmayan ölçekte doğrudan atama kesin mi? (dönük/eğik nesnelerde değil)
        direct = [o for o in self.roots if methods[o.name] == 'DIRECT']
        if not uniform and direct:
            for o in direct:
                o.matrix_world = M @ self.orig[o.name]
            context.view_layer.update()
            for o in direct:
                if not geom.matrices_close(o.matrix_world, M @ self.orig[o.name], 1e-5):
                    methods[o.name] = 'EMPTY'
            for o in direct:
                o.matrix_world = self.orig[o.name]
            context.view_layer.update()

        for o in self.roots:
            if methods[o.name] in ('DIRECT', 'FCURVE'):
                o.matrix_world = M @ self.orig[o.name]
        fc_roots = [o for o in self.roots if methods[o.name] == 'FCURVE']
        for o in fc_roots:
            _scale_fcurves(o, s, M.translation)
        if fc_roots:
            msgs.append(f"{len(fc_roots)} animasyonlu nesnenin anahtarları ölçeklendi")

        empties = []
        em_roots = [o for o in self.roots if methods[o.name] == 'EMPTY']
        if em_roots:
            empties = _scale_with_empty(context, em_roots, M, frame, pivot)
            msgs.append(f"{len(em_roots)} nesne '{ROOT_EMPTY_NAME}' altında kesin ölçeklendi")

        context.view_layer.update()
        if fc_roots:
            context.scene.frame_set(context.scene.frame_current)

        if apply_data:
            if not uniform:
                msgs.append("Eşit olmayan ölçek veriye uygulanmadı (nesne ölçeği olarak kaldı)")
            else:
                objs = []
                for o in self.roots:
                    if methods[o.name] == 'DIRECT':
                        objs.extend([o] + descendants(o))
                if objs:
                    rep = apply_scale(context, objs)
                    msgs.extend(rep.messages())
        return msgs, empties


def _is_uniform(lin, tol=1e-6):
    s = lin.median_scale
    return all(abs(lin[i][j] - (s if i == j else 0.0)) <= tol * max(1.0, abs(s))
               for i in range(3) for j in range(3))


def _affine_keys(fc, a, b):
    for k in fc.keyframe_points:
        k.co.y = a * k.co.y + b
        k.handle_left.y = a * k.handle_left.y + b
        k.handle_right.y = a * k.handle_right.y + b
    fc.update()


def _scale_fcurves(o, s, t):
    """Ebeveynsiz kök, M = [s·I | t]:  loc' = s*loc + t + (s-1)*dloc ;  scale' = s*scale."""
    for fc in transform_fcurves(o):
        i = fc.array_index
        if fc.data_path == "location":
            c = t[i] + (s - 1.0) * o.delta_location[i]
            _affine_keys(fc, s, c)
        elif fc.data_path == "scale":
            _affine_keys(fc, s, 0.0)


def _target_collection(context, o):
    cols = list(o.users_collection)
    for c in cols:
        if c.library is None and not getattr(c, "override_library", None):
            return c
    return context.scene.collection


def _scale_with_empty(context, roots, M, frame, pivot):
    groups = {}
    for o in roots:
        key = (o.parent.name if o.parent else "", o.parent_type, o.parent_bone)
        groups.setdefault(key, []).append(o)
    F = Matrix.Translation(Vector(pivot)) @ Matrix(frame).to_4x4()
    made = []
    for (_pn, ptype, pbone), objs in groups.items():
        par = objs[0].parent
        e = bpy.data.objects.new(ROOT_EMPTY_NAME, None)
        e.empty_display_type = 'PLAIN_AXES'
        _target_collection(context, objs[0]).objects.link(e)
        if par is not None:
            e.parent = par
            e.parent_type = ptype if ptype in ('OBJECT', 'BONE') else 'OBJECT'
            if e.parent_type == 'BONE':
                e.parent_bone = pbone
        e.matrix_world = F
        context.view_layer.update()
        Ew = e.matrix_world.copy()
        Ewi = Ew.inverted_safe()
        for o in objs:
            # dünya = Ew @ PI_yeni @ basis  ==  önceki dünya   (basis ve animasyon değişmez)
            prev = o.matrix_world.copy()
            try:
                chain = prev @ o.matrix_basis.inverted()
            except ValueError:
                chain = o.matrix_parent_inverse.copy()
                if o.parent:
                    chain = o.parent.matrix_world @ chain
            o.parent = e
            o.parent_type = 'OBJECT'
            o.matrix_parent_inverse = Ewi @ chain
        e.matrix_world = M @ F
        # görünüm boyutu: kutu boyuna yakın
        e.empty_display_size = max(0.1, min(5.0, (M.to_3x3().median_scale)))
        made.append(e)
    return made


# =================================================================== güvenli uygula

# uzunluk cinsinden değiştirici özellikleri (eşit ölçekte s ile çarpılır)
MOD_LEN = {
    'BEVEL': ("width",),
    'SOLIDIFY': ("thickness",),
    'ARRAY': ("merge_threshold", "constant_offset_displace"),
    'MIRROR': ("merge_threshold", "bisect_distance"),
    'WELD': ("merge_threshold",),
    'DISPLACE': ("strength",),
    'SCREW': ("screw_offset", "merge_threshold"),
    'WIREFRAME': ("thickness",),
    'SHRINKWRAP': ("offset",),
    'REMESH': ("voxel_size",),
    'WAVE': ("height", "width", "falloff_radius", "start_position_x", "start_position_y"),
    'CAST': ("radius",),
    'WARP': ("falloff_radius",),
    'BOOLEAN': ("double_threshold",),
    'DECIMATE': (),
    'SUBSURF': (),
    'TRIANGULATE': (),
    'EDGE_SPLIT': (),
    'SMOOTH': (),
    'CORRECTIVE_SMOOTH': (),
    'LAPLACIANSMOOTH': (),
    'ARMATURE': (),
    'LATTICE': (),
    'CURVE': (),
    'SIMPLE_DEFORM': (),
    'DATA_TRANSFER': (),
    'NORMAL_EDIT': (),
    'WEIGHTED_NORMAL': (),
    'UV_PROJECT': (),
    'UV_WARP': (),
    'VERTEX_WEIGHT_EDIT': (),
    'VERTEX_WEIGHT_MIX': (),
    'VERTEX_WEIGHT_PROXIMITY': ("min_dist", "max_dist"),
    'MASK': (),
    'BUILD': (),
    'SKIN': (),
    'COLLISION': (),
    'SMOOTH_CORRECTIVE': (),
}
# eşit olmayan (afin) dönüşümde sonucu değiştirmeyen değiştiriciler
AFFINE_SAFE = {'SUBSURF', 'TRIANGULATE', 'ARMATURE', 'LATTICE', 'MASK', 'BUILD',
               'VERTEX_WEIGHT_EDIT', 'VERTEX_WEIGHT_MIX', 'DATA_TRANSFER', 'UV_PROJECT', 'UV_WARP'}

DATA_TYPES = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META', 'EMPTY', 'LIGHT', 'CAMERA'}


class ApplyReport:
    def __init__(self):
        self.applied = []
        self.skipped = {}           # ad -> neden
        self.copied = 0
        self.flipped = 0

    def skip(self, o, why):
        self.skipped[o.name] = why

    def messages(self):
        out = [f"Ölçek {len(self.applied)} nesnenin verisine uygulandı"]
        if self.copied:
            out.append(f"Dışarıyla paylaşılan {self.copied} veri kopyalandı")
        if self.skipped:
            items = list(self.skipped.items())
            txt = ", ".join(f"{n} ({w})" for n, w in items[:4])
            more = f" +{len(items) - 4}" if len(items) > 4 else ""
            out.append(f"Ölçeği korunanlar: {txt}{more}")
        return out


def _polar(W):
    lin = W.to_3x3()
    R = geom.orthonormal(lin)
    L = R.transposed() @ lin          # veri-uzayı dönüşümü: W = T R L
    return R, L


def _is_identity3(L, tol=1e-6):
    return all(abs(L[i][j] - (1.0 if i == j else 0.0)) <= tol for i in range(3) for j in range(3))


def _is_diagonal3(L, tol=1e-6):
    return all(abs(L[i][j]) <= tol * max(1.0, abs(L[i][i])) for i in range(3) for j in range(3) if i != j)


def _mods_ok(o, uniform, diagonal):
    for m in getattr(o, "modifiers", ()):
        if m.type not in MOD_LEN:
            return f"{m.type.lower()} değiştiricisi"
        if not uniform:
            if m.type in AFFINE_SAFE:
                continue
            if diagonal and m.type in ('MIRROR', 'ARRAY'):
                continue
            return f"eşit olmayan ölçek + {m.type.lower()}"
    if getattr(o, "particle_systems", None) and len(o.particle_systems):
        return "parçacık sistemi"
    for c in getattr(o, "constraints", ()):
        if c.type in ('CHILD_OF', 'TRANSFORM', 'LIMIT_SCALE', 'MAINTAIN_VOLUME', 'COPY_SCALE',
                      'COPY_TRANSFORMS', 'ARMATURE', 'TRANSFORM_CACHE') and c.enabled:
            return f"{c.type.lower()} kısıtı"
    return None


def _data_ok(o, uniform, diagonal):
    t = o.type
    if t not in DATA_TYPES:
        return f"{t.lower()} türü"
    d = o.data
    if d is not None and (d.library is not None or getattr(d, "override_library", None)):
        return "bağlı (linked) veri"
    if t == 'MESH' and d.shape_keys and d.shape_keys.use_relative is False:
        return "mutlak şekil anahtarı"
    if not uniform:
        if t in ('META', 'LIGHT', 'CAMERA', 'EMPTY', 'FONT'):
            return "eşit olmayan ölçek"
        if t in ('CURVE', 'SURFACE') and (d.bevel_depth > 0 or d.extrude > 0 or d.bevel_object):
            return "eşit olmayan ölçek + kalınlık"
    return None


def _scale_modifiers(o, s):
    for m in o.modifiers:
        for p in MOD_LEN.get(m.type, ()):
            if m.type == 'BEVEL' and p == "width" and getattr(m, "offset_type", "") == 'PERCENT':
                continue
            if not hasattr(m, p):
                continue
            v = getattr(m, p)
            try:
                setattr(m, p, v * s)
            except TypeError:
                setattr(m, p, [x * s for x in v])


def _scale_modifiers_affine(o, L):
    for m in o.modifiers:
        if m.type == 'ARRAY':
            m.constant_offset_displace = L @ Vector(m.constant_offset_displace)


def _transform_data(d, t, L, uniform, s):
    L4 = L.to_4x4()
    neg = L.determinant() < 0
    if t == 'MESH':
        d.transform(L4, shape_keys=True)
        if neg:
            d.flip_normals()
        d.update()
    elif t in ('CURVE', 'SURFACE'):
        d.transform(L4, shape_keys=True)
        if uniform:
            d.bevel_depth *= abs(s)
            d.extrude *= abs(s)
        d.update_tag()
    elif t == 'FONT':
        a = abs(s)
        d.size *= a
        d.offset_x *= a
        d.offset_y *= a
        d.extrude *= a
        d.bevel_depth *= a
        for tb in d.text_boxes:
            tb.x *= a
            tb.y *= a
            tb.width *= a
            tb.height *= a
    elif t == 'META':
        a = abs(s)
        for el in d.elements:
            el.co = L @ Vector(el.co)
            el.radius *= a
            el.size_x *= a
            el.size_y *= a
            el.size_z *= a
        d.resolution *= a
        d.render_resolution *= a
    elif t == 'LIGHT':
        a = abs(s)
        if hasattr(d, "shadow_soft_size"):
            d.shadow_soft_size *= a
        if d.type == 'AREA':
            d.size *= a
            d.size_y *= a
    elif t == 'CAMERA':
        d.display_size *= abs(s)


def _clean(M):
    R, _L = _polar(M)
    out = R.to_4x4()
    out.translation = M.translation
    return out


def apply_scale(context, objects):
    """Nesnelerin ölçek/eğikliğini verilerine aktarır; görünüm milim kaymaz.

    W = T R L  ->  W' = T R ,  veri' = L veri
    Paylaşılan veri: tüm kullanıcılar aynı L ile dönüşüyorsa bir kez dönüştürülür,
    yoksa (ya da set dışından kullanan varsa) kopya oluşturulur.
    """
    rep = ApplyReport()
    objs = sorted({o for o in objects}, key=lambda o: (depth(o), o.name))
    names = {o.name for o in objs}
    W = {o.name: o.matrix_world.copy() for o in objs}
    plan = {}                                      # ad -> (L, uniform, s)
    for o in objs:
        R, L = _polar(W[o.name])
        if _is_identity3(L):
            continue
        uniform = _is_uniform(L, 1e-6)
        diagonal = _is_diagonal3(L)
        s = L.median_scale if uniform else None
        if uniform and L.determinant() < 0:
            s = -abs(s)
        why = None
        if has_transform_anim(o):
            why = "animasyonlu"
        why = why or _data_ok(o, uniform, diagonal) or _mods_ok(o, uniform, diagonal)
        if why:
            rep.skip(o, why)
            continue
        plan[o.name] = (L, uniform, s)

    # ---- veri paylaşımı
    by_data = {}
    for o in objs:
        if o.name in plan and o.data is not None:
            by_data.setdefault(o.data, []).append(o)
    data_jobs = []                         # (veri, tür, L, uniform, s)
    for d, users in by_data.items():
        inside = sum(1 for o in objs if o.data == d)
        planned = len(users)
        outside = d.users - inside - (1 if d.use_fake_user else 0)
        groups = []
        for o in users:
            L = plan[o.name][0]
            for g in groups:
                if geom.matrices_close(g[0].to_4x4(), L.to_4x4(), 1e-6):
                    g[1].append(o)
                    break
            else:
                groups.append((L, [o]))
        keep_original = outside <= 0 and planned == inside
        for gi, (L, gusers) in enumerate(groups):
            if gi == 0 and keep_original:
                dd = d
            else:
                dd = d.copy()
                rep.copied += 1
                for o in gusers:
                    o.data = dd
            _L, uniform, s = plan[gusers[0].name]
            data_jobs.append((dd, gusers[0].type, L, uniform, s))
    for o in objs:                         # verisiz (empty) nesneler
        if o.name in plan and o.data is None:
            data_jobs.append((o, 'EMPTY', plan[o.name][0], plan[o.name][1], plan[o.name][2]))

    for d, t, L, uniform, s in data_jobs:
        if t == 'EMPTY':
            d.empty_display_size *= abs(s) if s else 1.0
            continue
        _transform_data(d, t, L, uniform, s)

    for name, (L, uniform, s) in plan.items():
        o = bpy.data.objects[name]
        if uniform:
            _scale_modifiers(o, abs(s))
        else:
            _scale_modifiers_affine(o, L)

    # ---- matrisler: üstten alta, her düzeyden sonra güncelle
    levels = {}
    for o in objs:
        levels.setdefault(depth(o), []).append(o)
    for lv in sorted(levels):
        for o in levels[lv]:
            par = o.parent
            if o.name not in plan and (par is None or par.name not in plan):
                continue                    # ne kendisi ne ebeveyni değişti
            target = _clean(W[o.name]) if o.name in plan else W[o.name]
            if par is not None and o.parent_type == 'OBJECT':
                if has_transform_anim(o):
                    # animasyonlu alt nesne: basis'e dokunma, ters matrisle telafi et
                    chain_old = W[o.name] @ o.matrix_basis.inverted_safe()
                    o.matrix_parent_inverse = par.matrix_world.inverted_safe() @ chain_old
                    continue
                if o.name in plan:
                    o.matrix_parent_inverse = _clean(o.matrix_parent_inverse)
            o.matrix_world = target
        context.view_layer.update()
    rep.applied = list(plan.keys())
    return rep
