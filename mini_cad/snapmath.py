# Copyright (C) 2026 Paul Ogunsola / RenderCraftStudio (FORGE), GPL-3.0-or-later.
# Mini CAD'e kernel/snap_math.py'den olduğu gibi alınmıştır (GPL-3.0-or-later).
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
"""
FORGE — pure 2D snap mathematics (S1, the snap-is-a-constraint doctrine)
========================================================================
Every function here works in SKETCH-PLANE coordinates (u, v) with plain
tuples and floats — no bpy, no mathutils — so the whole module unit-tests
headless. The UI glue (ui/snap_directional.py) converts world↔plane and
owns tolerances-in-pixels, stickiness and drawing; THIS module owns the
geometry.

Doctrine (design of record, step-back 2026-07-26): while you draw, the
cursor does the constraining — a snap silently records the matching
constraint. The functions below are the geometric halves of those snaps:

  direction_snap        — parallel / perpendicular / H / V / 45° (one
                          mechanism: rotate the segment to the best
                          candidate direction, keep its length)
  tangent_dir_at        — tangent direction of a circle at a point (for
                          "start a line FROM a curve" direction locking)
  line_circle_tangent   — snap a segment's END to the tangency point of a
                          circle ("end a line ONTO a curve, kissing it")
  angle_step_snap       — Shift-held 15°/45° stepping from a base direction
  hv_align_snap         — endpoint alignment guides: snap u and/or v to
                          line up with existing points (the dashed-guide
                          inference), including the two-guide intersection
  extension_snap        — snap onto the infinite extension of a segment
"""

from __future__ import annotations

import math

__all__ = [
    "direction_snap", "expand_parallel_perp", "tangent_dir_at",
    "line_circle_tangent", "angle_step_snap", "hv_align_snap",
    "extension_snap", "mid_between_points", "midline_between_segs",
]


def _norm(dx: float, dy: float):
    l = math.hypot(dx, dy)
    if l < 1e-12:
        return None
    return (dx / l, dy / l)


def _undirected_err_deg(d1, d2) -> float:
    """Smallest angle in degrees between two UNDIRECTED directions (0..90)."""
    dot = abs(d1[0] * d2[0] + d1[1] * d2[1])
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(math.acos(dot))


def expand_parallel_perp(ref_dirs):
    """[(dx, dy, tag)] → candidate list [(dx, dy, kind, tag)] with each
    reference direction contributing a 'parallel' candidate and its 90°
    rotation as a 'perpendicular' candidate. Directions need not be unit."""
    out = []
    for dx, dy, tag in ref_dirs:
        n = _norm(dx, dy)
        if n is None:
            continue
        out.append((n[0], n[1], "parallel", tag))
        out.append((-n[1], n[0], "perpendicular", tag))
    return out


def direction_snap(anchor, pt, candidates, tol_deg: float):
    """Snap the segment anchor→pt to the angularly-closest candidate
    direction within tol_deg, PRESERVING the segment's length.

    candidates: [(dx, dy, kind, tag)] — unit-ish directions, UNDIRECTED
    (a candidate matches the segment pointing either way).

    Returns (new_pt, kind, tag, err_deg) for the best candidate, or None
    when nothing is within tolerance. Ties resolve to the smallest error.
    """
    seg = _norm(pt[0] - anchor[0], pt[1] - anchor[1])
    if seg is None:
        return None
    length = math.hypot(pt[0] - anchor[0], pt[1] - anchor[1])
    best = None
    for dx, dy, kind, tag in candidates:
        d = _norm(dx, dy)
        if d is None:
            continue
        err = _undirected_err_deg(seg, d)
        if err > tol_deg:
            continue
        if best is None or err < best[3]:
            # orient the candidate the same way the user is dragging
            sign = 1.0 if (seg[0] * d[0] + seg[1] * d[1]) >= 0.0 else -1.0
            np_ = (anchor[0] + d[0] * sign * length,
                   anchor[1] + d[1] * sign * length)
            best = (np_, kind, tag, err)
    return best


def tangent_dir_at(center, p):
    """Unit tangent direction of a circle centred at `center` at point `p`
    (perpendicular to the radius). None if p is at the centre."""
    r = _norm(p[0] - center[0], p[1] - center[1])
    if r is None:
        return None
    return (-r[1], r[0])


