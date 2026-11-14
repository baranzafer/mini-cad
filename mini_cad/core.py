"""Veri modeli, eğri okuma, yeniden hesaplama, önbellek ve canlı güncelleme."""

import json
import math
import os
import time
import traceback
import uuid

import bpy
import numpy as np
from bpy.app.handlers import persistent

from . import kernel
from .errors import CadError


# ================================================================ özellikler

def _on_setting_change(self, context):
    ob = self.id_data
    if isinstance(ob, bpy.types.Object):
        schedule(ob, preview=False)


def _poll_curve(self, obj):
    return obj.type == "CURVE"


def _poll_not_cad(self, obj):
    return not obj.cad.is_cad


def _poll_cad(self, obj):
    return obj.cad.is_cad


class MINICAD_CurveRef(bpy.types.PropertyGroup):
    obj: bpy.props.PointerProperty(name="Eğri", type=bpy.types.Object, poll=_poll_curve,
                                   update=_on_setting_change)


class MINICAD_SegRef(bpy.types.PropertyGroup):
    """Bir eğri objesindeki tek segment: spline sırası + segment sırası."""
    obj: bpy.props.PointerProperty(type=bpy.types.Object, poll=_poll_curve)
    spline: bpy.props.IntProperty()
    seg: bpy.props.IntProperty()


METHOD_ITEMS = [
    ("AUTO", "Otomatik", "Düzlemselse Düzlem, 4 kenarlıysa Coons, değilse Dolgu"),
    ("PLANE", "Düzlem", "Gerçek düzlem yüzü (döngü düzlemsel olmalı)"),
    ("COONS", "Coons", "4 kenarlı döngüde karşılıklı eğriler arası loft benzeri geçiş"),
    ("FILL", "Dolgu", "Her sayıda kenar için gergin zar benzeri yüzey"),
]


BLEND_ITEMS = [
    ("SHARP", "Keskin (G0)", "Yüzeyler ortak kenarda sadece buluşur; kenar / köşe çizgisi "
     "görünür (önceki davranış)"),
    ("TANGENT", "Teğet (G1)", "Yüzey komşu yüzlere ortak kenar boyunca teğet bağlanır; kenar "
     "çizgisi kaybolur, yüzeyler kaynaşır. 4 kenarlı yüzeyler mühendislik programlarındaki gibi "
     "sınır yüzeyi olarak kurulur (gergin; Teğet Ağırlığı ile dolgunluk ayarlanır)"),
    ("TANGENT_FREE", "Teğet – serbest dolgu", "Teğet (G1), yüzeyler serbest dolgu (plaka) "
     "olarak kurulur (v0.23 davranışı): dışa doğru balon gibi taşabilir"),
]

TANGENT_WEIGHT_DESC = ("Teğet (G1) birleşimde yüzeyin kenardan ne kadar \"uzun\" teğet "
                       "ayrıldığı (mühendislik programlarındaki teğet ağırlığı). 1: doğal "
                       "(gergin sınır yüzeyi); büyük: komşuya teğet daha uzun devam eder, yüzey "
                       "dolgunlaşır; küçük: yüzey içe gerilir. 4 kenarlı yüzeylerde geçerli")


