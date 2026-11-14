"""Hata / iş akışı kaydı: kısayola (Ctrl+Alt+R) ya da panel düğmesine basınca birkaç saniye
boyunca Blender'daki olayları ve Mini CAD durumunu kaydeder, öncesindeki son dakikanın
günlüğünü de ekleyip okunur bir raporu PANOYA kopyalar. Rapor Claude'a Ctrl+V ile yapıştırılır.

Kaydedilenler: tuş / fare olayları (hangi alan ve bölgede), Mini CAD'in kendi günlüğü
(hesaplar, seçim / çizim eylemleri, hesap süreci), konsola düşen hatalar, sahnedeki CAD
gövdelerinin ve tel kafeslerin durumu, açık araçların (Kenar Seç / Çiz) iç durumu.
Görüntü kaydı yapılmaz; istenirse sonda bir ekran görüntüsü (PNG) dosyaya alınır.
"""

import collections
import math
import os
import platform
import re
import sys
import time
import traceback

import bpy

_BUF = collections.deque(maxlen=1500)     # (zaman, tür, metin)
_STATE = {"active": None}
_KEYMAPS = []
RETRO_SECONDS = 60.0
MAX_CHARS = 60000


def log(cat, msg):
    """Mini CAD'in kendi olay günlüğü (her zaman açık, hafif)."""
    try:
        _BUF.append((time.time(), cat, str(msg)[:500]))
    except Exception:
        pass


# ---------------------------------------------------------------- konsol yakalama

class _Tee:
    """sys.stdout / sys.stderr'e yazılanları hem konsola hem günlüğe gönderir."""

    def __init__(self, orig, cat):
        self._orig = orig
        self._cat = cat
        self._part = ""

    def write(self, s):
        try:
            self._part += s
            if "\n" in self._part:
                lines = self._part.split("\n")
                self._part = lines.pop()
                for ln in lines:
                    if ln.strip():
                        log(self._cat, ln)
        except Exception:
            pass
        return self._orig.write(s)

    def flush(self):
        return self._orig.flush()

    def __getattr__(self, name):
        return getattr(self._orig, name)


def _install_tee():
    if not isinstance(sys.stdout, _Tee):
        sys.stdout = _Tee(sys.stdout, "konsol")
    if not isinstance(sys.stderr, _Tee):
        sys.stderr = _Tee(sys.stderr, "HATA")


def _remove_tee():
    if isinstance(sys.stdout, _Tee):
        sys.stdout = sys.stdout._orig
    if isinstance(sys.stderr, _Tee):
        sys.stderr = sys.stderr._orig


# ---------------------------------------------------------------- durum anlık görüntüsü

def _version():
    try:
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "blender_manifest.toml")
        m = re.search(r'^version\s*=\s*"([^"]+)"', open(p, encoding="utf-8").read(), re.M)
        return m.group(1) if m else "?"
    except Exception:
        return "?"


def fmt_pt(p):
    if p is None:
        return "None"
    try:
        return "(" + ", ".join(f"{float(x):.5g}" for x in p) + ")"
    except Exception:
        return str(p)


def _short(s, n=160):
    s = str(s)
    return s if len(s) <= n else s[:n] + "…"


