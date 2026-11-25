"""Diş ve vida hesapları (v0.36.0) — bpy / OCC'siz: standartlar, diş profili, tolerans.

Diş, eksenel düzlemdeki (meridyen) bir profilin helis boyunca süpürülmesidir. Profil bir
adım (P) boyunca periyodik bir çizgidir: s eksenel konum (0..P), t diş dibinden radyal
yükseklik (0: dip, h: tepe). Dış dişin (vidanın) dişi tepe ortası P/2'de olacak biçimde
kurulur. İç diş (somun / dişli delik) aynı profilin tersidir: delikten çıkarılan malzeme
vidanın dişi biçimindedir. Böylece tek bir profil hem deliği hem vidayı verir; tolerans
(boşluk) yüzeye dik ofsetle iki parçaya paylaştırılır.

Hesap aracı (geometry / threadgeo) iki çokgen ister:
  diş çokgeni (delik için):   dişin kendisi, alt ucu matkap silindirinin içine taşar
  oluk çokgeni (vida için):   iki diş arasındaki boşluk, üst ucu vida silindirinin dışına
Her iki çokgenin eksenel genişliği adımdan küçüktür: helisin komşu turları birbirine
değmez (kendini kesen katı olmaz). Bu yüzden kesim çizgileri dip / tepe düzeyinin biraz
içinden geçer (dip ve tepe yüzeyi silindirle çakışmaz).

Ölçüler mm cinsinden tablolardadır; sahne birimine mm_to_units ile çevrilir.
"""

import math

INCH = 25.4

# ---------------------------------------------------------------- standart ölçüler
# aile: (ad, açıklama, profil anahtarı, [(ölçü adı, anma çapı mm, adım mm)])

def _tpi(name, d_in, tpi):
    return (name, d_in * INCH, INCH / tpi)


_ISO_M = [("M1", 1.0, 0.25), ("M1.2", 1.2, 0.25), ("M1.4", 1.4, 0.3), ("M1.6", 1.6, 0.35),
          ("M2", 2.0, 0.4), ("M2.5", 2.5, 0.45), ("M3", 3.0, 0.5), ("M3.5", 3.5, 0.6),
          ("M4", 4.0, 0.7), ("M5", 5.0, 0.8), ("M6", 6.0, 1.0), ("M7", 7.0, 1.0),
          ("M8", 8.0, 1.25), ("M10", 10.0, 1.5), ("M12", 12.0, 1.75), ("M14", 14.0, 2.0),
          ("M16", 16.0, 2.0), ("M18", 18.0, 2.5), ("M20", 20.0, 2.5), ("M22", 22.0, 2.5),
          ("M24", 24.0, 3.0), ("M27", 27.0, 3.0), ("M30", 30.0, 3.5), ("M33", 33.0, 3.5),
          ("M36", 36.0, 4.0), ("M42", 42.0, 4.5), ("M48", 48.0, 5.0), ("M56", 56.0, 5.5),
          ("M64", 64.0, 6.0)]
_ISO_MF = [(f"M{d:g}×{p:g}", d, p) for d, p in (
    (3, 0.35), (4, 0.5), (5, 0.5), (6, 0.75), (8, 0.75), (8, 1.0), (10, 0.75), (10, 1.0),
    (10, 1.25), (12, 1.0), (12, 1.25), (12, 1.5), (14, 1.25), (14, 1.5), (16, 1.0),
    (16, 1.5), (18, 1.0), (18, 1.5), (18, 2.0), (20, 1.0), (20, 1.5), (20, 2.0), (22, 1.5),
    (22, 2.0), (24, 1.0), (24, 1.5), (24, 2.0), (27, 1.5), (27, 2.0), (30, 1.5), (30, 2.0),
    (36, 1.5), (36, 2.0), (36, 3.0), (42, 2.0), (42, 3.0), (48, 2.0), (48, 3.0))]
_UNC = [_tpi("#2-56", 0.086, 56), _tpi("#4-40", 0.112, 40), _tpi("#5-40", 0.125, 40),
        _tpi("#6-32", 0.138, 32), _tpi("#8-32", 0.164, 32), _tpi("#10-24", 0.190, 24),
        _tpi("#12-24", 0.216, 24), _tpi("1/4-20", 0.25, 20), _tpi("5/16-18", 0.3125, 18),
        _tpi("3/8-16", 0.375, 16), _tpi("7/16-14", 0.4375, 14), _tpi("1/2-13", 0.5, 13),
        _tpi("9/16-12", 0.5625, 12), _tpi("5/8-11", 0.625, 11), _tpi("3/4-10", 0.75, 10),
        _tpi("7/8-9", 0.875, 9), _tpi("1-8", 1.0, 8), _tpi("1 1/4-7", 1.25, 7),
        _tpi("1 1/2-6", 1.5, 6)]
_UNF = [_tpi("#2-64", 0.086, 64), _tpi("#4-48", 0.112, 48), _tpi("#6-40", 0.138, 40),
        _tpi("#8-36", 0.164, 36), _tpi("#10-32", 0.190, 32), _tpi("1/4-28", 0.25, 28),
        _tpi("5/16-24", 0.3125, 24), _tpi("3/8-24", 0.375, 24), _tpi("7/16-20", 0.4375, 20),
        _tpi("1/2-20", 0.5, 20), _tpi("9/16-18", 0.5625, 18), _tpi("5/8-18", 0.625, 18),
        _tpi("3/4-16", 0.75, 16), _tpi("7/8-14", 0.875, 14), _tpi("1-12", 1.0, 12)]
