"""BlendCAD araç pencerelerinin içerikleri (v0.29.0).

Her fonksiyon spec(ui, ctx): ribbon_forms.UI ile pencereyi kurar. Eski N panellerinin
(panels.py) içeriği yeni tasarım diliyle burada; işlemler mevcut operatörlere ve araçlara
gider (ribbon_actions.call / key). Panel sınıfları geçiş dönemi için yerinde duruyor.
"""

import bpy

from . import ribbon_actions as ra
from .ribbon_forms import Meta

BOOL_NAMES = {"CUT": "Kesim", "UNION": "Ekleme", "INTERSECT": "Kesişim"}
SOURCES = ("Model kaynaklı", "Geometrik olarak mümkün değil", "Ölçü sınırı",
           "Çekirdek sınırı (OCC)")


# ---------------------------------------------------------------- ortak parçalar

def _target(ctx):
    return ra._target(ctx)


def _need_body(ui, ctx, kernel=True):
    if kernel and not ra._kernel_ready():
        ui.label("Hesap çekirdeği (OpenCASCADE) kurulu değil.", "warn")
        ui.button("Çekirdeği kur", lambda: ra.call("minicad.install_kernel"), icon="KERNEL",
                  primary=True)
        return None
    t = _target(ctx)
    if t is None:
        ui.label("Gövde yok.", "warn")
        ui.label("Önce bir yüzey oluştur: Yüzey → Sınır yüzeyi (Kenar seçimi: Enter yüzey, "
                 "Ctrl+Enter yeni gövde) ya da çizimde kapalı çizgide F.", "dim")
        return None
    return t


def _cad_objects(ctx):
    return [(o, o.name) for o in ctx.scene.objects if getattr(o, "cad", None) and o.cad.is_cad]


def _meshes(ctx, exclude=None):
    return [(o, o.name) for o in ctx.scene.objects if o.type == "MESH" and o != exclude]


def _curves(ctx):
    return [(o, o.name) for o in ctx.scene.objects if o.type == "CURVE"]


def _info(ui, f, index):
    """İşlem bilgisi: kaynak etiketi, satırlar, başarısızsa ayrıntılı teşhis."""
    txt = (f.info or "").strip()
    if not txt:
        return
    src = next((sv for sv in SOURCES if sv + ":" in txt), None)
    if src:
        pre, txt = txt.split(src + ":", 1)
        ui.label(f"Kaynak: {src}", "err" if (not f.ok and src != "Ölçü sınırı") else "warn")
        pre = pre.strip().rstrip(":").strip(" ·")
        if pre and pre != "Hesaplanamadı":
            ui.label(pre, "dim")
    first = True
    for part in txt.strip().split(" · "):
        ui.label(part, ("ok" if f.ok else "err") if first else "dim")
        first = False
    if not f.ok:
        ui.button("Ayrıntılı teşhis", lambda: ra.call("minicad.diagnose_feature", index=index),
                  icon="DIAG")


def _pick():
    return ra.pick_op()


def _pick_row(ui, ctx, what="kenar"):
    pk = _pick()
    n = len(pk.selected) if pk is not None else 0
    if pk is None:
        ui.label("Kenar seçimi kapalı", "dim")
    else:
        ui.label(f"Kenar seçimi açık · {n} {what} seçili", "ok" if n else "info")
    with ui.row(2, 1):
        ui.button("Seçimi kapat" if pk else "Kenar seç", lambda: ra.call("minicad.pick_edges",
                                                                         invoke=True),
                  icon="EDGE_PICK", depress=pk is not None)
        ui.button("Temizle", lambda: ra.key_pick("BACK_SPACE"), enabled=n > 0, key="⌫")
    return pk, n


def _feature_cells(f, kind_text):
    def cells(u, it, i):
        idx, ff = it
        u.prop(ff, "enabled", "", style="check", weight=0.13)
        u.label(ff.name, "" if ff.ok else "err", weight=1.0)
        u.label(kind_text(ff), "dim", weight=0.9)
    return cells


