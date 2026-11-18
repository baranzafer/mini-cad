"""BlendCAD model denetimi (v0.32.0): her işlem tamamlanınca gizli uyuşmazlıkları bul, sonra
çıkacak sorunları önceden söyle ve onaylı düzeltme öner.

Sürekli döngü yok: yalnız bir gövdenin TAM hesabı bitince (core.AFTER_FINAL, başarılı ya da
başarısız) ve çizim Bitir'lenince (schedule_curve) kısa bir gecikmeyle bir kez çalışır;
aynı durum için yeniden hesaplanmaz (imza).

Denetimler (bulgu: seviye, metin, işaret noktaları, düzeltmeler):
  Tel kafes  yakın ama değmeyen uç, nokta olmayan kenar ortasına bağlı uç, üst üste binen
             kenar, çok kısa parça  →  uçları kaynat / kenarı böl / fazlayı sil
  Yüzey      kurulamayan yüzeyin döngü sorunu → onarım; neredeyse teğet ama kırık (G0)
             komşu yüzeyler → Teğet (G1) birleşim; kapalı olmayan katı → serbest kenarlar
  Fillet     başarısız: teşhisten en büyük uygulanabilir ölçü, sorunlu kenarı çıkarma, köşe
             modu, işlem sırası, ayrıntılı teşhis · başarılı ama riskli: ölçü komşu kenara
             göre büyük, 4+ kenarlı köşe
  Boolean    başarısız: kenar ölçüsü, işlem sırası, aracı kaydır · etkisiz (hacim değişmedi)
             · aracın yüzü gövde yüzüyle aynı düzlemde (çakışık yüz) → aracı az kaydır ·
             çok kısa yeni kenar (sonraki fillet'i bozar)

Hiçbir düzeltme sormadan yapılmaz: "Öneriler" penceresinde (Araçlar → Öneriler) düğmeyle.
"""

import math
import re
import traceback

import numpy as np

import bpy

from . import core, loopfix

FINDINGS = {}       # anahtar ("body:Ad" / "curve:Ad") -> [bulgu]
_SEEN = {}          # anahtar -> önceki bulgu kimlikleri (yeni olanlar bildirilir)
_PENDING = set()
_SIG = {}


# ---------------------------------------------------------------- zamanlama

def on_final(obj):
    """core.AFTER_FINAL: gövdenin tam hesabı bitti."""
    _schedule("body:" + obj.name)


def schedule_curve(name):
    _schedule("curve:" + name)


def _schedule(key):
    _PENDING.add(key)
    try:
        if not bpy.app.timers.is_registered(_run_pending):
            bpy.app.timers.register(_run_pending, first_interval=0.3)
    except Exception:
        pass


def _run_pending():
    keys = list(_PENDING)
    _PENDING.clear()
    for k in keys:
        try:
            run(k)
        except Exception:
            traceback.print_exc()
    return None


def run(key, notify=True):
    kind, name = key.split(":", 1)
    ob = bpy.data.objects.get(name)
    if ob is None:
        FINDINGS.pop(key, None)
        return []
    if kind == "body":
        if not getattr(ob.cad, "is_cad", False):
            return []
        out = check_body(ob)
    else:
        if ob.type != "CURVE":
            return []
        out = check_curves([ob])
    FINDINGS[key] = out
    ids = {f["id"] for f in out}
    new = [f for f in out if f["id"] not in _SEEN.get(key, set())]
    _SEEN[key] = ids
    if notify and new:
        _announce(name, new, len(out))
    _redraw()
    return out


LEVEL_ORDER = {"error": 0, "warn": 1, "hint": 2}


def _announce(name, new, total):
    new = sorted(new, key=lambda f: LEVEL_ORDER[f["level"]])
    f = new[0]
    more = f" (+{len(new) - 1} öneri daha)" if len(new) > 1 else ""
    text = f"Model denetimi · {name}: {f['msg']}{more} · Araçlar → Öneriler"
    try:
        from . import notify, ribbon_actions as ra, ribbon_state
        import time
        notify.CENTER.push({"error": "error", "warn": "warn", "hint": "hint"}[f["level"]], text,
                           time.monotonic())
        if f["level"] == "error" and ribbon_state.is_running():
            ra._open("REPAIR", keep=True)
    except Exception:
        print("[BlendCAD]", text)


def _redraw():
    try:
        for win in bpy.context.window_manager.windows:
            for a in win.screen.areas:
                if a.type == "VIEW_3D":
                    a.tag_redraw()
    except Exception:
        pass


def _F(fid, level, msg, pts=(), fixes=()):
    return {"id": fid, "level": level, "msg": msg, "pts": [np.asarray(p, dtype=np.float64)
                                                            for p in pts],
            "fixes": list(fixes)}


def _undo(text):
    try:
        bpy.ops.ed.undo_push(message=f"BlendCAD: {text}")
    except Exception:
        pass


def apply_fix(key, fn, label):
    """Pencere düğmesi: düzeltmeyi uygula, geri alma adımı, gövdeyi yenile, yeniden denetle."""
    try:
        msg = fn()
    except Exception as e:
        traceback.print_exc()
        _msg(f"Hata: düzeltme uygulanamadı: {e}")
        return
    _undo(label)
    kind, name = key.split(":", 1)
    ob = bpy.data.objects.get(name)
    if ob is not None and kind == "body" and ob.cad.is_cad:
        core.rebuild(ob)             # AFTER_FINAL yeniden denetler
    run(key, notify=False)
    for k in list(FINDINGS):         # aynı eğriye bağlı diğerleri
        if k != key:
            run(k, notify=False)
    _msg(msg or f"Uygulandı: {label}")
    _refresh_tools()


def _refresh_tools():
    try:
        from . import repair
        repair._refresh_tools()
    except Exception:
        pass


