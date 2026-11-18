"""Yüzey onarımı (v0.31.0): yüzey oluşturulamayınca sebebi bul, kullanıcıya sor, onaylanırsa
eğrileri düzeltip yüzeyi yeniden dene.

ui.apply_surface başarısız olunca offer() çağrılır: loopfix.diagnose seçili kenarlarda
sorunları bulur (kenar ortasına değen uç, yakın ama değmeyen uçlar, üst üste binen kenar, çok
kısa parça, taşan / fazla parça, dal). Şerit açıksa "Yüzey onarımı" penceresi açılır; her
öneri "Düzelt" ile tek tek ya da "Hepsini düzelt ve yüzeyi oluştur" ile birlikte uygulanır.
Hiçbir şey sormadan değiştirilmez. Görünümde sorun noktaları halkayla işaretlenir.

Uygulama (eğri verisinde): uç taşıma (tutamaçlar uçla birlikte), kenarı bölme
(split.insert_point: biçim değişmez, bütün referanslar core.remap_insert ile eşlenir),
seçimden çıkarma. Ardından tek geri alma adımı.
"""

import numpy as np

import bpy

from . import core, loopfix

PENDING = {"data": None}        # {"refs", "new_body", "msg", "issues", "tol"}


def _P(ref):
    s = core._ref_segment(ref)
    if s is None:
        return None
    p = [np.array(tuple(v), dtype=np.float64) for v in s["p"]]
    if len(p) == 4:
        return np.array(p)
    a, b = p[0], p[-1]
    return np.array([a, a + (b - a) / 3, a + 2 * (b - a) / 3, b])


def _name(ref):
    ob, si, i = ref
    if isinstance(i, float) and not float(i).is_integer():
        return f"{ob.name} {si + 1}.{int(i) + 1} (2. yarı)"     # benzetimde bölünen kenar
    return f"{ob.name} {si + 1}.{int(i) + 1}"


def _segs(refs):
    segs = [(r, _P(r)) for r in refs]
    return [(r, P) for r, P in segs if P is not None]


def analyze(refs, tol):
    return loopfix.diagnose(_segs(refs), tol, names=_name)


def plan(refs, tol):
    """Bütün adımlar (pencerede gösterilir)."""
    return loopfix.plan(_segs(refs), tol, names=_name,
                        new_ref=lambda r: (r[0], r[1], r[2] + 0.5))


# ---------------------------------------------------------------- eğri verisinde onarım

def _move_end(ref, e, world):
    from mathutils import Vector
    ob, si, i = ref
    sp = ob.data.splines[si]
    loc = ob.matrix_world.inverted() @ Vector(tuple(float(x) for x in world))
    if sp.type == "BEZIER":
        n = len(sp.bezier_points)
        bp = sp.bezier_points[i if e == 0 else (i + 1) % n]
        d = loc - bp.co
        bp.co = bp.co + d
        bp.handle_left = bp.handle_left + d
        bp.handle_right = bp.handle_right + d
    else:
        n = len(sp.points)
        p = sp.points[i if e == 0 else (i + 1) % n]
        p.co = (loc.x, loc.y, loc.z, p.co[3])


def apply(refs, fix):
    """Onarımı uygula; güncel seçim referanslarını döndür."""
    refs = list(refs)
    op = fix["op"]
    if op == "drop":
        return [r for r in refs if r != fix["ref"]]
    if op == "weld":
        for ref, e in fix["ends"]:
            _move_end(ref, e, fix["to"])
        return refs
    if op == "split":
        from . import split
        ob, si, k = fix["ref"]
        if ob.data.splines[si].type != "BEZIER":
            raise core.CadError(f"{_name(fix['ref'])} bezier değil: bölünemiyor")
        split.insert_point(ob, si, k, float(fix["t"]))

        def shift(r):
            o, s, j = r
            return (o, s, j + 1) if (o == ob and s == si and j > k) else r
        out = []
        for r in refs:
            out.append(shift(r))
            if r == (ob, si, k):
                out.append((ob, si, k + 1))      # ikinci yarı (taşan ise sonra çıkar)
        eref, e = fix["end"]
        _move_end(shift(eref), e, fix["to"])
        return out
    raise ValueError(op)


# ---------------------------------------------------------------- akış