def _flist(ui, p, lid, pred, active_prop, kind_text, rows=4):
    items = [(i, f) for i, f in enumerate(p.features) if pred(f)]
    cur = getattr(p, active_prop)
    act = next((j for j, (i, _f) in enumerate(items) if i == cur), -1)

    def sel(j):
        setattr(p, active_prop, items[j][0])
    ui.list(lid, items, act, sel, _feature_cells(None, kind_text), rows=rows,
            empty="Henüz yok")
    if 0 <= cur < len(p.features) and pred(p.features[cur]):
        return cur, p.features[cur]
    return None, None


def _fmt_len(v):
    try:
        from . import core
        return core.fmt_len(v)
    except Exception:
        return f"{v:g}"


# ---------------------------------------------------------------- Fillet / pah

def fillet(ui, ctx):
    t = _need_body(ui, ctx)
    if t is None:
        return
    p = t.cad
    from . import core
    ui.prop(p, "use_bevels", "Fillet / pah uygulansın", style="check")
    with ui.enabled(p.use_bevels):
        ui.section("Yeni fillet")
        pk, n = _pick_row(ui, ctx)
        ui.prop(p, "default_bevel", "Ölçü")
        ui.button("Fillet uygula", lambda: ra.key_pick("B"), icon="FILLET3D", primary=True,
                  enabled=n > 0, key="B")
        ui.section("Köşe")
        ui.prop(p, "corner_mode", "Köşe")
        if p.corner_mode == "TRANSITION":
            ui.prop(p, "transition_factor")
        if p.corner_mode != "EDGEWISE":
            ui.prop(p, "smooth_corners", style="check")
        ui.section("Önizleme")
        with ui.row():
            ui.prop(p, "ghost_bevel", "Hayalet fillet", style="toggle")
            ui.prop(p, "preview_bevel", "Önizlemede gerçek", style="toggle")
        ui.section("Filletler")
        i, f = _flist(ui, p, "bevels", core.is_bevel, "active_bevel",
                      lambda ff: ("Fillet " if ff.kind == "FILLET" else "Pah ") +
                      _fmt_len(ff.size))
        if f is not None:
            ui.prop(f, "kind", "", style="seg")
            ui.prop(f, "size", "Ölçü")
            if len(f.geo_edges):
                ui.label(f"{len(f.segs)} tel kafes + {len(f.geo_edges)} gövde kenarı", "dim")
            _info(ui, f, i)
            ui.button("Fillet'i sil", lambda: ra.call("minicad.remove_feature", index=i),
                      icon="CLOSE")
    ui.button("Yenile (baştan hesapla)", lambda: ra.call("minicad.rebuild"), icon="REBUILD")


# ---------------------------------------------------------------- Boolean

def boolean(ui, ctx):
    t = _need_body(ui, ctx)
    if t is None:
        return
    sc = ctx.scene
    p = t.cad
    ui.prop(p, "use_booleans", "Boolean'lar uygulansın", style="check")
    with ui.enabled(p.use_booleans):
        ui.section("Yeni boolean")
        with ui.row(4, 1):
            ui.prop(sc, "minicad_target", "Gövde", style="object",
                    choices=lambda: _cad_objects(ctx))
            ui.button("Aktif", lambda: ra.call("minicad.set_target_active"), weight=1)
        with ui.row(4, 1):
            ui.prop(sc, "minicad_bool_tool", "İkincil", style="object",
                    choices=lambda: _meshes(ctx, sc.minicad_target))
            ui.button("Aktif", lambda: ra.call("minicad.pick_bool_tool"))
        ui.prop(sc, "minicad_bool_type", "", style="seg")
        with ui.row(1, 1):
            ui.prop(sc, "minicad_bool_highlight", "Vurgula", style="toggle")
            ui.button("Gövde ⇄ İkincil", lambda: ra.call("minicad.swap_bool"))
        tool = sc.minicad_bool_tool
        ui.button("Boolean ekle", lambda: ra.call("minicad.add_boolean"), icon="BOOL_DIFF",
                  primary=True, enabled=tool is not None and tool != sc.minicad_target)
        if tool is not None and tool.cad.is_cad and "Kapalı katı" not in tool.cad.status:
            ui.label("İkincil gövde kapalı katı değil", "err")
        if "Kapalı katı" not in p.status:
            ui.label("Ana gövde açık kabuk: Kesim yüzeyi deler, Kesişim içte kalanı bırakır; "
                     "Birleşim olmaz", "info")
        ui.section("Boolean'lar")
        i, f = _flist(ui, p, "bools", lambda ff: ff.op == "BOOLEAN", "active_bool",
                      lambda ff: f"{BOOL_NAMES.get(ff.bool_type, '')} · "
                                 f"{ff.tool.name if ff.tool else '—'}")
        if f is not None:
            ui.prop(f, "bool_type", "", style="seg")
            ui.prop(f, "tool", "İkincil", style="object", choices=lambda: _meshes(ctx, t))
            with ui.row(1, 1):
                ui.prop(f, "edge_size", "Kenar")
                if f.edge_size > 0:
                    ui.prop(f, "edge_mode", "")
            if p.use_mirror and (p.mirror_x or p.mirror_y or p.mirror_z):
                ui.prop(f, "mirror_tool", style="check")
            _info(ui, f, i)
            with ui.row(1, 1):
                ui.button("Gövde ⇄ İkincil", lambda: ra.call("minicad.swap_existing_bool",
                                                             index=i))
                ui.button("Sil", lambda: ra.call("minicad.remove_feature", index=i),
                          icon="CLOSE")


