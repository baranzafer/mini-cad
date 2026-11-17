"""BlendCAD şerit simgeleri: [-1,1]² içinde çizgi parçaları (nokta çiftleri).

2B çizim simgeleri palette.icon_lines'tan gelir; burada 3B özellik, delik / vida ve araç
simgeleri tanımlıdır. bpy / gpu kullanmaz (palette yalnızca gerektiğinde içe aktarılır).
"""

import math


def _poly(pts, closed=False):
    out = []
    for i in range(len(pts) - 1):
        out += [pts[i], pts[i + 1]]
    if closed and len(pts) > 2:
        out += [pts[-1], pts[0]]
    return out


def _arc(cx, cy, r, a0, a1, n=12, ry=None):
    ry = r if ry is None else ry
    return [(cx + r * math.cos(a0 + (a1 - a0) * k / n), cy + ry * math.sin(a0 + (a1 - a0) * k / n))
            for k in range(n + 1)]


def _dot(x, y, s=0.08):
    return _poly([(x - s, y - s), (x + s, y - s), (x + s, y + s), (x - s, y + s)], True)


def _dash(a, b, n=4):
    out = []
    for k in range(n):
        t0, t1 = (2 * k) / (2 * n - 1), (2 * k + 1) / (2 * n - 1)
        out += [(a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0),
                (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1)]
    return out


# yarı izometrik izdüşüm (x sağa-aşağı, y sola-aşağı, z yukarı)
_C, _S = math.cos(math.radians(30)), math.sin(math.radians(30))


def _iso(x, y, z, ox=0.0, oy=0.0, k=1.0):
    return (ox + (x - y) * _C * k, oy + (z - (x + y) * _S) * k)


def _box(x0, y0, z0, x1, y1, z1, k=1.0, ox=0.0, oy=0.0, hidden=False):
    """Kutu: görünen kenarlar (sağ-ön-üst görünüş)."""
    P = lambda x, y, z: _iso(x, y, z, ox, oy, k)  # noqa: E731
    top = [P(x0, y0, z1), P(x1, y0, z1), P(x1, y1, z1), P(x0, y1, z1)]
    out = _poly(top, True)
    out += _poly([P(x1, y0, z1), P(x1, y0, z0), P(x1, y1, z0), P(x1, y1, z1)])
    out += _poly([P(x1, y1, z0), P(x0, y1, z0), P(x0, y1, z1)])
    if hidden:
        out += _dash(P(x0, y0, z0), P(x1, y0, z0), 3) + _dash(P(x0, y0, z0), P(x0, y1, z0), 3) + \
            _dash(P(x0, y0, z0), P(x0, y0, z1), 3)
    return out


def _dash_arc(cx, cy, r, a0, a1, n=7):
    out = []
    for k in range(n):
        t0 = a0 + (a1 - a0) * (2 * k) / (2 * n - 1)
        t1 = a0 + (a1 - a0) * (2 * k + 1) / (2 * n - 1)
        out += _poly(_arc(cx, cy, r, math.radians(t0), math.radians(t1), 3))
    return out


def _ellipse(cx, cy, rx, ry, a0=0.0, a1=2 * math.pi, n=20):
    return _poly(_arc(cx, cy, rx, a0, a1, n, ry))


def _arrow(x0, y0, x1, y1, h=0.22):
    dx, dy = x1 - x0, y1 - y0
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L
    return _poly([(x0, y0), (x1, y1)]) + \
        _poly([(x1 - ux * h - uy * h * 0.7, y1 - uy * h + ux * h * 0.7), (x1, y1),
               (x1 - ux * h + uy * h * 0.7, y1 - uy * h - ux * h * 0.7)])


def _gear(cx, cy, r0, r1, teeth=8):
    pts = []
    for i in range(teeth * 4):
        a = i * math.pi * 2 / (teeth * 4)
        r = r1 if (i % 4) in (1, 2) else r0
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return _poly(pts, True)


def _hexagon(cx, cy, r, ry=None, rot=0.0):
    ry = r if ry is None else ry
    return _poly([(cx + r * math.cos(rot + k * math.pi / 3), cy + ry * math.sin(rot + k * math.pi / 3))
                  for k in range(6)], True)


