"""Delik hesapları (v0.33.0; v0.36.0: ağız pahı, havşa üstü pay, modellenmiş diş) — bpy / OCC'siz: standart ölçüler, döndürme profili, hacim.

Delik, ekseni etrafında döndürülen bir profilden kurulan katının gövdeden çıkarılmasıdır
(geometry.apply_holes). Profil (r, s) noktalarıdır: r eksenden uzaklık, s yüzeyden içeri
derinlik (s < 0 yüzeyin üstü). Profil yüzeyin biraz üstünden başlar: araç yüzü gövde
yüzüyle çakışık olmasın (çakışık yüz boolean'da şerit / hata sebebi).

Türler: SIMPLE düz · CBORE havşa başlı (kademeli) · CSINK havşalı · TAPPED dişli (matkap
çapında delik; diş bilgisi saklanır).
Bitiş: mesafe (isteğe bağlı matkap ucu, 118°) ya da tümüyle geçen.

Ölçüler mm cinsinden tablolardır; sahne birimine mm_to_units ile çevrilir.
"""

import math

# ISO metrik kaba diş (ISO 261 / 262): ad → (anma çapı, adım, kılavuz matkabı)
ISO_COARSE = {
    "M2": (2.0, 0.4, 1.6), "M2.5": (2.5, 0.45, 2.05), "M3": (3.0, 0.5, 2.5),
    "M4": (4.0, 0.7, 3.3), "M5": (5.0, 0.8, 4.2), "M6": (6.0, 1.0, 5.0),
    "M8": (8.0, 1.25, 6.8), "M10": (10.0, 1.5, 8.5), "M12": (12.0, 1.75, 10.2),
    "M14": (14.0, 2.0, 12.0), "M16": (16.0, 2.0, 14.0), "M20": (20.0, 2.5, 17.5),
    "M24": (24.0, 3.0, 21.0),
}
SIZES = list(ISO_COARSE)

# Geçme deliği (ISO 273, orta): ad → çap
CLEARANCE = {"M2": 2.4, "M2.5": 2.9, "M3": 3.4, "M4": 4.5, "M5": 5.5, "M6": 6.6, "M8": 9.0,
             "M10": 11.0, "M12": 13.5, "M14": 15.5, "M16": 17.5, "M20": 22.0, "M24": 26.0}

# v0.36.0: ISO 273 ince / kaba geçme (orta: CLEARANCE)
CLEARANCE_FINE = {"M2": 2.2, "M2.5": 2.7, "M3": 3.2, "M4": 4.3, "M5": 5.3, "M6": 6.4, "M8": 8.4,
                  "M10": 10.5, "M12": 13.0, "M14": 15.0, "M16": 17.0, "M20": 21.0, "M24": 25.0}
CLEARANCE_COARSE = {"M2": 2.6, "M2.5": 3.1, "M3": 3.6, "M4": 4.8, "M5": 5.8, "M6": 7.0,
                    "M8": 10.0, "M10": 12.0, "M12": 14.5, "M14": 16.5, "M16": 18.5,
                    "M20": 24.0, "M24": 28.0}

# Havşa başlı (kademeli) — imbus vida (ISO 4762) için: ad → (baş yuvası çapı, derinliği)
CBORE = {"M2": (4.3, 2.0), "M2.5": (5.0, 2.5), "M3": (6.5, 3.3), "M4": (8.0, 4.4),
         "M5": (10.0, 5.4), "M6": (11.0, 6.5), "M8": (15.0, 8.6), "M10": (18.0, 10.8),
         "M12": (20.0, 13.0), "M14": (24.0, 15.0), "M16": (26.0, 17.5), "M20": (33.0, 21.5),
         "M24": (40.0, 25.5)}

# Havşalı — havşa başlı vida (ISO 10642, 90°) için: ad → havşa çapı
CSINK = {"M2": 4.4, "M2.5": 5.5, "M3": 6.6, "M4": 9.0, "M5": 11.0, "M6": 13.0, "M8": 17.2,
         "M10": 21.5, "M12": 25.5, "M14": 28.5, "M16": 32.0, "M20": 40.0, "M24": 48.0}

KINDS = (("SIMPLE", "Düz", "Düz silindirik delik (geçme deliği)"),
         ("CBORE", "Kademeli", "Silindirik yuva + delik: silindir başlı (imbus) vida başı "
          "yüzeyin altına gömülür"),
         ("CSINK", "Konik havşa", "Konik havşa + delik: havşa başlı vidanın başı yüzeyle aynı "
          "hizaya gömülür"),
         ("TAPPED", "Dişli", "İç dişli delik: modellenmiş helisel diş ya da kılavuz matkabı"))


def mm_to_units(mm, scale_length=1.0):
    """mm → sahne birimi (Blender birimi metre, scale_length ile)."""
    return mm * 0.001 / (scale_length or 1.0)


def preset(kind, size, scale_length=1.0):
    """Vida ölçüsünden delik değerleri (sahne biriminde): {"d", "cb_d", "cb_depth", "cs_d"}."""
    u = lambda v: mm_to_units(v, scale_length)  # noqa: E731
    if size not in ISO_COARSE:
        raise ValueError(size)
    out = {"d": u(CLEARANCE[size])}
    if kind == "TAPPED":
        out["d"] = u(ISO_COARSE[size][2])
        out["thread_d"] = u(ISO_COARSE[size][0])
        out["pitch"] = u(ISO_COARSE[size][1])
    if kind == "CBORE":
        out["cb_d"], out["cb_depth"] = u(CBORE[size][0]), u(CBORE[size][1])
    if kind == "CSINK":
        out["cs_d"] = u(CSINK[size])
    return out


