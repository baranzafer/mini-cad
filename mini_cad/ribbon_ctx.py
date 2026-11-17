"""BlendCAD bağlam (v0.30.0): üzerine gelinen öğeyi vurgula, sağ tıkta ona özel mini menü aç.

Öğeler ve menüler:
  PATCH    gövdenin bir yüzeyi (yüz etiketi 'cad_patch'): sil, devre dışı bırak, eğrilerini
           seç, birleşim (Gövde ayarı / Keskin / Teğet), yüzeyi böl, yüzey ayarları
  BODYFACE fillet / boolean / süpürme yüzü (etiket -1): ilgili işlem pencereleri
  CURVE    tel kafes / çizim eğrisi (araç kapalıyken): çizimi düzenle, eğriyi sil, seç, profil
  SKETCH   çizim açıkken taslak nesnesi / noktası: Sil, Kırp, Böl, Uzat, Ötele, Taşı, Kopyala,
           Döndür, Ayna, kısıtlar, ölçü
  EDGE     kenar seçimi açıkken kenar: fillet, süpürme, yüzey, yeni gövde, seçime ekle

Menü eylemleri mevcut kod yolunu kullanır: operatörler (ribbon_actions.call) ya da açık araca
araç + yapay tık / tuş (ribbon_actions.send_key / send_click) — klavye ve fareyle aynı sonuç.
Ana şeritten hiçbir düğme kalkmaz; menü kısayoldur.
"""

import numpy as np

import bpy

from . import ribbon_actions as ra
from . import ribbon_state

HOVER = {"target": None, "geom": None, "key": None}


# ---------------------------------------------------------------- yardımcılar

def _project(M, pts, region):
    P = np.c_[pts, np.ones(len(pts))] @ M.T
    w = P[:, 3:4]
    ok = (w[:, 0] > 1e-9)
    w = np.where(np.abs(w) < 1e-12, 1e-12, w)
    ndc = P[:, :2] / w
    px = np.c_[(ndc[:, 0] + 1) * 0.5 * region.width, (ndc[:, 1] + 1) * 0.5 * region.height]
    return px, ok


def _seg_dist(a, b, m):
    ab = b - a
    L = np.einsum("ij,ij->i", ab, ab)
    L = np.where(L < 1e-12, 1e-12, L)
    t = np.clip(np.einsum("ij,ij->i", m - a, ab) / L, 0.0, 1.0)
    q = a + ab * t[:, None]
    return np.linalg.norm(q - m, axis=1)


def _bezier(p0, h0, h1, p1, n=12):
    t = np.linspace(0.0, 1.0, n)[:, None]
    return ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * h0 + 3 * (1 - t) * t * t * h1 + \
        (t ** 3) * p1


def curve_polylines(ob):
    """[(spline sırası, dünya noktaları N×3)]"""
    out = []
    mw = np.array(ob.matrix_world, dtype=np.float64)
    for si, sp in enumerate(ob.data.splines):
        pts = []
        if sp.type == "BEZIER":
            bp = sp.bezier_points
            n = len(bp)
            segs = n if sp.use_cyclic_u else n - 1
            for i in range(segs):
                a, b = bp[i], bp[(i + 1) % n]
                pts.extend(_bezier(np.array(a.co), np.array(a.handle_right),
                                   np.array(b.handle_left), np.array(b.co)))
        else:
            pts = [tuple(p.co)[:3] for p in sp.points]
            if sp.use_cyclic_u and pts:
                pts.append(pts[0])
        if len(pts) < 2:
            continue
        P = np.asarray(pts, dtype=np.float64)
        P = (np.c_[P, np.ones(len(P))] @ mw.T)[:, :3]
        out.append((si, P))
    return out


# ---------------------------------------------------------------- boşta üzerine gelme