def _icon(name):
    P = _poly
    # ------------------------------------------------ eskiz
    if name == "SKETCH_NEW":
        # düzlem paralelkenarı + kalem
        return P([(-0.9, -0.45), (0.15, -0.85), (0.9, -0.35), (-0.15, 0.05)], True) + \
            P([(-0.45, -0.4), (0.2, -0.62)]) + \
            P([(0.05, -0.15), (0.7, 0.75), (0.88, 0.62), (0.22, -0.28), (0.05, -0.15)]) + \
            P([(0.6, 0.6), (0.78, 0.48)])
    if name == "FINISH":
        return P([(-0.75, 0.0), (-0.25, -0.5), (0.8, 0.6)])
    if name == "SHOW":
        return P(_arc(0.0, -0.55, 1.0, math.radians(35), math.radians(145), 12)) + \
            P(_arc(0.0, 0.55, 1.0, math.radians(215), math.radians(325), 12)) + \
            P(_arc(0.0, 0.0, 0.25, 0, 2 * math.pi, 12))
    if name == "AUTOCONS":
        # dik kısıt simgesi + kıvılcım
        return P([(-0.85, -0.7), (0.25, -0.7)]) + P([(-0.85, -0.7), (-0.85, 0.4)]) + \
            P([(-0.85, -0.35), (-0.5, -0.35), (-0.5, -0.7)]) + \
            P([(0.55, 0.15), (0.55, 0.85)]) + P([(0.2, 0.5), (0.9, 0.5)]) + \
            P([(0.32, 0.27), (0.78, 0.73)]) + P([(0.32, 0.73), (0.78, 0.27)])
    if name == "LINKS":
        return P(_arc(-0.3, 0.0, 0.38, math.radians(40), math.radians(320), 12)) + \
            P(_arc(0.3, 0.0, 0.38, math.radians(220), math.radians(500), 12)) + \
            P([(-0.15, 0.0), (0.15, 0.0)])
    # ------------------------------------------------ tel kafes · yüzey
    if name == "WIRE_MESH":
        out = []
        for i in range(3):
            y = -0.6 + i * 0.5
            out += P([(-0.85, y - 0.15), (-0.2, y + 0.05), (0.85, y - 0.1)])
        for x in (-0.85, -0.2, 0.85):
            out += P([(x, -0.75 + (0.15 if x == -0.2 else 0.0)), (x, 0.4 + (0.15 if x == -0.2 else 0.0))])
        return out
    if name == "EDGE_PICK":
        return P([(-0.9, -0.3), (-0.1, -0.75), (0.75, -0.3)]) + \
            P([(-0.9, -0.3), (-0.9, 0.55)]) + P([(-0.1, -0.75), (-0.1, 0.15)]) + \
            P([(-0.1, 0.15), (0.0, 0.2)]) + P([(-0.9, 0.55), (-0.1, 0.15)]) + \
            P([(0.25, 0.1), (0.25, 0.9), (0.45, 0.7), (0.58, 0.95), (0.7, 0.88), (0.57, 0.63),
               (0.85, 0.6)], True)
    if name == "SKETCH3D":
        return _dash(_iso(0, 0, 0, -0.1, -0.35), _iso(1.1, 0, 0, -0.1, -0.35), 3) + \
            _dash(_iso(0, 0, 0, -0.1, -0.35), _iso(0, 1.1, 0, -0.1, -0.35), 3) + \
            _dash(_iso(0, 0, 0, -0.1, -0.35), _iso(0, 0, 1.1, -0.1, -0.35), 3) + \
            P([_iso(0.2 + 0.8 * t, 0.9 - 0.7 * t, 0.2 + 0.9 * math.sin(t * math.pi) * 0.8, -0.1, -0.35)
               for t in [k / 12 for k in range(13)]])
    if name in ("PATCH", "PATCH_HOLE"):
        out = P([(-0.85, -0.55), (-0.3, -0.35), (0.3, -0.7), (0.85, -0.45)]) + \
            P([(-0.85, 0.45), (-0.25, 0.7), (0.3, 0.4), (0.85, 0.6)]) + \
            P([(-0.85, -0.55), (-0.85, 0.45)]) + P([(0.85, -0.45), (0.85, 0.6)])
        if name == "PATCH":
            out += P([(-0.3, -0.42), (-0.25, 0.62)]) + P([(0.3, -0.62), (0.3, 0.45)]) + \
                P([(-0.85, -0.05), (-0.25, 0.15), (0.3, -0.1), (0.85, 0.08)])
        else:
            out += P(_arc(0.0, 0.0, 0.3, 0, 2 * math.pi, 16))
        return out
    if name in ("BLEND", "BLEND_G0"):
        if name == "BLEND_G0":
            return P([(-0.9, -0.55), (0.0, -0.55), (0.6, 0.8)]) + _dot(0.0, -0.55)
        return P([(-0.9, -0.55), (0.0, -0.55)]) + \
            P([(x, -0.55 + 1.35 * ((x) / 0.8) ** 2) for x in [k / 10 * 0.8 for k in range(11)]]) + \
            _dot(0.0, -0.55) + _dash((-0.3, -0.55), (0.35, -0.55), 2)
    if name == "SPLIT_FACE":
        return P([(-0.85, -0.6), (0.85, -0.6), (0.85, 0.6), (-0.85, 0.6)], True) + \
            P([(-0.15, -0.75), (0.05, -0.1), (-0.05, 0.25), (0.15, 0.75)])
    if name == "LOFT":
        return _ellipse(-0.55, -0.55, 0.35, 0.14) + \
            P([(0.25, 0.35), (0.85, 0.35), (0.95, 0.6), (0.35, 0.6)], True) + \
            P([(-0.9, -0.55), (0.25, 0.35)]) + P([(-0.2, -0.55), (0.85, 0.35)]) + \
            P([(-0.55, -0.41), (0.6, 0.6)])
    if name == "RULED":
        return P([(-0.85, -0.6), (-0.2, -0.3), (0.4, -0.55), (0.85, -0.3)]) + \
            P([(-0.85, 0.35), (-0.2, 0.65), (0.4, 0.4), (0.85, 0.65)]) + \
            P([(-0.85, -0.6), (-0.85, 0.35)]) + P([(-0.2, -0.3), (-0.2, 0.65)]) + \
            P([(0.4, -0.55), (0.4, 0.4)]) + P([(0.85, -0.3), (0.85, 0.65)])
    if name == "STITCH":
        out = P([(-0.9, -0.6), (-0.1, -0.6), (-0.1, 0.6), (-0.9, 0.6)]) + \
            P([(0.9, -0.6), (0.1, -0.6), (0.1, 0.6), (0.9, 0.6)])
        for y in (-0.4, 0.0, 0.4):
            out += P([(-0.3, y - 0.12), (0.3, y + 0.12)])
        return out
    if name == "THICKEN":
        return P([(-0.85, -0.05), (-0.3, 0.2), (0.3, -0.1), (0.85, 0.15)]) + \
            P([(-0.85, -0.5), (-0.3, -0.25), (0.3, -0.55), (0.85, -0.3)]) + \
            P([(-0.85, -0.05), (-0.85, -0.5)]) + P([(0.85, 0.15), (0.85, -0.3)]) + \
            _arrow(0.0, 0.1, 0.0, 0.85, 0.18)
    if name == "MIRROR_BODY":
        return P([(-0.15, -0.75), (-0.85, -0.45), (-0.85, 0.45), (-0.15, 0.75)]) + \
            P([(0.15, -0.75), (0.85, -0.45), (0.85, 0.45), (0.15, 0.75)]) + \
            _dash((0.0, -0.95), (0.0, 0.95), 5)
    # ------------------------------------------------ katı
    if name == "BODY":
        return _box(-0.6, -0.6, -0.6, 0.6, 0.6, 0.6, k=0.95, oy=0.15) + \
            P([(0.55, 0.55), (0.95, 0.55)]) + P([(0.75, 0.35), (0.75, 0.75)])
    if name == "REBUILD":
        return P(_arc(0.0, 0.0, 0.7, math.radians(30), math.radians(300), 16)) + \
            P([(0.6, 0.62), (0.62, 0.32), (0.32, 0.3)])
    if name == "EXTRUDE":
        return _box(-0.55, -0.55, -0.55, 0.55, 0.55, 0.25, oy=-0.15) + \
            _arrow(0.0, 0.1, 0.0, 0.95, 0.18)
    if name == "REVOLVE":
        return _dash((-0.75, -0.95), (-0.75, 0.95), 5) + \
            P([(-0.6, -0.6), (0.2, -0.6), (0.2, -0.1), (-0.1, 0.2), (-0.1, 0.6), (-0.6, 0.6)], True) + \
            P(_arc(-0.75, 0.0, 1.55, math.radians(-25), math.radians(25), 8)) + \
            P([(0.55, 0.44), (0.65, 0.66), (0.86, 0.55)])
    if name == "SWEEP":
        return P([(-0.85, -0.7), (-0.4, -0.7)] + _arc(-0.4, 0.0, 0.7, -math.pi / 2, 0.0, 8)[1:] +
                 [(0.3, 0.7)]) + \
            _ellipse(-0.85, -0.7, 0.12, 0.28) + _ellipse(0.3, 0.7, 0.28, 0.12) + \
            P([(-0.85, -0.42), (-0.4, -0.42)] + _arc(-0.4, 0.0, 0.42, -math.pi / 2, 0.0, 8)[1:] +
              [(0.02, 0.7)]) + \
            P([(-0.85, -0.98), (-0.4, -0.98)] + _arc(-0.4, 0.0, 0.98, -math.pi / 2, 0.0, 8)[1:] +
              [(0.58, 0.7)])
    if name in ("BOOL_UNION", "BOOL_DIFF", "BOOL_INT"):
        L = lambda a0, a1, n=12: P(_arc(-0.3, 0.0, 0.55, math.radians(a0), math.radians(a1), n))  # noqa
        R = lambda a0, a1, n=12: P(_arc(0.3, 0.0, 0.55, math.radians(a0), math.radians(a1), n))  # noqa
        dL = lambda a0, a1: _dash_arc(-0.3, 0.0, 0.55, a0, a1)  # noqa
        dR = lambda a0, a1: _dash_arc(0.3, 0.0, 0.55, a0, a1)  # noqa
        if name == "BOOL_UNION":
            return L(57, 303, 16) + R(-123, 123, 16) + \
                P([(-0.55, 0.0), (-0.05, 0.0)]) + P([(-0.3, -0.25), (-0.3, 0.25)])
        if name == "BOOL_DIFF":
            return L(57, 303, 16) + R(123, 237, 8) + dR(-123, 123) + \
                P([(-0.55, 0.0), (-0.1, 0.0)])
        return L(-57, 57, 8) + R(123, 237, 8) + dL(57, 303) + dR(-123, 123)
    if name == "FILLET3D":
        out = P([_iso(0.6, -0.6, 0.2), _iso(0.6, -0.6, -0.6), _iso(0.6, 0.6, -0.6)]) + \
            P([_iso(-0.6, -0.6, 0.6), _iso(0.2, -0.6, 0.6)]) + \
            P([_iso(-0.6, 0.6, 0.6), _iso(0.2, 0.6, 0.6)]) + \
            P([_iso(-0.6, -0.6, 0.6), _iso(-0.6, 0.6, 0.6)]) + \
            P([_iso(0.6, 0.6, -0.6), _iso(0.6, 0.6, 0.2)]) + \
            P([_iso(-0.6, 0.6, 0.6), _iso(-0.6, 0.6, -0.6), _iso(0.6, 0.6, -0.6)])
        for yy in (-0.6, 0.6):
            out += P([_iso(0.2 + 0.4 * math.sin(t), yy, 0.2 + 0.4 * math.cos(t))
                      for t in [k / 8 * math.pi / 2 for k in range(9)]])
        return out
    if name == "CHAMFER3D":
        out = P([_iso(0.6, -0.6, 0.2), _iso(0.6, -0.6, -0.6), _iso(0.6, 0.6, -0.6)]) + \
            P([_iso(-0.6, -0.6, 0.6), _iso(0.2, -0.6, 0.6)]) + \
            P([_iso(-0.6, 0.6, 0.6), _iso(0.2, 0.6, 0.6)]) + \
            P([_iso(-0.6, -0.6, 0.6), _iso(-0.6, 0.6, 0.6)]) + \
            P([_iso(0.6, 0.6, -0.6), _iso(0.6, 0.6, 0.2)]) + \
            P([_iso(-0.6, 0.6, 0.6), _iso(-0.6, 0.6, -0.6), _iso(0.6, 0.6, -0.6)])
        for yy in (-0.6, 0.6):
            out += P([_iso(0.2, yy, 0.6), _iso(0.6, yy, 0.2)])
        out += P([_iso(0.2, -0.6, 0.6), _iso(0.2, 0.6, 0.6)]) + \
            P([_iso(0.6, -0.6, 0.2), _iso(0.6, 0.6, 0.2)])
        return out
    if name == "SHELL":
        return _box(-0.6, -0.6, -0.6, 0.6, 0.6, 0.6, oy=0.05) + \
            P([_iso(-0.4, -0.4, 0.6, 0, 0.05), _iso(0.4, -0.4, 0.6, 0, 0.05),
               _iso(0.4, 0.4, 0.6, 0, 0.05), _iso(-0.4, 0.4, 0.6, 0, 0.05)], True) + \
            P([_iso(0.4, -0.4, 0.6, 0, 0.05), _iso(0.4, -0.4, -0.3, 0, 0.05)]) + \
            P([_iso(0.4, -0.4, -0.3, 0, 0.05), _iso(0.4, 0.4, -0.3, 0, 0.05)]) + \
            P([_iso(-0.4, 0.4, -0.3, 0, 0.05), _iso(0.4, 0.4, -0.3, 0, 0.05)])
    if name in ("PAT3D_R", "PAT3D_C"):
        if name == "PAT3D_R":
            out = []
            for i in range(3):
                out += _box(-0.25, -0.25, -0.25, 0.25, 0.25, 0.25, k=0.85, ox=-0.6 + i * 0.6,
                            oy=-0.2 + i * 0.12)
            return out
        out = _dot(0, 0, 0.06)
        for k in range(6):
            a = k * math.pi / 3 + 0.3
            out += _box(-0.15, -0.15, -0.15, 0.15, 0.15, 0.15, k=0.9, ox=0.62 * math.cos(a),
                        oy=0.62 * math.sin(a))
        return out
    if name == "ORDER":
        out = []
        for i, w in enumerate((1.0, 0.8, 0.9)):
            y = 0.55 - i * 0.55
            out += P([(-0.85, y - 0.18), (-0.5, y - 0.18), (-0.5, y + 0.18), (-0.85, y + 0.18)], True)
            out += P([(-0.3, y), (-0.3 + w * 1.1, y)])
        return out
    # ------------------------------------------------ delik · vida
    if name in ("HOLE", "HOLE_CBORE", "HOLE_CSK", "TAPPED"):
        # kesit görünüşü: blok + delik
        out = P([(-0.9, 0.55), (-0.9, -0.75), (0.9, -0.75), (0.9, 0.55)])
        if name == "HOLE_CBORE":
            out += P([(-0.9, 0.55), (-0.5, 0.55), (-0.5, 0.2), (-0.25, 0.2), (-0.25, -0.75)]) + \
                P([(0.9, 0.55), (0.5, 0.55), (0.5, 0.2), (0.25, 0.2), (0.25, -0.75)])
        elif name == "HOLE_CSK":
            out += P([(-0.9, 0.55), (-0.6, 0.55), (-0.25, 0.2), (-0.25, -0.75)]) + \
                P([(0.9, 0.55), (0.6, 0.55), (0.25, 0.2), (0.25, -0.75)])
        else:
            out += P([(-0.9, 0.55), (-0.3, 0.55), (-0.3, -0.75)]) + \
                P([(0.9, 0.55), (0.3, 0.55), (0.3, -0.75)])
            if name == "TAPPED":
                for y in (0.35, 0.05, -0.25, -0.55):
                    out += P([(-0.3, y), (-0.42, y - 0.12)]) + P([(0.3, y), (0.42, y - 0.12)])
        out += _dash((0.0, 0.85), (0.0, -0.95), 5)
        return out
    if name == "THREAD":
        out = P([(-0.4, -0.9), (-0.4, 0.9)]) + P([(0.4, -0.9), (0.4, 0.9)])
        for k in range(6):
            y = -0.75 + k * 0.28
            out += P([(-0.4, y), (0.4, y + 0.14)])
        return out
    if name == "BOLT":
        out = _hexagon(0.0, 0.62, 0.62, 0.22) + \
            P([(-0.62, 0.62), (-0.62, 0.42)]) + P([(0.62, 0.62), (0.62, 0.42)]) + \
            P([(-0.31, 0.43), (-0.31, 0.23)]) + P([(0.31, 0.43), (0.31, 0.23)]) + \
            P([(-0.62, 0.42), (-0.31, 0.23), (0.31, 0.23), (0.62, 0.42)]) + \
            P([(-0.25, 0.23), (-0.25, -0.9), (0.25, -0.9), (0.25, 0.23)])
        for k in range(5):
            y = -0.8 + k * 0.2
            out += P([(-0.25, y), (0.25, y + 0.1)])
        return out
    if name == "NUT":
        return _hexagon(0.0, 0.0, 0.85, rot=math.pi / 6) + P(_arc(0, 0, 0.4, 0, 2 * math.pi, 16)) + \
            P(_arc(0, 0, 0.3, 0, 1.6 * math.pi, 12))
    # ------------------------------------------------ araçlar
    if name == "STEP":
        return P([(-0.6, -0.85), (0.6, -0.85), (0.6, 0.45), (0.25, 0.85), (-0.6, 0.85)], True) + \
            P([(0.25, 0.85), (0.25, 0.45), (0.6, 0.45)]) + \
            _arrow(-0.35, -0.3, 0.95, -0.3, 0.2)
    if name == "DIAG":
        return P([(-0.9, -0.1), (-0.5, -0.1), (-0.3, 0.55), (-0.05, -0.7), (0.2, 0.25), (0.35, -0.1),
                  (0.9, -0.1)])
    if name == "REC":
        return P(_arc(0, 0, 0.75, 0, 2 * math.pi, 20)) + P(_arc(0, 0, 0.35, 0, 2 * math.pi, 14)) + \
            P(_arc(0, 0, 0.18, 0, 2 * math.pi, 10))
    if name == "SETTINGS":
        return _gear(0, 0, 0.62, 0.85, 8) + P(_arc(0, 0, 0.28, 0, 2 * math.pi, 14))
    if name == "KERNEL":
        return _hexagon(0.0, 0.0, 0.85, rot=math.pi / 2) + \
            P([(0.0, 0.0), (0.0, 0.85)]) + P([(0.0, 0.0), (-0.74, -0.42)]) + \
            P([(0.0, 0.0), (0.74, -0.42)])
    # ------------------------------------------------ şerit denetimleri
    if name == "LOGO":
        # tel kafes küp + eğri: BlendCAD işareti
        return _box(-0.55, -0.55, -0.55, 0.55, 0.55, 0.55, k=1.0, oy=0.05, hidden=True)
    if name == "CLOSE":
        return P([(-0.6, -0.6), (0.6, 0.6)]) + P([(-0.6, 0.6), (0.6, -0.6)])
    if name == "COLLAPSE":
        return P([(-0.6, -0.25), (0.0, 0.35), (0.6, -0.25)])
    if name == "EXPAND":
        return P([(-0.6, 0.25), (0.0, -0.35), (0.6, 0.25)])
    if name == "CHEV_L":
        return P([(0.3, -0.6), (-0.3, 0.0), (0.3, 0.6)])
    if name == "CHEV_R":
        return P([(-0.3, -0.6), (0.3, 0.0), (-0.3, 0.6)])
    if name == "PIN":
        return P([(-0.3, 0.8), (0.3, 0.8)]) + P([(-0.2, 0.8), (-0.2, 0.1), (-0.45, -0.1),
                                                 (0.45, -0.1), (0.2, 0.1), (0.2, 0.8)]) + \
            P([(0.0, -0.1), (0.0, -0.85)])
    return None


def icon_lines(name):
    out = _icon(name)
    if out is not None:
        return out
    from . import palette          # 2B çizim simgeleri (gpu gerektirir)
    return palette.icon_lines(name)
