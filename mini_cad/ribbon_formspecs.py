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


# ---------------------------------------------------------------- Saydamlık (v0.34.0)

def opacity_form(ui, ctx):
    sc = ctx.scene
    with ui.row(4, 1):
        ui.prop(sc, "minicad_target", "Gövde", style="object", choices=lambda: _cad_objects(ctx))
        ui.button("Aktif", lambda: ra.call("minicad.set_target_active"))
    t = _target(ctx)
    if t is None:
        ui.label("Gövde yok", "info")
    else:
        ui.prop(t.cad, "opacity", "Opaklık")
        with ui.row():
            for v in (1.0, 0.6, 0.35, 0.15):
                ui.button(f"%{int(v * 100)}", lambda v=v: setattr(t.cad, "opacity", v),
                          depress=abs(t.cad.opacity - v) < 1e-3)
        ui.button("Bütün gövdelere uygula",
                  lambda: [setattr(o.cad, "opacity", t.cad.opacity) for o, _n in _cad_objects(ctx)])
    ui.section("Çizerken")
    ui.prop(sc, "minicad_draw_ghost", "Çizim açıkken saydam", style="check")
    ui.prop(sc, "minicad_draw_opacity", "Çizerken opaklık", enabled=sc.minicad_draw_ghost)
    ui.label("Görünüm Katı (Solid) ya da Malzeme önizlemesindeyken etkilidir", "dim")


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
                "Delik" if it.op == "HOLE" else "Ekstrüzyon" if it.op == "EXTRUDE" else
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
    ui.section("Uzun hesaplar")
    if pr is not None:
        ui.prop(pr, "calc_budget", "Süre sınırı (sn, 0 = sınırsız)")
    ui.label("Süre aşılınca o ana kadarki gövde gösterilir, kalanı için sorulur", "dim")
    if t is not None:
        ui.prop(t.cad, "full_calc", "Bu gövdede her zaman tamamını hesapla", style="check")
        pa = core.PARTIAL.get(t.name)
        if pa is not None or t.name in core.HELD:
            ui.label(t.cad.status, "warn")
            ui.button("Tamamla (sınırsız)", lambda: ra._msg(core.continue_full(t.name) or ""),
                      icon="CALC_CONT", primary=True)
    r = core.running()
    if r is not None:
        ui.label(f"Süren hesap: {r['name']} · {r['progress']} · {r['sec']:.0f} sn", "info")
        ui.button("Hesabı durdur", lambda: core.cancel_running(), icon="CALC_STOP")
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



# ---------------------------------------------------------------- Delik (v0.33.0)

HOLE_END = Meta.enum([("DIST", "Mesafe", ""), ("THRU", "Tümüyle geçen", "")])


class _HoleEnd:
    """Bitiş seçimi (hole_through bool'unu bölmeli seçime çevirir)."""

    def __init__(self, f):
        self.f = f

    @property
    def end(self):
        return "THRU" if self.f.hole_through else "DIST"

    @end.setter
    def end(self, v):
        self.f.hole_through = v == "THRU"


def _hole_feature(ctx, t):
    op = ra.hole_op()
    if op is not None and op.body_name == t.name:
        f = op.feature()
        if f is not None:
            return f, True
    uid = ra.form_state.get("hole_uid")
    holes = [f for f in t.cad.features if f.op == "HOLE"]
    f = next((f for f in holes if f.uid == uid), None) or (holes[-1] if holes else None)
    return f, False


