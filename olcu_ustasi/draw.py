# SPDX-License-Identifier: GPL-3.0-or-later
"""GPU çizim yardımcıları (Vulkan / Metal / OpenGL uyumlu yerleşik gölgelendiriciler)."""
import math

import blf
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

FONT = 0

COL_X = (0.96, 0.27, 0.33, 1.0)
COL_Y = (0.55, 0.86, 0.10, 1.0)
COL_Z = (0.20, 0.56, 0.98, 1.0)
COL_AXIS = (COL_X, COL_Y, COL_Z)
COL_MEASURE = (1.0, 0.78, 0.15, 1.0)
COL_REF = (0.55, 0.85, 1.0, 1.0)
COL_BOX = (1.0, 0.58, 0.15, 0.55)
COL_BOX_HOVER = (1.0, 0.85, 0.4, 0.30)
COL_TEXT = (1.0, 1.0, 1.0, 1.0)
COL_DIM = (0.75, 0.75, 0.78, 1.0)
COL_BG = (0.06, 0.06, 0.07, 0.78)
COL_PIN = (0.75, 0.55, 1.0, 1.0)

KIND_COLOR = {
    'VERT': (0.35, 1.0, 0.45, 1.0),
    'EDGE_MID': (0.30, 0.90, 1.0, 1.0),
    'EDGE': (1.0, 0.95, 0.25, 1.0),
    'FACE': (0.85, 0.85, 0.90, 1.0),
    'FACE_CENTER': (0.55, 0.75, 1.0, 1.0),
    'PERP': (1.0, 0.40, 0.95, 1.0),
    'BOX_CORNER': (1.0, 0.58, 0.15, 1.0),
    'BOX_MID': (1.0, 0.70, 0.30, 1.0),
    'BOX_FACE': (1.0, 0.70, 0.30, 1.0),
    'BOX_CENTER': (1.0, 0.70, 0.30, 1.0),
    'BOX_EDGE': (1.0, 0.58, 0.15, 1.0),
    'ORIGIN': (1.0, 1.0, 1.0, 1.0),
    'CURSOR': (1.0, 0.35, 0.35, 1.0),
    'FREE': (0.8, 0.8, 0.8, 0.9),
    'AXIS': (1.0, 1.0, 1.0, 1.0),
    'PLANE': (1.0, 1.0, 1.0, 1.0),
}


def ui_scale():
    try:
        import bpy
        return bpy.context.preferences.system.ui_scale or 1.0
    except (AttributeError, ImportError):
        return 1.0


class State:
    """with State(): ... çizim durumunu kaydeder / geri yükler."""

    def __enter__(self):
        self._blend = gpu.state.blend_get()
        self._depth = gpu.state.depth_test_get()
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('NONE')
        return self

    def __exit__(self, *exc):
        gpu.state.blend_set(self._blend)
        gpu.state.depth_test_set(self._depth)
        return False


def _viewport():
    vp = gpu.state.viewport_get()
    return (float(vp[2]), float(vp[3]))


def lines(coords, color, width=2.0, prim='LINES'):
    """3B (POST_VIEW) ya da 2B (POST_PIXEL, z=0) kalın çizgiler."""
    if len(coords) < 2:
        return
    pts = [(c[0], c[1], c[2] if len(c) > 2 else 0.0) for c in coords]
    sh = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
    b = batch_for_shader(sh, prim, {"pos": pts})
    sh.bind()
    sh.uniform_float("viewportSize", _viewport())
    sh.uniform_float("lineWidth", width * ui_scale())
    sh.uniform_float("color", color)
    b.draw(sh)


def dashed(a, b, color, width=1.5, n=None, view=None):
    a = Vector(a)
    b = Vector(b)
    if n is None:
        n = 24
    segs = []
    for i in range(n):
        if i % 2:
            continue
        segs.append(a.lerp(b, i / n))
        segs.append(a.lerp(b, (i + 1) / n))
    lines(segs, color, width)


def tris(coords, color, indices=None):
    sh = gpu.shader.from_builtin('UNIFORM_COLOR')
    pts = [(c[0], c[1], c[2] if len(c) > 2 else 0.0) for c in coords]
    b = batch_for_shader(sh, 'TRIS', {"pos": pts}, indices=indices)
    sh.bind()
    sh.uniform_float("color", color)
    b.draw(sh)


def rect(x, y, w, h, color):
    tris([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], color, [(0, 1, 2), (0, 2, 3)])


def circle_pts(c, r, n=20):
    return [(c[0] + r * math.cos(2 * math.pi * i / n), c[1] + r * math.sin(2 * math.pi * i / n))
            for i in range(n)]