def line_circle_tangent(anchor, pt, center, radius, tol_deg: float):
    """END-tangency snap: if the segment anchor→pt points nearly tangently
    at the circle (center, radius), snap the endpoint ONTO the tangency
    point so the finished line kisses the circle.

    Geometry: from an external anchor there are exactly two tangent lines;
    their tangency points are where the circle meets the Thales circle over
    anchor↔center. Picks the tangency point on the side the cursor favours.

    Returns (tangency_pt, err_deg) or None (anchor inside the circle, zero
    segment, or direction further than tol_deg from either tangent line).
    """
    ax, ay = anchor
    cx, cy = center
    dx, dy = cx - ax, cy - ay
    dist = math.hypot(dx, dy)
    if dist <= radius * (1.0 + 1e-9):
        return None                      # anchor on/inside circle — no external tangent
    seg = _norm(pt[0] - ax, pt[1] - ay)
    if seg is None:
        return None
    # angle of the tangent lines away from the anchor→center direction
    alpha = math.asin(min(1.0, radius / dist))
    base = math.atan2(dy, dx)
    tan_len = math.sqrt(max(dist * dist - radius * radius, 0.0))
    best = None
    for side in (1.0, -1.0):
        ang = base + side * alpha
        tdir = (math.cos(ang), math.sin(ang))
        # DIRECTED error — the segment must head toward the circle, not away
        dot = max(-1.0, min(1.0, seg[0] * tdir[0] + seg[1] * tdir[1]))
        err = math.degrees(math.acos(dot))
        if err > tol_deg:
            continue
        tpt = (ax + tdir[0] * tan_len, ay + tdir[1] * tan_len)
        if best is None or err < best[1]:
            best = (tpt, err)
    return best


def tangent_points(anchor, center, radius):
    """The two tangency points on the circle (center, radius) for tangent
    lines from `anchor`. [] when the anchor is on/inside the circle.
    Used for the rim-slide feel: gliding along the rim NEAR a tangency
    point ticks into exact tangency."""
    ax, ay = anchor
    cx, cy = center
    dx, dy = cx - ax, cy - ay
    dist = math.hypot(dx, dy)
    if dist <= radius * (1.0 + 1e-9):
        return []
    alpha = math.asin(min(1.0, radius / dist))
    base = math.atan2(dy, dx)
    tan_len = math.sqrt(max(dist * dist - radius * radius, 0.0))
    out = []
    for side in (1.0, -1.0):
        ang = base + side * alpha
        out.append((ax + math.cos(ang) * tan_len,
                    ay + math.sin(ang) * tan_len))
    return out


def angle_step_snap(anchor, pt, base_dir, step_deg: float):
    """Shift-stepping: snap the segment anchor→pt to the nearest multiple
    of step_deg measured from base_dir, preserving length. Always snaps
    (this runs only while the modifier is held). Returns (new_pt,
    stepped_angle_deg) or None on a degenerate segment/base."""
    seg_len = math.hypot(pt[0] - anchor[0], pt[1] - anchor[1])
    if seg_len < 1e-12:
        return None
    b = _norm(base_dir[0], base_dir[1])
    if b is None:
        return None
    base = math.atan2(b[1], b[0])
    cur = math.atan2(pt[1] - anchor[1], pt[0] - anchor[0])
    rel = cur - base
    step = math.radians(step_deg)
    stepped = round(rel / step) * step
    ang = base + stepped
    return ((anchor[0] + math.cos(ang) * seg_len,
             anchor[1] + math.sin(ang) * seg_len),
            math.degrees(stepped))


def hv_align_snap(pt, ref_pts, tol: float, skip=None):
    """Alignment-guide snap: pull pt's u and/or v onto the u/v of nearby
    reference points (the dashed-guide inference). Each axis snaps to its
    own closest reference within `tol` (plane units); snapping BOTH gives
    the guide intersection.

    ref_pts: [(u, v, tag)]. `skip`: optional (u, v) to ignore (the anchor —
    aligning to your own rubber-band origin is _snap-to-self_ noise).

    Returns (new_pt, guides) where guides is a list of ("V"|"H", tag,
    (ref_u, ref_v)) — "V" means pt.u locked to ref.u (a VERTICAL guide
    line through the reference), "H" means pt.v locked (horizontal guide).
    Empty guides → pt returned unchanged.
    """
    best_u = None      # (err, ref_u, tag, ref_pt)
    best_v = None
    for (ru, rv, tag) in ref_pts:
        if skip is not None and abs(ru - skip[0]) < 1e-12 \
                and abs(rv - skip[1]) < 1e-12:
            continue
        du = abs(pt[0] - ru)
        dv = abs(pt[1] - rv)
        if du <= tol and (best_u is None or du < best_u[0]):
            best_u = (du, ru, tag, (ru, rv))
        if dv <= tol and (best_v is None or dv < best_v[0]):
            best_v = (dv, rv, tag, (ru, rv))
    if best_u is None and best_v is None:
        return pt, []
    u = best_u[1] if best_u is not None else pt[0]
    v = best_v[1] if best_v is not None else pt[1]
    guides = []
    if best_u is not None:
        guides.append(("V", best_u[2], best_u[3]))
    if best_v is not None:
        guides.append(("H", best_v[2], best_v[3]))
    return (u, v), guides