# ---------------------------------------------------------------- Profil süpürme

def sweep(ui, ctx):
    t = _need_body(ui, ctx)
    if t is None:
        return
    sc = ctx.scene
    p = t.cad
    ui.section("Yeni süpürme")
    ui.label("1) Profil: XY'de çiz — orijin = kenar, +Y = dışarı", "dim")
    ui.prop(sc, "minicad_sweep_profile", "Profil", style="object", choices=lambda: _curves(ctx))
    ui.prop(sc, "minicad_sweep_type", "", style="seg")
    ui.label("2) Yol: kenarları seç", "dim")
    pk, n = _pick_row(ui, ctx)
    ui.button("Süpürme ekle", lambda: ra.key_pick("P"), icon="SWEEP", primary=True,
              enabled=n > 0 and sc.minicad_sweep_profile is not None, key="P")
    ui.section("Süpürmeler")
    i, f = _flist(ui, p, "sweeps", lambda ff: ff.op == "SWEEP", "active_sweep",
                  lambda ff: f"{BOOL_NAMES.get(ff.bool_type, '')} · "
                             f"{ff.profile.name if ff.profile else '—'}")
    if f is None:
        return
    ui.prop(f, "bool_type", "", style="seg")
    ui.prop(f, "profile", "Profil", style="object", choices=lambda: _curves(ctx))
    with ui.row(3, 2):
        ui.label(f"Yol: {len(f.segs)} tel kafes + {len(f.geo_edges)} gövde kenarı", "dim")
        ui.button("Seçimi yol yap", lambda: ra.call("minicad.sweep_set_path", index=i),
                  enabled=n > 0)
    ui.prop(f, "sw_place", "", style="seg")
    if f.sw_place == "AUTO":
        ui.prop(f, "sw_ref", "", style="seg")
        ui.prop(f, "sw_angle", "Açı")
        with ui.row():
            ui.prop(f, "sw_off_x", "X")
            ui.prop(f, "sw_off_y", "Y")
        with ui.row():
            ui.prop(f, "sw_scale", "Ölçek")
            ui.prop(f, "sw_flip", "Çevir", style="toggle")
    ui.label("Açık profil:", "dim")
    ui.prop(f, "sw_close", "", style="seg")
    with ui.row():
        ui.prop(f, "sw_reverse", style="toggle")
        ui.prop(f, "sw_extend_auto", style="toggle")
    if f.sw_extend_auto:
        ui.prop(f, "sw_extend")
    with ui.row(1, 1):
        ui.prop(f, "edge_size", "Kenar")
        if f.edge_size > 0:
            ui.prop(f, "edge_mode", "")
    if p.use_mirror and (p.mirror_x or p.mirror_y or p.mirror_z):
        ui.prop(f, "mirror_tool", style="check")
    _info(ui, f, i)
    ui.button("Süpürmeyi sil", lambda: ra.call("minicad.remove_feature", index=i), icon="CLOSE")