class MINICAD_Patch(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(default="Yüzey")
    curves: bpy.props.CollectionProperty(type=MINICAD_CurveRef)  # obje modu: eğrinin tamamı
    segs: bpy.props.CollectionProperty(type=MINICAD_SegRef)      # edit modu: seçili segmentler
    method: bpy.props.EnumProperty(name="Yöntem", items=METHOD_ITEMS, default="AUTO",
                                   update=_on_setting_change)
    enabled: bpy.props.BoolProperty(name="Etkin", default=True, update=_on_setting_change)
    blend: bpy.props.EnumProperty(
        name="Birleşim", description="Bu yüzeyin komşu yüzlerle ortak kenarlarda birleşimi. "
        "Kaynaşan yüzey Dolgu olarak komşularına uyar; düzlemsel yüzler, Düzlem ve Coons "
        "sabit kalır",
        items=[("BODY", "Gövde ayarı", "Gövdenin Yüzey Birleşimi ayarını kullan")] + BLEND_ITEMS,
        default="BODY", update=_on_setting_change)
    own_weight: bpy.props.BoolProperty(
        name="Kendi Teğet Ağırlığı", description="Gövdenin Teğet Ağırlığı yerine bu yüzeye özel "
        "değer kullan", default=False, update=_on_setting_change)
    tangent_weight: bpy.props.FloatProperty(
        name="Teğet Ağırlığı", description=TANGENT_WEIGHT_DESC, default=1.0, min=0.2, max=2.0,
        step=5, precision=2, update=_on_setting_change)
    info: bpy.props.StringProperty(default="")
    ok: bpy.props.BoolProperty(default=True)


FEATURE_KINDS = [
    ("FILLET", "Fillet", "Yuvarlatılmış bevel (rolling-ball)"),
    ("CHAMFER", "Pah", "Düz pah"),
]


def _poll_scene_tool(self, obj):
    return obj.type == "MESH" and obj != self.minicad_target


def _poll_tool(self, obj):
    return obj.type == "MESH" and obj != self.id_data


FEATURE_OPS = [("BEVEL", "Bevel", ""), ("BOOLEAN", "Boolean", "")]
BOOL_TYPES = [
    ("CUT", "Çıkar", "Aracın hacmini gövdeden çıkarır (trim / cep / kesim)"),
    ("UNION", "Birleştir", "Aracı gövdeye ekler"),
    ("INTERSECT", "Kesişim", "Sadece gövdeyle aracın ortak hacmi kalır"),
]
EDGE_MODES = [
    ("SECTION", "Kesişim kenarları", "Sadece aracın gövde yüzeyini kestiği çizgiler"),
    ("ALL", "Tüm yeni kenarlar", "Araçtan gelen bütün kenarlar (cebin iç köşeleri dahil)"),
]


def _on_bevel_param(self, context):
    """Fillet ölçüsü/türü: sürüklerken hayalet önizleme, bırakınca gerçek fillet."""
    ob = self.id_data
    if isinstance(ob, bpy.types.Object):
        schedule(ob, preview=bool(ob.cad.preview))


class MINICAD_GeoEdge(bpy.types.PropertyGroup):
    """Gövdenin (boolean'ın oluşturduğu) bir kenarına kalıcı referans. Kenar indeksle değil
    geometrik tanımla (9 örnek nokta + boy) tutulur; her tam hesapta güncellenir."""
    id: bpy.props.StringProperty()
    src: bpy.props.StringProperty()     # kenarı oluşturan boolean'ın uid'i
    data: bpy.props.StringProperty()    # JSON {"s": [[x,y,z]*9], "len": L}


class MINICAD_Feature(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty(default="Bevel")
    uid: bpy.props.StringProperty()
    geo_edges: bpy.props.CollectionProperty(type=MINICAD_GeoEdge)
    op: bpy.props.EnumProperty(items=FEATURE_OPS, default="BEVEL")
    bool_type: bpy.props.EnumProperty(name="Boolean", items=BOOL_TYPES, default="CUT",
                                      update=_on_setting_change)
    tool: bpy.props.PointerProperty(name="Araç", type=bpy.types.Object, poll=_poll_tool,
                                    update=_on_setting_change)
    edge_size: bpy.props.FloatProperty(
        name="Yeni Kenar Fillet", description="Boolean'ın oluşturduğu sert kenarları bu "
        "yarıçapla yuvarlar (0 = yuvarlama yok)", default=0.0, min=0.0, soft_max=0.05,
        precision=4, unit="LENGTH", update=_on_setting_change)
    edge_mode: bpy.props.EnumProperty(name="Hangi Kenarlar", items=EDGE_MODES,
                                      default="SECTION", update=_on_setting_change)
    mirror_tool: bpy.props.BoolProperty(
        name="Aracı Aynala", description="Gövdede ayna açıksa aracı da aynalı uygular",
        default=True, update=_on_setting_change)
    kind: bpy.props.EnumProperty(name="Tür", items=FEATURE_KINDS, default="FILLET",
                                 update=_on_bevel_param)
    size: bpy.props.FloatProperty(name="Ölçü", default=0.002, min=0.0, soft_max=0.05,
                                  precision=4, unit="LENGTH", update=_on_bevel_param)
    enabled: bpy.props.BoolProperty(name="Etkin", default=True, update=_on_setting_change)
    segs: bpy.props.CollectionProperty(type=MINICAD_SegRef)
    info: bpy.props.StringProperty(default="")
    ok: bpy.props.BoolProperty(default=True)


def _on_bevel_edit(self, context):
    ob = self.id_data
    if isinstance(ob, bpy.types.Object):
        ob.cad.bevel_dirty = True


class MINICAD_BevelEdge(bpy.types.PropertyGroup):
    """Kenar havuzundaki tek kenar (tek bezier segmenti) ve kendi bevel değeri."""
    obj: bpy.props.PointerProperty(type=bpy.types.Object, poll=_poll_curve)
    spline: bpy.props.IntProperty()
    seg: bpy.props.IntProperty()
    kind: bpy.props.EnumProperty(name="Tür", items=FEATURE_KINDS, default="FILLET",
                                 update=_on_bevel_edit)
    size: bpy.props.FloatProperty(name="Ölçü", default=0.002, min=0.0, soft_max=0.05,
                                  precision=4, unit="LENGTH", update=_on_bevel_edit)
    checked: bpy.props.BoolProperty(name="Seç", default=False)
    ok: bpy.props.BoolProperty(default=True)
    applied: bpy.props.BoolProperty(default=False)
    info: bpy.props.StringProperty(default="")
    max_ok: bpy.props.FloatProperty(default=-1.0, unit="LENGTH")
    suggested: bpy.props.FloatProperty(default=-1.0, unit="LENGTH")


CONSTRAINT_KINDS = [
    ("AXIS", "Eksen", "Kenar bir dünya eksenine paralel"),
    ("PARALLEL", "Paralel", ""), ("PERP", "Dik", ""), ("COLLINEAR", "Doğrusal", ""),
    ("EQUAL", "Eşit", "Eşit boy"), ("DISTANCE", "Uzunluk", ""), ("ANGLE", "Açı", ""),
    ("FIX", "Sabit", ""), ("COINCIDENT", "Çakışık", ""), ("SYMMETRIC", "Simetrik", ""),
    ("TANGENT", "Teğet", ""),
    ("CONCENTRIC", "Eş merkezli", "İki yay / daire aynı merkezde"),
    ("RADIUS", "Yarıçap", "Yay / daire yarıçapı (dairede çap gösterilir)"),
    ("SMOOTH", "Pürüzsüz (G2)", "Teğet + birleşimde eğrilik eşit"),
    ("SYMLINE", "Simetrik (çizgi)", "İki nokta bir doğruya göre simetrik"),
    ("PTLINE", "Nokta-doğru", "Noktanın doğruya uzaklığı"),
    ("LINEDIST", "Doğru-doğru", "Paralel iki doğru arası uzaklık"),
    ("CENTERDIST", "Merkez mesafesi", "Yay / daire merkezinden yay, nokta ya da doğruya"),
]


def _on_constraint_change(self, context):
    try:
        from . import constraints
        constraints.request_solve(force=True)
    except Exception:
        pass


class MINICAD_CRef(bpy.types.PropertyGroup):
    """Kısıt referansı: bir eğri objesindeki segment (point=False) ya da nokta."""
    obj: bpy.props.PointerProperty(type=bpy.types.Object, poll=_poll_curve)
    spline: bpy.props.IntProperty()
    index: bpy.props.IntProperty()
    point: bpy.props.BoolProperty(default=False)


class MINICAD_Constraint(bpy.types.PropertyGroup):
    kind: bpy.props.EnumProperty(items=CONSTRAINT_KINDS, default="PARALLEL")
    refs: bpy.props.CollectionProperty(type=MINICAD_CRef)
    enabled: bpy.props.BoolProperty(name="Etkin", default=True, update=_on_constraint_change)
    length: bpy.props.FloatProperty(name="Uzunluk", default=0.01, min=0.0, precision=4,
                                    unit="LENGTH", update=_on_constraint_change)
    angle: bpy.props.FloatProperty(name="Açı", default=math.radians(90), min=0.0,
                                   max=math.pi, subtype="ANGLE",
                                   update=_on_constraint_change)
    axis: bpy.props.IntProperty(default=0)
    offset: bpy.props.FloatProperty(default=0.0)
    pos: bpy.props.FloatVectorProperty(size=3)     # FIX: objenin yerel koordinatı
    auto: bpy.props.BoolProperty(default=False)
    driven: bpy.props.BoolProperty(
        name="Referans", description="Referans ölçü: şekli yönetmez, yalnızca ölçüp gösterir "
        "(Inventor'daki driven dimension)", default=False, update=_on_constraint_change)
    ok: bpy.props.BoolProperty(default=True)
    info: bpy.props.StringProperty(default="")


def _on_link_change(self, context):
    try:
        from . import links
        links.request(force=True)
    except Exception:
        pass


class MINICAD_Link(bpy.types.PropertyGroup):
    """Tel kafes eğrisindeki ilişkisel geometri (Inventor gibi düzenlenebilir):
      RPAT / CPAT  desen: kaynak spline'lar (src) ve kopyalar (dst, örnek sırasıyla)
      PROJ         yansıtma: kaynak segment (src_obj, src = "spline:segment") → dst spline
    Kaynak değişince ya da değerler düzenlenince kopyalar yeniden üretilir (links.py)."""
    kind: bpy.props.EnumProperty(items=[("RPAT", "Dikdörtgen desen", ""),
                                        ("CPAT", "Dairesel desen", ""),
                                        ("PROJ", "Yansıtma", "")], default="RPAT")
    enabled: bpy.props.BoolProperty(name="Etkin", default=True, update=_on_link_change)
    src: bpy.props.StringProperty()          # "3,4" ya da PROJ: "spline:segment"
    src_obj: bpy.props.PointerProperty(type=bpy.types.Object, poll=_poll_curve)
    dst: bpy.props.StringProperty()          # "7,8,9,10"
    n1: bpy.props.IntProperty(name="Adet", default=3, min=1, max=200, update=_on_link_change)
    n2: bpy.props.IntProperty(name="Adet 2", default=1, min=1, max=200, update=_on_link_change)
    s1: bpy.props.FloatProperty(name="Aralık", default=1.0, unit="LENGTH",
                                update=_on_link_change)
    s2: bpy.props.FloatProperty(name="Aralık 2", default=1.0, unit="LENGTH",
                                update=_on_link_change)
    dir1: bpy.props.FloatVectorProperty(size=3)
    dir2: bpy.props.FloatVectorProperty(size=3)
    center: bpy.props.FloatVectorProperty(size=3)
    axis: bpy.props.FloatVectorProperty(size=3, default=(0.0, 0.0, 1.0))
    angle: bpy.props.FloatProperty(name="Açı", default=math.radians(360.0), subtype="ANGLE",
                                   update=_on_link_change)
    plane_o: bpy.props.FloatVectorProperty(size=3)
    plane_n: bpy.props.FloatVectorProperty(size=3, default=(0.0, 0.0, 1.0))
    info: bpy.props.StringProperty(default="")


class MINICAD_ObjectProps(bpy.types.PropertyGroup):
    is_cad: bpy.props.BoolProperty(default=False)
    links: bpy.props.CollectionProperty(type=MINICAD_Link)   # tel kafes eğrilerinde
    constraints: bpy.props.CollectionProperty(type=MINICAD_Constraint)  # tel kafes eğrilerinde
    curves: bpy.props.CollectionProperty(type=MINICAD_CurveRef)  # v0.1 uyumluluğu
    patches: bpy.props.CollectionProperty(type=MINICAD_Patch)
    active_patch: bpy.props.IntProperty(default=0)
    features: bpy.props.CollectionProperty(type=MINICAD_Feature)
    active_bevel: bpy.props.IntProperty(default=0)
    active_bool: bpy.props.IntProperty(default=0)
    active_order: bpy.props.IntProperty(default=0)
    use_mirror: bpy.props.BoolProperty(name="Simetri", default=True,
                                       update=_on_setting_change)
    use_booleans: bpy.props.BoolProperty(name="Boolean", default=True,
                                         update=_on_setting_change)
    use_bevels: bpy.props.BoolProperty(name="Fillet", default=True,
                                       update=_on_setting_change)
    bevels: bpy.props.CollectionProperty(type=MINICAD_BevelEdge)
    bevel_dirty: bpy.props.BoolProperty(default=False)
    bulk_size: bpy.props.FloatProperty(
        name="Değer", default=0.002, min=0.0, soft_max=0.05, precision=4, unit="LENGTH")
    bulk_kind: bpy.props.EnumProperty(name="Tür", items=FEATURE_KINDS, default="FILLET")
    show_bevel_overlay: bpy.props.BoolProperty(
        name="Kenar Numaralarını Göster", default=True)
    analysis: bpy.props.StringProperty(default="")
    default_bevel: bpy.props.FloatProperty(
        name="Varsayılan Bevel", description="Seçim modunda B ile eklenen bevelin başlangıç ölçüsü",
        default=0.002, min=0.0, soft_max=0.05, precision=4, unit="LENGTH")
    corner_mode: bpy.props.EnumProperty(
        name="Köşe Modu",
        description="Farklı bevel'ler aynı köşede buluştuğunda nasıl hesaplanacağı",
        items=[
            ("JOINT", "Birlikte (köşe yaması)", "Hepsi tek işlemde; köşede Inventor'daki gibi "
             "üç kenarlı bir köşe yaması oluşur"),
            ("TRANSITION", "Yumuşak geçiş", "Köşede buluşan küçük fillet'lerin yarıçapı köşeye "
             "yaklaştıkça büyüğe yükselir"),
            ("HISTORY", "Oluşturma sırası", "Bevel'ler listedeki sırayla uygulanır, sonraki "
             "öncekinin yüzeyi boyunca yuvarlanır"),
            ("BIG_FIRST", "Büyükten küçüğe", "Önce büyük yarıçaplar, küçükler onlara kaynaşır"),
            ("SMALL_FIRST", "Küçükten büyüğe", "Önce küçük yarıçaplar"),
            ("EDGEWISE", "Kenar kenar", "Her kenar tek başına sırayla; köşe yaması oluşmaz, "
             "fillet'ler birbirini keser"),
        ],
        default="JOINT", update=_on_setting_change)
    smooth_corners: bpy.props.BoolProperty(
        name="Pürüzsüz Köşe Yaması",
        description="Fillet'lerin buluştuğu köşe yamasını komşu fillet'lere teğet (G1), minimum "
        "bükülmeli bir yüzeyle yeniden kurar",
        default=True, update=_on_setting_change)
    transition_factor: bpy.props.FloatProperty(
        name="Geçiş Uzunluğu", description="Yarıçap geçişinin uzunluğu, köşedeki büyük yarıçapın "
        "katı olarak (kenar uzunluğunun en fazla %45'i)",
        default=3.0, min=0.5, soft_max=10.0, update=_on_setting_change)
    preview_bevel: bpy.props.BoolProperty(
        name="Önizlemede Bevel", description="Kapalıysa sürüklerken bevel atlanır (daha akıcı)",
        default=False)
    ghost_bevel: bpy.props.BoolProperty(
        name="Hayalet Fillet", description="Sürüklerken (ya da fillet ölçüsünü değiştirirken) "
        "gerçek fillet yerine hızlı, yarı saydam bir fillet şeridi göster; bırakınca gerçek "
        "fillet hesaplanır", default=True)

    live: bpy.props.BoolProperty(name="Canlı Güncelle", default=True)
    preview: bpy.props.BoolProperty(
        name="Sürüklerken Önizleme",
        description="Eğri oynatılırken kaba hesapla, bırakınca tam kaliteye geç", default=True)
    make_solid: bpy.props.BoolProperty(
        name="Katı Gövde", description="Kapalı kabuğu içi dolu katıya çevir", default=True,
        update=_on_setting_change)
    surface_blend: bpy.props.EnumProperty(
        name="Yüzey Birleşimi", description="Yüzeylerin ortak kenarlarda nasıl birleşeceği. "
        "Teğet: eğri yüzeyler komşularına kaynaşır (kenar çizgisi kaybolur); "
        "düzlemsel yüzler sabit kalır. Yüzey başına ayrıca değiştirilebilir",
        items=BLEND_ITEMS, default="SHARP", update=_on_setting_change)
    tangent_weight: bpy.props.FloatProperty(
        name="Teğet Ağırlığı", description=TANGENT_WEIGHT_DESC, default=1.0, min=0.2, max=2.0,
        step=5, precision=2, update=_on_setting_change)

    mirror_x: bpy.props.BoolProperty(name="X", default=False, update=_on_setting_change)
    mirror_y: bpy.props.BoolProperty(name="Y", default=False, update=_on_setting_change)
    mirror_z: bpy.props.BoolProperty(name="Z", default=False, update=_on_setting_change)
    mirror_center: bpy.props.PointerProperty(
        name="Ayna Merkezi", description="Boşsa dünya merkezi; bir Empty seçilirse onun konumu "
        "ve yönü kullanılır", type=bpy.types.Object, poll=_poll_not_cad,
        update=_on_setting_change)

    lin_defl: bpy.props.FloatProperty(
        name="Doğrusal Sapma", description="Üçgenleme hassasiyeti (küçük = daha yoğun)",
        default=0.0003, min=1e-6, soft_max=0.01, precision=5, unit="LENGTH",
        update=_on_setting_change)
    ang_defl: bpy.props.FloatProperty(
        name="Açısal Sapma", default=math.radians(5), min=math.radians(0.5),
        max=math.radians(45), subtype="ANGLE", update=_on_setting_change)
    join_tol: bpy.props.FloatProperty(
        name="Birleşme Toleransı", description="Eğri uçlarının çakışık sayılacağı mesafe",
        default=0.001, min=1e-7, soft_max=0.05, precision=5, unit="LENGTH",
        update=_on_setting_change)
    status: bpy.props.StringProperty(default="")


# ================================================================ eğri okuma

def _seg_count(sp):
    n = len(sp.bezier_points) if sp.type == "BEZIER" else len(sp.points)
    return n if sp.use_cyclic_u else n - 1


def _poly_settings():
    try:
        sc = bpy.context.scene
        return bool(sc.minicad_poly_smooth), math.cos(sc.minicad_poly_corner)
    except Exception:
        return True, math.cos(math.radians(30.0))


def _arc_len(chord, t, d):
    """Çember yayını birebir veren tutamaç boyu (düzde kiriş/3)."""
    c = max(-1.0, min(1.0, abs(t.dot(d))))
    return chord / (3.0 * max(0.5, math.cos(math.acos(c) / 2.0) ** 2))


def _poly_tangent(pts, j, n, cyclic, mw, cos_lim):
    """Poly eğrinin j. noktasındaki pürüzsüz teğet yönü. Uç nokta veya köşeyse None."""
    if not cyclic and (j == 0 or j == n - 1):
        return None
    p = mw @ pts[j].co.xyz
    q = mw @ pts[(j - 1) % n].co.xyz
    r = mw @ pts[(j + 1) % n].co.xyz
    u, v = p - q, r - p
    if u.length < 1e-12 or v.length < 1e-12:
        return None
    if u.normalized().dot(v.normalized()) < cos_lim:
        return None                       # gerçek köşe: keskin kalsın
    # 3 noktadan geçen çemberin teğeti: düzensiz aralıklarda da yaylar için kesin
    t = u * v.length_squared + v * u.length_squared
    return t.normalized() if t.length > 1e-15 else None


def _spline_segment(ob, si, sp, i, mw):
    """Spline'ın i. segmentini dünya koordinatında döndürür (None = sıfır uzunluk)."""
    tag = (ob.name, si)
    ref = (ob.name, si, i)
    if sp.type == "BEZIER":
        bp = sp.bezier_points
        n = len(bp)
        a, b = bp[i], bp[(i + 1) % n]
        p = [mw @ a.co, mw @ a.handle_right, mw @ b.handle_left, mw @ b.co]
        return {"p": p, "tag": tag, "ref": ref} if (p[3] - p[0]).length > 1e-9 else None
    if sp.type == "POLY":
        pts = sp.points
        n = len(pts)
        j = (i + 1) % n
        a, b = mw @ pts[i].co.xyz, mw @ pts[j].co.xyz
        L = (b - a).length
        if L <= 1e-9:
            return None
        smooth, cos_lim = _poly_settings()
        if smooth and n > 2:
            ta = _poly_tangent(pts, i, n, sp.use_cyclic_u, mw, cos_lim)
            tb = _poly_tangent(pts, j, n, sp.use_cyclic_u, mw, cos_lim)
            if ta is not None or tb is not None:
                d = (b - a) / L
                da = ta if ta is not None else d
                db = tb if tb is not None else d
                p = [a, a + da * _arc_len(L, da, d), b - db * _arc_len(L, db, d), b]
                return {"p": p, "tag": tag, "ref": ref}
        return {"p": [a, b], "tag": tag, "ref": ref}
    raise CadError(f"'{ob.name}': NURBS eğriler henüz desteklenmiyor")


def sample_segment(p, samples=24):
    """Segment kontrol noktalarından (K,3) numpy örnek dizisi üretir."""
    import numpy as np
    if len(p) == 2:
        return np.array([tuple(p[0]), tuple(p[1])], dtype=np.float64)
    p0, p1, p2, p3 = (np.array(tuple(v), dtype=np.float64) for v in p)
    t = np.linspace(0.0, 1.0, samples)[:, None]
    u = 1.0 - t
    return u ** 3 * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t ** 3 * p3


def collect_segments(curve_objs):
    """Obje modu: eğri objelerinin bütün segmentleri."""
    segs = []
    for ob in curve_objs:
        mw = ob.matrix_world
        for si, sp in enumerate(ob.data.splines):
            for i in range(_seg_count(sp)):
                s = _spline_segment(ob, si, sp, i, mw)
                if s is not None:
                    segs.append(s)
    return segs


def collect_segrefs(refs):
    """Edit modu: kayıtlı (obje, spline, segment) referansları."""
    segs = []
    for r in refs:
        ob = r.obj
        if ob is None:
            raise CadError("Yüzeyin bağlı olduğu eğri objesi silinmiş")
        splines = ob.data.splines
        if r.spline >= len(splines) or r.seg >= _seg_count(splines[r.spline]):
            raise CadError(f"'{ob.name}' içinde eğri yapısı değişmiş (spline/nokta silinmiş). "
                           "Bu yüzeyi silip yeniden ekle")
        s = _spline_segment(ob, r.spline, splines[r.spline], r.seg, ob.matrix_world)
        if s is not None:
            segs.append(s)
    return segs


def selected_segment_refs(curve_objs):
    """Edit modunda iki uç noktası da seçili olan segmentler: [(obj, spline, seg)]."""
    refs = []
    for ob in curve_objs:
        for si, sp in enumerate(ob.data.splines):
            if sp.type == "BEZIER":
                sel = [p.select_control_point for p in sp.bezier_points]
            elif sp.type == "POLY":
                sel = [p.select for p in sp.points]
            else:
                continue
            n = len(sel)
            for i in range(_seg_count(sp)):
                if sel[i] and sel[(i + 1) % n]:
                    refs.append((ob, si, i))
    return refs


def _ref_key(ref):
    ob, si, i = ref
    return (ob.name, si, i)


def _ref_segment(ref):
    ob, si, i = ref
    splines = ob.data.splines
    if si >= len(splines) or i >= _seg_count(splines[si]):
        return None
    return _spline_segment(ob, si, splines[si], i, ob.matrix_world)


def patch_refs(patch):
    """Bir yüzeyin segmentlerini (obj, spline, seg) listesi olarak döndürür."""
    if len(patch.segs):
        return [(r.obj, r.spline, r.seg) for r in patch.segs if r.obj is not None]
    refs = []
    for r in patch.curves:
        ob = r.obj
        if ob is None:
            continue
        for si, sp in enumerate(ob.data.splines):
            refs += [(ob, si, i) for i in range(_seg_count(sp))]
    return refs


def complete_loop(sel_refs, pool_refs, tol):
    """Seçim kapalı değilse, uçlarını mevcut yüzeylerin kenarları üzerinden en kısa yolla
    birleştirir. Tam döngünün referanslarını ve eklenen segment sayısını döndürür."""
    nodes = []

    def node(p):
        for idx, q in enumerate(nodes):
            if (q - p).length <= tol:
                return idx
        nodes.append(p.copy())
        return len(nodes) - 1

    def edge(ref):
        s = _ref_segment(ref)
        if s is None:
            return None
        p = s["p"]
        length = sum((p[k + 1] - p[k]).length for k in range(len(p) - 1))
        return node(p[0]), node(p[-1]), length

    sel_keys = {_ref_key(r) for r in sel_refs}
    degree = {}
    for r in sel_refs:
        e = edge(r)
        if e is None:
            continue
        for n in e[:2]:
            degree[n] = degree.get(n, 0) + 1
    ends = [n for n, d in degree.items() if d == 1]
    if not ends:
        return list(sel_refs), 0
    if len(ends) != 2 or any(d > 2 for d in degree.values()):
        raise CadError("Seçim tek parça bir zincir değil. Yüzeyin kenarlarını sırayla seç")

    # Yalnızca mevcut yüzeylerin kenarları kullanılır; seçimin iç noktalarından geçilmez.
    blocked = {n for n in degree if n not in ends}
    adj = {}
    seen = set()
    for r in pool_refs:
        k = _ref_key(r)
        if k in sel_keys or k in seen:
            continue
        seen.add(k)
        e = edge(r)
        if e is None:
            continue
        a, b, w = e
        if a == b or a in blocked or b in blocked:
            continue
        adj.setdefault(a, []).append((b, w, r))
        adj.setdefault(b, []).append((a, w, r))

    import heapq
    start, goal = ends
    dist = {start: 0.0}
    prev = {}
    heap = [(0.0, start)]
    while heap:
        d, n = heapq.heappop(heap)
        if n == goal:
            break
        if d > dist.get(n, float("inf")):
            continue
        for m, w, r in adj.get(n, ()):
            nd = d + w
            if nd < dist.get(m, float("inf")):
                dist[m] = nd
                prev[m] = (n, r)
                heapq.heappush(heap, (nd, m))
    if goal not in prev:
        raise CadError("Seçim kapalı değil ve komşu yüzeylerin kenarlarıyla da "
                       "tamamlanamadı. Uçların mevcut bir yüzeyin köşelerine değmeli")
    path = []
    n = goal
    while n != start:
        n, r = prev[n]
        path.append(r)
    return list(sel_refs) + path, len(path)


def patch_segments(patch):
    if len(patch.segs):
        return collect_segrefs(patch.segs)
    return collect_segments([r.obj for r in patch.curves if r.obj is not None])


def chain_loop(segs, tol):
    """Segmentleri uç uca sıralar, kapalı döngü olduğunu doğrular ve uçları kaynaklar."""
    if len(segs) < 2:
        raise CadError("Kapalı bir sınır için en az 2 kenar gerekli")
    remaining = segs[1:]
    chain = [segs[0]]
    end = segs[0]["p"][-1]
    while remaining:
        found = None
        for i, s in enumerate(remaining):
            if (s["p"][0] - end).length <= tol:
                found = (i, False)
                break
            if (s["p"][-1] - end).length <= tol:
                found = (i, True)
                break
        if found is None:
            raise CadError("Eğriler kapalı döngü oluşturmuyor. Uçları snap ile birleştir "
                           f"(açık uç: {end.x:.4f}, {end.y:.4f}, {end.z:.4f})")
        i, rev = found
        s = remaining.pop(i)
        if rev:
            s = dict(s, p=list(reversed(s["p"])))
        chain.append(s)
        end = s["p"][-1]
        if remaining and (end - chain[0]["p"][0]).length <= tol:
            raise CadError(f"Döngü kapandı ama {len(remaining)} fazla segment seçili. "
                           "Sadece döngünün noktalarını seç")
    gap = (chain[-1]["p"][-1] - chain[0]["p"][0]).length
    if gap > tol:
        raise CadError(f"Döngü kapanmıyor, son boşluk: {gap:.5f}")
    n = len(chain)
    for k in range(n):
        a, b = chain[k]["p"], chain[(k + 1) % n]["p"]
        m = (a[-1] + b[0]) * 0.5
        a[-1] = m.copy()
        b[0] = m.copy()
    return chain


def chain_loops(segs, tol):
    """Segmentleri bir ya da daha çok kapalı döngüye ayırır (delikli yüzey: dış sınır +
    delikler). Her döngü chain_loop ile aynı biçimde sıralanır ve uçları kaynaklanır."""
    if len(segs) < 2:
        raise CadError("Kapalı bir sınır için en az 2 kenar gerekli")
    remaining = list(segs)
    loops = []
    while remaining:
        chain = [remaining.pop(0)]
        start = chain[0]["p"][0]
        end = chain[0]["p"][-1]
        while (end - start).length > tol:
            found = None
            for i, s_ in enumerate(remaining):
                if (s_["p"][0] - end).length <= tol:
                    found = (i, False)
                    break
                if (s_["p"][-1] - end).length <= tol:
                    found = (i, True)
                    break
            if found is None:
                raise CadError("Eğriler kapalı döngü oluşturmuyor. Uçları snap ile birleştir "
                               f"(açık uç: {end.x:.4f}, {end.y:.4f}, {end.z:.4f})")
            i, rev = found
            s_ = remaining.pop(i)
            if rev:
                s_ = dict(s_, p=list(reversed(s_["p"])))
            chain.append(s_)
            end = s_["p"][-1]
        if len(chain) < 2 and (chain[0]["p"][-1] - chain[0]["p"][0]).length > tol:
            raise CadError("Kapalı bir sınır için en az 2 kenar gerekli")
        n = len(chain)
        for k in range(n):
            a, b = chain[k]["p"], chain[(k + 1) % n]["p"]
            m = (a[-1] + b[0]) * 0.5
            a[-1] = m.copy()
            b[0] = m.copy()
        loops.append(chain)
    return loops


def _loop_poly(chain):
    pts = []
    for s_ in chain:
        P = [np.array(tuple(v), dtype=np.float64) for v in s_["p"]]
        if len(P) == 4:
            for t in np.linspace(0.0, 1.0, 9)[:-1]:
                u = 1.0 - t
                pts.append(u ** 3 * P[0] + 3 * u * u * t * P[1] + 3 * u * t * t * P[2] +
                           t ** 3 * P[3])
        else:
            pts.append(P[0])
    return np.array(pts)


def _inside(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            xc = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if xc > x:
                inside = not inside
    return inside


def nest_loops(loops):
    """Döngüleri iç içeliğe göre gruplar: [(dış döngü, [delikler])]. Çift derinlik dış
    sınır, tek derinlik delik (deliğin içindeki döngü yeniden ayrı yüzey: adacık).
    Birden çok döngü aynı düzlemde olmalı."""
    if len(loops) == 1:
        return [(loops[0], [])]
    polys = [_loop_poly(c) for c in loops]
    P = np.vstack(polys)
    c = P.mean(axis=0)
    size = float(np.linalg.norm(P.max(axis=0) - P.min(axis=0)))
    _, sv, vt = np.linalg.svd(P - c)
    n = vt[2]
    if float(np.abs((P - c) @ n).max()) > 1e-5 * (1.0 + size):
        raise CadError("Birden çok döngü seçili ama aynı düzlemde değiller (delikli yüzey "
                       "düzlemsel olmalı). Döngüleri ayrı yüzey olarak ekle")
    u, v = vt[0], vt[1]
    flat = [np.c_[(q - c) @ u, (q - c) @ v] for q in polys]

    def area(f):
        x, y = f[:, 0], f[:, 1]
        return 0.5 * abs(float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))
    areas = [area(f) for f in flat]
    k = len(loops)
    contains = [[j for j in range(k) if j != i and areas[j] > areas[i] and
                 _inside(flat[i][0], flat[j])] for i in range(k)]
    depth = [len(cs) for cs in contains]
    groups = []
    outer_of = {}
    for i in sorted(range(k), key=lambda i: depth[i]):
        if depth[i] % 2 == 0:
            outer_of[i] = len(groups)
            groups.append((loops[i], []))
        else:
            par = min(contains[i], key=lambda j: areas[j])
            if par in outer_of:
                groups[outer_of[par]][1].append(loops[i])
    return groups


def _dir(v):
    l = v.length
    return None if l < 1e-12 else (v[0] / l, v[1] / l, v[2] / l)


def _end_tangent(p):
    return _dir(p[-1] - p[-2]) or _dir(p[-1] - p[0])


def _start_tangent(p):
    return _dir(p[1] - p[0]) or _dir(p[-1] - p[0])


def split_sides(chain, corner_deg=20.0):
    """Döngüyü köşe noktalarından 'kenar'lara böler (teğeti kırılan yerler köşe sayılır)."""
    n = len(chain)
    lim = math.cos(math.radians(corner_deg))
    corners = []
    for k in range(n):
        a = _end_tangent(chain[k - 1]["p"])
        b = _start_tangent(chain[k]["p"])
        dot = 1.0 if a is None or b is None else a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
        corners.append(dot < lim)
    if not any(corners):
        return [[s] for s in chain]
    k = corners.index(True)
    chain = chain[k:] + chain[:k]
    corners = corners[k:] + corners[:k]
    sides = []
    for s, c in zip(chain, corners):
        if c:
            sides.append([s])
        else:
            sides[-1].append(s)
    if len(sides) != 4 and n == 4:
        return [[s] for s in chain]
    return sides


def _geom_key(chain):
    return tuple(round(c, 7) for s in chain for v in s["p"] for c in v)


# ================================================================ mesh yazma

def fmt_len(v):
    try:
        us = bpy.context.scene.unit_settings
        system = us.system if us.system != "NONE" else "METRIC"
        return bpy.utils.units.to_string(system, "LENGTH", v * us.scale_length, precision=3)
    except Exception:
        return f"{v * 1000:.3f} mm"


def _to_local(obj, verts, normals):
    """Gövde dünya koordinatında hesaplanır; mesh objenin kendi uzayına yazılır. Böylece
    gövde objesi taşınınca (tel kafesiyle birlikte) mesh kaymaz."""
    V = np.asarray(verts, dtype=np.float64).reshape(-1, 3)
    N = None if normals is None else np.asarray(normals, dtype=np.float64).reshape(-1, 3)
    M = obj.matrix_world
    if all(abs(M[i][j] - (1.0 if i == j else 0.0)) < 1e-12 for i in range(4) for j in range(4)):
        return V, N
    inv = np.array(M.inverted(), dtype=np.float64)
    V = V @ inv[:3, :3].T + inv[:3, 3]
    if N is not None:
        N = N @ np.array(M.to_3x3(), dtype=np.float64)
        ln = np.linalg.norm(N, axis=1)
        N = N / np.where(ln < 1e-12, 1.0, ln)[:, None]
    return V, N


def wire_objects(props):
    """Gövdeyi tanımlayan tel kafes eğri objeleri (araçlar ve ayna merkezi hariç)."""
    out = []
    for patch in props.patches:
        for r in list(patch.curves) + list(patch.segs):
            if r.obj is not None and r.obj not in out:
                out.append(r.obj)
    for f in props.features:
        for r in f.segs:
            if r.obj is not None and r.obj not in out:
                out.append(r.obj)
    return out


def link_wires(obj):
    """Tel kafes eğrilerini gövdeye bağlar (parent): gövde taşınınca tel kafes de gider.
    Başka bir objeye zaten bağlı eğrilere dokunulmaz."""
    for w in wire_objects(obj.cad):
        if w.type != "CURVE" or w.parent is not None or w == obj or w.mode != "OBJECT":
            continue
        # gövde de bu eğriye bağlıysa döngü oluşmasın
        p = obj.parent
        cyclic = False
        while p is not None:
            if p == w:
                cyclic = True
                break
            p = p.parent
        if cyclic:
            continue
        mw = w.matrix_world.copy()
        w.parent = obj
        w.matrix_world = mw


def write_mesh(me, verts, tris, normals):
    verts = np.asarray(verts, dtype=np.float64).reshape(-1, 3).tolist()
    tris = np.asarray(tris, dtype=np.int64).reshape(-1, 3).tolist()
    if normals is not None:
        normals = np.asarray(normals, dtype=np.float64).reshape(-1, 3).tolist()
    me.clear_geometry()
    me.from_pydata(verts, [], tris)
    me.update()
    try:
        me.shade_smooth()
    except Exception:
        me.polygons.foreach_set("use_smooth", [True] * len(me.polygons))
    if normals is not None and len(normals) == len(verts):
        try:
            me.normals_split_custom_set_from_vertices(normals)
        except Exception:
            traceback.print_exc()


# ================================================================ yeniden hesaplama

def weld_all(segs, tol):
    """Bütün yüzeylerin segment uçlarını birlikte kaynaklar: tol içindeki uçlar tek bir
    ortak noktaya (ortalamaya) taşınır. Böylece komşu yüzeyler aynı köşeyi paylaşır."""
    reps, sums, counts, assign = [], [], [], []
    for s in segs:
        for end in (0, -1):
            p = s["p"][end]
            j = next((k for k, r in enumerate(reps) if (r - p).length <= tol), None)
            if j is None:
                reps.append(p.copy())
                sums.append(p.copy())
                counts.append(1)
                j = len(reps) - 1
            else:
                sums[j] = sums[j] + p
                counts[j] += 1
            assign.append(j)
    cents = [sums[j] / counts[j] for j in range(len(reps))]
    k = 0
    for s in segs:
        for end in (0, -1):
            s["p"][end] = cents[assign[k]].copy()
            k += 1


def _migrate(props):
    if len(props.bevels):
        groups = {}
        for b in props.bevels:
            groups.setdefault((b.kind, round(b.size, 7)), []).append(b)
        for (kind, size), items in groups.items():
            f = props.features.add()
            f.name = f"Bevel {len(props.features)}"
            f.kind, f.size = kind, size
            for b in items:
                r = f.segs.add()
                r.obj, r.spline, r.seg = b.obj, b.spline, b.seg
        props.bevels.clear()
    if len(props.patches) == 0 and len(props.curves) > 0:
        p = props.patches.add()
        p.name = "Yüzey 1"
        for r in props.curves:
            p.curves.add().obj = r.obj
        props.curves.clear()
    for f in props.features:
        if not f.uid:
            f.uid = new_uid()


def _mirror_planes(props):
    if not props.use_mirror:
        return []
    axes = [(props.mirror_x, 0), (props.mirror_y, 1), (props.mirror_z, 2)]
    if not any(on for on, _ in axes):
        return []
    c = props.mirror_center
    if c is not None:
        mw = c.matrix_world
        origin = mw.translation
        basis = [mw.col[i].xyz.normalized() for i in range(3)]
    else:
        origin = (0.0, 0.0, 0.0)
        basis = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)]
    return [(tuple(round(x, 9) for x in origin), tuple(round(x, 9) for x in basis[i]))
            for on, i in axes if on]