def disc(c, r, color, n=20):
    pts = [tuple(c)] + circle_pts(c, r, n)
    idx = [(0, i + 1, (i + 1) % n + 1) for i in range(n)]
    tris(pts, color, idx)


def ring(c, r, color, width=2.0, n=24):
    pts = circle_pts(c, r, n)
    lines(pts + [pts[0]], color, width, prim='LINE_STRIP')


def marker(kind, p, color=None, size=7.0):
    """Yakalama türüne göre ayırt edilebilir işaret (2B)."""
    if p is None:
        return
    s = size * ui_scale()
    col = color or KIND_COLOR.get(kind, COL_TEXT)
    x, y = p[0], p[1]
    dark = (0, 0, 0, 0.65)
    if kind in ('VERT', 'BOX_CORNER'):
        rect(x - s - 1, y - s - 1, 2 * s + 2, 2 * s + 2, dark)
        q = [(x - s, y - s), (x + s, y - s), (x + s, y + s), (x - s, y + s)]
        lines(q + [q[0]], col, 2.0, 'LINE_STRIP')
        rect(x - 2, y - 2, 4, 4, col)
    elif kind in ('EDGE_MID', 'BOX_MID'):
        t = [(x - s, y - s * 0.8), (x + s, y - s * 0.8), (x, y + s)]
        lines(t + [t[0]], col, 2.0, 'LINE_STRIP')
    elif kind in ('EDGE', 'BOX_EDGE'):
        lines([(x - s, y - s), (x + s, y + s), (x - s, y + s), (x + s, y - s)], col, 2.0)
    elif kind in ('FACE_CENTER', 'BOX_FACE', 'BOX_CENTER'):
        d = [(x, y - s), (x + s, y), (x, y + s), (x - s, y)]
        lines(d + [d[0]], col, 2.0, 'LINE_STRIP')
        rect(x - 1.5, y - 1.5, 3, 3, col)
    elif kind == 'PERP':
        lines([(x - s, y - s), (x + s, y - s), (x - s * 0.3, y - s), (x - s * 0.3, y + s)], col, 2.0)
        lines([(x - s * 0.3, y - s * 0.4), (x + s * 0.3, y - s * 0.4), (x + s * 0.3, y - s * 0.4),
               (x + s * 0.3, y - s)], col, 1.5)
    elif kind == 'ORIGIN':
        ring((x, y), s, col, 2.0)
        disc((x, y), 2.0, col)
    elif kind == 'CURSOR':
        ring((x, y), s, col, 2.0)
        lines([(x - s * 1.4, y), (x + s * 1.4, y), (x, y - s * 1.4), (x, y + s * 1.4)], col, 1.5)
    elif kind == 'FACE':
        ring((x, y), s * 0.8, col, 1.5)
    else:   # serbest / eksen
        lines([(x - s, y), (x + s, y), (x, y - s), (x, y + s)], col, 1.5)


def point(p, color, size=5.0):
    if p is not None:
        disc(p, size * ui_scale() + 1.5, (0, 0, 0, 0.7))
        disc(p, size * ui_scale(), color)


def text_size(s, size):
    blf.size(FONT, size * ui_scale())
    return blf.dimensions(FONT, s)


def text(x, y, s, size=13, color=COL_TEXT, bg=COL_BG, pad=4, align='LEFT', valign='BOTTOM'):
    """Arka planlı metin. Döndürür: (genişlik, yükseklik)."""
    sz = size * ui_scale()
    blf.size(FONT, sz)
    w, h = blf.dimensions(FONT, s)
    h = max(h, sz * 0.75)
    if align == 'CENTER':
        x -= w * 0.5
    elif align == 'RIGHT':
        x -= w
    if valign == 'CENTER':
        y -= h * 0.5
    p = pad * ui_scale()
    if bg is not None:
        rect(x - p, y - p, w + 2 * p, h + 2 * p, bg)
    blf.position(FONT, x, y, 0)
    blf.color(FONT, *color)
    blf.draw(FONT, s)
    return w, h


def rich_line(x, y, parts, size=13, bg=COL_BG, pad=5):
    """parts: [(metin, renk), ...] tek satır, ortak arka plan."""
    sz = size * ui_scale()
    blf.size(FONT, sz)
    widths = [blf.dimensions(FONT, t)[0] for t, _ in parts]
    total = sum(widths)
    h = sz * 0.8
    p = pad * ui_scale()
    if bg is not None:
        rect(x - p, y - p, total + 2 * p, h + 2 * p, bg)
    cx = x
    for (t, c), w in zip(parts, widths):
        blf.position(FONT, cx, y, 0)
        blf.color(FONT, *c)
        blf.draw(FONT, t)
        cx += w
    return total, h


def box_lines(box):
    out = []
    for a, b in box.edges():
        out.append(a)
        out.append(b)
    return out