def _cad_lines(context):
    from . import core
    out = []
    try:
        from .ui import get_target
        target = get_target(context)
    except Exception:
        target = None
    cads = [o for o in context.scene.objects if o.type == "MESH" and o.cad.is_cad][:8]
    if not cads:
        out.append("(sahnede CAD gövdesi yok)")
    for ob in cads:
        p = ob.cad
        try:
            vis = ob.visible_get()
        except Exception:
            vis = "?"
        me = ob.data
        out.append(f"- {ob.name}{'  [HEDEF]' if ob == target else ''} · görünür={vis} · "
                   f"mesh {len(me.vertices)}v/{len(me.polygons)}f · durum: {p.status!r}")
        out.append(f"    ayarlar: canlı={p.live} önizleme={p.preview} hayalet={p.ghost_bevel} "
                   f"önizlemede_bevel={p.preview_bevel} katı={p.make_solid} köşe={p.corner_mode} "
                   f"pürüzsüz={p.smooth_corners} ayna={p.use_mirror}"
                   f"({'X' if p.mirror_x else ''}{'Y' if p.mirror_y else ''}"
                   f"{'Z' if p.mirror_z else ''}) boolean={p.use_booleans} "
                   f"fillet={p.use_bevels} tol={p.join_tol:g} sapma={p.lin_defl:g} "
                   f"birleşim={getattr(p, 'surface_blend', '?')}")
        for i, pt in enumerate(p.patches):
            src = sorted({r.obj.name for r in pt.segs if r.obj} |
                         {r.obj.name for r in pt.curves if r.obj})
            out.append(f"    yüzey {i}: {pt.name} [{pt.method}/{getattr(pt, 'blend', '?')}] etkin={pt.enabled} "
                       f"{'OK' if pt.ok else 'HATA'} · {len(pt.segs)} segment "
                       f"{'+ ' + str(len(pt.curves)) + ' eğri objesi ' if len(pt.curves) else ''}"
                       f"· kaynak {src} · {_short(pt.info)}")
            if i < 16:
                out += _patch_geometry(pt, p.join_tol)
        for i, f in enumerate(p.features):
            if f.op == "BOOLEAN":
                desc = (f"BOOLEAN {f.bool_type} araç={f.tool.name if f.tool else None} "
                        f"yeni_kenar={f.edge_size:g} ({f.edge_mode}) aynala={f.mirror_tool}")
            else:
                desc = (f"{f.kind} {f.size:g} · {len(f.segs)} tel kafes kenarı + "
                        f"{len(f.geo_edges)} gövde kenarı")
            out.append(f"    işlem {i}: {f.name} etkin={f.enabled} {desc} "
                       f"{'OK' if f.ok else 'HATA'} · {_short(f.info)}")
        d = core._display.get(ob.name, {})
        g = d.get("ghost")
        out.append(f"    çizim verisi: {len(d.get('edges') or [])} kenar, "
                   f"{len(d.get('bool_edges') or [])} boolean kenarı, hayalet="
                   f"{'var' if g is not None else 'yok'}")
    return out


def _curve_lines(context):
    out = []
    curves = [o for o in context.scene.objects if o.type == "CURVE"][:10]
    if not curves:
        out.append("(eğri objesi yok)")
    for ob in curves:
        try:
            vis = ob.visible_get()
        except Exception:
            vis = "?"
        sps = ob.data.splines
        try:
            colls = [c.name for c in ob.users_collection]
        except Exception:
            colls = "?"
        lv = ""
        try:
            sp3d = next((a.spaces.active for a in bpy.context.screen.areas
                         if a.type == "VIEW_3D"), None)
            if sp3d is not None and sp3d.local_view is not None:
                lv = f" · yerel görünümde={ob.local_view_get(sp3d)}"
        except Exception:
            pass
        out.append(f"- {ob.name} · ebeveyn={ob.parent.name if ob.parent else None} · "
                   f"mod={ob.mode} · görünür={vis} · koleksiyon={colls}{lv} · "
                   f"{ob.data.dimensions} · {len(sps)} spline")
        for si, sp in enumerate(list(sps)[:16]):
            if sp.type == "BEZIER":
                bp = sp.bezier_points
                kinds = sorted({b.handle_left_type for b in bp} | {b.handle_right_type for b in bp})
                out.append(f"    spline {si}: BEZIER {len(bp)} nokta kapalı={sp.use_cyclic_u} "
                           f"tutamaç={kinds}")
            else:
                out.append(f"    spline {si}: {sp.type} {len(sp.points)} nokta "
                           f"kapalı={sp.use_cyclic_u}")
        if len(sps) > 16:
            out.append(f"    … {len(sps) - 16} spline daha")
    return out