def _msg(text):
    try:
        from . import ribbon_actions as ra
        ra._msg(text)
    except Exception:
        print("[BlendCAD]", text)


def _fmt(v):
    try:
        return core.fmt_len(v)
    except Exception:
        return f"{v:.4g}"


# ---------------------------------------------------------------- tel kafes

def _curve_refs(curves):
    refs = []
    for ob in curves:
        for si, sp in enumerate(ob.data.splines):
            if sp.type not in ("BEZIER", "POLY"):
                continue
            for i in range(core._seg_count(sp)):
                refs.append((ob, si, i))
    return refs


def _ref_name(r):
    from .repair import _name
    return _name(r)


def _used_refs():
    used = set()
    for ob in bpy.data.objects:
        try:
            if not ob.cad.is_cad:
                continue
        except Exception:
            continue
        for pt in ob.cad.patches:
            for r in core.patch_refs(pt):
                used.add(core._ref_key(r))
    return used


def check_curves(curves, tol=None):
    """Eğrilerin gizli uyuşmazlıkları (yakındaki diğer görünür eğrilerle birlikte)."""
    from . import repair
    curves = [c for c in curves if c is not None and c.type == "CURVE"]
    if not curves:
        return []
    tol = tol or 0.001
    refs = _curve_refs(curves)
    segs = [(r, repair._P(r)) for r in refs]
    segs = [(r, P) for r, P in segs if P is not None]
    if not segs or len(segs) > 800:
        return []
    pts = np.vstack([P for _r, P in segs])
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    others = []
    for ob in bpy.context.scene.objects:            # yakındaki diğer eğriler
        if ob.type != "CURVE" or ob in curves or not ob.visible_get():
            continue
        for r in _curve_refs([ob]):
            P = repair._P(r)
            if P is not None and np.all(P.max(axis=0) >= lo - 0.05) and \
                    np.all(P.min(axis=0) <= hi + 0.05):
                others.append((r, P))
    allsegs = segs + others[:400]
    out = []
    used = _used_refs()
    # sıfır boy segmentler (üst üste iki nokta): spline başına tek bulgu, düzeltmesi var
    zero = {}
    for ob0 in curves:                     # doğrudan spline noktalarından (dejenere segment
        mw = ob0.matrix_world              # okuyucuda atlanıyor: üst üste tam aynı noktalar)
        for si, sp in enumerate(ob0.data.splines):
            if sp.type != "BEZIER":
                continue
            bp = sp.bezier_points
            nseg = core._seg_count(sp)
            for k in range(nseg):
                a_, b_ = bp[k], bp[(k + 1) % len(bp)]
                if (mw @ a_.co - mw @ b_.co).length <= tol * 0.01 and \
                        (a_.handle_right - a_.co).length <= tol * 0.01 and \
                        (b_.handle_left - b_.co).length <= tol * 0.01:
                    zero.setdefault((ob0.name, si), []).append(
                        ((ob0, si, k), np.array([tuple(mw @ a_.co)] * 4)))
    for r, P in segs:
        if loopfix.length(P) <= tol * 0.01 and \
                not any(r == x[0] for lst in zero.values() for x in lst):
            zero.setdefault((r[0].name, r[1]), []).append((r, P))
    for (oname, si), lst in zero.items():
        ob0 = lst[0][0][0]
        sp = ob0.data.splines[si]
        ks = [r[2] for r, _P in lst]
        ok_fix = sp.type == "BEZIER" and not (sp.use_cyclic_u and
                                              max(ks) == len(sp.bezier_points) - 1)
        fixes = [("Fazla noktaları kaldır", (lambda o=oname, si=si, ks=tuple(ks):
                                             remove_zero_segments(o, si, ks)), "DELETE")] \
            if ok_fix else []
        out.append(_F(f"wire:ZERO:{oname}/{si}", "warn",
                      f"{oname} eğri {si + 1}: {len(ks)} sıfır boy parça (aynı yerde üst üste "
                      "noktalar). Görünmez ama kenar seçimi, yüzey bölme ve fillet bu noktada "
                      "takılır; o kenardan kurulan yüzey fazladan köşe görür", [lst[0][1][0]],
                      fixes))
    zero_keys = {core._ref_key(r) for lst in zero.values() for r, _P in lst}
    allsegs = [(r, P) for r, P in allsegs if core._ref_key(r) not in zero_keys]
    for k, iss in enumerate(loopfix.scan(allsegs, tol, names=_ref_name)):
        fx = iss["fix"]
        mine = any(c.name == r[0].name for c in curves for r in _issue_refs(fx))
        if not mine:
            continue
        fixes = []
        if fx["op"] in ("weld", "split"):
            label = {"weld": "Uçları kaynat", "split": "Kenarı böl ve kaynat"}[fx["op"]]
            fixes.append((label, (lambda fx=fx: _wire_fix(fx)), "SPLIT" if fx["op"] == "split"
                          else "CLOSE_LOOP"))
        elif fx["op"] == "drop":
            r = fx["ref"]
            sp = r[0].data.splines[r[1]]
            if core._seg_count(sp) == 1 and core._ref_key(r) not in used:
                fixes.append(("Fazla eğriyi sil", (lambda r=r: _delete_spline(r)), "DELETE"))
        fid = f"wire:{iss['kind']}:" + ",".join(f"{a.name}/{b}/{c}" for a, b, c in
                                                 _issue_refs(fx))
        out.append(_F(fid, "warn" if iss["kind"] in ("TJUNC", "GAP") else "hint",
                      iss["msg"], iss["pts"], fixes))
    return out