def profile(p, through_depth=None):
    """Döndürme profili [(r, s)] (kapalı çokgen, eksen r=0 üzerinde başlar ve biter).

    p: {"kind", "d", "depth", "through", "tip_angle" (derece, 0: düz dip),
        "cb_d", "cb_depth", "cs_d", "cs_angle" (derece)}
    through_depth: tümüyle geçen için kullanılacak derinlik (gövde boyundan büyük)."""
    R = 0.5 * float(p["d"])
    if R <= 0:
        raise ValueError("Delik çapı sıfır")
    through = bool(p.get("through"))
    depth = float(through_depth if through else p["depth"])
    if depth <= 0:
        raise ValueError("Delik derinliği sıfır")
    kind = p.get("kind", "SIMPLE")
    top = max(R * 0.5, depth * 0.02)           # yüzeyin üstüne taşma (çakışık yüz olmasın)
    if p.get("top"):
        top = max(top, float(p["top"]))        # v0.36: dişli delikte süpürmenin üstüne
    if kind in ("SIMPLE", "TAPPED") and float(p.get("mouth_d") or 0.0) > 2.0 * R * 1.001:
        # v0.36: ağız pahı / havşası — konik havşa gibi
        p = dict(p, cs_d=p["mouth_d"], cs_angle=p.get("mouth_angle", 90.0), cs_head=0.0)
        kind = "CSINK"
    tip = 0.0
    ang = float(p.get("tip_angle", 118.0) or 0.0)
    if not through and 1.0 < ang < 179.0:
        tip = R / math.tan(math.radians(ang) * 0.5)
    pts = [(0.0, -top)]
    if kind == "CBORE":
        rc, hc = 0.5 * float(p["cb_d"]), float(p["cb_depth"])
        if rc <= R or hc <= 0 or hc >= depth:
            raise ValueError("Havşa başı: çap delikten büyük, derinlik delikten küçük olmalı")
        pts += [(rc, -top), (rc, hc), (R, hc)]
    elif kind == "CSINK":
        rc = 0.5 * float(p["cs_d"])
        a = math.radians(float(p.get("cs_angle", 90.0))) * 0.5
        if rc <= R or not (0.05 < a < 1.5):
            raise ValueError("Havşa: çap delikten büyük, açı 6°–170° olmalı")
        hc = (rc - R) / math.tan(a)
        hh = max(float(p.get("cs_head") or 0.0), 0.0)   # v0.36: havşa üstü silindirik pay
        if hc + hh >= depth:
            raise ValueError("Havşa derinliği delikten uzun")
        if hh > 0:
            pts += [(rc, -top), (rc, hh), (R, hh + hc)]
        else:
            pts += [(rc + top * math.tan(a), -top), (R, hc)]
    else:
        pts += [(R, -top)]
    pts += [(R, depth)]
    if tip > 0:
        pts += [(0.0, depth + tip)]
    else:
        pts += [(0.0, depth)]
    return pts


def volume_below(prof):
    """Profilin yüzeyin altında (s ≥ 0) kalan kısmının döndürme hacmi (Pappus) — çıkarılan
    malzeme (delik gövdenin içindeyse). Doğrulama için."""
    clipped = _clip_s(prof)
    a = cx = 0.0
    n = len(clipped)
    for i in range(n):
        r0, s0 = clipped[i]
        r1, s1 = clipped[(i + 1) % n]
        cr = r0 * s1 - r1 * s0
        a += cr
        cx += (r0 + r1) * cr
    a *= 0.5
    if abs(a) < 1e-30:
        return 0.0
    rc = cx / (6.0 * a)
    return abs(2.0 * math.pi * rc * a)


def _clip_s(prof):
    """Çokgeni s ≥ 0 yarı düzlemine kırp (Sutherland–Hodgman)."""
    out = []
    n = len(prof)
    for i in range(n):
        a, b = prof[i], prof[(i + 1) % n]
        ina, inb = a[1] >= 0, b[1] >= 0
        if ina:
            out.append(a)
        if ina != inb:
            t = a[1] / (a[1] - b[1])
            out.append((a[0] + (b[0] - a[0]) * t, 0.0))
    return out


def describe(p, fmt=lambda v: f"{v:g}"):
    """Kısa açıklama: 'Havşa başlı Ø6.6 · yuva Ø11×6.5 · 20 derin'."""
    name = dict((k, n) for k, n, _d in KINDS).get(p.get("kind", "SIMPLE"), "Delik")
    t = f"{name} Ø{fmt(p['d'])}"
    if p.get("kind") == "CBORE":
        t += f" · yuva Ø{fmt(p['cb_d'])}×{fmt(p['cb_depth'])}"
    elif p.get("kind") == "CSINK":
        t += f" · havşa Ø{fmt(p['cs_d'])} {p.get('cs_angle', 90):g}°"
    elif float(p.get("mouth_d") or 0.0) > float(p["d"]):
        t += f" · ağız pahı Ø{fmt(p['mouth_d'])}"
    th = p.get("thr")
    if p.get("kind") == "TAPPED" and th:
        t = f"{th.get('name') or p.get('thread') or ''} " + t
        t += " · modellenmiş diş" if th.get("modeled") else " · kozmetik diş"
        if th.get("hand") == "LEFT":
            t += " · sol"
        if int(th.get("starts", 1)) > 1:
            t += f" · {int(th['starts'])} ağız"
    elif p.get("thread"):
        t = f"{p['thread']} " + t
    t += " · tümüyle geçen" if p.get("through") else f" · {fmt(p['depth'])} derin"
    return t