def hole_form(ui, ctx):
    from . import hole, holemath
    t = _need_body(ui, ctx)
    if t is None:
        return
    p = t.cad
    f, live = _hole_feature(ctx, t)
    holes = [x for x in p.features if x.op == "HOLE"]
    if live:
        ui.label(f"Yüzeye tıkla: delik yeri ({len(f.hole_pts)} delik) · eskiz noktası / daire "
                 "merkezine yakalar · Backspace: son deliği geri al", "info")
    if f is None:
        ui.label("Gövdede delik yok.", "dim")
        with ui.row():
            for k, nm, _d in holemath.KINDS:
                ui.button(nm, lambda k=k: ra._hole(ctx, k), icon="HOLE", primary=k == "SIMPLE")
        return
    ui.section("Tür")
    ui.prop(f, "hole_kind", "", style="seg",
            on_change=lambda v, f=f: hole.apply_preset(f))
    kinfo = {k: d for k, _n, d in holemath.KINDS}.get(f.hole_kind, "")
    ui.label(kinfo, "dim")
    if f.hole_kind == "TAPPED":
        if not f.thr.inited:
            hole.apply_preset(f)
        thread_ui(ui, f.thr, role="hole", on_change=lambda f=f: _hole_drill(f))
        with ui.row():
            ui.prop(f, "hole_mouth_d", "Ağız pahı Ø (0: yok)")
            ui.prop(f, "hole_mouth_angle", "Açı", meta=Meta("FLOAT", "Açı", min=10, max=170,
                                                           step=100, precision=0))
    else:
        _clearance_ui(ui, f, hole)
    ui.section("Bitiş")
    ui.prop(_HoleEnd(f), "end", "", meta=HOLE_END, style="seg")
    if not f.hole_through:
        with ui.row():
            ui.prop(f, "hole_depth", "Derinlik")
            ui.prop(f, "hole_tip", "Uç açısı", meta=Meta("FLOAT", "Uç açısı", min=0, max=179,
                                                        step=100, precision=0))
    ui.label(holemath.describe(core_params(f), fmt=_fmt_len), "dim")
    ui.section(f"Yerler ({len(f.hole_pts)})")

    def cells(u, h, i):
        u.label(f"{i + 1}.", "dim", weight=0.15)
        u.label("  ".join(f"{c:.3f}" for c in h.co), "", weight=1.0)
        u.button("", lambda i=i, f=f: _hole_drop(t, f, i), icon="CLOSE", weight=0.18)
    sel = ra.form_state.setdefault("hole_pt", [0])
    ui.list("holepts", list(f.hole_pts), sel[0], lambda j: sel.__setitem__(0, j), cells,
            rows=4, empty="Yüzeye tıklayarak yer ekle")
    if f.info:
        ui.label(f.info, "ok" if f.ok else "err")
    # v0.36.0: uyumlu vida / somun
    if len(f.hole_pts):
        ui.section("Vida")
        j = min(sel[0], len(f.hole_pts) - 1)
        with ui.row():
            ui.button("Uyumlu vida", lambda: _part_for(ctx, t, f, j, "SCREW"), icon="BOLT",
                      primary=f.hole_kind == "TAPPED",
                      tip="Bu deliğe uyan vida: diş ve tolerans delikten, boy delikten")
            if f.hole_kind != "TAPPED" and f.hole_through:
                ui.button("Somun", lambda: _part_for(ctx, t, f, j, "NUT"), icon="NUT",
                          tip="Geçen deliğin çıkışına somun")
            if len(f.hole_pts) > 1:
                ui.button("Her yere", lambda: _part_all(ctx, t, f), icon="BOLT",
                          tip="Bütün yerlere vida (geçen delikte somun da)")
        linked = _parts_of(t, f)
        if linked:
            ui.label(f"Bağlı: {', '.join(o.name for o in linked[:4])}"
                     + (" …" if len(linked) > 4 else ""), "dim")
    if live:
        with ui.row(2, 1):
            ui.button("Tamam", lambda: _hole_finish(ctx), icon="FINISH", primary=True,
                      key="Enter")
            ui.button("Vazgeç", lambda: _hole_finish(ctx, cancel=True), icon="CLOSE",
                      key="Esc")
    else:
        with ui.row():
            ui.button("Yer ekle", lambda f=f: _hole_edit(ctx, f), icon="HOLE", primary=True)
            ui.button("Deliği sil", lambda f=f: _hole_remove(t, f), icon="CLOSE")
    if len(holes) > 1 or not live:
        ui.section(f"Delikler ({len(holes)})")

        def hcells(u, x, i):
            u.prop(x, "enabled", "", style="check", weight=0.13)
            u.label(x.name, "" if x.ok else "err", weight=0.8)
            u.label(holemath.describe(core_params(x), fmt=_fmt_len), "dim", weight=1.6)
        act = next((i for i, x in enumerate(holes) if x == f), -1)

        def pick(j):
            ra.form_state["hole_uid"] = holes[j].uid
        ui.list("holes", holes, act, pick, hcells, rows=4)