def offer(context, refs, new_body, msg, tol):
    """apply_surface başarısız oldu: sorun varsa öneri olarak sakla, pencereyi aç.
    Kullanıcıya eklenecek kısa metin ('' : önerilecek onarım yok)."""
    try:
        issues = analyze(refs, tol)
    except Exception as e:  # teşhis yüzeyi hiç bozmamalı
        print("[BlendCAD] yüzey teşhisi yapılamadı:", e)
        return ""
    if not issues:
        PENDING["data"] = None
        return ""
    try:
        steps = plan(refs, tol)
    except Exception:
        steps = issues
    PENDING["data"] = {"refs": list(refs), "new_body": new_body, "msg": msg,
                       "issues": issues, "plan": steps, "tol": tol}
    n = sum(1 for i in steps if i["fix"])
    running = False
    try:
        from . import ribbon_actions as ra, ribbon_state
        running = ribbon_state.is_running()
        if running:
            ra._open("REPAIR", keep=True)
    except Exception:
        pass
    _redraw()
    if not n:
        tail = " · sebep görünümde işaretlendi"
    elif running:
        tail = f" · {n} onarım önerisi: Yüzey onarımı penceresi"
    else:
        tail = f" · {n} onarım önerisi hazır: BlendCAD şeridini aç (Araçlar → Yüzey onarımı)"
    _message(msg + tail)
    return tail


def _refresh_tools():
    try:
        from . import draw, pick
        if pick._STATE.get("active") is not None:
            op = pick._STATE["active"]
            op.selected.clear()          # segment sıraları değişmiş olabilir
            op.dirty = True
        if draw._STATE.get("active") is not None:
            draw._STATE["active"].dirty = True
    except Exception:
        pass


def _redraw():
    try:
        for win in bpy.context.window_manager.windows:
            for a in win.screen.areas:
                if a.type == "VIEW_3D":
                    a.tag_redraw()
    except Exception:
        pass


def _message(text):
    try:
        from . import ribbon_actions as ra
        ra._msg(text)
    except Exception:
        print("[BlendCAD]", text)


def fix(k=None, retry=True):
    """k. öneriyi (None: hepsini sırayla) uygula, yeniden teşhis et; sorun kalmadıysa yüzeyi
    yeniden dene."""
    d = PENDING["data"]
    if d is None:
        return
    refs, tol = d["refs"], d["tol"]
    done = 0
    try:
        if k is not None:
            f = d["issues"][k]["fix"]
            if f:
                refs = apply(refs, f)
                done = 1
        else:
            for _ in range(24):
                iss = [i for i in analyze(refs, tol) if i["fix"]]
                if not iss:
                    break
                refs = apply(refs, iss[0]["fix"])
                done += 1
    except Exception as e:
        _message(f"Hata: onarım uygulanamadı: {e}")
        return
    try:
        bpy.ops.ed.undo_push(message="BlendCAD: Yüzey onarımı")
    except Exception:
        pass
    _refresh_tools()
    d["refs"] = refs
    d["issues"] = analyze(refs, tol)
    try:
        d["plan"] = plan(refs, tol)
    except Exception:
        d["plan"] = d["issues"]
    if not [i for i in d["issues"] if i["fix"]] and retry:
        create()
    else:
        _message(f"{done} onarım uygulandı · {len(d['issues'])} sorun kaldı")
    _redraw()


def create():
    """Güncel seçimle yüzeyi yeniden dene."""
    d = PENDING["data"]
    if d is None:
        return
    from .ui import apply_surface
    PENDING["data"] = None
    ok, msg = apply_surface(bpy.context, "segs", d["refs"], new_body=d["new_body"])
    _message(msg)
    if ok:
        try:
            from . import ribbon_state
            rb = ribbon_state.STATE.get("ribbon")
            if rb is not None and rb.forms.is_open("REPAIR"):
                rb.forms.close()
        except Exception:
            pass
        _refresh_tools()
    _redraw()


def cancel():
    PENDING["data"] = None
    try:
        from . import ribbon_state
        rb = ribbon_state.STATE.get("ribbon")
        if rb is not None and rb.forms.is_open("REPAIR"):
            rb.forms.close()
    except Exception:
        pass
    _redraw()


def marker_points():
    d = PENDING["data"]
    if d is None:
        return []
    return [(i["kind"], p) for i in d.get("plan", d["issues"]) for p in i["pts"]]