_BSW = [_tpi("1/8 BSW", 0.125, 40), _tpi("3/16 BSW", 0.1875, 24), _tpi("1/4 BSW", 0.25, 20),
        _tpi("5/16 BSW", 0.3125, 18), _tpi("3/8 BSW", 0.375, 16), _tpi("7/16 BSW", 0.4375, 14),
        _tpi("1/2 BSW", 0.5, 12), _tpi("5/8 BSW", 0.625, 11), _tpi("3/4 BSW", 0.75, 10),
        _tpi("7/8 BSW", 0.875, 9), _tpi("1 BSW", 1.0, 8)]
_BSP = [("G1/16", 7.723, INCH / 28), ("G1/8", 9.728, INCH / 28), ("G1/4", 13.157, INCH / 19),
        ("G3/8", 16.662, INCH / 19), ("G1/2", 20.955, INCH / 14), ("G5/8", 22.911, INCH / 14),
        ("G3/4", 26.441, INCH / 14), ("G7/8", 30.201, INCH / 14), ("G1", 33.249, INCH / 11),
        ("G1 1/4", 41.910, INCH / 11), ("G1 1/2", 47.803, INCH / 11),
        ("G2", 59.614, INCH / 11)]
_TR = [(f"Tr{d:g}×{p:g}", d, p) for d, p in (
    (8, 1.5), (10, 2), (12, 3), (14, 3), (16, 4), (18, 4), (20, 4), (22, 5), (24, 5),
    (26, 5), (28, 5), (30, 6), (32, 6), (36, 6), (40, 7), (44, 7), (50, 8), (60, 9))]
_ACME = [_tpi("1/4 ACME", 0.25, 16), _tpi("5/16 ACME", 0.3125, 14),
         _tpi("3/8 ACME", 0.375, 12), _tpi("1/2 ACME", 0.5, 10), _tpi("5/8 ACME", 0.625, 8),
         _tpi("3/4 ACME", 0.75, 6), _tpi("1 ACME", 1.0, 5), _tpi("1 1/4 ACME", 1.25, 5),
         _tpi("1 1/2 ACME", 1.5, 4), _tpi("2 ACME", 2.0, 4)]
_SQ = [(f"Kare {d:g}×{p:g}", d, p) for d, p in (
    (8, 2), (10, 2), (12, 3), (16, 4), (20, 4), (24, 5), (30, 6), (36, 6), (40, 7))]
_RD = [(f"Rd{d:g}×1/8\"", d, INCH / 8) for d in (10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30,
                                                  32, 36, 38)] + \
      [(f"Rd{d:g}×1/6\"", d, INCH / 6) for d in (40, 44, 48, 52)]
_BUTT = [(f"S{d:g}×{p:g}", d, p) for d, p in (
    (10, 2), (12, 3), (16, 4), (20, 4), (24, 5), (28, 5), (32, 6), (36, 6), (40, 7),
    (44, 7), (50, 8))]

# profil anahtarı → biçim oranları (adım P'ye göre): (profil, yan açısı 1, yan açısı 2 (°,
# radyal doğrultudan), diş yüksekliği / P, tepe düzlüğü / P, tepe yarıçapı / P,
# dip yarıçapı / P)
SHAPES = {
    "ISO": ("TRI", 30.0, 30.0, 0.5412659, 0.125, 0.0, 0.0),       # ISO 68-1 / UN temel
    "WHIT": ("TRI", 27.5, 27.5, 0.6403270, 0.1666667, 0.137329, 0.137329),  # 55°
    "TR": ("TRAP", 15.0, 15.0, 0.5, 0.3660, 0.0, 0.0),            # ISO 2904, 30°
    "ACME": ("TRAP", 14.5, 14.5, 0.5, 0.3707, 0.0, 0.0),          # 29°
    "SQ": ("SQUARE", 0.0, 0.0, 0.5, 0.5, 0.0, 0.0),
    "RD": ("ROUND", 15.0, 15.0, 0.5, 0.3660, 0.23851, 0.25597),   # DIN 405
    "BUTT": ("BUTT", 3.0, 30.0, 0.75, 0.2638, 0.0, 0.12427),      # DIN 513 testere
}

FAMILIES = [
    # kimlik, ad, açıklama, biçim, ölçüler
    ("ISO_M", "Metrik (kaba)", "ISO 261 / 262 metrik kaba diş, 60°", "ISO", _ISO_M),
    ("ISO_MF", "Metrik (ince)", "ISO 261 metrik ince diş, 60°", "ISO", _ISO_MF),
    ("UNC", "UNC (inç kaba)", "Unified National Coarse, 60°", "ISO", _UNC),
    ("UNF", "UNF (inç ince)", "Unified National Fine, 60°", "ISO", _UNF),
    ("BSW", "Whitworth (BSW)", "İngiliz Whitworth, 55°, yuvarlatılmış", "WHIT", _BSW),
    ("BSP", "Boru (G / BSPP)", "ISO 228 paralel boru dişi, 55°", "WHIT", _BSP),
    ("TR", "Trapez (Tr)", "ISO 2904 metrik trapez, 30° — hareket vidası", "TR", _TR),
    ("ACME", "ACME", "ACME trapez, 29° — hareket vidası", "ACME", _ACME),
    ("SQ", "Kare", "Kare profil — en az sürtünmeli hareket vidası", "SQ", _SQ),
    ("RD", "Yuvarlak (Rd)", "DIN 405 yuvarlak diş, 30° — kirli ortam, kolay baskı", "RD", _RD),
    ("BUTT", "Testere (S)", "DIN 513 testere dişi, 3° / 30° — tek yönlü yük", "BUTT", _BUTT),
    ("CUSTOM", "Özel", "Bütün değerler elle; profil türü ya da eğri seçilir", None, []),
]
_FAM = {f[0]: f for f in FAMILIES}

