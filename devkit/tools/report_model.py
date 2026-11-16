"""Kayıt raporundan (Ctrl+Alt+R) CAD gövdesini birebir kurar — GERÇEK OCC araçları için.

    from report_model import load_report, build_body
    rep = load_report("kayit.txt")
    shape, info, segs = build_body(g, rep, "CAD_Govde")   # g = mini_cad geometry modülü

Rapordan okunanlar:
  * "Tel kafes eğrileri": her spline'ın bezier noktaları (nokta, sol / sağ tutamaç, dünya)
  * "CAD gövdeleri": her yüzeyin döngü kenarları ve kenarların segment referansları
    ('CAD_TelKafes:4.0' = eğri CAD_TelKafes, spline 4, segment 0)
Segment yönleri döngü boyunca uç uca gelecek şekilde çevrilir (gather'daki chain_loops gibi).
"""
import re

import numpy as np

_NUM = r"(-?[\d.]+(?:e-?\d+)?)"
_VEC = r"\(" + _NUM + r", " + _NUM + r", " + _NUM + r"\)"


def _vec(m, i):
    return tuple(float(m.group(i + k)) for k in range(3))


def load_report(path):
    """{"curves": {ad: [spline: {"cyclic", "pts": [(co, sol, sağ)]}]},
        "bodies": {ad: [yüzey: {"name", "method", "loops": [[kenar: [segref]]]}]}}"""
    lines = open(path, encoding="utf-8").read().splitlines()
    curves, bodies = {}, {}
    sec, body, curve, patch, loop, spline = None, None, None, None, None, None
    for ln in lines:
        if ln.startswith("## "):
            if "sonundaki" in ln:          # yalnız ilk (kayıt başındaki) durum okunur
                break
            continue
        if ln.startswith("CAD gövdeleri"):
            sec = "body"
            continue
        if ln.startswith("Tel kafes eğrileri"):
            sec = "curve"
            continue
        if ln and not ln.startswith(" ") and not ln.startswith("-"):
            sec = None if sec == "curve" and ln.endswith(":") else sec
        if sec == "body":
            m = re.match(r"- (\S+)", ln)
            if m:
                body = m.group(1)
                if body in bodies:         # aynı gövde iki kez listelenebilir
                    body = None
                else:
                    bodies[body] = []
                continue
            if body is None:
                continue
            m = re.match(r"\s+yüzey \d+: (.+?) \[(\w+)/", ln)
            if m:
                patch = {"name": m.group(1), "method": m.group(2), "loops": []}
                bodies[body].append(patch)
                continue
            if re.match(r"\s+döngü \d+:", ln) and patch is not None:
                loop = []
                patch["loops"].append(loop)
                continue
            m = re.match(r"\s+kenar \d+: .*?\[(.*?)\]", ln)
            if m and loop is not None:
                refs = re.findall(r"'([^']+):(\d+)\.(\d+)'", m.group(1))
                loop.append([(c, int(s), int(k)) for c, s, k in refs])
        elif sec == "curve":
            m = re.match(r"- (\S+) ·", ln)
            if m:
                curve = m.group(1)
                curves[curve] = []
                continue
            m = re.match(r"\s+spline \d+: (\w+) \d+ nokta kapalı=(\w+)", ln)
            if m and curve is not None:
                spline = {"type": m.group(1), "cyclic": m.group(2) == "True", "pts": []}
                curves[curve].append(spline)
                continue
            m = re.match(r"\s+n\d+: " + _VEC + " sol " + _VEC + " sağ " + _VEC, ln)
            if m and spline is not None:
                spline["pts"].append((_vec(m, 1), _vec(m, 4), _vec(m, 7)))
    return {"curves": curves, "bodies": bodies}


def segment(rep, ref):
    """Segment referansının 4 kontrol noktası."""
    c, s, k = ref
    sp = rep["curves"][c][s]
    P = sp["pts"]
    a, b = P[k], P[(k + 1) % len(P)]
    return [a[0], a[2], b[1], b[0]]


def _close(a, b, tol=2e-3):
    return np.linalg.norm(np.subtract(a, b)) < tol


def _orient_loop(segs):
    """Segmentleri döngü boyunca uç uca gelecek şekilde çevirir."""
    out = [list(s) for s in segs]
    if len(out) > 1:
        a, b = out[0], out[1]
        if not (_close(a[3], b[0]) or _close(a[3], b[3])):
            out[0] = a[::-1]
    for i in range(1, len(out)):
        if not _close(out[i - 1][3], out[i][0]):
            out[i] = out[i][::-1]
    return out


def build_body(g, rep, name, sew_tol=1e-4, preview=False):
    """Gövdeyi geometry.Builder ile kurar. (şekil, bilgi, {segref: kontrol noktaları})"""
    bld = g.Builder()
    faces, used = [], {}
    for patch in rep["bodies"][name]:
        for loop in patch["loops"]:
            refs = [r for side in loop for r in side]
            pts = _orient_loop([segment(rep, r) for r in refs])
            objs = [{"p": [tuple(map(float, q)) for q in p]} for p in pts]
            for r, p in zip(refs, pts):
                used[r] = p
            sides, k = [], 0
            for side in loop:
                sides.append(objs[k:k + len(side)])
                k += len(side)
            f, _label = bld.face(objs, sides, patch["method"], preview)
            faces.append(f)
    shape, info = g.assemble(faces, [], sew_tol, True)
    return shape, info, used


def samples(p, n=64):
    P = np.array(p, float)
    t = np.linspace(0, 1, n)[:, None]
    return (1 - t) ** 3 * P[0] + 3 * (1 - t) ** 2 * t * P[1] + 3 * (1 - t) * t * t * P[2] + \
        t ** 3 * P[3]