# ---------------------------------------------------------------- Yüzeyler

def surfaces(ui, ctx):
    t = _need_body(ui, ctx)
    if t is None:
        return
    p = t.cad
    ui.section("Gövde")
    ui.prop(p, "surface_blend", "Birleşim")
    if p.surface_blend == "TANGENT" or any(pt.blend == "TANGENT" for pt in p.patches):
        ui.prop(p, "tangent_weight", "Teğet ağırlığı")
    ui.prop(p, "make_solid", style="check")
    ui.section(f"Yüzeyler ({len(p.patches)})")

    def cells(u, it, i):
        u.prop(it, "enabled", "", style="check", weight=0.13)
        u.label(it.name, "" if it.ok else "err", weight=1.0)
        u.prop(it, "method", "", weight=0.8)
    items = list(p.patches)

    def sel(j):
        p.active_patch = j
    ui.list("patches", items, p.active_patch, sel, cells, rows=5, empty="Yüzey yok")
    i = p.active_patch
    if 0 <= i < len(p.patches):
        pt = p.patches[i]
        if pt.info:
            ui.label(pt.info, "dim" if pt.ok else "err")
        with ui.row(1, 1):
            ui.button("Eğrilerini seç", lambda: ra.call("minicad.select_patch_curves", index=i))
            ui.button("Sil", lambda: ra.call("minicad.remove_patch", index=i), icon="CLOSE")
        ui.prop(pt, "blend", "Birleşim")
        eff = p.surface_blend if pt.blend == "BODY" else pt.blend
        if eff == "TANGENT":
            with ui.row(1, 2):
                ui.prop(pt, "own_weight", "Kendi", style="toggle")
                with ui.enabled(pt.own_weight):
                    ui.prop(pt, "tangent_weight", "Ağırlık")


# ---------------------------------------------------------------- Ayna simetrisi

def mirror(ui, ctx):
    t = _need_body(ui, ctx)
    if t is None:
        return
    p = t.cad
    ui.prop(p, "use_mirror", "Simetri açık", style="check")
    with ui.enabled(p.use_mirror):
        ui.label("Eksenler", "dim")
        with ui.row():
            ui.prop(p, "mirror_x", "X", style="toggle")
            ui.prop(p, "mirror_y", "Y", style="toggle")
            ui.prop(p, "mirror_z", "Z", style="toggle")
        ui.prop(p, "mirror_center", "Merkez", style="object",
                choices=lambda: [(o, o.name) for o in ctx.scene.objects])
        ui.label("Dikiş kenarı ortak olur; ikincil işlemlerde 'Aynala' ile araç da aynalanır.",
                 "dim")


# ---------------------------------------------------------------- Gövde

def body(ui, ctx):
    from . import core
    sc = ctx.scene
    if not ra._kernel_ready():
        kernel(ui, ctx)
        return
    with ui.row(4, 1):
        ui.prop(sc, "minicad_target", "Gövde", style="object", choices=lambda: _cad_objects(ctx))
        ui.button("Aktif", lambda: ra.call("minicad.set_target_active"))
    t = _target(ctx)
    if t is None:
        ui.label("Gövde yok: Yüzey → Sınır yüzeyi ile kenarları seç, Ctrl+Enter: yeni gövde",
                 "info")
        return
    p = t.cad
    if core.frozen(p):
        ui.label("Çizim düzenleniyor: yüzeyler Bitir / Çizimi kapat ile güncellenir", "info")
    elif p.status:
        bad = not p.status.startswith(("Tamam", "Önizleme")) or "Hatalı" in p.status
        ui.label(p.status, "err" if bad else "ok")
    st = core._stats
    with ui.row(1, 1):
        ui.label(f"Hesaplama: {st['count']}", "dim")
        ui.button("Yenile", lambda: ra.call("minicad.rebuild"), icon="REBUILD")
    ui.section("Özet")
    ui.label(f"{len(p.patches)} yüzey · {sum(1 for f in p.features if core.is_bevel(f))} fillet"
             f" · {sum(1 for f in p.features if f.op == 'BOOLEAN')} boolean · "
             f"{sum(1 for f in p.features if f.op == 'SWEEP')} süpürme", "dim")