def _clearance_ui(ui, f, hole):
    """Düz / kademeli / konik havşa: vida ölçüsü, geçme sınıfı, baş türü, ölçüler."""
    with ui.row(1, 1):
        ui.prop(f, "hole_thread", "Vida", on_change=lambda v, f=f: hole.apply_preset(f))
        ui.button("Ölçülerden doldur", lambda f=f: hole.apply_preset(f),
                  enabled=f.hole_thread != "NONE")
    ui.prop(f, "hole_fit", "", style="seg", on_change=lambda v, f=f: hole.apply_preset(f))
    if f.hole_kind == "CBORE":
        ui.prop(f, "hole_head", "Vida başı", on_change=lambda v, f=f: hole.apply_preset(f))
    elif f.hole_kind == "CSINK":
        ui.prop(f, "hole_csk", "Havşa türü", on_change=lambda v, f=f: hole.apply_preset(f))
    ui.section("Ölçüler")
    ui.prop(f, "hole_d", "Çap")
    if f.hole_kind == "CBORE":
        with ui.row():
            ui.prop(f, "hole_cb_d", "Yuva Ø")
            ui.prop(f, "hole_cb_depth", "Derinlik")
    elif f.hole_kind == "CSINK":
        with ui.row():
            ui.prop(f, "hole_cs_d", "Havşa Ø")
            ui.prop(f, "hole_cs_angle", "Açı", meta=Meta("FLOAT", "Açı", min=10, max=170,
                                                        step=100, precision=0))
        ui.prop(f, "hole_cs_head", "Havşa üstü pay")
    else:
        with ui.row():
            ui.prop(f, "hole_mouth_d", "Ağız pahı Ø")
            ui.prop(f, "hole_mouth_angle", "Açı", meta=Meta("FLOAT", "Açı", min=10, max=170,
                                                           step=100, precision=0))


def _hole_drill(f):
    """Diş ayarı değişince matkap çapı (görüntü ve ön ayarlar için) güncellenir."""
    from . import thread
    try:
        f.hole_d = thread.hole_thread_params(f)[0]
    except Exception:
        pass


# ---------------------------------------------------------------- Diş ayarları (v0.36.0)

class _ThrAdapter:
    """Dinamik seçimler (standart, ölçü, profil, geçme) için bölmeli / açılır seçim."""

    def __init__(self, thr, on_change=None):
        self.thr, self.cb = thr, on_change

    def _done(self):
        if self.cb:
            self.cb()

    @property
    def family(self):
        return self.thr.family

    @family.setter
    def family(self, v):
        from . import thread
        if v == "CUSTOM":
            self.thr.family = "CUSTOM"
        else:
            thread.fill_standard(self.thr, v, None)
        self._done()

    @property
    def size(self):
        return self.thr.size

    @size.setter
    def size(self, v):
        from . import thread
        thread.fill_standard(self.thr, self.thr.family, v)
        self._done()

    @property
    def profile(self):
        return self.thr.profile

    @profile.setter
    def profile(self, v):
        from . import thread
        thread.set_profile(self.thr, v)
        self._done()

    @property
    def fit(self):
        return self.thr.fit

    @fit.setter
    def fit(self, v):
        from . import thread
        self.thr.fit = v
        thread.apply_fit(self.thr)
        self._done()