def remove_zero_segments(obname, si, ks):
    """Sıfır boy segmentlerin fazla noktalarını kaldır; eğrinin biçimi ve bağlı bütün
    referanslar korunur.

    Blender'ın Python API'si tek bezier noktası silemez; edit modda silme arka planda sessizce
    hiçbir şey yapmıyordu (ölçüldü). Bu yüzden spline fazla noktalar olmadan YENİDEN yazılır:
    önce segment / nokta referansları core.remap_remove ile, sonra spline'ın sona taşınması
    core.remap_splines ile eşlenir (Taslağa al'daki gibi). Nokta sayısı doğrulanır."""
    ob = bpy.data.objects[obname]
    from . import split
    split._check_insertable(ob, si)          # desen / yansıtma ilişkisindeki spline'a dokunma
    sp = ob.data.splines[si]
    if sp.type != "BEZIER":
        raise core.CadError("Yalnız bezier eğride yapılabilir")
    bps = sp.bezier_points
    n = len(bps)
    ks = sorted(set(int(k) for k in ks))
    if any(k + 1 >= n for k in ks):
        raise core.CadError("Kapanış kenarındaki nokta bu yolla kaldırılamaz")
    rec = [{"co": p.co.copy(), "hl": p.handle_left.copy(), "hr": p.handle_right.copy(),
            "tl": p.handle_left_type, "tr": p.handle_right_type,
            "radius": p.radius, "tilt": p.tilt} for p in bps]
    runs = []                                # ardışık sıfır boy parçalar: [ilk k, son k]
    for k in ks:
        if runs and runs[-1][1] == k - 1:
            runs[-1][1] = k
        else:
            runs.append([k, k])
    for a_, b_ in runs:                      # kalan nokta sonraki kenarın tutamacını alır
        last = rec[b_ + 1]
        rec[a_]["hr"] = last["hr"].copy()
        rec[a_]["tr"] = last["tr"] if last["tr"] in ("VECTOR", "FREE") else "FREE"
        if rec[a_]["tl"] in ("AUTO", "ALIGNED"):
            rec[a_]["tl"] = "FREE"
    drop = {k + 1 for k in ks}
    keep = [r for i, r in enumerate(rec) if i not in drop]
    attrs = {"use_cyclic_u": sp.use_cyclic_u, "resolution_u": sp.resolution_u,
             "material_index": sp.material_index, "use_smooth": sp.use_smooth}
    for k in reversed(ks):                   # büyükten küçüğe: küçük sıralar kaymaz
        core.remap_remove(ob, si, k)
    new = ob.data.splines.new("BEZIER")
    new.bezier_points.add(len(keep) - 1)
    for k_, v in attrs.items():
        setattr(new, k_, v)
    for p, r in zip(new.bezier_points, keep):
        p.handle_left_type = p.handle_right_type = "FREE"
        p.co, p.handle_left, p.handle_right = r["co"], r["hl"], r["hr"]
        p.radius, p.tilt = r["radius"], r["tilt"]
    for p, r in zip(new.bezier_points, keep):
        p.handle_left_type, p.handle_right_type = r["tl"], r["tr"]
    ob.data.splines.remove(ob.data.splines[si])
    last = len(ob.data.splines) - 1
    core.remap_splines(ob, lambda j: last if j == si else (j - 1 if j > si else j))
    got = len(ob.data.splines[last].bezier_points)
    if got != n - len(drop):
        raise core.CadError(f"Doğrulama başarısız: {got} nokta (beklenen {n - len(drop)})")
    return f"{obname} eğri {si + 1}: {len(ks)} fazla nokta kaldırıldı (eğri sona taşındı, " \
        "bağlı yüzeyler korundu)"


def _issue_refs(fx):
    if fx["op"] == "drop":
        return [fx["ref"]]
    if fx["op"] == "weld":
        return [r for r, _e in fx["ends"]]
    return [fx["ref"], fx["end"][0]]


def _wire_fix(fx):
    from . import repair
    refs = _issue_refs(fx)
    repair.apply(refs, fx)
    return "Tel kafes düzeltildi"


def _delete_spline(r):
    from . import links
    links.remove_splines(r[0], [r[1]])
    return f"{_ref_name(r)} silindi"


# ---------------------------------------------------------------- gövde

def check_body(ob):
    p = ob.cad
    out = []
    for fn in (_check_patches, _check_open, _check_seams, _check_fillets, _check_booleans,
               _check_holes, _check_body_wires):
        try:
            out += fn(ob, p)
        except Exception:
            traceback.print_exc()
    return out


def _check_patches(ob, p):
    from . import repair
    out = []
    for idx, pt in enumerate(p.patches):
        if not pt.enabled:
            continue
        if not pt.ok:
            refs = core.patch_refs(pt)
            try:
                iss = repair.analyze(refs, p.join_tol) if refs else []
            except Exception:
                iss = []
            fixes = []
            if any(i["fix"] for i in iss):
                fixes.append(("Hepsini düzelt", (lambda n=pt.name: _fix_patch(ob.name, n)),
                              "PATCH"))
            msg = f"{pt.name} kurulamadı: {pt.info}"
            if iss:
                msg += " · " + " · ".join(i["msg"] for i in iss[:2])
            pts = [q for i in iss for q in i["pts"]]
            out.append(_F(f"patch:{pt.name}:fail", "error", msg, pts, fixes))
        elif "UYARI" in (pt.info or ""):
            fixes = []
            if pt.method != "FILL":
                fixes.append(("Yöntemi Dolgu yap", (lambda n=pt.name: _set_patch(ob.name, n,
                                                                                  "method",
                                                                                  "FILL")),
                              "PATCH"))
            out.append(_F(f"patch:{pt.name}:fold", "warn",
                          f"{pt.name}: {pt.info[pt.info.index('UYARI'):]}", (), fixes))
    return out


def _set_patch(obname, pname, attr, val):
    ob = bpy.data.objects[obname]
    for pt in ob.cad.patches:
        if pt.name == pname:
            setattr(pt, attr, val)
            return f"{pname}: {attr} = {val}"