def _match_tol(props):
    return max(min(props.join_tol, 1e-3), 1e-5)



# ================================================================ yeniden hesaplama
#
# Akış:  gather (ana iş parçacığı, bpy -> düz veri)
#        -> engine (ayrı süreçte OCC: yüzey, katı, boolean, fillet, üçgenleme)
#        -> _apply (ana iş parçacığı: mesh, bilgi metinleri, çizim verisi)
# Operatörler senkron (rebuild), canlı güncelleme asenkron (_tick) çalışır.

_display = {}       # obj_name -> {"edges", "bool_edges", "ghost"} (dünya koordinatı, numpy)
_final_known = {}   # obj_name -> son tam kalite şeklin bulunduğu hesap oturumu
_final_ver = {}     # obj_name -> tam kalite sayacı (araç imzaları için)
_final_parts = {}   # obj_name -> (eğri imzası, yapı imzası) son tam kalitede
_tool_sent = {}     # araç adı -> (oturum, imza): mesh verisi sürece gönderildi mi
_force_full = set()  # hayalet yetmedi, tam önizleme gerekiyor
_edit_blocked = set()  # gövde mesh'i düzenleme modundaydı, sonuç yazılamadı (v0.25.9)
_gathering = set()  # döngüsel boolean koruması
_result_hooks = []  # sonuç geldiğinde çağrılır (seçim modu yenilensin diye)