def mid_between_points(pt, ref_pts, tol: float, max_refs: int = 20):
    """Snap pt onto the MIDPOINT of a pair of reference points — the
    'exactly between those two corners' inference. Considers the
    `max_refs` references closest to the cursor (pair count stays sane).

    ref_pts: [(u, v, tag)]. Returns (mid_pt, (tagA, ptA), (tagB, ptB)) for
    the qualifying pair whose midpoint is closest to pt within `tol`, or
    None. Degenerate pairs (the two refs on top of each other) are skipped.
    """
    if len(ref_pts) < 2:
        return None
    near = sorted(ref_pts,
                  key=lambda r: (r[0] - pt[0]) ** 2 + (r[1] - pt[1]) ** 2)
    near = near[:max_refs]
    best = None
    for i in range(len(near)):
        for j in range(i + 1, len(near)):
            a, b = near[i], near[j]
            if math.hypot(a[0] - b[0], a[1] - b[1]) < tol * 2.0:
                continue                      # refs basically coincident
            m = ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5)
            d = math.hypot(pt[0] - m[0], pt[1] - m[1])
            if d <= tol and (best is None or d < best[3]):
                best = (m, (a[2], (a[0], a[1])), (b[2], (b[0], b[1])), d)
    if best is None:
        return None
    return best[0], best[1], best[2]


def midline_between_segs(pt, segs, tol: float, par_tol_deg: float = 1.5):
    """Snap pt onto the CENTERLINE between two (near-)parallel segments —
    'the middle of those two lines'. The centerline runs along the shared
    direction, halfway between the two lines' perpendicular offsets.

    segs: [((ax, ay), (bx, by), tag)]. Returns
    (snapped_pt, line_a, line_b, (m0, m1)) where line_a/line_b are the
    (seg, tag) pair the centerline sits between and (m0, m1) is a stretch
    of the centerline for drawing. None when no pair qualifies within
    `tol` (perpendicular distance from pt to the centerline).
    """
    dirs = []
    for a, b, tag in segs:
        d = _norm(b[0] - a[0], b[1] - a[1])
        if d is not None:
            dirs.append((a, b, tag, d))
    best = None
    for i in range(len(dirs)):
        for j in range(i + 1, len(dirs)):
            a1, b1, t1, d1 = dirs[i]
            a2, b2, t2, d2 = dirs[j]
            if _undirected_err_deg(d1, d2) > par_tol_deg:
                continue
            # offsets of each line and of pt along the shared normal
            nx, ny = -d1[1], d1[0]
            o1 = a1[0] * nx + a1[1] * ny
            o2 = a2[0] * nx + a2[1] * ny
            if abs(o1 - o2) < tol:            # same line, not a pair
                continue
            om = (o1 + o2) * 0.5
            op = pt[0] * nx + pt[1] * ny
            d = abs(op - om)
            if d <= tol and (best is None or d < best[4]):
                proj = (pt[0] + (om - op) * nx, pt[1] + (om - op) * ny)
                m0 = (proj[0] - d1[0] * 0.5, proj[1] - d1[1] * 0.5)
                m1 = (proj[0] + d1[0] * 0.5, proj[1] + d1[1] * 0.5)
                best = (proj, ((a1, b1), t1), ((a2, b2), t2), (m0, m1), d)
    if best is None:
        return None
    return best[0], best[1], best[2], best[3]