PROFILES = [("TRI", "Üçgen (V)", "Üçgen profil: açı ve tepe / dip düzlüğü ayarlanır"),
            ("TRAP", "Trapez", "Geniş tepe ve dipli trapez profil"),
            ("SQUARE", "Kare", "Dik yanlı kare profil"),
            ("ROUND", "Yuvarlak", "Tepe ve dibi yay ile yuvarlatılmış profil"),
            ("BUTT", "Testere", "Asimetrik: iki yanın açısı ayrı"),
            ("CUSTOM", "Eğri (özel)", "Profil bir eğri objesinden alınır")]


def family_items():
    return [(k, n, d) for k, n, d, _s, _z in FAMILIES]


def sizes(family):
    f = _FAM.get(family)
    return [] if f is None else [z[0] for z in f[4]]


def mm_to_units(mm, scale_length=1.0):
    return mm * 0.001 / (scale_length or 1.0)


def units_to_mm(v, scale_length=1.0):
    return v * (scale_length or 1.0) * 1000.0


def standard(family, size):
    """Standart dişin değerleri (mm): {"D", "P", "profile", "a1", "a2", "depth", "crest",
    "rc", "rr", "tap"}. tap: kılavuz matkabı (D − P'ye yakın, kozmetik dişte delik)."""
    f = _FAM.get(family)
    if f is None or f[3] is None:
        raise ValueError(f"Standart yok: {family}")
    for name, d, p in f[4]:
        if name == size:
            prof, a1, a2, h, c, rc, rr = SHAPES[f[3]]
            out = {"D": d, "P": p, "profile": prof, "a1": a1, "a2": a2, "depth": h * p,
                   "crest": c * p, "rc": rc * p, "rr": rr * p}
            out["tap"] = tap_drill(d, p, family)
            return out
    raise ValueError(f"Ölçü yok: {family} {size}")


def tap_drill(d, p, family="ISO_M"):
    """Kılavuz matkabı (mm): metrikte D − P (0.05'e yuvarlı), trapez / kare D − P, diğerleri
    temel iç çap + %25 diş payı."""
    if family == "BUTT":
        return round((d - 1.5 * p) * 20) / 20
    if family in ("TR", "ACME", "SQ", "RD"):
        return round((d - p) * 20) / 20
    if family in ("BSW", "BSP"):
        return round((d - 1.28065 * p * 0.85) * 20) / 20
    return round((d - p) * 20) / 20


def find_size(family, d_mm, p_mm=None):
    """Çap (ve adım) bilinen dişin standart adı | None."""
    best = None
    for name, d, p in _FAM.get(family, (None,) * 5)[4] or ():
        if abs(d - d_mm) < 1e-3 and (p_mm is None or abs(p - p_mm) < 1e-3):
            return name
        if abs(d - d_mm) < 1e-3 and best is None:
            best = name
    return best


# ---------------------------------------------------------------- tolerans (geçme)
# Boşluk: vida ile delik dişlerinin yan yüzleri arasındaki dik açıklık (yüzeysel öpüşme
# aralığı). pay: boşluğun deliğe giden kısmı (0: hepsi vidadan, 1: hepsi delikten).
# Baskı genleşmesi: filament / reçinenin yatay şişmesi; delik bu kadar büyütülür, vida bu
# kadar küçültülür (yazıcı sonrası gerçek boşluk = boşluk).

FITS = [("NOMINAL", "Birebir", "Boşluksuz, anma ölçüsü (görsel / talaşlı imalat çizimi)", 0.0),
        ("ISO", "ISO 6H / 6g", "Talaşlı imalat: vida dişi temel sapma kadar küçültülür", None),
        ("SLA", "Reçine (SLA)", "Reçine baskı: 0.10 mm boşluk", 0.10),
        ("FDM_TIGHT", "FDM sıkı", "FDM: 0.15 mm boşluk — sıkı, elle zorlanarak döner", 0.15),
        ("FDM", "FDM normal", "FDM 0.4 mm nozul: 0.25 mm boşluk — rahat döner", 0.25),
        ("FDM_LOOSE", "FDM gevşek", "FDM: 0.40 mm boşluk — gevşek, kaba baskı", 0.40),
        ("CUSTOM", "Özel", "Boşluk ve paylaşım elle", None)]
_FITS = {f[0]: f for f in FITS}


def fit_clearance(fit, p_mm):
    """Ön ayarın boşluğu (mm) | None (Özel: elle girilen değer kalır)."""
    f = _FITS.get(fit)
    if f is None:
        return None
    if fit == "ISO":
        # 6g temel sapma es = −(15 + 11P) µm (bölüm dairesi çapında); 60° yanda dik ofset
        # ≈ |es| / 2 · sin 30° = |es| / 4
        return (15.0 + 11.0 * p_mm) * 1e-3 / 4.0
    return f[3]


def fit_offsets(clearance, share=0.5, swell=0.0):
    """(delik dişi ofseti, vida dişi ofseti) — dişin büyümesi pozitif (yüzeye dik).

    Delikten çıkan malzeme vida dişi biçimindedir: deliğe giden boşluk payı bu dişi
    büyütür. Vida dişi küçülür."""
    share = min(max(float(share), 0.0), 1.0)
    c = max(float(clearance), 0.0)
    return c * share + swell, -(c * (1.0 - share) + swell)


# ---------------------------------------------------------------- profil

