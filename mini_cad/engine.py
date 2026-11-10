"""Hesap motoru: bütün OpenCASCADE işleri burada yapılır.

Bu modül bpy KULLANMAZ. Ya ayrı bir Python sürecinde (engine_host.py, varsayılan) ya da
yedek olarak doğrudan Blender içinde çalışır. Girdi/çıktılar düz Python + numpy verisidir;
OCC şekilleri bu modülün dışına hiç çıkmaz. Böylece:
  * ağır fillet/boolean hesabı sırasında Blender donmaz,
  * OCC içinde bir çökme olursa Blender değil sadece hesap süreci kapanır.
"""

import math
import time
import traceback

import numpy as np

from .errors import CadError

_builders = {}      # gövde adı -> Builder (ortak köşe/kenar/yüz kayıtları)
_bevel_cache = {}   # gövde adı -> (anahtar, şekil, sonuçlar, boolean kenarları)
_final = {}         # gövde adı -> {"shape", "solid", "info"} son tam kalite
_stage_base = {}    # gövde adı -> {aşama anahtarı: fillet öncesi şekil} (hayalet önizleme)
_bool_new = {}      # gövde adı -> {boolean uid: [kenar kaydı]} son tam kalite
_tool_cache = {}    # araç adı -> (anahtar, katı)
_tool_good = {}     # araç adı -> son başarıyla okunan katı


def _geo():
    from . import geometry
    return geometry


# ---------------------------------------------------------------- yardımcılar

def _desc_dist(a_s, a_len, b_s, b_len):
    """İki kenar tanımlayıcısı arasındaki fark (yönden bağımsız)."""
    A, B = np.asarray(a_s, dtype=np.float64), np.asarray(b_s, dtype=np.float64)
    if A.shape != B.shape:
        return float("inf")
    d1 = np.linalg.norm(A - B, axis=1).mean()
    d2 = np.linalg.norm(A - B[::-1], axis=1).mean()
    dc = np.linalg.norm(A.mean(axis=0) - B.mean(axis=0))
    return float(0.5 * min(d1, d2) + dc + 0.5 * abs(a_len - b_len))


def resolve_ref(desc, cands):
    """Kayıtlı kenar tanımını aday kenarlar arasında eşler. Tam eşleşme ya da açık ara en
    yakın tek aday kabul edilir; iki aday neredeyse eşit yakınsa (belirsiz) reddedilir.
    (aday indeksi | None, sebep)"""
    if not cands:
        return None, "kaynak boolean yeni kenar üretmedi"
    sc = sorted((_desc_dist(desc["s"], desc["len"], c["s"], c["len"]), i)
                for i, c in enumerate(cands))
    best, i = sc[0]
    if len(sc) == 1 or best <= 1e-7:
        return i, ""
    second = sc[1][0]
    if second <= best * 1.5 + 1e-9:
        return None, "kenar belirsizleşti (iki aday eşit yakın); kenarı yeniden seç"
    return i, ""


def _mirror_polys(polys, mirrors):
    geometry = _geo()
    out = list(polys)
    for origin, normal in mirrors:
        out += [geometry._reflect(q, origin, normal) for q in out]
    return out


def _tool_shape(spec):
    geometry = _geo()
    name = spec["name"]
    if spec["kind"] == "cad":
        f = _final.get(name)
        if f is None:
            raise CadError(f"'{name}' gövdesi hesaplanamadı")
        if not f["solid"]:
            raise CadError(f"Araç '{name}' kapalı katı değil ({f['info']}); "
                           "aracın bütün yüzeylerini tamamla")
        return f["shape"]
    hit = _tool_cache.get(name)
    if hit is not None and hit[0] == spec["key"]:
        return hit[1]
    if spec.get("verts") is None:
        last = _tool_good.get(name)
        if last is None:
            raise CadError(f"İkincil parça okunamadı: {spec.get('read_error') or 'veri yok'}")
        print("[Mini CAD] ikincil parça okunamadı, son çalışan şekil kullanılıyor")
        return last
    sh = geometry.mesh_to_solid(spec["verts"], spec["polys"])
    _tool_cache[name] = (spec["key"], sh)
    _tool_good[name] = sh
    return sh


def _resolve_geo(name, item, bool_new, tol):
    """Fillet'in gövde kenarı referanslarını o anki boolean kenarlarına çözer.
    (sık örnekli çizgiler, {ref id: güncel tanım}, [hata], {uid: kullanılan aday indeksleri})"""
    geometry = _geo()
    polys, updates, errs, used = [], {}, [], {}
    for g in item.get("geo", ()):
        cands = bool_new.get(g["src"])
        if cands is None:
            errs.append("kaynak boolean bulunamadı ya da bu fillet'ten sonra geliyor")
            continue
        k, why = resolve_ref(g["desc"], cands)
        if k is None:
            errs.append(why)
            continue
        c = cands[k]
        try:
            polys.append(geometry.edge_dense(c["edge"], tol))
        except Exception as e:
            errs.append(f"kenar örneklenemedi: {e}")
            continue
        used.setdefault(g["src"], set()).add(k)
        updates[g["id"]] = {"s": c["s"].tolist(), "len": c["len"]}
    return polys, updates, errs, used