def hover_update(context, area, region, mx, my):
    """Araç kapalıyken (çizim / kenar seçimi / bölme yok) üzerine gelinen öğe."""
    old = HOVER["key"]
    HOVER["target"] = None
    rv3d = area.spaces.active.region_3d
    s = context.preferences.system.ui_scale
    M = np.array(rv3d.perspective_matrix, dtype=np.float64)
    m = np.array([mx, my], dtype=np.float64)
    best = None
    for ob in context.visible_objects:
        if ob.type != "CURVE":
            continue
        try:
            for si, P in curve_polylines(ob):
                px, ok = _project(M, P, region)
                if not ok.all():
                    continue
                d = float(_seg_dist(px[:-1], px[1:], m).min())
                if d < 8 * s and (best is None or d < best[0]):
                    best = (d, ob.name, si, P)
        except Exception:
            continue
    if best is not None:
        HOVER["target"] = {"kind": "CURVE", "obj": best[1], "spline": best[2]}
        HOVER["geom"] = ("LINE", best[3])
    else:
        hit = _ray(context, region, rv3d, mx, my)
        if hit is not None:
            ob, poly = hit
            lab = _label(ob, poly)
            if lab is not None and lab >= 0:
                HOVER["target"] = {"kind": "PATCH", "obj": ob.name, "patch": lab}
            elif lab is not None:
                HOVER["target"] = {"kind": "BODYFACE", "obj": ob.name}
    t = HOVER["target"]
    key = None if t is None else tuple(sorted(t.items()))
    if key != old:
        HOVER["key"] = key
        if t is None or t["kind"] != "CURVE":
            HOVER["geom"] = _patch_geom(context, t) if t and t["kind"] == "PATCH" else None
        return True
    return False


def clear():
    ch = HOVER["key"] is not None
    HOVER.update(target=None, geom=None, key=None)
    return ch


def _ray(context, region, rv3d, mx, my):
    from bpy_extras import view3d_utils
    try:
        o = view3d_utils.region_2d_to_origin_3d(region, rv3d, (mx, my))
        d = view3d_utils.region_2d_to_vector_3d(region, rv3d, (mx, my))
        dg = context.evaluated_depsgraph_get()
        ok, _loc, _n, idx, ob, _mat = context.scene.ray_cast(dg, o, d)
    except Exception:
        return None
    if not ok or ob is None:
        return None
    try:
        if not ob.cad.is_cad:
            return None
    except Exception:
        return None
    return ob, idx


def _label(ob, poly):
    at = ob.data.attributes.get("cad_patch")
    if at is None or not (0 <= poly < len(at.data)):
        return None
    return at.data[poly].value