def _flank_shape(spec):
    """(a1, a2, h, crest, rc, rr) — adım içinde sığmayan değerler kırpılır."""
    P = float(spec["P"])
    h = max(float(spec["depth"]), P * 1e-3)
    a1 = math.radians(min(max(float(spec.get("a1", 30.0)), 0.0), 80.0))
    a2 = math.radians(min(max(float(spec.get("a2", spec.get("a1", 30.0))), 0.0), 80.0))
    w = h * (math.tan(a1) + math.tan(a2))
    if w > 0.96 * P:                       # yanlar adımı dolduruyor: yüksekliği kıs
        h *= 0.96 * P / w
        w = 0.96 * P
    crest = min(max(float(spec.get("crest", 0.0)), 0.0), P - w - 0.02 * P)
    crest = max(crest, 0.0)
    return a1, a2, h, crest, max(float(spec.get("rc", 0.0)), 0.0), \
        max(float(spec.get("rr", 0.0)), 0.0)


def outline(spec, n_arc=6):
    """Dış dişin bir adımlık periyodik profili [(s, t)]: (0, 0) dipten başlar, diş adımın
    ortasında, (P, 0) dipte biter. spec: {"P", "depth", "a1", "a2", "crest", "rc", "rr",
    "profile", "custom" (eğri noktaları, isteğe bağlı), "custom_w"}."""
    P = float(spec["P"])
    if P <= 0:
        raise ValueError("Adım sıfır")
    if spec.get("profile") == "CUSTOM" and spec.get("custom"):
        return _custom_outline(spec)
    a1, a2, h, crest, rc, rr = _flank_shape(spec)
    w1, w2 = h * math.tan(a1), h * math.tan(a2)
    sa = 0.5 * (P - (w1 + crest + w2))     # diş adımın ortasında (asimetrikte de sığar)
    sb = sa + w1                           # tepe başı
    sc = sb + crest                        # tepe sonu
    sd = sc + w2                           # inen yanın dibi
    pts = [(0.0, 0.0), (sa, 0.0), (sb, h), (sc, h), (sd, 0.0), (P, 0.0)]
    pts = _dedupe(pts, 1e-9 * P)
    if rc > 0 or rr > 0:
        pts = _round_corners(pts, rc, rr, h, n_arc)
    return pts


def _custom_outline(spec):
    """Eğriden profil: spec["custom"] eksenel x, radyal y noktaları (eğrinin kendi
    birimiyle). x aralığı diş genişliğine (custom_w · P), y aralığı yüksekliğe (depth)
    ölçeklenir; başı ve sonu dipte (y = en küçük) kabul edilir."""
    P = float(spec["P"])
    h = max(float(spec["depth"]), P * 1e-3)
    pts = [(float(x), float(y)) for x, y in spec["custom"]]
    if len(pts) < 3:
        raise ValueError("Özel profil eğrisinde en az 3 nokta olmalı")
    if pts[0][0] > pts[-1][0]:
        pts.reverse()
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if x1 - x0 < 1e-12 or y1 - y0 < 1e-12:
        raise ValueError("Özel profil eğrisi düz (genişlik ya da yükseklik yok)")
    width = min(max(float(spec.get("custom_w", 0.85)), 0.1), 0.96) * P
    s0 = 0.5 * (P - width)
    out = [(0.0, 0.0)]
    for x, y in pts:
        out.append((s0 + (x - x0) / (x1 - x0) * width, (y - y0) / (y1 - y0) * h))
    out[1] = (out[1][0], 0.0)
    out[-1] = (out[-1][0], 0.0)
    out.append((P, 0.0))
    return _dedupe(out, 1e-9 * P)


def _dedupe(pts, eps):
    out = [pts[0]]
    for q in pts[1:]:
        if math.hypot(q[0] - out[-1][0], q[1] - out[-1][1]) > eps:
            out.append(q)
    return out


def _round_corners(pts, rc, rr, h, n):
    """İç köşeleri yayla yuvarlat: tepe köşelerine rc, dip köşelerine rr."""
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = pts[i - 1], pts[i], pts[i + 1]
        r = rc if b[1] > 0.5 * h else rr
        if r <= 0:
            out.append(b)
            continue
        u = (a[0] - b[0], a[1] - b[1])
        v = (c[0] - b[0], c[1] - b[1])
        lu, lv = math.hypot(*u), math.hypot(*v)
        if lu < 1e-15 or lv < 1e-15:
            out.append(b)
            continue
        u = (u[0] / lu, u[1] / lu)
        v = (v[0] / lv, v[1] / lv)
        cosang = max(-1.0, min(1.0, u[0] * v[0] + u[1] * v[1]))
        ang = math.acos(cosang)                # köşedeki iç açı
        if ang > math.pi - 1e-6:
            out.append(b)
            continue
        t = r / math.tan(0.5 * ang)            # teğet uzunluğu
        # komşu köşeyle paylaşılan kenarın yarısından fazla yenmesin
        t = min(t, 0.5 * lu if i > 1 else lu, 0.5 * lv if i < len(pts) - 2 else lv)
        r_eff = t * math.tan(0.5 * ang)
        p1 = (b[0] + u[0] * t, b[1] + u[1] * t)
        p2 = (b[0] + v[0] * t, b[1] + v[1] * t)
        bis = (u[0] + v[0], u[1] + v[1])
        lb = math.hypot(*bis)
        bis = (bis[0] / lb, bis[1] / lb)
        dc = r_eff / math.sin(0.5 * ang)
        cen = (b[0] + bis[0] * dc, b[1] + bis[1] * dc)
        a1 = math.atan2(p1[1] - cen[1], p1[0] - cen[0])
        a2 = math.atan2(p2[1] - cen[1], p2[0] - cen[0])
        da = a2 - a1
        while da > math.pi:
            da -= 2 * math.pi
        while da < -math.pi:
            da += 2 * math.pi
        for k in range(n + 1):
            q = a1 + da * k / n
            out.append((cen[0] + r_eff * math.cos(q), cen[1] + r_eff * math.sin(q)))
    out.append(pts[-1])
    return _dedupe(out, 1e-12)