def _patch_geometry(pt, tol):
    """v0.25.7: yüzeyin sınırı — kenar kenar segment referansları ve köşe / orta noktaların
    dünya koordinatları (yüzey biçimi sorunlarını yeniden kurabilmek için)."""
    try:
        from . import core
        segs = core.patch_segments(pt)
        loops = core.chain_loops(segs, max(min(tol, 1e-3), 1e-6))
    except Exception as e:
        return [f"      sınır okunamadı: {e}"]
    out = []

    def f3(v):
        return "(" + ", ".join(f"{float(x):.4g}" for x in v) + ")"

    def mid(sg):
        P = [tuple(q) for q in sg["p"]]
        if len(P) == 2:
            return tuple((a + b) / 2 for a, b in zip(*P))
        return tuple(0.125 * a + 0.375 * b + 0.375 * c + 0.125 * d for a, b, c, d in zip(*P))
    for li, chain in enumerate(loops):
        try:
            sides = core.split_sides(chain)
        except Exception:
            sides = [[s_] for s_ in chain]
        out.append(f"      döngü {li}: {len(sides)} kenar")
        for j, side in enumerate(sides):
            refs = [s_.get("ref") for s_ in side]
            refs = [f"{r[0]}:{r[1]}.{r[2]}" for r in refs if r]
            pts = " → ".join(f3(mid(s_)) for s_ in side)
            out.append(f"        kenar {j}: {f3(side[0]['p'][0])} … {f3(side[-1]['p'][-1])} · "
                       f"{len(side)} seg {refs} · ortalar {pts}")
    return out


def _tool_lines():
    out = []
    try:
        from . import pick
        op = pick._STATE["active"]
        if op is not None:
            sc = getattr(op, "scene", None)
            out.append(f"Kenar Seç AÇIK · seçili {len(op.selected)} · üzerinde={op.hover} · "
                       f"sahnede {len(sc.refs) if sc else '?'} kenar "
                       f"({sc.kinds.count('body') if sc and hasattr(sc, 'kinds') else 0} gövde)")
    except Exception as e:
        out.append(f"Kenar Seç durumu okunamadı: {e}")
    try:
        from . import draw
        op = draw._STATE["active"]
        if op is not None:
            pl = op.plane or op.tmp_plane
            cur = fmt_pt(op.cursor)
            out.append(f"Çiz AÇIK · araç={op.tool} · düzlem modu={op.plane_mode} "
                       f"etkin={pl.name if pl else None} · {len(op.segs)} parça · "
                       f"ara noktalar={len(op.stage)} · başlangıç={op.start is not None} · "
                       f"imleç={cur} · yakalama={op.snap_kind} · kılavuz="
                       f"{(op.info or {}).get('kind')} · yazılan={op.typed} alan={op.field} · "
                       f"kısıt seçimi={[r[:4] for r in op.c_refs]} · yakalama açık={op.snap_on} · "
                       f"aşama={op.phase} · taslak={len(op.sketch)} çizgi · iz="
                       f"{len(op.track['pts']) if op.track else None} · sürükleme="
                       f"{op.sk_drag['key'] if op.sk_drag else None} · geçici zemin="
                       f"{(getattr(op, 'temp', None) or {}).get('label')}")
    except Exception as e:
        out.append(f"Çiz durumu okunamadı: {e}")
    try:
        from . import split
        op = split._STATE["active"]
        if op is not None:
            hov = op.edges[op.hover[0]][0] if op.hover is not None else None
            out.append(f"Yüzeyi Böl AÇIK · yöntem={op.mode} · kesim sayısı={op.count} · "
                       f"yazılan={op.typed!r} · ortala={op.center} · üzerinde={hov} · "
                       f"bıçak noktaları={len(op.knife)} · önizleme={len(op.preview)} kesim · "
                       f"görünüş izdüşümü={op.view_proj} · {len(op.edges)} kenar · "
                       f"mesh={'var' if op.mesh else 'yok'} · bölünen={op.done}")
    except Exception as e:
        out.append(f"Yüzeyi Böl durumu okunamadı: {e}")
    return out or ["(Kenar Seç, Çiz ve Yüzeyi Böl kapalı)"]