def _client():
    from . import jobs
    return jobs.client()


def _log(cat, msg):
    try:
        from . import recorder
        recorder.log(cat, msg)
    except Exception:
        pass


def _plain_seg(s):
    return {"p": [np.array(tuple(v), dtype=np.float64) for v in s["p"]],
            "tag": s["tag"], "ref": s["ref"]}


def _geo_desc(g):
    try:
        d = json.loads(g.data)
        s = np.asarray(d["s"], dtype=np.float64)
        if s.shape != (9, 3):
            return None
        return {"s": s, "len": float(d["len"])}
    except Exception:
        return None


def geo_desc_json(poly):
    """65 noktalı kenar çizgisinden kalıcı kenar tanımı (9 nokta + boy)."""
    P = np.asarray(poly, dtype=np.float64)
    L = float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())
    return json.dumps({"s": P[::8].tolist(), "len": L})


def new_uid():
    return uuid.uuid4().hex[:12]


def _tool_spec(obj, f):
    """Boolean aracının sürece gidecek tanımı ve önbellek anahtarı."""
    t = f.tool
    if t is None:
        raise CadError("Araç objesi seçilmemiş")
    if t == obj:
        raise CadError("Gövde kendisini araç olarak kullanamaz")
    c = _client()
    if t.cad.is_cad:
        if t.name in _gathering:
            raise CadError("Döngüsel boolean: gövdeler birbirini araç olarak kullanıyor")
        if _final_known.get(t.name) != c.session:
            rebuild(t, preview=False)
        if _final_known.get(t.name) != _client().session:
            raise CadError(f"'{t.name}' gövdesi hesaplanamadı: {t.cad.status}")
        return {"kind": "cad", "name": t.name}, ("cad", t.name, _final_ver.get(t.name))
    key = tool_signature(t, obj)
    spec = {"kind": "mesh", "name": t.name, "key": key, "verts": None, "polys": None}
    if _tool_sent.get(t.name) != (c.session, key):
        try:
            spec["verts"], spec["polys"] = _read_tool_mesh(t, t.matrix_world)
            _tool_sent[t.name] = (c.session, key)
        except Exception as e:
            spec["read_error"] = str(e)
    return spec, key


