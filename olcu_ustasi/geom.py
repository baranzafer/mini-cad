# SPDX-License-Identifier: GPL-3.0-or-later
"""Saf geometri yardımcıları: görünüm izdüşümü, ışın / doğru / düzlem, kutu."""
import numpy as np
from mathutils import Matrix, Vector

EPS = 1e-9


class View:
    """Bölge izdüşümü. Yalnızca perspektif matrisine dayanır (testte sahte kurulabilir)."""

    def __init__(self, persmat, width, height):
        self.P = Matrix(persmat)
        self.Pinv = self.P.inverted_safe()
        self.w = float(width)
        self.h = float(height)
        self._np = np.array(self.P, dtype=np.float64)

    @classmethod
    def from_region(cls, region, rv3d):
        return cls(rv3d.perspective_matrix, region.width, region.height)

    def project(self, co):
        v = self.P @ Vector((co[0], co[1], co[2], 1.0))
        if v.w <= 1e-7:
            return None
        return Vector(((v.x / v.w + 1.0) * 0.5 * self.w, (v.y / v.w + 1.0) * 0.5 * self.h))

    def project_np(self, pts):
        """(N,3) -> (N,2) ekran ve (N,) geçerlilik."""
        P = self._np
        h = pts @ P[:3, :3].T + P[:3, 3]
        w = pts @ P[3, :3] + P[3, 3]
        ok = w > 1e-7
        w = np.where(ok, w, 1.0)
        sx = (h[:, 0] / w + 1.0) * 0.5 * self.w
        sy = (h[:, 1] / w + 1.0) * 0.5 * self.h
        return np.stack((sx, sy), axis=1), ok

    def ray(self, x, y):
        nx = 2.0 * x / self.w - 1.0
        ny = 2.0 * y / self.h - 1.0
        a = self.Pinv @ Vector((nx, ny, -1.0, 1.0))
        b = self.Pinv @ Vector((nx, ny, 1.0, 1.0))
        a = a.xyz / a.w
        b = b.xyz / b.w
        d = b - a
        if d.length < EPS:
            d = Vector((0, 0, -1))
        return a, d.normalized()

    def view_dir(self):
        return self.ray(self.w * 0.5, self.h * 0.5)[1]

    def pixel_size_at(self, co):
        """co noktasında 1 pikselin dünya uzunluğu (yaklaşık)."""
        s = self.project(co)
        if s is None:
            return 0.01
        o1, d1 = self.ray(s.x, s.y)
        o2, d2 = self.ray(s.x + 1.0, s.y)
        t = (Vector(co) - o1).dot(d1)
        return ((o2 + d2 * t) - (o1 + d1 * t)).length or 0.01


# ------------------------------------------------------------------ doğru / ışın

def closest_on_line_to_ray(lo, ld, ro, rd):
    """Doğru (lo + t*ld) üzerinde ışına en yakın noktanın t değeri; paralelse None."""
    ld = Vector(ld)
    w0 = Vector(lo) - Vector(ro)
    a = ld.dot(ld)
    b = ld.dot(rd)
    c = rd.dot(rd)
    d = ld.dot(w0)
    e = rd.dot(w0)
    den = a * c - b * b
    if abs(den) < 1e-12:
        return None
    return (b * e - c * d) / den


def closest_on_segment_to_ray(p0, p1, ro, rd):
    d = Vector(p1) - Vector(p0)
    if d.length_squared < 1e-18:
        return Vector(p0), 0.0
    t = closest_on_line_to_ray(p0, d, ro, rd)
    if t is None:
        t = 0.0
    t = max(0.0, min(1.0, t))
    return Vector(p0) + d * t, t


def ray_plane(ro, rd, po, pn):
    den = Vector(rd).dot(pn)
    if abs(den) < 1e-9:
        return None
    t = (Vector(po) - Vector(ro)).dot(pn) / den
    return Vector(ro) + Vector(rd) * t


def seg_dist_2d(p, a, b):
    ab = b - a
    L2 = ab.length_squared
    if L2 < 1e-12:
        return (p - a).length, 0.0
    t = max(0.0, min(1.0, (p - a).dot(ab) / L2))
    return (p - (a + ab * t)).length, t


def foot_on_line(p, a, d):
    """p'nin a + t*d doğrusuna dik izdüşümü (t, nokta)."""
    d = Vector(d)
    L2 = d.length_squared
    if L2 < 1e-18:
        return 0.0, Vector(a)
    t = (Vector(p) - Vector(a)).dot(d) / L2
    return t, Vector(a) + d * t


# --------------------------------------------------------------------- dönüşüm

def scale_matrix(pivot, factors, frame=None):
    """pivot etrafında ölçek. factors: sayı (eşit) ya da 3'lü. frame: eksen takımı (3x3, dik)."""
    p = Vector(pivot)
    if isinstance(factors, (int, float)):
        L = Matrix.Diagonal((factors, factors, factors))
    else:
        R = Matrix(frame) if frame is not None else Matrix.Identity(3)
        L = R @ Matrix.Diagonal(tuple(factors)) @ R.transposed()
    M = L.to_4x4()
    return Matrix.Translation(p) @ M @ Matrix.Translation(-p)