def _ghost_for(shape, item, polys, mirrors, tol):
    geometry = _geo()
    try:
        edges = geometry.match_edges(shape, _mirror_polys(polys, mirrors), tol)
        okf = geometry.two_face_filter(shape)
        edges = [e for e in edges if okf(e)]
        return geometry.fillet_ghost(shape, edges, item["kind"], float(item["size"]))
    except Exception:
        traceback.print_exc()
        return None


def _merge_ghosts(parts):
    parts = [g for g in parts if g is not None]
    if not parts:
        return None
    V, T, L, off = [], [], [], 0
    for v, t, l in parts:
        V.append(v)
        T.append(t + off)
        L.append(l)
        off += len(v)
    return {"verts": np.vstack(V), "tris": np.vstack(T),
            "lines": np.vstack(L) if L else np.zeros((0, 3), np.float32)}


# ---------------------------------------------------------------- gövde hesabı

def build(job):
    geometry = _geo()
    t0 = time.perf_counter()
    name, preview = job["name"], job["preview"]
    res = {"ok": False, "error": "", "patches": {}, "features": {}, "geo_updates": {},
           "errors": list(job.get("errors", ()))}
    try:
        _build(job, res, geometry)
    except CadError as e:
        res["error"] = str(e)
    except Exception as e:
        traceback.print_exc()
        res["error"] = f"Hata: {e}"
    res["ms"] = (time.perf_counter() - t0) * 1000.0
    return res


def _build(job, res, geometry):
    name, preview = job["name"], job["preview"]
    errors = res["errors"]
    tol = job["tol"]
    mirrors = [tuple(map(tuple, m)) for m in job["mirrors"]]

    # 1) Ortak köşe/kenar kayıtlarıyla yüzleri üret
    builder = geometry.Builder(prev=_builders.get(name))
    faces = []
    for p in job["patches"]:
        try:
            face, label = builder.face(p["chain"], p["sides"], p["method"], preview)
            res["patches"][p["idx"]] = (True, f"{label} · {len(p['sides'])} kenar · "
                                              f"{len(p['chain'])} segment")
            faces.append(face)
        except CadError as e:
            res["patches"][p["idx"]] = (False, str(e))
            errors.append(p["name"])
    _builders[name] = builder
    if not faces:
        if errors:
            raise CadError(f"Hatalı yüzey: {', '.join(errors)}")
        raise CadError("Etkin yüzey yok")

    # 2) Birleştir, aynala, katı yap
    shape, shape_info = geometry.assemble(faces, mirrors, job["sew_tol"], job["make_solid"])
    res["shape_info"] = shape_info

    # 3) Sıralı işlemler. Liste sırası = geçmiş sırası.
    run_bevels = job["run_bevels"]
    want_ghost = job.get("ghost", False) and not run_bevels
    stages = job["stages"]
    ghosts, bool_new, used = [], {}, {}
    if stages:
        key = (tuple(builder.face_keys), tuple(mirrors), job["make_solid"],
               tuple(st["key"] for st in stages), job["corner_mode"],
               round(job["factor"], 4), job["smooth"], run_bevels, want_ghost)
        hit = _bevel_cache.get(name)
        if hit is not None and hit[0] == key:
            shape, results, bool_new, ghosts, used, upd = hit[1:]
            res["geo_updates"] = upd
        else:
            results, upd, bases = {}, {}, {}
            for st in stages:
                if st["op"] == "BEVEL":
                    items = st["items"]
                    if not run_bevels and not want_ghost:
                        continue
                    feats = []
                    for it in items:
                        gp, gu, ge, gused = _resolve_geo(name, it, bool_new, tol)
                        for src, ks in gused.items():
                            used.setdefault(src, set()).update(ks)
                        if gu:
                            upd[it["uid"]] = gu
                        if ge and not gp and not it["polys"]:
                            results[it["uid"]] = (False, "Gövde kenarı: " + ge[0])
                        feats.append((it, gp, ge))
                    live = [(it, gp, ge) for it, gp, ge in feats
                            if it["uid"] not in results]
                    if not run_bevels:
                        for it, gp, _ in live:
                            ghosts.append(_ghost_for(shape, it, list(it["polys"]) + gp,
                                                     mirrors, tol))
                        continue
                    bases[st["skey"]] = shape
                    if not live:
                        continue
                    shape, rr = geometry.apply_features(
                        shape, [{"kind": it["kind"], "size": it["size"], "polys": it["polys"],
                                 "geo_polys": gp} for it, gp, _ in live],
                        mirrors, tol, job["corner_mode"], job["factor"],
                        job["smooth"] and not preview, fast=preview)
                    for (it, gp, ge), r in zip(live, rr):
                        ok, info = r
                        if ok and ge:
                            info += f" · {len(ge)} gövde kenarı çözülemedi: {ge[0]}"
                        results[it["uid"]] = (ok, info)
                else:
                    try:
                        tools = [_tool_shape(st["tool"])]
                        if st["mirror_tool"] and mirrors:
                            tools = geometry.mirror_copies(tools[0], mirrors)
                        before = shape
                        shape, ok, info = geometry.apply_boolean(
                            shape, tools, st["bool_type"],
                            st["edge_size"] if run_bevels else 0.0, st["edge_mode"], tol,
                            job["smooth"], preview=preview)
                        results[st["uid"]] = (ok, info)
                        if st.get("want_edges"):
                            try:
                                bool_new[st["uid"]] = geometry.edge_records(
                                    geometry.boolean_new_edges(shape, before, tools, "ALL",
                                                               tol))
                            except Exception:
                                traceback.print_exc()
                    except CadError as e:
                        results[st["uid"]] = (False, str(e))
                    except Exception as e:   # hiçbir hata boolean'ı sessizce yok etmesin
                        traceback.print_exc()
                        results[st["uid"]] = (False, f"Hata: {e}")
            res["geo_updates"] = upd
            _bevel_cache[name] = (key, shape, results, bool_new, ghosts, used, upd)
            if not preview:
                _stage_base[name] = bases
        for uid, r in results.items():
            res["features"][uid] = r
            if not r[0]:
                errors.append(job["feature_names"].get(uid, uid))

    if not preview:
        _final[name] = {"shape": shape, "solid": "Kapalı katı" in shape_info,
                        "info": shape_info}
        _bool_new[name] = bool_new
    lin, ang = job["lin"], job["ang"]
    if preview:
        lin, ang = lin * 4.0, max(ang * 3.0, math.radians(20))
    verts, tris, normals = geometry.tessellate(shape, lin, ang)
    n_bad = getattr(geometry, "LAST_FAILED", 0)
    if n_bad:
        errors.append(f"{n_bad} yüz görüntülenemedi")
    res["verts"] = np.asarray(verts, dtype=np.float64).reshape(-1, 3)
    res["tris"] = np.asarray(tris, dtype=np.int32).reshape(-1, 3)
    res["normals"] = None if normals is None else \
        np.asarray(normals, dtype=np.float64).reshape(-1, 3)
    res["ghost"] = _merge_ghosts(ghosts) if want_ghost else None
    if not preview:
        disp = {"edges": [], "bool_edges": []}
        try:
            disp["edges"] = [np.asarray(p, dtype=np.float32)
                             for p in geometry.shape_edge_polylines(shape)]
        except Exception:
            traceback.print_exc()
        for uid, recs in bool_new.items():
            u = used.get(uid, set())
            for k, r in enumerate(recs):
                disp["bool_edges"].append((uid, r["poly"].astype(np.float32), k in u))
        res["display"] = disp
    res["solid"] = "Kapalı katı" in shape_info
    res["ok"] = True