def offset(pts, d):
    """Periyodik profili yüzeye dik d kadar ötele (+: diş büyür, yukarı / dışa).

    Köşelerde kesişim (miter) kullanılır; uçlar dip düzlüğünde olduğundan düz kayar.
    Sonuç yine s = 0 .. P aralığına oturtulur (uçlar periyodik)."""
    if abs(d) < 1e-15:
        return list(pts)
    n = len(pts)
    # kenar normalleri (sol el: profil soldan sağa gider, dış (malzeme dışı) yukarıda)
    norms = []
    for i in range(n - 1):
        a, b = pts[i], pts[i + 1]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(dx, dy) or 1.0
        norms.append((-dy / ln, dx / ln))
    out = []
    for i in range(n):
        if i == 0 or i == n - 1:
            nn = norms[0] if i == 0 else norms[-1]
            out.append((pts[i][0] + nn[0] * d, pts[i][1] + nn[1] * d))
            continue
        n1, n2 = norms[i - 1], norms[i]
        m = (n1[0] + n2[0], n1[1] + n2[1])
        dot = 1.0 + n1[0] * n2[0] + n1[1] * n2[1]
        if dot < 1e-6:
            out.append((pts[i][0] + n1[0] * d, pts[i][1] + n1[1] * d))
            continue
        k = d / dot
        out.append((pts[i][0] + m[0] * k, pts[i][1] + m[1] * k))
    out = _remove_loops(out)
    out[0] = (pts[0][0], out[0][1])
    out[-1] = (pts[-1][0], out[-1][1])
    return out


def _seg_x(a, b, c, d):
    """İki doğru parçasının kesişimi | None."""
    r = (b[0] - a[0], b[1] - a[1])
    q = (d[0] - c[0], d[1] - c[1])
    den = r[0] * q[1] - r[1] * q[0]
    if abs(den) < 1e-300:
        return None
    w = (c[0] - a[0], c[1] - a[1])
    t = (w[0] * q[1] - w[1] * q[0]) / den
    u = (w[0] * r[1] - w[1] * r[0]) / den
    if 1e-12 < t < 1 - 1e-12 and 1e-12 < u < 1 - 1e-12:
        return (a[0] + r[0] * t, a[1] + r[1] * t)
    return None


def _remove_loops(pts):
    """Ötelemede oluşan kendini kesen ilmekleri (dar tepe / dipte) kes at."""
    pts = list(pts)
    changed = True
    while changed:
        changed = False
        n = len(pts)
        for i in range(n - 1):
            for j in range(n - 2, i + 1, -1):
                x = _seg_x(pts[i], pts[i + 1], pts[j], pts[j + 1])
                if x is not None:
                    pts = pts[:i + 1] + [x] + pts[j + 1:]
                    changed = True
                    break
            if changed:
                break
    return pts


def _clip(poly, axis, value, keep_ge):
    """Sutherland–Hodgman: kapalı çokgeni q[axis] ≥ value (keep_ge) yarı düzlemine kırp."""
    out = []
    m = len(poly)
    for i in range(m):
        a, b = poly[i], poly[(i + 1) % m]
        ia = (a[axis] >= value) if keep_ge else (a[axis] <= value)
        ib = (b[axis] >= value) if keep_ge else (b[axis] <= value)
        if ia:
            out.append(a)
        if ia != ib:
            t = (value - a[axis]) / (b[axis] - a[axis])
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return _dedupe(out, 1e-14) if out else out


def clean_poly(poly, P):
    """Kırpma / yuvarlamadan kalan çok kısa kenarları ve doğrusal ara noktaları at (OCC
    süpürmesi 1e-7·P'lik kenarda kurulamıyordu)."""
    eps = 1e-4 * P
    out = []
    for q in poly:
        if out and math.hypot(q[0] - out[-1][0], q[1] - out[-1][1]) < eps:
            continue
        out.append(q)
    while len(out) > 3 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < eps:
        out.pop()
    changed = True
    while changed and len(out) > 3:
        changed = False
        for i in range(len(out)):
            a, b, c = out[i - 1], out[i], out[(i + 1) % len(out)]
            cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            la = math.hypot(b[0] - a[0], b[1] - a[1])
            lc = math.hypot(c[0] - b[0], c[1] - b[1])
            if abs(cr) < 1e-9 * la * lc:
                out.pop(i)
                changed = True
                break
    return out


def area_centroid(poly):
    """Kapalı çokgenin (s, t) alanı ve ağırlık merkezi. Alan işaretsiz döner."""
    a = cs = ct = 0.0
    m = len(poly)
    for i in range(m):
        s0, t0 = poly[i]
        s1, t1 = poly[(i + 1) % m]
        cr = s0 * t1 - s1 * t0
        a += cr
        cs += (s0 + s1) * cr
        ct += (t0 + t1) * cr
    a *= 0.5
    if abs(a) < 1e-300:
        return 0.0, (0.0, 0.0)
    return abs(a), (cs / (6 * a), ct / (6 * a))