def radial_rail_snap(pt, rails, tol: float):
    """Snap pt onto an arc's RADIAL rail — the line through the arc's
    CENTER and its midpoint (a fillet corner's bisector). Sliding along it
    places a point nearer/farther from the fillet edge while staying on
    the arc's axis of symmetry (user check 2026-07-26).

    rails: [((ox, oy), (dx, dy), tag)] — origin (the center) + unit-ish
    direction. Returns (snapped_pt, tag, origin) for the closest rail
    within `tol` (perpendicular distance), or None.
    """
    best = None
    for (o, d, tag) in rails:
        dn = _norm(d[0], d[1])
        if dn is None:
            continue
        rx, ry = pt[0] - o[0], pt[1] - o[1]
        t = rx * dn[0] + ry * dn[1]
        proj = (o[0] + dn[0] * t, o[1] + dn[1] * t)
        dist = math.hypot(pt[0] - proj[0], pt[1] - proj[1])
        if dist <= tol and (best is None or dist < best[3]):
            best = (proj, tag, o, dist)
    if best is None:
        return None
    return best[0], best[1], best[2]


def mirror_snap(pt, ref_points, segs, tol: float):
    """SYMMETRY guide (S3.5c): snap pt onto the MIRRORED position of an
    existing point across an existing line. For each line (a, b, ltag)
    and reference point (px, py, ptag): candidate = reflect(P, line).
    Returns (snapped_pt, line_tag, src_tag, src_pt, line_seg) for the
    closest candidate within tol, or None. Points sitting ON the line
    mirror onto themselves and are skipped (noise)."""
    best = None
    best_d = tol
    for a, b, ltag in segs:
        dx, dy = b[0] - a[0], b[1] - a[1]
        l2 = dx * dx + dy * dy
        if l2 < 1e-18:
            continue
        for (px, py, ptag) in ref_points:
            t = ((px - a[0]) * dx + (py - a[1]) * dy) / l2
            fx, fy = a[0] + dx * t, a[1] + dy * t      # foot on the line
            cx, cy = 2.0 * fx - px, 2.0 * fy - py      # the reflection
            if math.hypot(cx - px, cy - py) <= 2.0 * tol:
                continue                               # P ≈ on the line
            d = math.hypot(pt[0] - cx, pt[1] - cy)
            if d < best_d:
                best_d = d
                best = ((cx, cy), ltag, ptag, (px, py), (a, b))
    return best


def rhythm_snap(pt, centers, tol: float):
    """Equal-spacing RHYTHM (S3.5b, the Figma smart-guide): for each
    ordered pair (A, B) of reference centres, the next beat is
    C = B + (B - A). The cursor within `tol` of a beat snaps to it.

    centers: [(x, y), ...]. Returns (snapped_pt, A, B) for the closest
    beat, or None. Degenerate pairs (A ≈ B) contribute nothing."""
    best = None
    best_d = tol
    n = len(centers)
    for i in range(n):
        ax, ay = centers[i][0], centers[i][1]
        for j in range(n):
            if i == j:
                continue
            bx, by = centers[j][0], centers[j][1]
            if math.hypot(bx - ax, by - ay) < 1e-9:
                continue
            cx, cy = 2.0 * bx - ax, 2.0 * by - ay
            d = math.hypot(pt[0] - cx, pt[1] - cy)
            if d < best_d:
                best_d = d
                best = ((cx, cy), (ax, ay), (bx, by))
    return best


def extension_snap(pt, segs, tol: float):
    """Snap pt onto the infinite EXTENSION of an existing segment — the
    'continue that line' inference. Only fires when the projection falls
    OUTSIDE the segment (on the segment itself the positional near-edge
    snap already owns the cursor).

    segs: [((ax, ay), (bx, by), tag)]. Returns (new_pt, tag, seg) for the
    closest qualifying extension within `tol`, or None.
    """
    best = None
    for a, b, tag in segs:
        abx, aby = b[0] - a[0], b[1] - a[1]
        l2 = abx * abx + aby * aby
        if l2 < 1e-18:
            continue
        t = ((pt[0] - a[0]) * abx + (pt[1] - a[1]) * aby) / l2
        if -0.02 <= t <= 1.02:
            continue                    # on (or basically on) the segment
        proj = (a[0] + abx * t, a[1] + aby * t)
        d = math.hypot(pt[0] - proj[0], pt[1] - proj[1])
        if d <= tol and (best is None or d < best[3]):
            best = (proj, tag, (a, b), d)
    if best is None:
        return None
    return best[0], best[1], best[2]