# ---------------------------------------------------------------- İşlem sırası

def order(ui, ctx):
    t = _need_body(ui, ctx)
    if t is None:
        return
    p = t.cad
    ui.label("Yukarıdan aşağı uygulanır (ör. fillet → kesim → fillet)", "dim")

    def cells(u, it, i):
        u.prop(it, "enabled", "", style="check", weight=0.13)
        u.label(f"{i + 1}. {it.name}", "" if it.ok else "err", weight=1.2)
        u.label("Boolean" if it.op == "BOOLEAN" else "Süpürme" if it.op == "SWEEP" else
                ("Fillet" if it.kind == "FILLET" else "Pah"), "dim", weight=0.6)

    def sel(j):
        p.active_order = j
    ui.list("order", list(p.features), p.active_order, sel, cells, rows=6,
            empty="Henüz fillet / boolean / süpürme yok")
    i = p.active_order
    ok = 0 <= i < len(p.features)
    with ui.row():
        ui.button("Yukarı", lambda: ra.call("minicad.move_feature", index=i, direction=-1),
                  enabled=ok and i > 0, icon="COLLAPSE")
        ui.button("Aşağı", lambda: ra.call("minicad.move_feature", index=i, direction=1),
                  enabled=ok and i < len(p.features) - 1, icon="EXPAND")
        ui.button("Sil", lambda: ra.call("minicad.remove_feature", index=i), enabled=ok,
                  icon="CLOSE")


# ---------------------------------------------------------------- Ayarlar

def settings(ui, ctx):
    from . import core
    sc = ctx.scene
    t = _target(ctx)
    if t is not None:
        p = t.cad
        ui.section("Gövde")
        ui.prop(p, "live", style="check")
        ui.prop(p, "preview", style="check")
        with ui.row():
            ui.prop(p, "preview_bevel", "Önizlemede fillet", style="toggle")
            ui.prop(p, "ghost_bevel", "Hayalet", style="toggle")
        ui.section("Doğruluk")
        ui.prop(p, "lin_defl")
        ui.prop(p, "ang_defl")
        ui.prop(p, "join_tol")
    ui.section("Izgara")
    for n in ("minicad_grid_alpha", "minicad_grid_fade", "minicad_grid_size"):
        if hasattr(sc, n):
            ui.prop(sc, n)
    ui.section("Hesap motoru")
    pr = ra.prefs()
    if pr is not None:
        ui.prop(pr, "background", style="check")
    try:
        c = core._client()
        ui.label(c.describe(), "ok" if c.mode == "process" else "info")
    except Exception:
        pass
    ui.button("Tanı raporu", lambda: ra.call("minicad.diag"), icon="DIAG")


# ---------------------------------------------------------------- Kısıtlar