def ghost(job):
    """Sadece fillet ölçüsü/türü değiştiyse: son tam kalite hesabın fillet öncesi
    şekilleri üzerinde hayalet şeritleri üretir (gövde yeniden hesaplanmaz)."""
    name = job["name"]
    bases = _stage_base.get(name)
    if bases is None:
        return {"ok": False, "need_preview": True, "error": ""}
    tol = job["tol"]
    mirrors = [tuple(map(tuple, m)) for m in job["mirrors"]]
    bool_new = _bool_new.get(name, {})
    parts = []
    for st in job["stages"]:
        if st["op"] != "BEVEL":
            continue
        base = bases.get(st["skey"])
        if base is None:
            return {"ok": False, "need_preview": True, "error": ""}
        for it in st["items"]:
            gp, _, _, _ = _resolve_geo(name, it, bool_new, tol)
            parts.append(_ghost_for(base, it, list(it["polys"]) + gp, mirrors, tol))
    return {"ok": True, "ghost": _merge_ghosts(parts)}


def write_step(data):
    f = _final.get(data["name"])
    if f is None:
        raise CadError("Gövde hesaplanamadı")
    _geo().write_step(f["shape"], data["path"], data["scale"])
    return {"ok": True}


def forget(data):
    name = data.get("name")
    tables = (_builders, _bevel_cache, _final, _stage_base, _bool_new)
    if name is None:
        for t in tables + (_tool_cache,):
            t.clear()
    else:
        for t in tables:
            t.pop(name, None)
    return {"ok": True}


def forget_tool(data):
    _tool_cache.pop(data["name"], None)
    return {"ok": True}


def ping(data):
    import sys
    try:
        _geo()
        return {"ok": True, "python": sys.version.split()[0]}
    except Exception as e:
        return {"ok": False, "error": f"Çekirdek yüklenemedi: {e}"}


COMMANDS = {"build": build, "ghost": ghost, "step": write_step, "forget": forget,
            "forget_tool": forget_tool, "ping": ping}


def handle(cmd, data):
    try:
        return COMMANDS[cmd](data)
    except CadError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        traceback.print_exc()
        return {"ok": False, "error": f"Hata: {e}"}