# Diş tepesi / dibinde bırakılan kırpma payı (yüksekliğe oranı). Matkap / vida silindiri
# ile süpürmenin kesim yüzü arasında bu kadar açıklık olmazsa OCC iki yakın eş eksenli yüzeyi
# (süpürme B-spline yaklaşımıyla) ayıramıyor, kesim sessizce hiçbir şey yapmıyordu. %12:
# M6'da çapta ~0.13 mm — ISO 6H / 6g tolerans aralığının içinde; baskıda sivri tepeyi de
# yumuşatır.
TRUNC = 0.12


def tooth_region(spec, d=0.0, engage=1.0):
    """Delik için diş çokgeni (dişli deliğin matkaptan sonra kesilen helisel oluğu).

    (çokgen [(s, t)], matkap düzeyi t_d, yükseklik h') — t dip düzeyinden (ofsetsiz) ölçülür.
    engage: diş kavrama oranı (1: tam profil; 0.75: kılavuz matkabı gibi)."""
    base = outline(spec)
    pts = offset(base, d)
    top = max(q[1] for q in pts)
    low = min(q[1] for q in pts)
    h = top - low
    t_d = top - min(max(float(engage), 0.3), 1.0) * h
    t_cut = max(t_d - TRUNC * h, low + 0.02 * h)
    t_d = max(t_d, t_cut + TRUNC * h)
    poly = list(pts) + [(pts[-1][0], low - h), (pts[0][0], low - h)]
    poly = clean_poly(_clip(poly, 1, t_cut, True), float(spec["P"]))
    return poly, t_d, h


def groove_region(spec, d=0.0):
    """Vida için oluk çokgeni (silindirden kesilen helisel boşluk, iki diş arası).

    (çokgen [(s, t)], silindir düzeyi t_c) — çokgen tepe ortasından tepe ortasına uzanır,
    üstten silindir yüzeyinin biraz içinden kırpılır (çakışık yüz olmaz)."""
    base = outline(spec)
    pts = offset(base, d)
    P = float(spec["P"])
    top = max(q[1] for q in pts)
    low = min(q[1] for q in pts)
    h = top - low
    t_cut = top - 0.01 * h                 # oluk vida silindirinin dışına taşar...
    t_c = t_cut - TRUNC * h                # vida silindiri (tepe düzeyinin biraz altı)
    # ... ama tepe düzlüğünün kenarında kalır: tepe ortasından başlayan pencere
    k = max(range(len(pts)), key=lambda i: pts[i][1])
    flat = [i for i, q in enumerate(pts) if q[1] >= top - 1e-9 * (h or 1)]
    smid = 0.5 * (pts[flat[0]][0] + pts[flat[-1]][0]) if flat else pts[k][0]
    left = [q for q in pts if q[0] > smid + 1e-12]
    right = [(q[0] + P, q[1]) for q in pts[1:] if q[0] < smid - 1e-12]
    win = [(smid, top)] + left + right[0:] + [(smid + P, top)]
    win = _dedupe(win, 1e-12)
    poly = win + [(smid + P, top + h), (smid, top + h)]
    poly = clean_poly(_clip(poly, 1, t_cut, False), P)
    return poly, t_c, h


def check_regions(spec, d_hole, d_screw, engage=1.0):
    """Hesap öncesi denetim: çokgenler adımdan dar olmalı (komşu turlar değmesin).
    Hata metni | ''."""
    P = float(spec["P"])
    lead = P * max(int(spec.get("starts", 1)), 1)
    for nm, (poly, *_r) in (("delik", tooth_region(spec, d_hole, engage)),
                            ("vida", groove_region(spec, d_screw))):
        if len(poly) < 3:
            return f"Diş profili ({nm}) oluşmadı: boşluk / yükseklik çok büyük"
        w = max(q[0] for q in poly) - min(q[0] for q in poly)
        if w >= min(P, lead) * 0.999:
            return (f"Diş profili ({nm}) adımı dolduruyor: tepe / dip düzlüğü ya da boşluk "
                    "küçültülmeli")
    return ""


def thread_volume_per_turn(poly, r_root):
    """Helis süpürmenin tur başına hacmi (Pappus, meridyen profili): 2π r̄ A."""
    a, (_s, t) = area_centroid(poly)
    return 2.0 * math.pi * (r_root + t) * a


# ---------------------------------------------------------------- spec

def spec_from(p, scale_length=1.0):
    """Ayarlardan (sahne biriminde) diş tanımı. p: {"D", "P", "profile", "angle",
    "angle2", "depth", "crest", "rc", "rr", "hand", "starts", "custom", "custom_w"}."""
    prof = p.get("profile", "TRI")
    ang = float(p.get("angle", 60.0))
    if prof == "SQUARE":
        a1 = a2 = 0.0
    elif prof == "BUTT":
        a1, a2 = float(p.get("angle2", 3.0)), max(ang - float(p.get("angle2", 3.0)), 0.0)
    else:
        a1 = a2 = 0.5 * ang
    return {"D": float(p["D"]), "P": float(p["P"]), "profile": prof, "a1": a1, "a2": a2,
            "depth": float(p["depth"]), "crest": float(p.get("crest", 0.0)),
            "rc": float(p.get("rc", 0.0)) if prof in ("ROUND", "TRI", "TRAP", "BUTT",
                                                      "CUSTOM") else 0.0,
            "rr": float(p.get("rr", 0.0)),
            "hand": p.get("hand", "RIGHT"), "starts": max(int(p.get("starts", 1)), 1),
            "custom": p.get("custom"), "custom_w": float(p.get("custom_w", 0.85))}