def constraints_form(ui, ctx):
    from . import constraints
    sc = ctx.scene
    with ui.row():
        ui.prop(sc, "minicad_auto_constraints", "Oto kısıt", style="toggle")
        ui.prop(sc, "minicad_show_constraints", "Göster", style="toggle")
    with ui.row():
        ui.button("Çöz", lambda: ra.call("minicad.constraint_solve"), icon="SOLVE")
        ui.button("Otomatikleri sil", lambda: ra.call("minicad.constraint_clear", auto_only=True))
        ui.button("Tümü", lambda: ra.call("minicad.constraint_clear", auto_only=False),
                  icon="CLOSE", weight=0.6)
    items = list(constraints.all_constraints(sc))
    bad = sum(1 for _o, _i, c in items if c.enabled and not c.ok)
    ui.section(f"Kısıtlar ({len(items)})" + (f" · {bad} sağlanamadı" if bad else ""))

    def cells(u, it, i):
        ob, k, c = it
        u.prop(c, "enabled", "", style="check", weight=0.13)
        name = constraints.NAMES.get(c.kind, c.kind)
        if c.kind == "AXIS":
            name += " " + "XYZ"[c.axis]
        u.label(name + (" (oto)" if c.auto else ""), "" if (c.ok or not c.enabled) else "err",
                weight=1.0)
        if c.kind in ("DISTANCE", "PTLINE", "LINEDIST", "CENTERDIST", "RADIUS"):
            u.prop(c, "length", "", weight=0.9)
        elif c.kind == "ANGLE":
            u.prop(c, "angle", "", weight=0.9)
        else:
            u.label(constraints.describe(c), "dim", weight=0.9)
        u.button("", lambda ob=ob, k=k: ra.call("minicad.constraint_remove", obj=ob.name,
                                                 index=k), icon="CLOSE", weight=0.18)
    sel = ra.form_state.setdefault("cons_sel", [0])
    ui.list("cons", items, sel[0], lambda j: sel.__setitem__(0, j), cells, rows=7,
            empty="Kısıt yok · Kısıt sekmesindeki araçlarla ekle")
    lks = [(ob, i, lk) for ob in sc.objects if ob.type == "CURVE" for i, lk in enumerate(ob.cad.links)]
    if lks:
        ui.section(f"İlişkiler ({len(lks)})")

        def lcells(u, it, j):
            ob, i, lk = it
            u.prop(lk, "enabled", "", style="check", weight=0.13)
            u.label({"RPAT": "Dikdörtgen desen", "CPAT": "Dairesel desen",
                     "PROJ": "Yansıtma"}[lk.kind], "err" if lk.info else "", weight=1.0)
            if lk.kind == "RPAT":
                u.prop(lk, "n1", "", weight=0.5)
                u.prop(lk, "s1", "", weight=0.7)
            elif lk.kind == "CPAT":
                u.prop(lk, "n1", "", weight=0.5)
                u.prop(lk, "angle", "", weight=0.7)
            u.button("", lambda ob=ob, i=i: ra.call("minicad.link_remove", obj=ob.name, index=i),
                     icon="CLOSE", weight=0.18)
        lsel = ra.form_state.setdefault("link_sel", [0])
        ui.list("links", lks, lsel[0], lambda j: lsel.__setitem__(0, j), lcells, rows=4)
        j = lsel[0]
        if 0 <= j < len(lks) and lks[j][2].kind == "RPAT" and lks[j][2].n2 > 1:
            lk = lks[j][2]
            with ui.row():
                ui.prop(lk, "n2", "2. yön adet")
                ui.prop(lk, "s2", "Aralık")
        if 0 <= j < len(lks) and lks[j][2].info:
            ui.label(lks[j][2].info, "err")


# ---------------------------------------------------------------- Çekirdek

def kernel(ui, ctx):
    from . import kernel as kmod
    ok = ra._kernel_ready()
    if ok:
        ui.label("OpenCASCADE çekirdeği hazır", "ok")
    else:
        ui.label("OpenCASCADE çekirdeği kurulu değil: CAD yüzeyleri ve katı işlemleri için "
                 "gerekli (bir kez indirilir).", "warn")
        try:
            err = kmod.last_error()
            if err:
                ui.label(err[:160], "err")
        except Exception:
            pass
        ui.button("Çekirdeği kur", lambda: ra.call("minicad.install_kernel"), icon="KERNEL",
                  primary=True)
    ui.button("Yeniden denetle", lambda: ra.call("minicad.check_kernel"), icon="REBUILD")
    try:
        from . import core
        ui.label("Hesap motoru: " + core._client().describe(), "dim")
    except Exception:
        pass


# ---------------------------------------------------------------- Mesh → tel kafes

def wire_mesh(ui, ctx):
    sc = ctx.scene
    ui.label("Mesh düzenleme modunda kenarları seç, sonra dönüştür.", "dim")
    with ui.row(1, 1):
        ui.prop(sc, "minicad_poly_smooth", style="check")
        with ui.enabled(sc.minicad_poly_smooth):
            ui.prop(sc, "minicad_poly_corner", "")
    edit = ctx.mode == "EDIT_MESH"
    ui.button("Seçili kenarlardan tel kafes", lambda: ra.call("minicad.mesh_to_wire",
                                                              invoke=True),
              icon="WIRE_MESH", primary=True, enabled=edit)
    if not edit:
        ui.label("Şu an mesh düzenleme modunda değilsin (Tab)", "info")