def gather(obj, preview, allow_ghost=True):
    """bpy verisini hesap sürecine gidecek düz veriye çevirir. (komut, iş)"""
    import time as _t
    props = obj.cad
    _migrate(props)
    parts = _signature_parts(props)
    sig = hash(parts)
    _last_sig[obj.name] = sig
    _stats["count"] += 1
    errors = []

    # 1) Segmentleri topla ve hepsini birlikte kaynakla
    items, all_segs = [], []
    for idx, patch in enumerate(props.patches):
        if not patch.enabled:
            continue
        try:
            segs = patch_segments(patch)
        except CadError as e:
            patch.info, patch.ok = str(e), False
            errors.append(patch.name)
            continue
        items.append((idx, patch, segs))
        all_segs += segs
    weld_all(all_segs, props.join_tol)
    patches = []
    for idx, patch, segs in items:
        try:
            groups = nest_loops(chain_loops(segs, props.join_tol))   # delikli yüzey (v0.22)
            groups = [(chain, holes, split_sides(chain)) for chain, holes in groups]
        except CadError as e:
            patch.info, patch.ok = str(e), False
            errors.append(patch.name)
            continue
        blend = getattr(patch, "blend", "BODY")
        if blend == "BODY":
            blend = getattr(props, "surface_blend", "SHARP")
        weight = float(getattr(patch, "tangent_weight", 1.0)) if getattr(patch, "own_weight",
                                                                           False) \
            else float(getattr(props, "tangent_weight", 1.0))
        for sub, (chain, holes, sides) in enumerate(groups):
            pc = [_plain_seg(s) for s in chain]
            look = {id(s): pc[i] for i, s in enumerate(chain)}
            ps = [[look.get(id(s)) or _plain_seg(s) for s in side] for side in sides]
            entry = {"idx": idx, "name": patch.name, "chain": pc, "sides": ps,
                     "method": patch.method, "blend": blend}
            if blend != "SHARP" and abs(weight - 1.0) > 1e-9:
                entry["weight"] = weight
            if holes:
                entry["holes"] = [[_plain_seg(s) for s in h] for h in holes]
            if len(groups) > 1:
                entry["sub"] = sub
            patches.append(entry)

    # 2) Sıralı işlemler (art arda bevel'ler bir aşama, her boolean ayrı aşama)
    mirrors = _mirror_planes(props)
    run_bevels = props.preview_bevel or not preview
    ghost = bool(preview and not run_bevels and props.ghost_bevel and props.use_bevels)
    geo_srcs = {g.src for f in props.features if f.enabled and f.op != "BOOLEAN"
                for g in f.geo_edges}
    stages, names = [], {}
    _gathering.add(obj.name)
    try:
        for f in props.features:
            if not f.enabled:
                continue
            names[f.uid] = f.name
            if f.op == "BOOLEAN":
                if not props.use_booleans:
                    continue
                try:
                    spec, tkey = _tool_spec(obj, f)
                except CadError as e:
                    f.ok, f.info = False, str(e)
                    errors.append(f.name)
                    continue
                stages.append({
                    "op": "BOOL", "uid": f.uid, "bool_type": f.bool_type, "tool": spec,
                    "edge_size": f.edge_size, "edge_mode": f.edge_mode,
                    "mirror_tool": f.mirror_tool,
                    "want_edges": (not preview) or (f.uid in geo_srcs and (run_bevels or ghost)),
                    "key": ("B", f.bool_type, tkey, round(f.edge_size, 9) if run_bevels else 0.0,
                            f.edge_mode, f.mirror_tool)})
                continue
            if not props.use_bevels or not (run_bevels or ghost):
                continue
            try:
                segs = collect_segrefs(f.segs) if len(f.segs) else []
            except CadError as e:
                f.ok, f.info = False, str(e)
                errors.append(f.name)
                continue
            geo = []
            for g in f.geo_edges:
                d = _geo_desc(g)
                if d is not None:
                    geo.append({"id": g.id, "src": g.src, "desc": d})
            if not segs and not geo:
                f.ok, f.info = False, "Kenar yok"
                errors.append(f.name)
                continue
            item = {"uid": f.uid, "kind": f.kind, "size": f.size,
                    "polys": [sample_segment(sg["p"], 64) for sg in segs], "geo": geo}
            ikey = ("F", f.kind, round(f.size, 9), _geom_key(segs), tuple(g["id"] for g in geo))
            if stages and stages[-1]["op"] == "BEVEL":
                st = stages[-1]
                st["items"].append(item)
                st["key"] += (ikey,)
                st["skey"] += (f.uid,)
            else:
                stages.append({"op": "BEVEL", "items": [item], "key": (ikey,),
                               "skey": (f.uid,)})
    finally:
        _gathering.discard(obj.name)

    job = {"name": obj.name, "preview": preview, "patches": patches, "errors": errors,
           "tol": _match_tol(props), "mirrors": mirrors,
           "sew_tol": max(1e-6, min(props.join_tol, 1e-4)), "make_solid": props.make_solid,
           "run_bevels": run_bevels, "ghost": ghost, "stages": stages,
           "corner_mode": props.corner_mode, "factor": props.transition_factor,
           "smooth": props.smooth_corners, "lin": props.lin_defl, "ang": props.ang_defl,
           "feature_names": names, "sig": sig, "parts": (hash(parts[0]), hash(parts[1])),
           "t0": _t.perf_counter()}
    cmd = "build"
    if ghost and allow_ghost and _final_parts.get(obj.name) == job["parts"] and \
            _final_known.get(obj.name) == _client().session:
        cmd = "ghost"                  # sadece fillet ölçüsü/türü değişti
    return cmd, job