def _thr_custom(thr, cb=None):
    """Standart değer elle değişti: Özel."""
    if thr.family != "CUSTOM":
        from . import thread
        thr.size = thread.thread_name(thr)
        thr.family = "CUSTOM"
    if cb:
        cb()


def thread_ui(ui, thr, role="hole", on_change=None):
    """Diş bölümü: delik (iç diş) ve vida / somun (dış / iç diş) penceresinde ortak.
    Bağlı vidada aynı ayarlar düzenlenir: değişiklik hem deliğe hem vidaya gider."""
    from . import thread, threadmath as tm
    ad = _ThrAdapter(thr, on_change)
    cb = (lambda v=None: on_change()) if on_change else None
    ui.section("Diş")
    with ui.row(1, 1):
        ui.prop(ad, "family", "Standart", meta=Meta.enum(tm.family_items(), "Standart"),
                style="drop")
        if thr.family != "CUSTOM":
            ui.prop(ad, "size", "Ölçü", meta=Meta.enum([(n, n, "") for n in
                                                        tm.sizes(thr.family)], "Ölçü"),
                    style="drop")
    ui.prop(thr, "modeled", "Modellenmiş diş (helisel geometri)", style="check", on_change=cb)
    sp = None
    try:
        sp = thread.spec(thr)
        r_root, R = tm.radii(sp)
        dh, ds = thread.offsets(thr)
        txt = (f"{sp['name']} · adım {_fmt_len(thr.P)} · diş yüksekliği "
               f"{_fmt_len(R - r_root)}")
        if role == "hole":
            drill = tm.minor_drill(sp, dh, thr.engage) if thr.modeled else sp["tap"] + 2 * dh
            txt += f" · matkap Ø{_fmt_len(drill)}"
        ui.label(txt, "dim")
    except Exception as e:
        ui.label(f"Diş değeri hatalı: {e}", "err")
    with ui.row(1, 1):
        ui.prop(thr, "hand", "", style="seg", on_change=cb)
        ui.prop(thr, "starts", "Ağız", on_change=cb)
    if role != "screw":                     # vidada dişli kısım vida bölümünde
        ui.prop(thr, "length", "Diş boyu (0: tamamı)", on_change=cb)
    # ---- profil ayrıntıları (aç / kapa)
    key = f"thr_adv_{role}"
    adv = ra.form_state.setdefault(key, [False])
    ui.button(("▾ " if adv[0] else "▸ ") + "Diş profili ve ölçüleri",
              lambda: adv.__setitem__(0, not adv[0]), depress=adv[0])
    if adv[0]:
        ui.prop(ad, "profile", "", meta=Meta.enum(tm.PROFILES, "Profil"), style="drop")
        cc = lambda v=None, thr=thr: _thr_custom(thr, on_change)  # noqa: E731
        with ui.row():
            ui.prop(thr, "D", "Anma Ø", on_change=cc)
            ui.prop(thr, "P", "Adım", on_change=cc)
        if thr.profile not in ("SQUARE",):
            with ui.row():
                ui.prop(thr, "angle", "Açı", meta=Meta("FLOAT", "Profil açısı", min=0,
                                                       max=150, step=100, precision=1),
                        on_change=cc)
                if thr.profile == "BUTT":
                    ui.prop(thr, "angle2", "Yük yanı", meta=Meta("FLOAT", "Yük yanı açısı",
                                                                min=0, max=80, step=100,
                                                                precision=1), on_change=cc)
        with ui.row():
            ui.prop(thr, "depth", "Yükseklik", on_change=cc)
            ui.prop(thr, "crest", "Tepe genişliği", on_change=cc)
        with ui.row():
            ui.prop(thr, "rc", "Tepe R", on_change=cc)
            ui.prop(thr, "rr", "Dip R", on_change=cc)
        if thr.profile == "CUSTOM":
            ui.prop(thr, "custom_obj", "Eğri", style="object",
                    choices=lambda: [(o, o.name) for o in bpy.data.objects
                                     if o.type == "CURVE"], on_change=cb)
            ui.prop(thr, "custom_w", "Genişlik / adım", on_change=cb)
            ui.label("Eğri XY düzleminde: X diş genişliği boyunca, Y diş yüksekliği; başı "
                     "ve sonu dipte (Y en küçük).", "dim")
        if thr.family != "CUSTOM" or thr.size:
            ui.button("Standart değerlere dön", lambda: (thread.fill_standard(
                thr, thr.family if thr.family != "CUSTOM" else "ISO_M", None),
                on_change and on_change()), icon="REBUILD")
    # ---- geçme / tolerans
    ui.section("Geçme (vida ↔ delik boşluğu)")
    fits = [(k, n, d) for k, n, d, _c in tm.FITS]
    ui.prop(ad, "fit", "Ön ayar", meta=Meta.enum(fits, "Geçme"), style="drop")

    def fit_custom(v=None, thr=thr):
        if thr.fit != "CUSTOM":
            thr.fit = "CUSTOM"
        if on_change:
            on_change()
    with ui.row():
        ui.prop(thr, "clearance", "Boşluk", on_change=fit_custom)
        ui.prop(thr, "share", "Deliğe pay", on_change=cb)
    ui.prop(thr, "swell", "Baskı genleşmesi (XY)", on_change=cb)
    if role in ("hole", "nut"):
        ui.prop(thr, "engage", "Diş kavrama", on_change=cb)
    if role == "screw":
        ui.prop(thr, "lead_in", "Uçta giriş pahı", style="check", on_change=cb)
    try:
        dh, ds = thread.offsets(thr)
        ui.label(f"Delik dişi +{_fmt_len(dh)} · vida dişi −{_fmt_len(-ds)} (yüzeye dik)", "dim")
    except Exception:
        pass
    err = thread.check(thr)
    if err:
        ui.label(err, "err")