def axis_scale_matrix(pivot, axis, factor):
    """Tek doğrultuda ölçek: I + (f-1) d dT."""
    d = Vector(axis).normalized()
    L = Matrix.Identity(3)
    for i in range(3):
        for j in range(3):
            L[i][j] += (factor - 1.0) * d[i] * d[j]
    p = Vector(pivot)
    return Matrix.Translation(p) @ L.to_4x4() @ Matrix.Translation(-p)


def orthonormal(m3):
    """3x3'ün dönme kısmı (SVD kutupsal ayrışım), det=+1."""
    a = np.array(m3, dtype=np.float64)
    u, s, vt = np.linalg.svd(a)
    r = u @ vt
    if np.linalg.det(r) < 0:
        u[:, -1] *= -1
        r = u @ vt
    return Matrix(r.tolist())


def frame_from_matrix(m4):
    """Nesne matrisinden normalize eksen takımı (gölgesiz dönme)."""
    return orthonormal(Matrix(m4).to_3x3())


def matrices_close(a, b, tol=1e-5):
    sc = max(1.0, max(abs(a[i][j]) for i in range(4) for j in range(4)))
    return all(abs(a[i][j] - b[i][j]) <= tol * sc for i in range(4) for j in range(4))


# -------------------------------------------------------------------------- kutu

class Box:
    """frame (3x3 dik) yönelimli kutu; lo/hi frame koordinatlarında."""

    def __init__(self, lo, hi, frame=None):
        self.lo = Vector(lo)
        self.hi = Vector(hi)
        self.frame = Matrix(frame) if frame is not None else Matrix.Identity(3)

    @property
    def valid(self):
        return all(self.hi[i] >= self.lo[i] for i in range(3))

    @property
    def size(self):
        return self.hi - self.lo

    def axis(self, i):
        return self.frame.col[i].copy()

    def to_world(self, c):
        return self.frame @ Vector(c)

    def local(self, u):
        """u: 0..1 kutu içi oranlar."""
        return Vector(tuple(self.lo[i] + (self.hi[i] - self.lo[i]) * u[i] for i in range(3)))

    def point(self, u):
        return self.to_world(self.local(u))

    @property
    def center(self):
        return self.point((0.5, 0.5, 0.5))

    def bottom_center(self):
        """Dünya Z'ye en çok bakan eksene göre 'alt' yüz merkezi."""
        best, sign = 2, 1.0
        bz = -1.0
        for i in range(3):
            z = abs(self.frame.col[i].z)
            if z > bz:
                bz, best = z, i
                sign = 1.0 if self.frame.col[i].z >= 0 else -1.0
        u = [0.5, 0.5, 0.5]
        u[best] = 0.0 if sign > 0 else 1.0
        return self.point(u)

    def corners(self):
        return [self.point((x, y, z)) for x in (0, 1) for y in (0, 1) for z in (0, 1)]

    def edges(self):
        """12 kenar (dünya noktası çiftleri)."""
        out = []
        for ax in range(3):
            o = [a for a in range(3) if a != ax]
            for s0 in (0, 1):
                for s1 in (0, 1):
                    u0 = [0, 0, 0]
                    u0[o[0]] = s0
                    u0[o[1]] = s1
                    u1 = list(u0)
                    u1[ax] = 1
                    out.append((self.point(u0), self.point(u1)))
        return out

    def face_centers(self):
        """[(eksen, işaret, nokta)] x6."""
        out = []
        for ax in range(3):
            for side in (0, 1):
                u = [0.5, 0.5, 0.5]
                u[ax] = side
                out.append((ax, 1 if side else -1, self.point(u)))
        return out

    def snap_points(self):
        pts = [(c, 'BOX_CORNER') for c in self.corners()]
        pts += [((a + b) * 0.5, 'BOX_MID') for a, b in self.edges()]
        pts += [(c, 'BOX_FACE') for _, _, c in self.face_centers()]
        pts.append((self.center, 'BOX_CENTER'))
        return pts

    def transformed(self, M):
        """Afin dönüşüm sonrası kutu (eksen hizalı ölçekler için kesin)."""
        cs = [M @ c for c in self.corners()]
        F = self.frame
        FT = F.transposed()
        loc = [FT @ c for c in cs]
        lo = Vector(tuple(min(c[i] for c in loc) for i in range(3)))
        hi = Vector(tuple(max(c[i] for c in loc) for i in range(3)))
        return Box(lo, hi, F)


def box_from_points(pts, frame=None):
    """pts: (N,3) numpy dünya noktaları."""
    if pts is None or len(pts) == 0:
        return None
    F = Matrix(frame) if frame is not None else Matrix.Identity(3)
    if frame is not None:
        loc = pts @ np.array(F, dtype=np.float64)   # (F^T p)^T = p^T F
    else:
        loc = pts
    lo = loc.min(axis=0)
    hi = loc.max(axis=0)
    return Box(Vector(lo.tolist()), Vector(hi.tolist()), F)