def radii(spec):
    """(dip yarıçapı, tepe yarıçapı) — temel (ofsetsiz) profil."""
    R = 0.5 * float(spec["D"])
    if spec.get("profile") == "CUSTOM" and spec.get("custom"):
        h = float(spec["depth"])
    else:
        h = _flank_shape(spec)[2]
    return R - h, R


def minor_drill(spec, d_hole=0.0, engage=1.0):
    """Modellenmiş dişli delikte matkap çapı (sahne birimi)."""
    r_root, _R = radii(spec)
    _poly, t_d, _h = tooth_region(spec, d_hole, engage)
    return 2.0 * (r_root + t_d)


def describe(p, fmt=lambda v: f"{v:g}"):
    nm = p.get("size") or f"Ø{fmt(p['D'])}×{fmt(p['P'])}"
    t = nm
    if int(p.get("starts", 1)) > 1:
        t += f" · {int(p['starts'])} ağızlı"
    if p.get("hand") == "LEFT":
        t += " · sol"
    return t


# ---------------------------------------------------------------- vida başı / somun (mm)

# ISO 4762 imbus (silindir başlı): dk, k, s (anahtar), t (yuva derinliği)
SOCKET = {"M1.6": (3.0, 1.6, 1.5, 0.7), "M2": (3.8, 2.0, 1.5, 1.0), "M2.5": (4.5, 2.5, 2.0, 1.1),
          "M3": (5.5, 3.0, 2.5, 1.3), "M4": (7.0, 4.0, 3.0, 2.0), "M5": (8.5, 5.0, 4.0, 2.5),
          "M6": (10.0, 6.0, 5.0, 3.0), "M8": (13.0, 8.0, 6.0, 4.0), "M10": (16.0, 10.0, 8.0, 5.0),
          "M12": (18.0, 12.0, 10.0, 6.0), "M14": (21.0, 14.0, 12.0, 7.0),
          "M16": (24.0, 16.0, 14.0, 8.0), "M20": (30.0, 20.0, 17.0, 10.0),
          "M24": (36.0, 24.0, 19.0, 12.0), "M30": (45.0, 30.0, 22.0, 15.0),
          "M36": (54.0, 36.0, 27.0, 19.0)}
# ISO 4017 altıgen başlı: s (anahtar ağzı), k
HEX = {"M1.6": (3.2, 1.1), "M2": (4.0, 1.4), "M2.5": (5.0, 1.7), "M3": (5.5, 2.0),
       "M4": (7.0, 2.8), "M5": (8.0, 3.5), "M6": (10.0, 4.0), "M8": (13.0, 5.3),
       "M10": (16.0, 6.4), "M12": (18.0, 7.5), "M14": (21.0, 8.8), "M16": (24.0, 10.0),
       "M20": (30.0, 12.5), "M24": (36.0, 15.0), "M30": (46.0, 18.7), "M36": (55.0, 22.5)}
# ISO 10642 havşa başlı imbus (90°): dk, s, t
CSK = {"M2": (4.4, 1.3, 1.2), "M2.5": (5.5, 1.5, 1.5), "M3": (6.72, 2.0, 1.86),
       "M4": (8.96, 2.5, 2.48), "M5": (11.2, 3.0, 3.1), "M6": (13.44, 4.0, 3.72),
       "M8": (17.92, 5.0, 4.96), "M10": (22.4, 6.0, 6.2), "M12": (26.88, 8.0, 7.44),
       "M14": (30.8, 10.0, 8.4), "M16": (33.6, 10.0, 8.8), "M20": (40.32, 12.0, 10.16),
       "M24": (48.0, 14.0, 11.0)}
# ISO 7380 mercimek başlı imbus: dk, k, s
BUTTON = {"M3": (5.7, 1.65, 2.0), "M4": (7.6, 2.2, 2.5), "M5": (9.5, 2.75, 3.0),
          "M6": (10.5, 3.3, 4.0), "M8": (14.0, 4.4, 5.0), "M10": (17.5, 5.5, 6.0),
          "M12": (21.0, 6.6, 8.0), "M16": (28.0, 8.8, 10.0)}
# ISO 4032 altıgen somun: s, m
NUT = {"M1.6": (3.2, 1.3), "M2": (4.0, 1.6), "M2.5": (5.0, 2.0), "M3": (5.5, 2.4),
       "M4": (7.0, 3.2), "M5": (8.0, 4.7), "M6": (10.0, 5.2), "M8": (13.0, 6.8),
       "M10": (16.0, 8.4), "M12": (18.0, 10.8), "M14": (21.0, 12.8), "M16": (24.0, 14.8),
       "M20": (30.0, 18.0), "M24": (36.0, 21.5), "M30": (46.0, 25.6), "M36": (55.0, 31.0)}
# DIN 7984 alçak başlı imbus: k (dk ISO 4762 ile aynı)
LOWHEAD_K = {"M3": 2.0, "M4": 2.8, "M5": 3.5, "M6": 4.0, "M8": 5.0, "M10": 6.0, "M12": 7.0,
             "M16": 9.0, "M20": 11.0, "M24": 13.0}

HEADS = [("SOCKET", "İmbus (silindir)", "ISO 4762 silindir başlı imbus vida"),
         ("HEX", "Altıgen", "ISO 4017 altıgen başlı cıvata"),
         ("CSK", "Havşa başlı", "ISO 10642 havşa başlı (90°) imbus vida"),
         ("BUTTON", "Mercimek", "ISO 7380 mercimek başlı imbus vida"),
         ("CHEESE", "Silindir (yarıklı)", "Yarıklı silindir başlı vida (DIN 84 benzeri)"),
         ("NONE", "Başsız (saplama)", "Başsız: saplama / setskur / dişli çubuk")]