def _redraw_views():
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                if area.type == "VIEW_3D":
                    area.tag_redraw()
    except Exception:
        pass


def _notify():
    for fn in list(_result_hooks):
        try:
            fn()
        except Exception:
            traceback.print_exc()
    _redraw_views()


def _apply(obj, job, res, cmd="build"):
    """Hesap sonucunu Blender'a yazar (ana iş parçacığı). True / False / "need_preview"."""
    import time as _t
    props = obj.cad
    name = obj.name
    _log("hesap", f"{name}: {cmd} {'önizleme' if job.get('preview') else 'tam'} sonucu "
                  f"{'OK' if res.get('ok') else 'HATA: ' + str(res.get('error') or res.get('need_preview') and 'tam önizleme gerekli')}"
                  f" · {res.get('ms', 0):.0f} ms")
    if cmd == "ghost":
        if res.get("need_preview"):
            return "need_preview"
        _display.setdefault(name, {})["ghost"] = res.get("ghost") if res.get("ok") else None
        props.status = "Önizleme · fillet hayaleti (bırakınca gerçek fillet hesaplanacak)"
        _notify()
        return bool(res.get("ok"))
    for idx, (ok, info) in res.get("patches", {}).items():
        if idx < len(props.patches):
            p = props.patches[idx]
            p.ok, p.info = ok, info
    by_uid = {f.uid: f for f in props.features if f.uid}
    for uid, (ok, info) in res.get("features", {}).items():
        f = by_uid.get(uid)
        if f is not None:
            f.ok, f.info = ok, info
    for uid, ups in res.get("geo_updates", {}).items():
        f = by_uid.get(uid)
        if f is None:
            continue
        for g in f.geo_edges:
            d = ups.get(g.id)
            if d is not None:
                txt = json.dumps(d)
                if g.data != txt:
                    g.data = txt
    if not res.get("ok"):
        props.status = res.get("error") or "Hata"
        if res.get("crashed"):
            _final_sig.pop(name, None)
        _display.setdefault(name, {})["ghost"] = None
        _notify()
        return False
    if getattr(obj.data, "is_editmode", False) is True:
        # v0.25.9: gövdenin kendisi (mesh) düzenleme modundayken Blender mesh verisini
        # değiştirtmez; sonuç sessizce kayboluyordu ("güncellenmiyor, Yenile de üretmiyor").
        # Moddan çıkılınca kendiliğinden yeniden hesaplanır (on_depsgraph_update).
        _edit_blocked.add(name)
        _final_sig.pop(name, None)
        _last_sig.pop(name, None)
        props.status = ("Gövde düzenleme modunda: sonuç yazılamıyor. Tab ile çıkınca "
                        "kendiliğinden güncellenir (tel kafesi düzenlemek için eğriyi seç)")
        _notify()
        return False
    try:
        verts, normals = _to_local(obj, res["verts"], res["normals"])
        write_mesh(obj.data, verts, res["tris"], normals)
    except Exception as e:
        traceback.print_exc()
        props.status = f"Mesh yazılamadı: {e}"
        return False
    d = _display.setdefault(name, {})
    d["ghost"] = res.get("ghost")
    errors = res.get("errors", [])
    if job["preview"]:
        _final_sig.pop(name, None)
        has_bevel = props.use_bevels and any(f.enabled and f.op != "BOOLEAN"
                                             for f in props.features)
        if has_bevel and not props.preview_bevel:
            mode = "Önizleme (fillet'ler bırakınca gelecek)"
        else:
            mode = "Önizleme"
    else:
        disp = res.get("display") or {}
        d["edges"] = disp.get("edges", [])
        d["bool_edges"] = disp.get("bool_edges", [])
        _final_known[name] = _client().session
        _final_ver[name] = _final_ver.get(name, 0) + 1
        _final_sig[name] = job["sig"]
        _final_parts[name] = job["parts"]
        try:
            link_wires(obj)
        except Exception:
            traceback.print_exc()
        mode = "Tamam"
    ms = (_t.perf_counter() - job["t0"]) * 1000.0
    _stats["last_ms"] = ms
    warn = f" · Hatalı: {', '.join(errors)}" if errors else ""
    props.status = f"{mode} · {res.get('shape_info', '')} · {len(res['tris'])} üçgen · " \
                   f"{ms:.0f} ms{warn}"
    _notify()
    return True


def rebuild(obj, preview=False):
    """Senkron yeniden hesaplama (operatörler için). Başarılıysa True."""
    props = obj.cad
    if not kernel.kernel_available():
        props.status = "Çekirdek yüklü değil"
        return False
    try:
        _, job = gather(obj, preview, allow_ghost=False)
    except CadError as e:
        props.status = str(e)
        return False
    except Exception as e:
        traceback.print_exc()
        props.status = f"Hata: {e}"
        return False
    _log("hesap", f"{obj.name}: senkron {'önizleme' if preview else 'tam'} hesap")
    res = _client().call("build", job)
    try:
        return _apply(obj, job, res) is True
    except Exception as e:
        traceback.print_exc()
        props.status = f"Hata: {e}"
        return False


def _start_build(ob, preview):
    """Canlı güncelleme: işi hazırlayıp sürece gönderir; sonuç gelince _apply çalışır."""
    name = ob.name
    if not kernel.kernel_available():
        ob.cad.status = "Çekirdek yüklü değil"
        return
    try:
        cmd, job = gather(ob, preview, allow_ghost=name not in _force_full)
    except CadError as e:
        ob.cad.status = str(e)
        return
    _force_full.discard(name)

    def done(res, name=name, job=job, cmd=cmd):
        o = bpy.data.objects.get(name)
        if o is None or not o.cad.is_cad:
            return
        prev = _flags["building"]
        _flags["building"] = True
        try:
            if _apply(o, job, res, cmd) == "need_preview":
                _force_full.add(name)
                _dirty[name] = True
                _ensure_timer()
        except Exception as e:
            traceback.print_exc()
            try:
                o.cad.status = f"Hata: {e}"
            except Exception:
                pass
        finally:
            _flags["building"] = prev

    _client().submit(cmd, job, done)


def _rows(m):
    return [[m[i][j] for j in range(4)] for i in range(4)]


def mesh_signature(ob):
    import numpy as np
    me = ob.data
    n = len(me.vertices)
    arr = np.empty(n * 3, dtype=np.float64)
    me.vertices.foreach_get("co", arr)
    mods = tuple((m.type, m.show_viewport) for m in ob.modifiers)
    return (n, len(me.polygons), round(float(arr.sum()), 6), round(float((arr * arr).sum()), 6),
            mods)


def tool_signature(tool, target):
    if tool is None:
        return None
    mat = tuple(round(x, 7) for row in tool.matrix_world for x in row)
    if tool.cad.is_cad:
        # CAD aracının şekli kendi tel kafesinden dünya koordinatında kurulur
        return (tool.name, "cad", _last_sig.get(tool.name), _final_ver.get(tool.name))
    try:
        return (tool.name, "mesh", mesh_signature(tool), mat)
    except Exception:
        return (tool.name, "mesh", None, mat)