def snapshot(context):
    from . import core
    lines = []
    ao = context.active_object
    sel = [o.name for o in context.selected_objects][:12]
    lines.append(f"Mod: {context.mode} · aktif: {ao.name + ' (' + ao.type + ')' if ao else None}"
                 f" · seçili: {sel}")
    try:
        us = context.scene.unit_settings
        lines.append(f"Birim: {us.system} {getattr(us, 'length_unit', '')} ölçek={us.scale_length}")
    except Exception:
        pass
    try:
        c = core._client()
        lines.append(f"Hesap motoru: {c.describe()} · oturum {c.session} · çökme "
                     f"{len(c.crashes)} · meşgul={c.busy()} · son hesap "
                     f"{core._stats.get('last_ms', 0):.0f} ms · toplam {core._stats.get('count')}")
    except Exception as e:
        lines.append(f"Hesap motoru okunamadı: {e}")
    lines.append("")
    lines.append("CAD gövdeleri:")
    try:
        lines += _cad_lines(context)
    except Exception as e:
        lines.append(f"(okunamadı: {e})")
    lines.append("")
    lines.append("Tel kafes eğrileri:")
    try:
        lines += _curve_lines(context)
    except Exception as e:
        lines.append(f"(okunamadı: {e})")
    lines.append("")
    lines.append("Kısıtlar:")
    try:
        from . import constraints
        items = list(constraints.all_constraints(context.scene))
        if not items:
            lines.append("(yok)")
        for ob, i, c in items[:40]:
            val = f" {c.length:g}" if c.kind == "DISTANCE" else (
                f" {math.degrees(c.angle):.2f}°" if c.kind == "ANGLE" else "")
            lines.append(f"- {ob.name}[{i}] {c.kind}{val} etkin={c.enabled} oto={c.auto} "
                         f"{'OK' if c.ok else 'HATA'} · {constraints.describe(c)} · {c.info}")
    except Exception as e:
        lines.append(f"(okunamadı: {e})")
    lines.append("")
    lines.append("Araçlar:")
    lines += _tool_lines()
    return lines


def _short_state(context):
    """Kayıt sırasında sık örneklenen kısa durum (sadece değişince günlüğe yazılır)."""
    parts = []
    for ob in context.scene.objects:
        if ob.type == "MESH" and ob.cad.is_cad:
            parts.append(f"{ob.name}: {ob.cad.status}")
    parts += [t for t in _tool_lines() if not t.startswith("(")]
    return parts


# ---------------------------------------------------------------- rapor

def _area_at(context, x, y):
    try:
        for area in context.window.screen.areas:
            if area.x <= x < area.x + area.width and area.y <= y < area.y + area.height:
                for r in area.regions:
                    if r.x <= x < r.x + r.width and r.y <= y < r.y + r.height and \
                            r.width > 1 and r.height > 1:
                        return f"{area.type}/{r.type} {x - r.x},{y - r.y}"
                return f"{area.type} {x - area.x},{y - area.y}"
    except Exception:
        pass
    return f"{x},{y}"


def build_report(context, rec):
    t0 = rec["t0"]
    out = [f"=== Mini CAD kayıt raporu (Claude için) ===",
           f"Mini CAD {_version()} · Blender {bpy.app.version_string} · "
           f"{platform.system()} {platform.release()} · Python {sys.version.split()[0]}",
           f"Dosya: {os.path.basename(bpy.data.filepath) or '(kaydedilmemiş)'} · "
           f"kayıt {rec['dur']:.1f} sn · {time.strftime('%Y-%m-%d %H:%M:%S')}",
           ""]
    if rec.get("note"):
        out += [f"Not: {rec['note']}", ""]
    out.append("## Kayıt başındaki durum")
    out += rec["before"]
    out.append("")
    out.append("## Zaman çizelgesi (saniye; eksi = kayıttan önce)")
    events = [(t, c, m) for (t, c, m) in list(_BUF) if t >= t0 - RETRO_SECONDS]
    events += rec["events"]
    events.sort(key=lambda e: e[0])
    last = None
    for t, c, m in events:
        line = f"{t - t0:+7.2f}  [{c}] {m}"
        if line != last:
            out.append(line)
        last = line
    if not events:
        out.append("(olay yok)")
    out.append("")
    out.append("## Kayıt sonundaki durum")
    out += snapshot(context)
    try:
        from . import core
        log_path = core._client().log_path
        if log_path and os.path.isfile(log_path):
            txt = open(log_path, encoding="utf-8", errors="replace").read().strip()
            if txt:
                out += ["", "## Hesap süreci günlüğü (son 1500 karakter)", txt[-1500:]]
    except Exception:
        pass
    if rec.get("shot"):
        out += ["", f"Ekran görüntüsü: {rec['shot']}"]
    text = "\n".join(out)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS // 3] + "\n… (kısaltıldı) …\n" + text[-2 * MAX_CHARS // 3:]
    return text