# ---------------------------------------------------------------- Kenar seçimi

def edge_pick(ui, ctx):
    pk, n = _pick_row(ui, ctx)
    ui.label("Tık: zincir · Alt+tık: tek parça · Sarı: boolean kenarları", "dim")
    ui.section("Seçimden")
    with ui.row():
        ui.button("Yüzey", lambda: ra.key_pick("RET"), icon="PATCH", primary=True,
                  enabled=n > 0, key="Enter")
        ui.button("Yeni gövde", lambda: ra.key_pick("RET", ctrl=True), icon="BODY",
                  enabled=n > 0, key="Ctrl+Enter")
    with ui.row():
        ui.button("Fillet", lambda: ra.key_pick("B"), icon="FILLET3D", enabled=n > 0, key="B")
        ui.button("Süpürme", lambda: ra.key_pick("P"), icon="SWEEP", enabled=n > 0, key="P")
    if pk is not None:
        ui.button("Tel kafesi düzenle (Tab)", lambda: ra.key_pick("TAB"), icon="EDITSK")
    t = _target(ctx)
    if t is not None and ra._kernel_ready():
        ui.prop(t.cad, "default_bevel", "Fillet ölçüsü")


# ---------------------------------------------------------------- Yüzeyi böl

SPLIT_MODES = Meta.enum([("LOOP", "Halka (R)", ""), ("KNIFE", "Bıçak (K)", "")])


def split_face(ui, ctx):
    op = ra.split_op()
    if op is None:
        ui.label("Yüzeyi böl kapalı", "dim")
        ui.button("Yüzeyi böl", lambda: ra.call("minicad.split_surface", invoke=True),
                  icon="SPLIT_FACE", primary=True)
        return
    ui.prop(op, "mode", "", meta=SPLIT_MODES, style="seg",
            on_change=lambda v: ra.key_split("R" if v == "LOOP" else "K"))
    if op.mode == "LOOP":
        ui.label("Bir yüzey kenarının üzerine gel, tıkla: halka boyunca böler.", "dim")
        ui.prop(op, "count", "Kesim sayısı", meta=Meta.int(1, 16, "Kesim sayısı"))
        ui.prop(op, "center", "Ortadan (C)", meta=Meta.bool("Ortadan"), style="check")
    else:
        ui.label("Yüzey sınırına tıkla, noktaları ver, Enter: kes.", "dim")
        ui.prop(op, "view_proj", "Görüşten izdüşür (V)", meta=Meta.bool("Görüş"),
                style="check")
    ui.button("Kapat", lambda: ra.call("minicad.split_surface", invoke=True), icon="CLOSE")


# ---------------------------------------------------------------- Yüzey onarımı (v0.31.0)

TONE = {"GAP": "warn", "TJUNC": "warn", "DUP": "warn", "TINY": "warn", "EXTRA": "warn",
        "BRANCH": "err"}
ICON = {"GAP": "CLOSE_LOOP", "TJUNC": "SPLIT", "DUP": "COLLINEAR", "TINY": "DELETE",
        "EXTRA": "TRIM", "BRANCH": "COINCIDENT"}
FIX_TEXT = {"GAP": "Uçları birleştir", "TJUNC": "Böl ve kaynat", "DUP": "Fazlayı çıkar",
            "TINY": "Parçayı çıkar", "EXTRA": "Seçimden çıkar"}


def repair_form(ui, ctx):
    """v0.32.0: Öneriler — bekleyen yüzey onarımı + model denetimi bulguları."""
    from . import repair
    d = repair.PENDING["data"]
    if d is not None:
        ui.section("Yüzey oluşturulamadı")
        _repair_pending(ui, ctx, d)
    _health_section(ui, ctx, has_pending=d is not None)


LEVEL_TONE = {"error": "err", "warn": "warn", "hint": "info"}