def _parts_of(t, f):
    from . import thread
    return [o for o in thread.parts_linked_to(t) if o.cad.part.link_uid == f.uid]


def _part_for(ctx, t, f, j, kind):
    from . import thread
    ob, msg = thread.create_for_hole(bpy.context, t, f, j, kind)
    if ob is not None:
        ra.form_state["part"] = ob.name
        try:
            bpy.ops.ed.undo_push(message=f"BlendCAD: {ob.name}")
        except Exception:
            pass
    ra._msg(msg)


def _part_all(ctx, t, f):
    from . import thread
    n = 0
    for j in range(len(f.hole_pts)):
        ob, _m = thread.create_for_hole(bpy.context, t, f, j, "SCREW")
        n += ob is not None
        if f.hole_kind != "TAPPED" and f.hole_through:
            ob2, _m = thread.create_for_hole(bpy.context, t, f, j, "NUT")
            n += ob2 is not None
    try:
        bpy.ops.ed.undo_push(message="BlendCAD: vidalar")
    except Exception:
        pass
    ra._msg(f"{n} parça oluşturuldu")


# ---------------------------------------------------------------- Vida / somun (v0.36.0)

def _part_obj(ctx):
    from . import thread
    for ob in (bpy.context.view_layer.objects.active, _target(ctx),
               bpy.data.objects.get(ra.form_state.get("part", ""))):
        if thread.is_part(ob):
            return ob
    return None