def _report_dir():
    try:
        return bpy.utils.extension_path_user(__package__, path="reports", create=True)
    except Exception:
        d = os.path.join(bpy.app.tempdir or os.path.expanduser("~"), "mini_cad_reports")
        os.makedirs(d, exist_ok=True)
        return d


# ---------------------------------------------------------------- operatör

KEY_SKIP = {"TIMER", "TIMER_REPORT", "TIMERREGION", "NONE", "INBETWEEN_MOUSEMOVE",
            "WINDOW_DEACTIVATE", "TIMER0", "TIMER1", "TIMER2", "TIMER_AUTOSAVE",
            "TIMER_JOBS"}


class MINICAD_OT_record(bpy.types.Operator):
    bl_idname = "minicad.record"
    bl_label = "Kayıt → Claude"
    bl_description = ("Birkaç saniye boyunca yaptıklarını ve Mini CAD'in durumunu kaydeder, son "
                      "1 dakikanın günlüğüyle birlikte raporu panoya kopyalar (Claude'a Ctrl+V "
                      "ile yapıştır). Kısayol: Ctrl+Alt+R. Kayıt sürerken tekrar basınca erken "
                      "biter")
    bl_options = {"REGISTER"}

    def invoke(self, context, event):
        op = _STATE["active"]
        if op is not None:
            op.stop_now = True                       # ikinci basış: hemen bitir
            return {"CANCELLED"}
        sc = context.scene
        self.dur = float(getattr(sc, "minicad_rec_seconds", 3.0))
        self.shot = bool(getattr(sc, "minicad_rec_shot", False))
        self.stop_now = False
        self.t0 = time.time()
        self.events = []
        self.last_move = (0.0, -999, -999)
        self.last_state = None
        self.next_sample = 0.0
        try:
            self.before = snapshot(context)
        except Exception as e:
            self.before = [f"(anlık görüntü alınamadı: {e})"]
        log("kayıt", f"kayıt başladı ({self.dur:g} sn)")
        self._timer = context.window_manager.event_timer_add(0.1, window=context.window)
        context.window_manager.modal_handler_add(self)
        _STATE["active"] = self
        self._sample(context)
        self.report({"INFO"}, f"Mini CAD kaydı başladı ({self.dur:g} sn)")
        _redraw(context)
        return {"RUNNING_MODAL"}

    def _ev(self, cat, msg):
        self.events.append((time.time(), cat, msg))

    def _sample(self, context):
        try:
            st = _short_state(context)
        except Exception as e:
            st = [f"durum okunamadı: {e}"]
        if st != self.last_state:
            prev = set(self.last_state or [])
            for s in st:
                if s not in prev:
                    self._ev("durum", s)
            self.last_state = st

    def modal(self, context, event):
        now = time.time()
        if event.type == "TIMER":
            if now >= self.next_sample:
                self._sample(context)
                self.next_sample = now + 0.25
                _redraw(context)                     # paneldeki geri sayım
            if self.stop_now or now - self.t0 >= self.dur:
                return self._finish(context)
            return {"PASS_THROUGH"}
        if event.type in KEY_SKIP:
            return {"PASS_THROUGH"}
        try:
            where = _area_at(context, event.mouse_x, event.mouse_y)
            if event.type == "MOUSEMOVE":
                t, x, y = self.last_move
                if now - t >= 0.15 and abs(event.mouse_x - x) + abs(event.mouse_y - y) > 4:
                    self.last_move = (now, event.mouse_x, event.mouse_y)
                    self._ev("fare", where)
            else:
                mods = "+".join(m for m, on in (("Ctrl", event.ctrl), ("Shift", event.shift),
                                                ("Alt", event.alt)) if on)
                key = f"{mods + '+' if mods else ''}{event.type}"
                uni = f" '{event.unicode}'" if event.unicode and event.unicode.isprintable() \
                    else ""
                self._ev("girdi", f"{key} {event.value}{uni} @ {where}")
        except Exception:
            pass
        return {"PASS_THROUGH"}

    def _finish(self, context):
        try:
            context.window_manager.event_timer_remove(self._timer)
        except Exception:
            pass
        _STATE["active"] = None
        dur = time.time() - self.t0
        log("kayıt", "kayıt bitti")
        rec = {"t0": self.t0, "dur": dur, "events": self.events, "before": self.before}
        d = _report_dir()
        stamp = time.strftime("%Y%m%d_%H%M%S")
        if self.shot:
            path = os.path.join(d, f"mini_cad_{stamp}.png")
            try:
                bpy.ops.screen.screenshot(filepath=path)
                rec["shot"] = path
            except Exception as e:
                rec["shot"] = f"alınamadı: {e}"
        try:
            text = build_report(context, rec)
        except Exception as e:
            text = f"Mini CAD rapor oluşturulamadı: {e}\n{traceback.format_exc()}"
        context.window_manager.clipboard = text
        path = os.path.join(d, f"mini_cad_{stamp}.txt")
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception:
            path = None
        n = text.count("\n") + 1
        self.report({"INFO"}, f"Kayıt panoya kopyalandı ({n} satır) — Claude'a Ctrl+V ile "
                              f"yapıştır" + (f" · dosya: {path}" if path else ""))
        _redraw(context)
        return {"FINISHED"}