def _fix_patch(obname, pname):
    from . import repair
    ob = bpy.data.objects[obname]
    pt = next(x for x in ob.cad.patches if x.name == pname)
    refs = core.patch_refs(pt)
    n = 0
    for _ in range(24):
        iss = [i for i in repair.analyze(refs, ob.cad.join_tol) if i["fix"]]
        if not iss:
            break
        refs = repair.apply(refs, iss[0]["fix"])
        n += 1
    pt.segs.clear()
    for o, si, i in refs:
        r = pt.segs.add()
        r.obj, r.spline, r.seg = o, si, int(i)
    return f"{pname}: {n} onarım uygulandı"


def _edge_faces(me):
    """(kenar → yüzler) numpy ile: (kenar sırası dizisi, yüz sırası dizisi) sıralı."""
    nl = len(me.loops)
    le = np.empty(nl, dtype=np.int64)
    me.loops.foreach_get("edge_index", le)
    tot = np.empty(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("loop_total", tot)
    lf = np.repeat(np.arange(len(me.polygons)), tot)
    order = np.argsort(le, kind="stable")
    return le[order], lf[order]


def _check_open(ob, p):
    if not p.make_solid or "Açık kabuk" not in (p.status or ""):
        return []
    me = ob.data
    if not len(me.polygons):
        return []
    ee, _ff = _edge_faces(me)
    cnt = np.bincount(ee, minlength=len(me.edges))
    free = np.nonzero(cnt == 1)[0]
    ev = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", ev)
    ev = ev.reshape(-1, 2)
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    mw = np.array(ob.matrix_world, dtype=np.float64)
    mid = (co[ev[free, 0]] + co[ev[free, 1]]) * 0.5
    pts = list((np.c_[mid, np.ones(len(mid))] @ mw.T)[:, :3]) if len(free) else []
    if not pts:
        return []
    step = max(1, len(pts) // 24)
    m = re.search(r"(\d+) serbest kenar", p.status)
    n = m.group(1) if m else "bazı"
    return [_F("open", "warn", f"Gövde kapalı değil ({n} serbest kenar): boolean birleşim, "
                               "kabuk ve bazı fillet'ler çalışmaz. İşaretli açıklığa yüzey "
                               "ekle (Yüzey → Sınır yüzeyi)", pts[::step])]


def _patch_name(p, i):
    return p.patches[i].name if 0 <= i < len(p.patches) else f"Yüzey {i + 1}"


def _check_seams(ob, p):
    """Komşu yüzeyler neredeyse teğet ama keskin (G0): ışıkta iz, kırık kesişim / fillet."""
    me = ob.data
    at = me.attributes.get("cad_patch")
    if at is None or not len(me.polygons):
        return []
    lab = np.empty(len(at.data), dtype=np.int32)
    at.data.foreach_get("value", lab)
    nrm = np.empty(len(me.polygons) * 3)
    me.polygons.foreach_get("normal", nrm)
    nrm = nrm.reshape(-1, 3)
    ee, ff = _edge_faces(me)
    # yalnız iki yüzlü ve iki farklı yamaya ait kenarlar
    starts = np.r_[0, np.nonzero(np.diff(ee))[0] + 1]
    counts = np.diff(np.r_[starts, len(ee)])
    two = starts[counts == 2]
    f0, f1 = ff[two], ff[two + 1]
    la, lb = lab[f0], lab[f1]
    m = (la >= 0) & (lb >= 0) & (la != lb)
    pairs = {}
    if m.any():
        f0, f1, la, lb, eidx = f0[m], f1[m], la[m], lb[m], ee[two][m]
        ang = np.degrees(np.arccos(np.clip((nrm[f0] * nrm[f1]).sum(axis=1), -1.0, 1.0)))
        ev = np.empty(len(me.edges) * 2, dtype=np.int64)
        me.edges.foreach_get("vertices", ev)
        ev = ev.reshape(-1, 2)
        for a, b, g, e in zip(la.tolist(), lb.tolist(), ang.tolist(), eidx.tolist()):
            pairs.setdefault((min(a, b), max(a, b)), []).append((g, tuple(ev[e])))
    mw = ob.matrix_world
    out = []
    for (a, b), lst in pairs.items():
        if len(lst) < 3:
            continue
        angs = sorted(x[0] for x in lst)
        med = angs[len(angs) // 2]
        eff = [p.surface_blend if p.patches[i].blend == "BODY" else p.patches[i].blend
               for i in (a, b) if i < len(p.patches)]
        if not (1.0 < med < 12.0) or any(e != "SHARP" for e in eff):
            continue
        if all((p.patches[i].info or "").startswith("Düzlem") for i in (a, b)
               if i < len(p.patches)):
            continue                  # iki düzlem: Teğet birleşim düzlemi eğmez, öneri anlamsız
        ek = lst[len(lst) // 2][1]
        pt = np.array(mw @ ((me.vertices[ek[0]].co + me.vertices[ek[1]].co) * 0.5))
        na, nb = _patch_name(p, a), _patch_name(p, b)
        out.append(_F(f"seam:{na}:{nb}", "hint",
                      f"{na} ile {nb} neredeyse teğet ama {med:.1f}° kırık birleşiyor: ışıkta "
                      "iz görünür, bu dikişi kesen boolean / fillet kenarları kırık çıkar. "
                      "Teğet (G1) birleşim yapayım mı?", [pt],
                      [("Teğet (G1) yap", (lambda a=na, b=nb: _blend_pair(ob.name, a, b)),
                        "BLEND")]))
    return out


def _blend_pair(obname, a, b):
    ob = bpy.data.objects[obname]
    for pt in ob.cad.patches:
        if pt.name in (a, b):
            pt.blend = "TANGENT"
    return f"{a} ve {b}: Teğet (G1)"


# ---------------------------------------------------------------- fillet

_NUM = r"([0-9]+(?:\.[0-9]+)?(?:e[-+]?[0-9]+)?)"


def _wire_graph(p):
    """Gövdenin tel kafes grafiği: düğüm (tol) → [(ref, uzunluk)]."""
    from . import repair
    nodes, adj = [], {}

    def node(q):
        for k, n in enumerate(nodes):
            if np.linalg.norm(n - q) <= p.join_tol:
                return k
        nodes.append(q)
        return len(nodes) - 1
    seen = set()
    ends = {}
    for pt in p.patches:
        for r in core.patch_refs(pt):
            key = core._ref_key(r)
            if key in seen:
                continue
            seen.add(key)
            P = repair._P(r)
            if P is None:
                continue
            L = loopfix.length(P)
            a, b = node(P[0]), node(P[3])
            ends[key] = (a, b, L)
            adj.setdefault(a, []).append((key, L))
            adj.setdefault(b, []).append((key, L))
    return nodes, adj, ends


def _check_fillets(ob, p):
    out = []
    if not p.use_bevels:
        return out
    graph = None
    for i, f in enumerate(p.features):
        if not core.is_bevel(f) or not f.enabled:
            continue
        nm = f.name
        if not f.ok:
            out.append(_fillet_fail(ob, p, i, f))
            continue
        if graph is None:
            graph = _wire_graph(p)
        nodes, adj, ends = graph
        mine = {core._ref_key((r.obj, r.spline, r.seg)) for r in f.segs if r.obj is not None}
        touch = {}
        for key in mine:
            if key in ends:
                a, b, _L = ends[key]
                touch[a] = touch.get(a, 0) + 1
                touch[b] = touch.get(b, 0) + 1
        short = None
        for n in touch:
            for key, L in adj.get(n, ()):
                if key not in mine and (short is None or L < short[0]):
                    short = (L, n)
        if short is not None and f.size > 0.45 * short[0]:
            sug = 0.4 * short[0]
            out.append(_F(f"fillet:{nm}:big", "warn",
                          f"{nm} ölçüsü ({_fmt(f.size)}) komşu kenarın ({_fmt(short[0])}) "
                          "yarısına yakın: köşede komşu yüz yutulur, sonraki işlemler bozulabilir. "
                          f"Ölçüyü {_fmt(sug)} yapayım mı?", [nodes[short[1]]],
                          [(f"Ölçü {_fmt(sug)}", (lambda i=i, v=sug: _set_feat(ob.name, i,
                                                                               "size", v)),
                            "FILLET3D")]))
        for n in touch:
            deg = len(adj.get(n, ()))
            if deg >= 4:
                fixes = []
                if p.corner_mode != "EDGEWISE":
                    fixes.append(("Köşe modu: Kenar kenar",
                                  (lambda: _set_body(ob.name, "corner_mode", "EDGEWISE")),
                                  "FILLET2D"))
                out.append(_F(f"fillet:{nm}:deg{n}", "hint",
                              f"{nm}: bu köşede {deg} kenar buluşuyor; köşe yaması zorlanır, "
                              "ölçü büyüyünce fillet başarısız olabilir. Kenarları tek tek "
                              "uygulamak (Kenar kenar) genelde daha büyük ölçüye izin verir",
                              [nodes[n]], fixes))
                break
    return out


def _fillet_fail(ob, p, i, f):
    txt = f.info or ""
    fixes = []
    m = re.search(r"en fazla ≈" + _NUM, txt)
    if m:
        v = float(m.group(1)) * 0.97
        fixes.append((f"Ölçüyü {_fmt(v)} yap (uygulanabilen en büyük)",
                      (lambda v=v: _set_feat(ob.name, i, "size", v)), "FILLET3D"))
    else:
        m = re.search(_NUM + r" ile yapılabiliyor", txt)
        if m:
            v = float(m.group(1))
            fixes.append((f"Ölçüyü {_fmt(v)} yap", (lambda v=v: _set_feat(ob.name, i, "size",
                                                                         v)), "FILLET3D"))
        fixes.append(("En büyük ölçüyü bul (ayrıntılı teşhis)",
                      (lambda: _diagnose(ob.name, i)), "DIAG"))
    if "Kenar kenar" in txt and p.corner_mode != "EDGEWISE":
        fixes.append(("Köşe modu: Kenar kenar",
                      (lambda: _set_body(ob.name, "corner_mode", "EDGEWISE")), "FILLET2D"))
    pts = []
    m = re.search(r"ör\. \(" + r"(-?[0-9.]+), (-?[0-9.]+), (-?[0-9.]+)\)", txt)
    if m and len(f.segs) > 1:
        q = np.array([float(m.group(k)) for k in (1, 2, 3)])
        pts.append(q)
        j = _nearest_seg(f, q)
        if j is not None:
            fixes.append(("Sorunlu kenarı bu fillet'ten çıkar",
                          (lambda j=j: _drop_feat_seg(ob.name, i, j)), "TRIM"))
    if ("işlem sırası" in txt or "önce yapılınca" in txt or "sırasını" in txt):
        k = _first_before(p, i, ("BOOLEAN", "SWEEP"))
        if k is not None:
            fixes.append(("Fillet'i boolean'dan önceye al",
                          (lambda k=k: _move_to(ob.name, i, k)), "ORDER"))
    if not fixes:
        fixes.append(("Ayrıntılı teşhis", (lambda: _diagnose(ob.name, i)), "DIAG"))
    from .bool_overlay import short_error
    return _F(f"fillet:{f.name}:fail", "error", f"{f.name} uygulanamadı: {short_error(txt)}",
              pts, fixes)


def _nearest_seg(f, q):
    from . import repair
    best = None
    for j, r in enumerate(f.segs):
        if r.obj is None:
            continue
        P = repair._P((r.obj, r.spline, r.seg))
        if P is None:
            continue
        d = float(np.min(np.linalg.norm(loopfix.samples(P) - q, axis=1)))
        if best is None or d < best[0]:
            best = (d, j)
    return None if best is None else best[1]


def _set_feat(obname, i, attr, v):
    f = bpy.data.objects[obname].cad.features[i]
    setattr(f, attr, v)
    return f"{f.name}: {attr} {_fmt(v) if attr == 'size' else v}"


def _set_body(obname, attr, v):
    setattr(bpy.data.objects[obname].cad, attr, v)
    return f"{obname}: {attr} = {v}"


def _drop_feat_seg(obname, i, j):
    f = bpy.data.objects[obname].cad.features[i]
    f.segs.remove(j)
    return f"{f.name}: sorunlu kenar çıkarıldı ({len(f.segs)} kenar kaldı)"


def _diagnose(obname, i):
    from . import ribbon_actions as ra
    ra.call("minicad.diagnose_feature", _obj=bpy.data.objects[obname], index=i)
    return "Ayrıntılı teşhis tamamlandı"


def _first_before(p, i, ops):
    for k in range(i):
        if p.features[k].op in ops:
            return k
    return None


def _move_to(obname, i, k):
    p = bpy.data.objects[obname].cad
    p.features.move(i, k)
    return f"{p.features[k].name} işlem sırasında {k + 1}. oldu"


# ---------------------------------------------------------------- boolean

def _check_booleans(ob, p):
    out = []
    if not p.use_booleans:
        return out
    from .bool_overlay import short_error
    for i, f in enumerate(p.features):
        if f.op != "BOOLEAN" or not f.enabled:
            continue
        nm = f.name
        txt = f.info or ""
        tool = f.tool
        cop = _coplanar(ob, p, f) if tool is not None else None
        if not f.ok:
            fixes = []
            if f.edge_size > 0:
                fixes.append(("Kenar ölçüsünü 0 yap",
                              (lambda i=i: _set_feat(ob.name, i, "edge_size", 0.0)), "BOOL_DIFF"))
            if cop is not None:
                fixes.append(cop["fix"])
            if "fillet" in txt.lower() and _first_before(p, i, ("BEVEL",)) is not None:
                k = _first_before(p, i, ("BEVEL",))
                fixes.append(("Boolean'ı fillet'lerden önceye al",
                              (lambda k=k: _move_to(ob.name, i, k)), "ORDER"))
            out.append(_F(f"bool:{nm}:fail", "error", f"{nm} uygulanamadı: {short_error(txt)}",
                          cop["pts"] if cop else (), fixes))
            continue
        if re.search(r"hacim [-+]?0\.0%", txt):
            out.append(_F(f"bool:{nm}:noop", "warn",
                          f"{nm}: hacim değişmedi — araç gövdeye değmiyor ya da yalnız "
                          "yüzeyde temas ediyor; işlem etkisiz", ()))
        if cop is not None:
            out.append(_F(f"bool:{nm}:coplanar", "warn", cop["msg"], cop["pts"], [cop["fix"]]))
        short = _short_bool_edges(ob, p, f)
        if short:
            out.append(_F(f"bool:{nm}:short", "warn",
                          f"{nm} çok kısa ({_fmt(short[0][0])}) yeni kenar üretti: bu kenara "
                          "değen fillet / süpürme başarısız olur. Aracı biraz kaydırmak "
                          "genelde düzeltir", [q for _L, q in short[:6]]))
    return out


# ---------------------------------------------------------------- delik (v0.33.0)

def _check_holes(ob, p):
    out = []
    if not p.use_booleans:
        return out
    from .bool_overlay import short_error
    edges = [np.asarray(e, dtype=np.float64) for e in core._display.get(ob.name, {})
             .get("edges", []) if len(e) >= 2]
    mw = ob.matrix_world
    m3 = mw.to_3x3()
    for i, f in enumerate(p.features):
        if f.op != "HOLE" or not f.enabled:
            continue
        nm = f.name
        if not f.ok:
            fixes = []
            if f.hole_thread != "NONE":
                fixes.append(("Vida ölçüsünden doldur", (lambda i=i: _hole_preset(ob.name, i)),
                              "HOLE"))
            if "Havşa" in (f.info or ""):
                fixes.append(("Havşa ölçülerini çaptan türet",
                              (lambda i=i: _hole_derive(ob.name, i)), "HOLE_CBORE"))
            fixes.append(("Deliği sil", (lambda i=i: _drop_feature(ob.name, i)), "DELETE"))
            out.append(_F(f"hole:{nm}:fail", "error",
                          f"{nm} açılamadı: {short_error(f.info)}", (), fixes))
            continue
        R = 0.5 * max(f.hole_d, f.hole_cb_d if f.hole_kind == "CBORE" else 0.0,
                      f.hole_cs_d if f.hole_kind == "CSINK" else 0.0)
        radii = {0.5 * f.hole_d, R}
        for j, h in enumerate(f.hole_pts):
            co = np.array(mw @ _vec(h.co))
            d = np.array((m3 @ _vec(h.nrm)).normalized())
            depth = f.hole_depth if not f.hole_through else 1e9
            wall = _hole_wall(edges, co, d, R, radii, depth)
            if wall is None:
                continue
            w, q = wall
            need = max(0.5 * R, 1e-6)
            if w < need:
                txt = "yan yüzeyi deliyor" if w < 0 else f"kenara çok yakın: et kalınlığı {_fmt(w)}"
                mv = need - w
                away = co - q
                away -= d * float(away @ d)
                nn = float(np.linalg.norm(away))
                fixes = []
                if nn > 1e-12:
                    fixes.append(("Deliği içeri kaydır (et ≥ yarıçapın yarısı)",
                                  (lambda i=i, j=j: _hole_fix_wall(ob.name, i, j)), "MOVE"))
                fixes.append(("Bu deliği sil", (lambda i=i, j=j: _hole_drop(ob.name, i, j)),
                              "DELETE"))
                out.append(_F(f"hole:{nm}:{j}:wall", "warn",
                              f"{nm} ({j + 1}. yer) {txt} (en az {_fmt(need)} önerilir): vida "
                              "sıkınca kenar kırılır, sonraki fillet / pah bu kenarda zorlanır",
                              [q], fixes))
    return out


def _vec(t):
    from mathutils import Vector
    return Vector(tuple(t))


def _hole_wall(edges, co, d, R, radii, depth):
    """Deliğin eksenine en yakın (kendi ağzı / dibi olmayan) gövde kenarı: (et, nokta)."""
    best = None
    tol_r = max(R * 0.02, 1e-7)
    for P in edges:
        v = P - co
        s = v @ d
        radial = np.linalg.norm(v - np.outer(s, d), axis=1)
        if all(any(abs(r - rr) <= tol_r for rr in radii) for r in radial):
            continue                           # deliğin kendi ağız / kademe çemberi
        m = (s > -R) & (s < depth + R)         # delik boyunca
        if not m.any():
            continue
        k = int(np.argmin(np.where(m, radial, np.inf)))
        w = float(radial[k]) - R
        if best is None or w < best[0]:
            best = (w, P[k])
    return best


def _hole_preset(obname, i):
    from . import hole
    f = bpy.data.objects[obname].cad.features[i]
    hole.apply_preset(f)
    return f"{f.name}: {f.hole_thread} ölçüleri"


def _hole_derive(obname, i):
    f = bpy.data.objects[obname].cad.features[i]
    f.hole_cb_d = max(f.hole_cb_d, f.hole_d * 1.7)
    f.hole_cb_depth = min(max(f.hole_cb_depth, f.hole_d * 0.5), f.hole_depth * 0.8
                          if not f.hole_through else f.hole_cb_depth or f.hole_d)
    f.hole_cs_d = max(f.hole_cs_d, f.hole_d * 2.0)
    return f"{f.name}: havşa ölçüleri çaptan türetildi"


def _drop_feature(obname, i):
    ob = bpy.data.objects[obname]
    nm = ob.cad.features[i].name
    ob.cad.features.remove(i)
    core.forget_cache(obname)
    return f"{nm} silindi"


def _hole_move(obname, i, j, v):
    ob = bpy.data.objects[obname]
    f = ob.cad.features[i]
    h = f.hole_pts[j]
    w = ob.matrix_world @ _vec(h.co)
    from mathutils import Vector
    w = w + Vector(tuple(float(x) for x in v))
    h.co = tuple(ob.matrix_world.inverted() @ w)
    return f"{f.name} {j + 1}. yer {_fmt(float(np.linalg.norm(v)))} kaydırıldı"


def _hole_fix_wall(obname, i, j, rounds=5):
    """Deliği en yakın kenardan uzağa kaydır; her adımda yeniden hesapla ve ölç (delik yanı
    delmişse ilk ölçüm açılmış geometriden yapılır, tek adım yetmez)."""
    ob = bpy.data.objects[obname]
    total = 0.0
    for _ in range(rounds):
        f = ob.cad.features[i]
        mw, m3 = ob.matrix_world, ob.matrix_world.to_3x3()
        h = f.hole_pts[j]
        co = np.array(mw @ _vec(h.co))
        d = np.array((m3 @ _vec(h.nrm)).normalized())
        R = 0.5 * max(f.hole_d, f.hole_cb_d if f.hole_kind == "CBORE" else 0.0,
                      f.hole_cs_d if f.hole_kind == "CSINK" else 0.0)
        edges = [np.asarray(e, dtype=np.float64)
                 for e in core._display.get(ob.name, {}).get("edges", []) if len(e) >= 2]
        wall = _hole_wall(edges, co, d, R, {0.5 * f.hole_d, R},
                          f.hole_depth if not f.hole_through else 1e9)
        need = max(0.5 * R, 1e-6)
        if wall is None or wall[0] >= need * 0.999:
            break
        w, q = wall
        away = co - q
        away -= d * float(away @ d)
        nn = float(np.linalg.norm(away))
        if nn <= 1e-12:
            break
        step = (need - w) * 1.0001
        _hole_move(obname, i, j, away / nn * step)
        total += step
        core.rebuild(ob)
    return f"{ob.cad.features[i].name} {j + 1}. yer {_fmt(total)} içeri kaydırıldı"


def _hole_drop(obname, i, j):
    f = bpy.data.objects[obname].cad.features[i]
    f.hole_pts.remove(j)
    return f"{f.name}: {j + 1}. yer silindi"


def _short_bool_edges(ob, p, f):
    d = core._display.get(ob.name, {})
    near = max(p.join_tol * 20.0, 1e-4)
    out = []
    for uid, poly, _used in d.get("bool_edges", ()):
        if uid != f.uid:
            continue
        P = np.asarray(poly, dtype=np.float64)
        L = float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())
        if L < near:
            out.append((L, P[len(P) // 2]))
    return sorted(out, key=lambda x: x[0])


def _coplanar(ob, p, f):
    """Aracın bir yüzü, gövdenin düzlemsel bir yüzeyiyle aynı düzlemde mi (çakışık yüz)?"""
    tool = f.tool
    try:
        dg = bpy.context.evaluated_depsgraph_get()
        me = tool.evaluated_get(dg).to_mesh()
    except Exception:
        return None
    try:
        mw = np.array(tool.matrix_world, dtype=np.float64)
        n = len(me.polygons)
        if n == 0 or n > 20000:
            return None
        cen = np.empty(n * 3)
        me.polygons.foreach_get("center", cen)
        nor = np.empty(n * 3)
        me.polygons.foreach_get("normal", nor)
        area = np.empty(n)
        me.polygons.foreach_get("area", area)
    finally:
        try:
            tool.evaluated_get(dg).to_mesh_clear()
        except Exception:
            pass
    cen = (np.c_[cen.reshape(-1, 3), np.ones(n)] @ mw.T)[:, :3]
    nor = nor.reshape(-1, 3) @ np.linalg.inv(mw[:3, :3])
    nor /= np.maximum(np.linalg.norm(nor, axis=1)[:, None], 1e-12)
    from . import repair
    eps = max(p.join_tol * 0.1, 1e-6)
    out_n = _patch_normals(ob)
    for pi, pt in enumerate(p.patches):
        if not pt.enabled or not (pt.info or "").startswith("Düzlem"):
            continue
        refs = core.patch_refs(pt)
        P = [repair._P(r) for r in refs]
        P = np.vstack([q for q in P if q is not None]) if refs else None
        if P is None or len(P) < 3:
            continue
        c = P.mean(axis=0)
        _u, _s, vt = np.linalg.svd(P - c)
        pn = vt[2]
        lo, hi = P.min(axis=0) - eps, P.max(axis=0) + eps
        on = (np.abs((cen - c) @ pn) < eps) & (np.abs(nor @ pn) > 0.9999) & \
            np.all(cen >= lo, axis=1) & np.all(cen <= hi, axis=1)
        if not on.any():
            continue
        tn = nor[on][0]
        sh = max(p.join_tol * 0.5, 1e-4)
        bn = out_n.get(pi)
        flush = bn is not None and float(tn @ bn) > 0      # araç yüzü gövdeyle aynı yöne
        cut = f.bool_type in ("CUT", "INTERSECT")
        if cut and not flush:
            continue          # kesim aracı gövdeye dışarıdan değiyor: kaydırma anlamsız
        where = "dışarı" if flush else "gövdeye doğru"
        msg = (f"{f.name}: araç '{tool.name}' yüzü {pt.name} ile aynı düzlemde (çakışık yüz). "
               "OCC boolean'ında ince şerit, kırık kenar ya da başarısızlık sebebidir. Aracı "
               f"{_fmt(sh)} {where} kaydırayım mı?")
        vec = tn * sh         # araç yüzünün normali: flush → dışarı, dış temas → gövdeye

        def fix(tool_name=tool.name, v=vec):
            t = bpy.data.objects[tool_name]
            from mathutils import Vector
            t.location = t.location + Vector(tuple(float(x) for x in v))
            return f"'{tool_name}' {_fmt(float(np.linalg.norm(v)))} kaydırıldı"
        pts = list(cen[on][:6])
        return {"msg": msg, "pts": pts, "fix": ("Aracı kaydır", fix, "MOVE")}
    return None


def _patch_normals(ob):
    """Yama sırası → ortalama dışa bakan normal (gövde mesh'inden, 'cad_patch' ile)."""
    me = ob.data
    at = me.attributes.get("cad_patch")
    if at is None or not len(me.polygons):
        return {}
    lab = np.empty(len(at.data), dtype=np.int32)
    at.data.foreach_get("value", lab)
    nor = np.empty(len(me.polygons) * 3)
    me.polygons.foreach_get("normal", nor)
    nor = nor.reshape(-1, 3) @ np.linalg.inv(np.array(ob.matrix_world, dtype=np.float64)[:3, :3])
    out = {}
    for k in set(lab.tolist()):
        if k < 0:
            continue
        v = nor[lab == k].sum(axis=0)
        n = float(np.linalg.norm(v))
        if n > 1e-9:
            out[k] = v / n
    return out


def _check_body_wires(ob, p):
    curves = []
    for pt in p.patches:
        for r in core.patch_refs(pt):
            if r[0] not in curves:
                curves.append(r[0])
    out = check_curves(curves, p.join_tol)
    for f in out:
        f["id"] = "w/" + f["id"]
    return out


# ---------------------------------------------------------------- arayüz yardımcıları

def all_findings():
    """[(anahtar, ad, [bulgu])] — önce hedef gövde."""
    target = None
    try:
        from .ui import get_target
        t = get_target(bpy.context)
        target = t.name if t is not None else None
    except Exception:
        pass
    items = [(k, k.split(":", 1)[1], v) for k, v in FINDINGS.items()
             if v and bpy.data.objects.get(k.split(":", 1)[1]) is not None]
    items.sort(key=lambda x: (x[1] != target, x[0]))
    seen, out = set(), []                 # aynı bulgu (gövde + eğri taraması) tek yerde
    for k, n, fs in items:
        fs = [f for f in fs if f["msg"] not in seen]
        seen |= {f["msg"] for f in fs}
        if fs:
            out.append((k, n, fs))
    return out


def marker_points(limit=80):
    out = []
    for _k, _n, fs in all_findings():
        for f in fs:
            for q in f["pts"]:
                out.append((f["level"], q))
                if len(out) >= limit:
                    return out
    return out


def check_all():
    for ob in bpy.context.scene.objects:
        try:
            if ob.type == "MESH" and ob.cad.is_cad:
                run("body:" + ob.name, notify=False)
        except Exception:
            traceback.print_exc()
    _redraw()


def register():
    if on_final not in core.AFTER_FINAL:
        core.AFTER_FINAL.append(on_final)


def unregister():
    if on_final in core.AFTER_FINAL:
        core.AFTER_FINAL.remove(on_final)
    try:
        if bpy.app.timers.is_registered(_run_pending):
            bpy.app.timers.unregister(_run_pending)
    except Exception:
        pass