def _read_tool_mesh(t, mw):
    """Aracın (değiştiricileri uygulanmış) mesh'ini okur; olmazsa ham mesh'e düşer.
    Zamanlayıcıdan çağrıldığında bağlam kısıtlı olabildiği için birden çok yol denenir."""
    me_ev = ev = None
    try:
        dg = bpy.context.evaluated_depsgraph_get()
        ev = t.evaluated_get(dg)
        me_ev = ev.to_mesh()
    except Exception:
        me_ev = None
    try:
        me = me_ev if me_ev is not None else t.data
        verts = [tuple(mw @ v.co) for v in me.vertices]
        polys = [list(p.vertices) for p in me.polygons]
    finally:
        if me_ev is not None:
            try:
                ev.to_mesh_clear()
            except Exception:
                pass
    return verts, polys


def export_step(obj, path):
    """Gövdeyi tam kalitede yeniden hesaplar ve STEP (mm) olarak yazar."""
    ok = rebuild(obj, preview=False)
    if not ok and _final_known.get(obj.name) != _client().session:
        raise CadError(obj.cad.status or "Gövde hesaplanamadı")
    us = bpy.context.scene.unit_settings
    res = _client().call("step", {"name": obj.name, "path": path,
                                  "scale": us.scale_length * 1000.0})
    if not res.get("ok"):
        raise CadError(res.get("error") or "STEP yazılamadı")


def forget_tool(name):
    _tool_sent.pop(name, None)
    _client().control("forget_tool", {"name": name})


def forget_cache(obj_name=None):
    tables = (_final_sig, _last_sig, _final_known, _final_parts, _display)
    if obj_name is None:
        for t in tables:
            t.clear()
        _tool_sent.clear()
        _force_full.clear()
    else:
        for t in tables:
            t.pop(obj_name, None)
        _force_full.discard(obj_name)
    _client().control("forget", {"name": obj_name})


def _on_engine_reset():
    """Hesap süreci yenilendi: süreç tarafı önbellekler yok, yeniden gönderilecek."""
    _tool_sent.clear()
    _final_known.clear()
    _final_parts.clear()


SETTLE_TIME = 0.35  # son değişiklikten bu kadar sn sonra tam kalite hesaplanır
MAX_WAIT = 1.5      # sürükleme algılaması takılsa bile bu kadar boşta kalınca tam kalite
_final_sig = {}     # obj_name -> son TAM KALİTE hesaptaki girdi imzası

_dirty = {}          # obj_name -> preview (bool)
_pending_final = set()
_flags = {"timer": False, "building": False, "last_change": 0.0}


def _timer_alive():
    try:
        return bpy.app.timers.is_registered(_tick)
    except Exception:
        return _flags["timer"]


def _ensure_timer():
    # Bayrağa değil zamanlayıcının gerçekten kayıtlı olup olmadığına bakılır: bir hata
    # zamanlayıcıyı durdurmuş olsa bile canlı güncelleme kendini yeniden başlatır.
    if not _timer_alive():
        _flags["timer"] = True
        bpy.app.timers.register(_tick, first_interval=0.01)


def schedule(obj, preview=False):
    if obj is None:
        return
    name = obj.name
    if preview:
        _flags["last_change"] = time.perf_counter()
        _dirty[name] = _dirty.get(name, True) and True
    else:
        _dirty[name] = False
    _ensure_timer()


def _next_job():
    """Sıradaki hesap: önce bekleyen değişiklikler, sonra yerleşince tam kalite."""
    while _dirty:
        name = next(iter(_dirty))
        prev = _dirty.pop(name)
        ob = bpy.data.objects.get(name)
        if ob is None or not ob.cad.is_cad:
            _pending_final.discard(name)
            continue
        if prev:
            # Girdi son tam kalite hesaptan farklı değilse önizleme yapma
            # (fillet'li gövdenin üstüne fillet'siz önizleme yazılmasın)
            try:
                same = input_signature(ob.cad) == _final_sig.get(name)
            except Exception:
                same = False
            if same:
                continue
            _pending_final.add(name)
            return ob, True
        _pending_final.discard(name)
        return ob, False
    idle = time.perf_counter() - _flags["last_change"]
    if _pending_final and idle >= SETTLE_TIME and (not _transform_running() or idle >= MAX_WAIT):
        while _pending_final:
            name = _pending_final.pop()
            ob = bpy.data.objects.get(name)
            if ob is not None and ob.cad.is_cad:
                return ob, False
    return None


def _safe_start(ob, preview):
    try:
        _start_build(ob, preview)
    except Exception as e:          # canlı güncelleme hiçbir hatayla durmamalı
        traceback.print_exc()
        try:
            ob.cad.status = f"Hata: {e}"
        except Exception:
            pass


def _tick():
    try:
        c = _client()
        c.poll()
        _flags["building"] = True
        try:
            for _ in range(64):
                if c.busy():
                    break
                nxt = _next_job()
                if nxt is None:
                    break
                _safe_start(*nxt)
        finally:
            _flags["building"] = False
        if c.busy():
            if c.mode == "starting":
                for name in list(_dirty):
                    ob = bpy.data.objects.get(name)
                    if ob is not None and ob.cad.is_cad:
                        msg = "Hesap motoru başlatılıyor…"
                        if ob.cad.status != msg:
                            ob.cad.status = msg
            return 0.03
        if _dirty or _pending_final:
            return 0.1 if _pending_final and not _dirty else 0.05
    except Exception:
        traceback.print_exc()
        _dirty.clear()
        _pending_final.clear()
    _flags["timer"] = False
    return None


_last_sig = {}   # obj_name -> son hesaplamadaki girdi imzası
_stats = {"count": 0, "skipped": 0, "last_ms": 0.0}


def _r(v):
    return (round(v[0], 6), round(v[1], 6), round(v[2], 6))


def _signature_parts(props):
    """(eğri/obje verisi, yapı/ayarlar, fillet ölçüleri). Fillet ölçüsü dışında bir şey
    değişmediyse hayalet önizleme yeterlidir."""
    curve = []
    seen = set()
    for ob in _watched_objects(props):
        if ob.name in seen:
            continue
        seen.add(ob.name)
        mw = ob.matrix_world
        curve.append((ob.name, tuple(round(x, 6) for row in mw for x in row)))
        if ob.type == "MESH":
            if ob.cad.is_cad:
                curve.append(("cad", _last_sig.get(ob.name), _final_ver.get(ob.name)))
            else:
                try:
                    curve.append(mesh_signature(ob))
                except Exception:
                    pass
            continue
        if ob.type != "CURVE":
            continue
        for sp in ob.data.splines:
            if sp.type == "BEZIER":
                curve.append(tuple((_r(b.co), _r(b.handle_left), _r(b.handle_right))
                                   for b in sp.bezier_points))
            else:
                curve.append(tuple(_r(q.co) for q in sp.points))
            curve.append(sp.use_cyclic_u)
    struct, bev = [], []
    for p in props.patches:
        struct.append(("P", p.enabled, p.method, len(p.segs), len(p.curves),
                       getattr(p, "blend", "BODY"), getattr(p, "own_weight", False),
                       round(float(getattr(p, "tangent_weight", 1.0)), 4)))
    for f in props.features:
        if f.op == "BOOLEAN":
            struct.append(("B", f.uid, f.enabled, f.bool_type,
                           f.tool.name if f.tool is not None else None,
                           round(f.edge_size, 9), f.edge_mode, f.mirror_tool))
        else:
            struct.append(("F", f.uid, f.enabled, len(f.segs),
                           tuple(g.id for g in f.geo_edges)))
            bev.append((f.kind, round(f.size, 9)))
    struct.append((props.use_mirror, props.mirror_x, props.mirror_y, props.mirror_z,
                   props.use_booleans, props.use_bevels, props.make_solid, props.corner_mode,
                   props.smooth_corners, round(props.transition_factor, 4),
                   round(props.lin_defl, 9), round(props.ang_defl, 6),
                   round(props.join_tol, 9), props.preview_bevel, props.ghost_bevel,
                   getattr(props, "surface_blend", "SHARP"),
                   round(float(getattr(props, "tangent_weight", 1.0)), 4)))
    return tuple(curve), tuple(struct), tuple(bev)


def input_signature(props):
    """Gövdeyi etkileyen bütün eğri/obje verilerinin ve ayarların özeti.
    Değişmediyse yeniden hesaplanmaz."""
    return hash(_signature_parts(props))

def _transform_running():
    """Kullanıcı şu an bir şeyi sürüklüyor mu (G/R/S, gizmo)?"""
    try:
        for win in bpy.context.window_manager.windows:
            for op in win.modal_operators:
                if "TRANSFORM" in op.bl_idname.upper():
                    return True
    except Exception:
        pass
    return False


def _watched_objects(props):
    for patch in props.patches:
        for r in patch.curves:
            if r.obj is not None:
                yield r.obj
        for r in patch.segs:
            if r.obj is not None:
                yield r.obj
    for r in props.curves:
        if r.obj is not None:
            yield r.obj
    for f in props.features:
        for r in f.segs:
            if r.obj is not None:
                yield r.obj
        if f.op == "BOOLEAN" and f.tool is not None:
            yield f.tool
    if props.mirror_center is not None:
        yield props.mirror_center


@persistent
def on_depsgraph_update(scene, depsgraph):
    if _flags["building"]:
        return
    for nm in list(_edit_blocked):       # gövde düzenleme modundan çıktıysa şimdi hesapla
        ob = scene.objects.get(nm)
        if ob is None or not ob.cad.is_cad:
            _edit_blocked.discard(nm)
        elif getattr(ob.data, "is_editmode", False) is not True:
            _edit_blocked.discard(nm)
            schedule(ob, preview=False)
    ptrs = set()
    for u in depsgraph.updates:
        idd = u.id
        if isinstance(idd, bpy.types.Object):
            if not (u.is_updated_geometry or u.is_updated_transform):
                continue
        elif not isinstance(idd, (bpy.types.Curve, bpy.types.Mesh)):
            continue
        ptrs.add(idd.original.as_pointer())
    if not ptrs:
        return
    for ob in scene.objects:
        p = ob.cad
        if not p.is_cad or not p.live:
            continue
        for w in _watched_objects(p):
            if w.as_pointer() in ptrs or (w.data is not None and w.data.as_pointer() in ptrs):
                try:
                    sig = input_signature(p)
                except Exception:
                    sig = None
                if sig is not None and sig == _last_sig.get(ob.name):
                    _stats["skipped"] += 1   # sahte güncelleme: girdi değişmedi
                    break
                schedule(ob, preview=p.preview)
                break