DRIVES = [("HEXSOCKET", "İmbus", "Altıgen anahtar yuvası"),
          ("SLOT", "Düz (yarık)", "Düz tornavida yarığı"),
          ("CROSS", "Yıldız", "Çapraz yarık (basit yıldız)"),
          ("NONE", "Yok", "Yuva yok")]
STD_LENGTHS = (2, 3, 4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 22, 25, 28, 30, 35, 40, 45, 50, 55,
               60, 65, 70, 75, 80, 90, 100, 110, 120, 130, 140, 150, 160, 180, 200)


def _nominal_key(d_mm):
    """Anma çapına en yakın metrik tablo anahtarı (tabloda yoksa None)."""
    for name, d, _p in _ISO_M:
        if abs(d - d_mm) < 0.05:
            return name
    return None


def head_dims(head, d_mm):
    """Vida başı ölçüleri (mm): {"dk", "k", "s", "t", "angle"} — tabloda yoksa çapa
    orantılı. s: anahtar (altıgen başta anahtar ağzı, imbusta anahtar)."""
    key = _nominal_key(d_mm)
    d = d_mm
    if head == "SOCKET":
        v = SOCKET.get(key) or (1.5 * d + 1.0, d, 0.8 * d, 0.5 * d)
        return {"dk": v[0], "k": v[1], "s": v[2], "t": v[3]}
    if head == "LOWHEAD":
        v = SOCKET.get(key) or (1.5 * d + 1.0, d, 0.8 * d, 0.5 * d)
        k = LOWHEAD_K.get(key, 0.65 * d)
        return {"dk": v[0], "k": k, "s": v[2] * 0.8, "t": 0.5 * k}
    if head == "HEX":
        v = HEX.get(key) or (1.6 * d, 0.65 * d)
        return {"dk": v[0], "k": v[1], "s": v[0], "t": 0.0}
    if head == "CSK":
        v = CSK.get(key) or (2.0 * d + 0.5, 0.6 * d, 0.6 * d)
        return {"dk": v[0], "k": 0.5 * (v[0] - d), "s": v[1], "t": v[2], "angle": 90.0}
    if head == "BUTTON":
        v = BUTTON.get(key) or (1.75 * d, 0.55 * d, 0.6 * d)
        return {"dk": v[0], "k": v[1], "s": v[2], "t": 0.55 * v[1]}
    if head == "CHEESE":
        return {"dk": 1.6 * d + 0.5, "k": 0.65 * d, "s": 0.16 * d + 0.3, "t": 0.3 * d}
    return {"dk": d, "k": 0.0, "s": 0.5 * d, "t": 0.5 * d}


def nut_dims(d_mm):
    """Altıgen somun (mm): {"s", "m"}."""
    v = NUT.get(_nominal_key(d_mm)) or (1.6 * d_mm, 0.85 * d_mm)
    return {"s": v[0], "m": v[1]}


def std_length(avail_mm, d_mm=0.0):
    """Sığan en uzun standart boy (mm)."""
    best = STD_LENGTHS[0]
    for L in STD_LENGTHS:
        if L <= avail_mm + 1e-6:
            best = L
    return best


# delik ön ayarları (havşa başı / havşa yuvaları): baş türü → yuva ölçüsü (mm)
CBORE_HEADS = [("SOCKET", "İmbus (ISO 4762)", "Silindir başlı imbus vida yuvası"),
               ("LOWHEAD", "Alçak başlı (DIN 7984)", "Alçak silindir başlı imbus yuvası"),
               ("HEX", "Altıgen (ISO 4017)", "Altıgen baş + lokma anahtarı payı"),
               ("BUTTON", "Mercimek (ISO 7380)", "Mercimek başlı vida yuvası")]
CSK_HEADS = [("ISO10642", "ISO 10642 (90°)", "Havşa başlı imbus vida"),
             ("ISO7046", "ISO 7046 / 2009 (90°)", "Havşa başlı yıldız / düz vida"),
             ("INCH82", "İnç (82°)", "UNC / UNF havşa başlı vida, 82°"),
             ("DIN74", "Ahşap / sac (DIN 74, 90°)", "Geniş havşa")]
_ISO7046 = {"M2": 3.8, "M2.5": 4.7, "M3": 5.5, "M4": 8.4, "M5": 9.3, "M6": 11.3, "M8": 15.8,
            "M10": 18.3, "M12": 22.0, "M16": 29.0, "M20": 36.0}


def cbore_dims(head, d_mm, cbore_table):
    """Kademeli yuva (mm): (çap, derinlik)."""
    key = _nominal_key(d_mm)
    if head == "SOCKET" and key in cbore_table:
        return cbore_table[key]
    h = head_dims(head, d_mm)
    if head == "HEX":
        e = h["s"] / math.cos(math.radians(30))
        return (round(e + 0.4 * d_mm + 2.0, 1), round(h["k"] + 0.5, 1))
    return (round(h["dk"] + max(0.5, 0.1 * d_mm), 1), round(h["k"] + max(0.3, 0.05 * d_mm), 1))


def csink_dims(head, d_mm, csink_table):
    """Konik havşa (mm): (çap, açı)."""
    key = _nominal_key(d_mm)
    if head == "ISO10642" and key in csink_table:
        return csink_table[key], 90.0
    if head == "ISO7046":
        return _ISO7046.get(key, 1.9 * d_mm) + 0.3, 90.0
    if head == "INCH82":
        return round(2.0 * d_mm + 0.4, 2), 82.0
    return round(2.3 * d_mm, 1), 90.0