def _health_section(ui, ctx, has_pending):
    from . import health
    items = health.all_findings()
    n = sum(len(fs) for _k, _n, fs in items)
    if not n and not has_pending:
        ui.label("Model denetimi: sorun bulunmadı", "ok")
    for key, name, fs in items:
        ui.section(f"{name} ({len(fs)})")
        for f in sorted(fs, key=lambda f: health.LEVEL_ORDER[f["level"]]):
            ui.label(f["msg"], LEVEL_TONE[f["level"]])
            for label, fn, icon in f["fixes"]:
                ui.button(label, (lambda key=key, fn=fn, label=label:
                                  health.apply_fix(key, fn, label)), icon=icon)
    ui.sep()
    ui.button("Yeniden denetle", health.check_all, icon="DIAG")
    ui.label("Denetim her işlem bitince bir kez çalışır; düzeltmeler sorulmadan yapılmaz ve "
             "tek adımda geri alınır (Ctrl+Z). İşaretli noktalar görünümde halkalı.", "dim")


def _repair_pending(ui, ctx, d):
    from . import repair
    ui.label(d["msg"], "err")
    steps = d.get("plan") or d["issues"]
    fixable = [i for i in steps if i["fix"]]
    now = {id(i) for i in d["issues"]}
    ui.section(f"Öneriler ({len(steps)})")
    first = {i["msg"] for i in d["issues"]}
    for k, iss in enumerate(steps):
        ui.label(f"{k + 1}. " + iss["msg"], TONE.get(iss["kind"], "warn"))
        if iss["fix"] and iss["msg"] in first:      # şimdi uygulanabilen adım
            j = next(n for n, x in enumerate(d["issues"]) if x["msg"] == iss["msg"])
            ui.button(FIX_TEXT.get(iss["kind"], "Düzelt"), lambda j=j: repair.fix(j),
                      icon=ICON.get(iss["kind"]))
    del now
    ui.sep()
    ui.button("Hepsini düzelt ve yüzeyi oluştur", lambda: repair.fix(None), icon="PATCH",
              primary=True, enabled=bool(fixable))
    with ui.row():
        ui.button("Yeniden dene", repair.create, icon="REBUILD")
        ui.button("Vazgeç", repair.cancel, icon="CLOSE")



FORMS = {
    # şerit kimliği: (başlık, simge, spec, genişlik)
    "FILLET_R": ("Fillet / pah", "FILLET3D", fillet, 300),
    "CHAMFER": ("Fillet / pah", "FILLET3D", fillet, 300),
    "BOOL_DIFF": ("Boolean", "BOOL_DIFF", boolean, 310),
    "BOOL_UNION": ("Boolean", "BOOL_UNION", boolean, 310),
    "BOOL_INT": ("Boolean", "BOOL_INT", boolean, 310),
    "SWEEP": ("Profil süpürme", "SWEEP", sweep, 310),
    "SURF_LIST": ("Yüzeyler", "SURF_LIST", surfaces, 310),
    "BLEND_G0": ("Yüzeyler", "SURF_LIST", surfaces, 310),
    "BLEND_G1": ("Yüzeyler", "SURF_LIST", surfaces, 310),
    "SYM_BODY": ("Ayna simetrisi", "MIRROR_BODY", mirror, 280),
    "BODY": ("Gövde", "BODY", body, 300),
    "ORDER": ("İşlem sırası", "ORDER", order, 310),
    "SETTINGS": ("Ayarlar", "SETTINGS", settings, 300),
    "CONS_LIST": ("Kısıtlar ve ilişkiler", "CONS_LIST", constraints_form, 340),
    "KERNEL": ("Çekirdek", "KERNEL", kernel, 300),
    "WIRE_MESH": ("Mesh'ten tel kafes", "WIRE_MESH", wire_mesh, 300),
    "EDGE_PICK": ("Kenar seçimi", "EDGE_PICK", edge_pick, 300),
    "PATCH": ("Kenar seçimi", "EDGE_PICK", edge_pick, 300),
    "SPLIT_FACE": ("Yüzeyi böl", "SPLIT_FACE", split_face, 280),
    "REPAIR": ("Öneriler", "DIAG", repair_form, 360),
}


def _unused():   # pragma: no cover
    return bpy