def _on_poly_setting(self, context):
    forget_cache()
    for ob in context.scene.objects:
        if ob.cad.is_cad:
            schedule(ob, preview=False)


@persistent
def on_load(_dummy):
    forget_cache()
    try:
        if not bpy.app.timers.is_registered(_warmup):
            bpy.app.timers.register(_warmup, first_interval=1.0)
    except Exception:
        pass


classes = (MINICAD_CurveRef, MINICAD_SegRef, MINICAD_Patch, MINICAD_GeoEdge, MINICAD_Feature,
           MINICAD_BevelEdge, MINICAD_CRef, MINICAD_Constraint, MINICAD_Link,
           MINICAD_ObjectProps)


def _int_list(txt):
    out = []
    for x in (txt or "").split(","):
        x = x.strip()
        if x:
            try:
                out.append(int(x))
            except ValueError:
                pass
    return out


def remap_splines(curve_ob, fn, seg_count=None):
    """Bir eğri objesinin spline sırası değişince (silme / sona taşıma) ona bağlı bütün
    referansları günceller: yüzey ve özellik segmentleri, eski bevel kenarları, kısıtlar,
    ilişkiler. fn(eski sıra) -> yeni sıra ya da None (silindi: referans geçersiz olur, -1).
    seg_count: {yeni sıra: segment sayısı} — sayının dışında kalan segment referansları
    geçersizleşir. Değişen referans sayısı."""
    n = 0

    def m(si):
        r = fn(si)
        return -1 if r is None else r

    def fix_seg(ref, attr):
        nonlocal n
        if ref.obj != curve_ob:
            return
        new = m(ref.spline)
        if new != ref.spline:
            ref.spline = new
            n += 1
        if seg_count is not None and new in seg_count and getattr(ref, attr) >= \
                seg_count[new]:
            ref.spline = -1
            n += 1

    for ob in bpy.data.objects:
        try:
            props = ob.cad
        except Exception:
            continue
        for p in getattr(props, "patches", ()):
            for r in getattr(p, "segs", ()):
                fix_seg(r, "seg")
        for f in getattr(props, "features", ()):
            for r in getattr(f, "segs", ()):
                fix_seg(r, "seg")
        for r in getattr(props, "bevels", ()):
            fix_seg(r, "seg")
        for c in getattr(props, "constraints", ()):
            for r in c.refs:
                if r.obj == curve_ob:
                    new = m(r.spline)
                    if new != r.spline:
                        r.spline = new
                        n += 1
        for lk in getattr(props, "links", ()):
            if ob == curve_ob:
                for attr in ("src", "dst"):
                    if lk.kind == "PROJ" and attr == "src":
                        continue
                    old = _int_list(getattr(lk, attr))
                    new = [m(x) for x in old]
                    if new != old:
                        setattr(lk, attr, ",".join(str(x) for x in new))
                        n += 1
            if lk.kind == "PROJ" and lk.src_obj == curve_ob and ":" in lk.src:
                si, sg = lk.src.split(":")[:2]
                new = m(int(si))
                if new != int(si):
                    lk.src = f"{new}:{sg}"
                    n += 1
    try:
        from . import constraints
        for k in [k for k in constraints._last_pos if k[0] == curve_ob.name]:
            del constraints._last_pos[k]
    except Exception:
        pass
    return n


# Bölünen segmentin ilk yarısında da anlamı korunan kısıtlar (yön / çember kısıtları)
SPLIT_SAFE_KINDS = {"AXIS", "PARALLEL", "PERP", "COLLINEAR", "RADIUS", "CONCENTRIC"}


def remap_insert(curve_ob, si, k):
    """v0.25.0: eğri objesinin si. spline'ının k. segmentine yeni nokta eklendi (yeni nokta
    k+1. sırada). Bağlı referanslar güncellenir:
      - yüzey / özellik / bevel segmentleri: j > k → j+1; j == k → k ve k+1 (iki yarı)
      - kısıt noktaları: indeks > k → +1; kısıt segmentleri: j > k → j+1; j == k: yön /
        çember kısıtları (SPLIT_SAFE_KINDS) ilk yarıda kalır, diğerleri (uzunluk, eşit,
        teğet...) devre dışı bırakılır (bilgi notuyla).
    (güncellenen referans sayısı, devre dışı kalan kısıt sayısı)"""
    n = 0
    off = 0

    def seg_coll(coll, copy_attrs=()):
        nonlocal n
        extra = []
        for r in list(coll):
            if r.obj != curve_ob or r.spline != si:
                continue
            if r.seg > k:
                r.seg += 1
                n += 1
            elif r.seg == k:
                extra.append({a: getattr(r, a) for a in copy_attrs})
        for attrs in extra:
            x = coll.add()
            x.obj, x.spline, x.seg = curve_ob, si, k + 1
            for a_, v in attrs.items():
                setattr(x, a_, v)
            n += 1

    for ob in bpy.data.objects:
        try:
            props = ob.cad
        except Exception:
            continue
        for p in getattr(props, "patches", ()):
            seg_coll(p.segs)
        for f in getattr(props, "features", ()):
            seg_coll(f.segs)
        if hasattr(props, "bevels"):
            seg_coll(props.bevels, ("kind", "size"))
        for c in getattr(props, "constraints", ()):
            kill = False
            for r in c.refs:
                if r.obj != curve_ob or r.spline != si:
                    continue
                if r.point:
                    if r.index > k:
                        r.index += 1
                        n += 1
                elif r.index > k:
                    r.index += 1
                    n += 1
                elif r.index == k and c.kind not in SPLIT_SAFE_KINDS:
                    kill = True
            if kill and c.enabled:
                c.enabled = False
                c.info = "Kenar bölündü: kısıt devre dışı (yeniden ekle)"
                off += 1
    try:
        from . import constraints
        for key in [key for key in constraints._last_pos if key[0] == curve_ob.name]:
            del constraints._last_pos[key]
    except Exception:
        pass
    return n, off


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Object.cad = bpy.props.PointerProperty(type=MINICAD_ObjectProps)
    bpy.types.Scene.minicad_poly_smooth = bpy.props.BoolProperty(
        name="Poly Eğrileri Yumuşat",
        description="Düz parçalardan oluşan poly eğrileri (ör. mesh'ten dönüştürülen) noktalarından "
        "geçen pürüzsüz eğrilere çevirir; köşe açısından keskin kırılmalar korunur",
        default=True, update=_on_poly_setting)
    bpy.types.Scene.minicad_poly_corner = bpy.props.FloatProperty(
        name="Köşe Açısı", description="Bu açıdan keskin kırılmalar köşe kabul edilir",
        default=math.radians(30.0), min=math.radians(1.0), max=math.radians(89.0),
        subtype="ANGLE", update=_on_poly_setting)
    bpy.types.Scene.minicad_bool_tool = bpy.props.PointerProperty(
        name="İkincil", description="Gövdeye uygulanacak ikincil parça: negatif / ek obje "
        "(kapalı mesh ya da CAD gövdesi)", type=bpy.types.Object, poll=_poll_scene_tool)
    bpy.types.Scene.minicad_bool_highlight = bpy.props.BoolProperty(
        name="Boolean Vurgusu", description="Gövdenin mavi, ikincil parçanın turuncu dış hat "
        "çizgilerini viewport'ta göster / gizle", default=True)
    bpy.types.Scene.minicad_bool_type = bpy.props.EnumProperty(
        name="İşlem", items=BOOL_TYPES, default="CUT")
    bpy.types.Scene.minicad_target = bpy.props.PointerProperty(
        name="Hedef CAD Objesi", type=bpy.types.Object, poll=_poll_cad)
    bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)
    bpy.app.handlers.load_post.append(on_load)
    configure_engine()
    try:
        bpy.app.timers.register(_warmup, first_interval=1.0)
    except Exception:
        pass


def background_pref():
    try:
        return bool(bpy.context.preferences.addons[__package__].preferences.background)
    except Exception:
        return True


def configure_engine():
    """Hesap sürecinin ayarları (OCP klasörü, günlük dosyası, tercih)."""
    c = _client()
    try:
        c.site = kernel.site_dir() or ""
    except Exception:
        c.site = ""
    if c.site:
        c.log_path = os.path.join(os.path.dirname(c.site), "mini_cad_engine_log.txt")
    want = background_pref()
    if want != c.want_process:
        c.stop()
        c.want_process = want
        if c.mode == "inproc":
            c.mode = "off"
    if _on_engine_reset not in c.on_reset:
        c.on_reset.append(_on_engine_reset)
    c.log = _log


def _warmup():
    """Sahnede CAD gövdesi varsa hesap sürecini önceden başlatır (ilk hesap beklemesin)."""
    try:
        c = _client()
        if c.mode == "off":
            if not any(getattr(o, "cad", None) is not None and o.cad.is_cad
                       for o in bpy.data.objects):
                return 2.0
            if not kernel.kernel_available():
                return None
            c.ensure()
        c.poll()
        if c.mode == "starting":
            return 0.25
    except Exception:
        traceback.print_exc()
    return None


def unregister():
    try:
        _client().stop()
    except Exception:
        pass
    try:
        if bpy.app.timers.is_registered(_warmup):
            bpy.app.timers.unregister(_warmup)
    except Exception:
        pass
    for lst, fn in ((bpy.app.handlers.depsgraph_update_post, on_depsgraph_update),
                    (bpy.app.handlers.load_post, on_load)):
        if fn in lst:
            lst.remove(fn)
    del bpy.types.Scene.minicad_target
    del bpy.types.Scene.minicad_bool_tool
    del bpy.types.Scene.minicad_bool_highlight
    del bpy.types.Scene.minicad_bool_type
    del bpy.types.Scene.minicad_poly_smooth
    del bpy.types.Scene.minicad_poly_corner
    del bpy.types.Object.cad
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    forget_cache()