def part_form(ui, ctx):
    from . import thread
    ob = _part_obj(ctx)
    if not ra._kernel_ready():
        _need_body(ui, ctx)
        return
    if ob is None:
        ui.label("Seçili vida / somun yok. Dişli deliğin penceresinde 'Uyumlu vida' ile "
                 "delikten oluştur ya da bağımsız parça ekle (3B imleçte):", "dim")
        with ui.row():
            ui.button("Yeni vida", lambda: _part_new(ctx, "SCREW"), icon="BOLT", primary=True)
            ui.button("Yeni somun", lambda: _part_new(ctx, "NUT"), icon="NUT")
        _part_list(ui, None)
        return
    pt = ob.cad.part
    kind = ob.cad.part_kind
    ui.label(ob.name, "info")
    f = thread.linked_feature(ob)
    if f is not None:
        with ui.row(2, 1):
            ui.label(f"Delik: {pt.link_obj.name} · {f.name} · {pt.link_pt + 1}. yer", "dim",
                     weight=2)
            ui.button("Deliğe yerleştir", lambda: (thread.place(ob), _rb(ob)), icon="MOVE")
        if f.hole_kind == "TAPPED":
            ui.prop(pt, "linked", "Diş ve tolerans delikten (birlikte değişir)",
                    style="check")
    thr = thread.source_thread(ob)
    role = "screw" if kind == "SCREW" else "nut"
    if kind == "SCREW":
        ui.section("Vida")
        ui.prop(pt, "head", "Baş")
        if pt.head != "HEX":
            ui.prop(pt, "drive", "", style="seg")
        with ui.row(1, 1):
            ui.prop(pt, "length", "Boy")
            ui.prop(_LenAdapter(pt), "std", "Standart boy",
                    meta=Meta.enum(_std_lengths(), "Standart boy"), style="drop")
        ui.prop(pt.thr, "length", "Dişli kısım (0: tam)")
        ui.prop(pt, "auto_head", "Standart baş ölçüleri", style="check")
        if not pt.auto_head:
            with ui.row():
                ui.prop(pt, "head_dk", "Baş Ø" if pt.head != "HEX" else "Anahtar ağzı")
                ui.prop(pt, "head_k", "Yükseklik")
            with ui.row():
                ui.prop(pt, "drive_s", "Anahtar")
                ui.prop(pt, "drive_t", "Yuva derinliği")
    else:
        ui.section("Somun")
        ui.prop(pt, "auto_head", "Standart somun ölçüleri (ISO 4032)", style="check")
        if not pt.auto_head:
            with ui.row():
                ui.prop(pt, "nut_s", "Anahtar ağzı")
                ui.prop(pt, "nut_m", "Yükseklik")
    if thr == pt.thr or not pt.linked:
        thread_ui(ui, pt.thr, role=role)
    else:
        ui.label("Diş ayarları bağlı delikten geliyor; buradan değiştirince delik de değişir.",
                 "dim")
        thread_ui(ui, thr, role=role)
    if ob.cad.status:
        ok = "Kapalı katı" in ob.cad.status
        ui.label(ob.cad.status, "ok" if ok else "err")
    _part_list(ui, ob)


class _LenAdapter:
    def __init__(self, pt):
        self.pt = pt

    @property
    def std(self):
        from . import thread
        v = round(thread.mm(self.pt.length), 3)
        return f"{v:g}"

    @std.setter
    def std(self, v):
        from . import thread
        self.pt.length = thread.u(float(v))


def _std_lengths():
    from . import threadmath as tm
    return [(f"{L:g}", f"{L:g} mm", "") for L in tm.STD_LENGTHS]


def _rb(ob):
    from . import core
    core.rebuild(ob)


def _part_new(ctx, kind):
    from . import thread
    ob = thread.create_free(bpy.context, kind)
    ra.form_state["part"] = ob.name
    try:
        bpy.ops.ed.undo_push(message=f"BlendCAD: {ob.name}")
    except Exception:
        pass
    ra._msg(f"{ob.name}: {ob.cad.status}")