def _patch_geom(context, t):
    ob = bpy.data.objects.get(t["obj"])
    if ob is None:
        return None
    at = ob.data.attributes.get("cad_patch")
    if at is None:
        return None
    lab = np.empty(len(at.data), dtype=np.int32)
    at.data.foreach_get("value", lab)
    me = ob.data
    nv = len(me.vertices)
    co = np.empty(nv * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    nl = len(me.loops)
    lv = np.empty(nl, dtype=np.int32)
    me.loops.foreach_get("vertex_index", lv)
    ls = np.empty(len(me.polygons), dtype=np.int32)
    me.polygons.foreach_get("loop_start", ls)
    sel = np.nonzero(lab == t["patch"])[0]
    if not len(sel):
        return None
    tri = np.stack([lv[ls[sel]], lv[ls[sel] + 1], lv[ls[sel] + 2]], axis=1).reshape(-1)
    mw = np.array(ob.matrix_world, dtype=np.float64)
    W = (np.c_[co[tri], np.ones(len(tri))] @ mw.T)[:, :3]
    return ("TRIS", W)


def draw_hover(context):
    """POST_VIEW: üzerine gelinen yüzey (yarı saydam) ya da eğri (kalın)."""
    g = HOVER.get("geom")
    if g is None or HOVER["target"] is None:
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    from .ribbon import COL_ACCENT
    rv3d = context.region_data
    region = context.region
    if rv3d is None or region is None:
        return
    kind, P = g
    gpu.state.blend_set("ALPHA")
    try:
        if kind == "TRIS":
            vi = np.array(rv3d.view_matrix.inverted(), dtype=np.float64)
            if rv3d.is_perspective:
                d = vi[:3, 3][None, :] - P
                d /= np.maximum(np.linalg.norm(d, axis=1)[:, None], 1e-12)
            else:
                d = np.repeat(vi[:3, 2][None, :], len(P), axis=0)
            Q = P + d * (0.002 * float(rv3d.view_distance))     # z kavgası olmasın
            gpu.state.depth_test_set("LESS_EQUAL")
            sh = gpu.shader.from_builtin("UNIFORM_COLOR")
            b = batch_for_shader(sh, "TRIS", {"pos": [tuple(q) for q in Q]})
            sh.bind()
            sh.uniform_float("color", (COL_ACCENT[0], COL_ACCENT[1], COL_ACCENT[2], 0.30))
            b.draw(sh)
            gpu.state.depth_test_set("NONE")
        else:
            sh = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
            seg = []
            for i in range(len(P) - 1):
                seg += [tuple(P[i]), tuple(P[i + 1])]
            b = batch_for_shader(sh, "LINES", {"pos": seg})
            sh.bind()
            sh.uniform_float("viewportSize", (region.width, region.height))
            sh.uniform_float("lineWidth", 4.0)
            sh.uniform_float("color", (COL_ACCENT[0], COL_ACCENT[1], COL_ACCENT[2], 0.9))
            b.draw(sh)
    finally:
        gpu.state.blend_set("NONE")


# ---------------------------------------------------------------- menüler

def _I(id, text, fn, icon=None, key="", enabled=True, check=False):
    return {"id": id, "text": text, "fn": fn, "icon": icon, "key": key, "enabled": enabled,
            "check": check}


SEP = {"sep": True}


def _form(fid):
    return lambda: ra._open(fid)


def _target_set(ob):
    try:
        bpy.context.scene.minicad_target = ob
    except Exception:
        pass


def menu_for(target):
    """(başlık, simge, öğeler) ya da None."""
    k = target.get("kind")
    if k == "PATCH":
        return _patch_menu(target)
    if k == "BODYFACE":
        return _bodyface_menu(target)
    if k == "CURVE":
        return _curve_menu(target)
    if k == "SKETCH":
        return _sketch_menu(target)
    if k == "EDGE":
        return _edge_menu(target)
    return None


def _patch_menu(t):
    ob = bpy.data.objects.get(t["obj"])
    if ob is None or not (0 <= t["patch"] < len(ob.cad.patches)):
        return None
    i = t["patch"]
    pt = ob.cad.patches[i]

    def call(op, **kw):
        def f():
            _target_set(ob)
            ra.call(op, _obj=ob, **kw)
            clear()
        return f

    def blend(v):
        def f():
            pt.blend = v
            ra._msg(f"{pt.name}: birleşim {dict(BODY='Gövde ayarı', SHARP='Keskin', TANGENT='Teğet')[v]}")
        return f

    def disable():
        pt.enabled = False
        ra._msg(f"{pt.name} devre dışı bırakıldı (Yüzey listesinden yeniden açılır)")

    def settings():
        _target_set(ob)
        ob.cad.active_patch = i
        ra._open("SURF_LIST")

    def split():
        _target_set(ob)
        ra._dispatch(bpy.context, "TOOL", "SPLIT_FACE")
    items = [
        _I("del", "Yüzeyi sil", call("minicad.remove_patch", index=i), "DELETE", "Del"),
        _I("off", "Devre dışı bırak", disable, "SHOW"),
        _I("sel", "Eğrilerini seç", call("minicad.select_patch_curves", index=i), "SELECT"),
        _I("split", "Yüzeyi böl", split, "SPLIT_FACE"),
        SEP, {"head": "Birleşim"},
        _I("b0", "Gövde ayarı", blend("BODY"), check=pt.blend == "BODY"),
        _I("b1", "Keskin (G0)", blend("SHARP"), check=pt.blend == "SHARP"),
        _I("b2", "Teğet (G1)", blend("TANGENT"), check=pt.blend == "TANGENT"),
        SEP,
        _I("set", "Yüzey ayarları…", settings, "SURF_LIST"),
        _I("fil", "Fillet / pah…", lambda: (_target_set(ob), ra._dispatch(bpy.context, "TOOL",
                                                                         "FILLET_R")),
           "FILLET3D"),
    ]
    return f"{ob.name} · {pt.name}", "PATCH", items


def _bodyface_menu(t):
    ob = bpy.data.objects.get(t["obj"])
    if ob is None:
        return None

    def go(fid):
        def f():
            _target_set(ob)
            ra._dispatch(bpy.context, "TOOL", fid)
        return f
    items = [
        _I("fil", "Fillet / pah…", go("FILLET_R"), "FILLET3D"),
        _I("bool", "Boolean…", go("BOOL_DIFF"), "BOOL_DIFF"),
        _I("sw", "Profil süpürme…", go("SWEEP"), "SWEEP"),
        _I("ord", "İşlem sırası…", go("ORDER"), "ORDER"),
        SEP,
        _I("reb", "Yenile", lambda: (_target_set(ob), ra.call("minicad.rebuild", _obj=ob)),
           "REBUILD"),
        _I("body", "Gövde…", go("BODY"), "BODY"),
    ]
    return f"{ob.name} · işlem yüzü", "BODY", items


def _curve_menu(t):
    ob = bpy.data.objects.get(t["obj"])
    if ob is None:
        return None
    si = t["spline"]

    def edit():
        ra.call("minicad.edit_sketch", name=ob.name)

    def delete():
        from . import links
        links.remove_splines(ob, [si])
        try:
            bpy.ops.ed.undo_push(message="BlendCAD: Eğri sil")
        except Exception:
            pass
        clear()
        ra._msg(f"{ob.name}: eğri {si + 1} silindi (bağlı yüzey / kısıt referansları eşlendi)")

    def select():
        try:
            for o in bpy.context.selected_objects:
                o.select_set(False)
            ob.select_set(True)
            bpy.context.view_layer.objects.active = ob
        except Exception:
            pass

    def profile():
        bpy.context.scene.minicad_sweep_profile = ob
        ra._open("SWEEP")
    items = [
        _I("edit", "Çizimi düzenle (taslağa al)", edit, "EDIT_ALL"),
        _I("del", "Bu eğriyi sil", delete, "DELETE"),
        _I("pick", "Kenar seçimi (yüzey / fillet)", lambda: ra._dispatch(bpy.context, "TOOL",
                                                                         "EDGE_PICK"),
           "EDGE_PICK"),
        SEP,
        _I("sel", "Objeyi seç", select, "SELECT"),
        _I("prof", "Süpürme profili yap", profile, "SWEEP"),
    ]
    return f"{ob.name} · eğri {si + 1}", "CV", items


def _sketch_menu(t):
    op = ra.draw_op()
    if op is None:
        return None
    wx, wy = t["wx"], t["wy"]

    def tool(name, then=None):
        def f():
            o = ra.draw_op()
            if o is None:
                return
            o._set_tool(bpy.context, name)
            send_click(o, wx, wy)
            if then:
                ra.send_key(o, then)
            ra._after(bpy.context, o)
        return f
    if t.get("what") == "pt":
        items = [
            _I("del", "Noktayı sil", tool("DELETE"), "DELETE", "Del"),
            _I("fix", "Sabitle", tool("C_FIX"), "FIX"),
            _I("coin", "Çakışık (2. noktayı seç)", tool("C_COINCIDENT"), "COINCIDENT"),
            _I("move", "Taşı", tool("MOVE", "RET"), "MOVE"),
        ]
        return "Taslak noktası", "POINT", items
    items = [
        _I("del", "Sil", tool("DELETE"), "DELETE", "Del"),
        _I("trim", "Kırp (bu parça)", tool("TRIM"), "TRIM", "B"),
        _I("split", "Böl", tool("SPLIT"), "SPLIT"),
        _I("ext", "Uzat", tool("EXTEND"), "EXTEND"),
        _I("ofs", "Ötele", tool("OFFSET"), "OFFSET"),
        SEP,
        _I("move", "Taşı", tool("MOVE", "RET"), "MOVE"),
        _I("copy", "Kopyala", tool("COPY", "RET"), "COPY"),
        _I("rot", "Döndür", tool("ROTATE", "RET"), "ROTATE"),
        _I("mir", "Ayna", tool("MIRROR", "RET"), "MIRROR"),
        SEP, {"head": "Kısıt"},
        _I("h", "Yatay", tool("C_HORIZ"), "HORIZ"),
        _I("v", "Dikey", tool("C_VERT"), "VERT"),
        _I("dim", "Ölçü", tool("C_DIM", "RET"), "DIM"),
        _I("eq", "Eşit (2. nesneyi seç)", tool("C_EQUAL"), "EQUAL"),
        _I("tan", "Teğet (2. nesneyi seç)", tool("C_TANGENT"), "TANGENT"),
    ]
    return "Taslak nesnesi", "LINE", items


def _edge_menu(t):
    op = ra.pick_op()
    if op is None:
        return None
    keys = list(t.get("keys") or [])

    def add():
        o = ra.pick_op()
        if o is not None:
            o.selected += [k for k in keys if k not in o.selected]
            try:
                o._status(bpy.context)
                o.area.tag_redraw()
            except Exception:
                pass

    def then(key, ctrl=False):
        def f():
            add()
            ra.key_pick(key, ctrl=ctrl)
        return f
    n = len(op.selected)
    items = [
        _I("fil", "Fillet (bu kenar + seçim)", then("B"), "FILLET3D", "B"),
        _I("sw", "Süpürme yolu yap", then("P"), "SWEEP", "P"),
        _I("surf", "Yüzey oluştur", then("RET"), "PATCH", "Enter"),
        _I("body", "Yeni gövde", then("RET", True), "BODY", "Ctrl+Enter"),
        SEP,
        _I("add", "Seçime ekle", add, "EDGE_PICK"),
        _I("clr", f"Seçimi temizle ({n})", lambda: ra.key_pick("BACK_SPACE"), "CLOSE",
           enabled=n > 0),
    ]
    return "Kenar", "EDGE_PICK", items


# ---------------------------------------------------------------- açık araçlardan

def send_click(op, wx, wy):
    """Araca (window koordinatında) sol tık + bırak gönder."""
    region = getattr(op, "region", None)
    if region is None:
        return
    for val in ("PRESS", "RELEASE"):
        ev = ra._Ev("LEFTMOUSE", wx, wy)
        ev.value = val
        mv = ra._Ev("MOUSEMOVE", wx, wy)
        mv.value = "NOTHING"
        with ra._override(bpy.context):
            try:
                if val == "PRESS":
                    op.modal(bpy.context, mv)
                op.modal(bpy.context, ev)
            except Exception as e:
                ra._msg(f"Hata: {e}")


def open_menu(target, mx, my):
    """Şeridin menüsünü aç (bölge pikselinde mx, my). True: açıldı."""
    rb = ribbon_state.STATE.get("ribbon")
    if rb is None or not ribbon_state.is_running():
        return False
    m = menu_for(target)
    if m is None:
        return False
    title, icon, items = m
    rb.menu.open(title, items, mx, my, icon)
    try:
        bpy.context.area.tag_redraw()
    except Exception:
        pass
    return True


# ---------------------------------------------------------------- çizim aracı (taslak)

def sketch_idle(op):
    """Taslakta süren bir iş yok (sağ tık menüsü / vurgu güvenle açılabilir)."""
    from .draw_common import XFORM_TOOLS
    if getattr(op, "phase", "") != "DRAW":
        return False
    if op.segs or op.start is not None or getattr(op, "stage", None):
        return False
    for a in ("sk_drag", "gmenu", "txt", "dim_edit", "off_sel", "fl_sel", "track", "pen"):
        if getattr(op, a, None):
            return False
    t = getattr(op, "tool", "")
    if t.startswith("C_") or t in XFORM_TOOLS:
        return False
    return True


def sketch_hit(op, mx, my):
    pts = getattr(op, "sk_points", None) or []
    for j, q in enumerate(pts):
        p = op._px(q)
        if p is not None and ((p[0] - mx) ** 2 + (p[1] - my) ** 2) ** 0.5 <= op.radius:
            return {"kind": "SKETCH", "what": "pt", "j": j, "P": np.asarray([q])}
    if not op.sketch:
        return None
    hit = op._pick_seg(mx, my)
    if hit is None:
        return None
    from . import drawmath as dm
    from . import sketchmath as sm
    k, i, _t, _pos = hit
    st = op.sketch[k]
    ent = sm.entity_of(st, i)
    if ent is None:
        return None
    P = []
    for j in range(ent[0], ent[1]):
        sg = st["segs"][j]
        P.extend(dm.sample(sg, 2 if sg["kind"] == "line" else 24))
    return {"kind": "SKETCH", "what": "seg", "k": k, "i0": ent[0], "P": np.asarray(P)}


def draw_event(op, context, event, mx, my, inside):
    """Çizim aracının modal'ından: şerit açıkken üzerine gelme ve sağ tık menüsü.
    Dönüş: {"RUNNING_MODAL"} (olay işlendi) ya da None."""
    if not ribbon_state.is_running() or not inside:
        return None
    et = event.type
    if et in ("MOUSEMOVE", "INBETWEEN_MOUSEMOVE"):
        old = getattr(op, "ctx_hover", None)
        h = sketch_hit(op, mx, my) if sketch_idle(op) else None
        op.ctx_hover = h
        if (old is None) != (h is None) or (h and old and
                                            (h.get("k"), h.get("j")) != (old.get("k"), old.get("j"))):
            op.area.tag_redraw()
        return None
    if et == "RIGHTMOUSE" and event.value == "PRESS" and sketch_idle(op):
        try:
            from . import constraints
            if constraints.glyph_at(mx, my) is not None or op._skc_at(mx, my) is not None:
                return None                     # kısıt simgesinin kendi menüsü öncelikli
        except Exception:
            pass
        h = sketch_hit(op, mx, my)
        if h is None:
            return None
        h["wx"], h["wy"] = event.mouse_x, event.mouse_y
        if open_menu(h, mx, my):
            op.ctx_hover = None
            return {"RUNNING_MODAL"}
    return None


def draw_sketch_hover(op, region):
    h = getattr(op, "ctx_hover", None)
    if not h or not ribbon_state.is_running():
        return
    import gpu
    from gpu_extras.batch import batch_for_shader
    from .ribbon import COL_ACCENT
    P = h["P"]
    sh = gpu.shader.from_builtin("POLYLINE_UNIFORM_COLOR")
    if len(P) == 1:
        c = P[0]
        r = 0.0
        seg = []
        try:
            r = float(op._px_size(c)) * 6.0
        except Exception:
            r = 0.02
        for a, b in ((0, 1), (1, 0)):
            d = np.zeros(3)
            d[a] = r
            seg += [tuple(c - d), tuple(c + d)]
    else:
        seg = []
        for i in range(len(P) - 1):
            seg += [tuple(P[i]), tuple(P[i + 1])]
    b = batch_for_shader(sh, "LINES", {"pos": seg})
    sh.bind()
    sh.uniform_float("viewportSize", (region.width, region.height))
    sh.uniform_float("lineWidth", 4.0)
    sh.uniform_float("color", (COL_ACCENT[0], COL_ACCENT[1], COL_ACCENT[2], 0.55))
    b.draw(sh)


def pick_event(op, context, event, mx, my, inside):
    """Kenar seçiminin modal'ından: üzerine gelinen kenarda sağ tık menüsü."""
    if not ribbon_state.is_running() or not inside:
        return None
    if event.type == "RIGHTMOUSE" and event.value == "PRESS" and \
            getattr(op, "hover", None) is not None:
        keys = list(getattr(op, "hover_set", None) or [])
        if not keys:
            try:
                keys = [op.scene.keys[op.hover]]
            except Exception:
                keys = []
        if open_menu({"kind": "EDGE", "keys": keys}, mx, my):
            return {"RUNNING_MODAL"}
    return None