def _redraw(context):
    try:
        for area in context.window.screen.areas:
            if area.type == "VIEW_3D":
                area.tag_redraw()
    except Exception:
        pass


def is_recording():
    return _STATE["active"] is not None


def remaining():
    op = _STATE["active"]
    if op is None:
        return 0.0
    return max(0.0, op.dur - (time.time() - op.t0))


classes = (MINICAD_OT_record,)


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.minicad_rec_seconds = bpy.props.FloatProperty(
        name="Kayıt Süresi", description="Kısayola basınca kaç saniye kaydedilsin "
        "(son 1 dakikanın günlüğü her zaman eklenir)", default=3.0, min=0.5, max=60.0,
        unit="TIME_ABSOLUTE")
    bpy.types.Scene.minicad_rec_shot = bpy.props.BoolProperty(
        name="Ekran Görüntüsü", description="Kayıt sonunda ekran görüntüsünü PNG olarak da "
        "kaydet (dosya yolu raporda yazar; görüntüyü ayrıca sohbete ekleyebilirsin)",
        default=False)
    _install_tee()
    try:
        kc = bpy.context.window_manager.keyconfigs.addon
        if kc is not None:
            km = kc.keymaps.new(name="Window", space_type="EMPTY")
            kmi = km.keymap_items.new("minicad.record", "R", "PRESS", ctrl=True, alt=True)
            _KEYMAPS.append((km, kmi))
    except Exception:
        traceback.print_exc()
    log("kayıt", f"Mini CAD {_version()} yüklendi")


def unregister():
    for km, kmi in _KEYMAPS:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    _KEYMAPS.clear()
    _remove_tee()
    for name in ("minicad_rec_seconds", "minicad_rec_shot"):
        try:
            delattr(bpy.types.Scene, name)
        except Exception:
            pass
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