def _part_list(ui, cur):
    from . import thread
    parts = [o for o in bpy.data.objects if thread.is_part(o)]
    if not parts:
        return
    ui.section(f"Vidalar ve somunlar ({len(parts)})")

    def cells(u, o, i):
        u.label(o.name, "" if "Kapalı katı" in o.cad.status else "err", weight=1.2)
        u.label(o.cad.part.link_obj.name if o.cad.part.link_obj else "bağımsız", "dim")
    act = next((i for i, o in enumerate(parts) if o == cur), -1)

    def pick(j):
        ra.form_state["part"] = parts[j].name
        try:
            for o in bpy.context.selected_objects:
                o.select_set(False)
            parts[j].select_set(True)
            bpy.context.view_layer.objects.active = parts[j]
        except Exception:
            pass
    ui.list("parts", parts, act, pick, cells, rows=4)


# ---------------------------------------------------------------- Ekstrüzyon (v0.34.0)

def _ext_feature(ctx, t):
    op = ra.extrude_op()
    if op is not None and op.body_name == t.name:
        f = op.feature()
        if f is not None:
            return f, op
    uid = ra.form_state.get("ext_uid")
    exts = [f for f in t.cad.features if f.op == "EXTRUDE"]
    f = next((f for f in exts if f.uid == uid), None) or (exts[-1] if exts else None)
    return f, None


def extrude_form(ui, ctx):
    t = _need_body(ui, ctx)
    if t is None:
        return
    p = t.cad
    f, op = _ext_feature(ctx, t)
    exts = [x for x in p.features if x.op == "EXTRUDE"]
    if op is not None and op.asking:
        ui.label("Nasıl bir ekstrüzyon?", "info")
        ui.button("Doğrusal — tek yönde (yüz normali) uzat", lambda: op.set_kind(ctx, "LINEAR"),
                  icon="EXTRUDE", primary=True, key="1")
        ui.label("Yüz tek bir doğrultuda prizma gibi uzar (Inventor Extrude)", "dim")
        ui.button("Kalınlaştır — yüzey normalleri boyunca", lambda: op.set_kind(ctx, "THICK"),
                  icon="THICKEN", primary=True, key="2")
        ui.label("Yüz kendi normalleri boyunca kalınlık kazanır, geometrik şekli korunur; "
                 "eğri yüzeyde her nokta kendi normaline gider", "dim")
        ui.button("Vazgeç", lambda: op.finish(ctx, cancel=True), icon="CLOSE", key="Esc")
        return
    if f is None:
        ui.label("Gövdede ekstrüzyon yok.", "dim")
        ui.button("Ekstrüzyon", lambda: ra._extrude(ctx, ""), icon="EXTRUDE", primary=True)
        return
    if op is not None:
        ui.label(f"Yüzeye tıkla ({len(f.ext_pts)} yüz) · Shift+tık: ekle · oku sürükle / ölçü "
                 "yaz · F: yön · Tab: tür", "info")
    ui.prop(f, "ext_kind", "", style="seg")
    with ui.row(3, 1):
        ui.prop(f, "ext_dist", "Mesafe" if f.ext_kind == "LINEAR" else "Kalınlık")
        ui.prop(f, "ext_flip", "Çevir", style="toggle", icon="FLIP_DIR")
    ui.prop(f, "ext_sym", "İki yönlü (simetrik)", style="check")
    ui.section("İşlem")
    ui.prop(f, "ext_op", "", style="seg")
    ui.prop(f, "ext_scope", "", style="seg")
    if p.use_mirror and (p.mirror_x or p.mirror_y or p.mirror_z):
        ui.prop(f, "mirror_tool", "Aynalı uygula", style="check")
    ui.label(f"{len(f.ext_pts)} yüz seçili" if f.ext_scope == "FACE" else
             "Açık yüzey gövdesinin tamamı katılaşır", "dim")
    if f.info:
        ui.label(f.info, "ok" if f.ok else "err")
    if op is not None:
        with ui.row(2, 1):
            ui.button("Tamam", lambda: op.finish(ctx), icon="FINISH", primary=True,
                      key="Enter")
            ui.button("Vazgeç", lambda: op.finish(ctx, cancel=True), icon="CLOSE", key="Esc")
    else:
        with ui.row():
            ui.button("Yüz seç", lambda f=f: _ext_edit(ctx, f), icon="EXTRUDE", primary=True)
            ui.button("Sil", lambda f=f: _ext_remove(t, f), icon="CLOSE")
    if len(exts) > 1 or op is None:
        ui.section(f"Ekstrüzyonlar ({len(exts)})")

        def ecells(u, x, i):
            u.prop(x, "enabled", "", style="check", weight=0.13)
            u.label(x.name, "" if x.ok else "err", weight=0.9)
            u.label(("Doğrusal" if x.ext_kind == "LINEAR" else "Kalınlaştır") + " · " +
                    _fmt_len(x.ext_dist), "dim", weight=1.3)
        act = next((i for i, x in enumerate(exts) if x == f), -1)

        def pick(j):
            ra.form_state["ext_uid"] = exts[j].uid
        ui.list("exts", exts, act, pick, ecells, rows=4)


def _ext_edit(ctx, f):
    ra.form_state["ext_uid"] = f.uid
    ra._call(ctx, lambda: __import__("bpy").ops.minicad.extrude("INVOKE_DEFAULT", uid=f.uid))


def _ext_remove(t, f):
    from . import core
    for i, x in enumerate(t.cad.features):
        if x == f:
            t.cad.features.remove(i)
            break
    core.rebuild(t)


def core_params(f):
    from . import core
    return core.hole_params(f)


def _hole_drop(t, f, i):
    from . import core
    if 0 <= i < len(f.hole_pts):
        f.hole_pts.remove(i)
        core.rebuild(t)


def _hole_finish(ctx, cancel=False):
    op = ra.hole_op()
    if op is not None:
        op.finish(ctx, cancel=cancel)


def _hole_edit(ctx, f):
    ra.form_state["hole_uid"] = f.uid
    ra._call(ctx, lambda: bpy.ops.minicad.hole("INVOKE_DEFAULT", uid=f.uid))


def _hole_remove(t, f):
    from . import core
    for i, x in enumerate(t.cad.features):
        if x == f:
            t.cad.features.remove(i)
            break
    core.forget_cache(t.name)
    core.rebuild(t)


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
    "OPACITY": ("Saydamlık", "OPACITY", opacity_form, 290),
    "ORDER": ("İşlem sırası", "ORDER", order, 310),
    "SETTINGS": ("Ayarlar", "SETTINGS", settings, 300),
    "CONS_LIST": ("Kısıtlar ve ilişkiler", "CONS_LIST", constraints_form, 340),
    "KERNEL": ("Çekirdek", "KERNEL", kernel, 300),
    "WIRE_MESH": ("Mesh'ten tel kafes", "WIRE_MESH", wire_mesh, 300),
    "EDGE_PICK": ("Kenar seçimi", "EDGE_PICK", edge_pick, 300),
    "PATCH": ("Kenar seçimi", "EDGE_PICK", edge_pick, 300),
    "SPLIT_FACE": ("Yüzeyi böl", "SPLIT_FACE", split_face, 280),
    "REPAIR": ("Öneriler", "DIAG", repair_form, 360),
    "HOLE": ("Delik", "HOLE", hole_form, 340),
    "BOLT": ("Vida / somun", "BOLT", part_form, 340),
    "NUT": ("Vida / somun", "BOLT", part_form, 340),
    "SCREW_FIT": ("Vida / somun", "BOLT", part_form, 340),
    "EXTRUDE": ("Ekstrüzyon", "EXTRUDE", extrude_form, 330),
    "EXT_LINEAR": ("Ekstrüzyon", "EXTRUDE", extrude_form, 330),
    "EXT_THICK": ("Ekstrüzyon", "EXTRUDE", extrude_form, 330),
    "EXT_LIST": ("Ekstrüzyon", "EXTRUDE", extrude_form, 330),
}


def _unused():   # pragma: no cover
    return bpy
