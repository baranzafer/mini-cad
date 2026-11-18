# v0.28.0: BlendCAD şeridi işlevlere bağlı — ribbon_actions (sahte bpy / sahte çizim modülü),
# başlık örtüşmesine göre yerleşim (ribbon_state.insets), küçük düğmeler, durum kancaları.
import sys, types, importlib, contextlib
from types import SimpleNamespace as NS

fails = 0
def check(ok, msg):
    global fails
    print(("  ok  " if ok else "  HATA ") + msg)
    if not ok: fails += 1

for n in ("gpu", "blf", "gpu_extras", "gpu_extras.batch"):
    sys.modules[n] = types.ModuleType(n)
sys.modules["gpu_extras.batch"].batch_for_shader = None

# ---- sahte bpy
calls = []
class _Ops:
    def __init__(s, ns): s.ns = ns
    def __getattr__(s, name):
        def f(*a, **k):
            calls.append((s.ns + "." + name, a, k))
            hook = HOOKS.get(s.ns + "." + name)
            if hook: hook(*a, **k)
            return {"FINISHED"}
        return f
HOOKS = {}
bpy = types.ModuleType("bpy")
bpy.types = NS(Panel=object, Operator=object)
bpy.ops = NS(minicad=_Ops("minicad"), wm=_Ops("wm"))
bpy.utils = NS(register_class=lambda c: None, unregister_class=lambda c: None)
class Region(NS): pass
win_r = Region(type="WINDOW", x=0, y=0, width=1600, height=900)
hdr = Region(type="HEADER", x=0, y=874, width=1600, height=26)
thdr = Region(type="TOOL_HEADER", x=0, y=848, width=1600, height=26)
tools = Region(type="TOOLS", x=0, y=0, width=46, height=848)
ui_r = Region(type="UI", x=1600, y=0, width=1, height=1)
class Area(NS):
    def as_pointer(s): return 4242
area = Area(type="VIEW_3D", regions=[win_r, hdr, thdr, tools, ui_r])
window = NS(screen=NS(areas=[area]))
scene = NS(minicad_show_constraints=True, minicad_auto_constraints=True, minicad_grid_snap=True,
           minicad_look_at=True, minicad_pick_plane=True, minicad_draw_target="ACTIVE",
           minicad_bool_type="CUT")
@contextlib.contextmanager
def _tov(**kw):
    yield
ctx = NS(scene=scene, area=area, window=window, mode="OBJECT",
         window_manager=NS(windows=[window]), temp_override=_tov)
bpy.context = ctx
sys.modules["bpy"] = bpy

pkg = types.ModuleType("mini_cad"); pkg.__path__ = ["/home/claude/mini_cad"]; sys.modules["mini_cad"] = pkg
rs = importlib.import_module("mini_cad.ribbon_state")

# ---- başlık örtüşmesi
l, r, t = rs.insets(area, True)
check(t == 52 and l == 46 and r == 0, f"saydam başlık + araç başlığı: üst boşluk 52, sol 46 ({l}, {r}, {t})")
hdr2 = Region(type="HEADER", x=0, y=900, width=1600, height=26)   # örtüşmeyen başlık
check(rs.insets(Area(type="VIEW_3D", regions=[win_r, hdr2]), True)[2] == 0, "örtüşmeyen başlık: boşluk yok")
hdr3 = Region(type="HEADER", x=0, y=0, width=1600, height=26)     # altta başlık
check(rs.insets(Area(type="VIEW_3D", regions=[win_r, hdr3]), True)[2] == 0, "alttaki başlık sayılmaz")
check(rs.insets(area, False)[0] == 0, "örtüşme kapalı: araç çubuğu boşluğu yok")

ribbon = importlib.import_module("mini_cad.ribbon")
data = importlib.import_module("mini_cad.ribbon_data")
class P:
    def measure(s, t, size, bold=False): return (0.6 * size * len(t), size)
    def __getattr__(s, n): return lambda *a, **k: None
p = P()
rb = ribbon.Ribbon(1.0); rb.layout(p, 1600, 900, 46, 0, 52)
check(rb.box[3] <= 900 - 52 and rb.box[0] >= 46, f"şerit başlıkların altında, araç çubuğunun sağında {rb.box}")
lx0, ly0, lx1, ly1 = ribbon.launcher_rect(1600, 900, 1.0, 0, 60, 52)
check(ly1 <= 900 - 52, "başlatıcı başlıkların altında")
rb = ribbon.Ribbon(1.0); rb.layout(p, 2400, 900, 46, 0, 52)
small = [i for i in rb.items if i[4] == "btn" and data.find(i[5]) and data.find(i[5]).get("small")]
check(len(small) == 12 and all(i[3] - i[1] < 20 for i in small), f"Yardımcı + Seçenekler: 12 küçük düğme (v0.34.0: Çizerken saydam) ({len(small)})")

# ---- sahte çizim / kenar seçimi / gövde
class FakeDM:
    AXIS_PLANES = ("XY", "XZ", "YZ")
    class Plane:
        @staticmethod
        def axis(name, o): return ("plane", name)
class FakeOp:
    def __init__(s):
        s.tool, s.phase, s.snap_on, s.grid_on, s.log = "LINE", "PLANE", True, True, []
        s.area = NS(tag_redraw=lambda: None)
    def _set_tool(s, c, t): s.tool = t; s.log.append(("tool", t))
    def _set_plane(s, m): s.log.append(("plane", m)); s.phase = "PLANE" if m == "PICK" else "DRAW"
    def _start_offset(s, c, n, pl): s.log.append(("offset", n)); s.phase = "OFFSET"
    def _finish_sketch(s, c): s.log.append("finish")
    def _undo_last(s, c): s.log.append("undo")
    def _refresh(s, c): pass
    def _hist_sync(s): pass
fdraw = types.ModuleType("mini_cad.draw"); fdraw._STATE = {"active": None}; fdraw.dm = FakeDM
sys.modules["mini_cad.draw"] = fdraw
def _start_draw(*a, **k):
    fdraw._STATE["active"] = None if fdraw._STATE["active"] else FakeOp()
HOOKS["minicad.draw"] = _start_draw
fpick = types.ModuleType("mini_cad.pick"); fpick.run = False; fpick.is_running = lambda: fpick.run
sys.modules["mini_cad.pick"] = fpick
HOOKS["minicad.pick_edges"] = lambda *a, **k: setattr(fpick, "run", not fpick.run)
fsplit = types.ModuleType("mini_cad.split"); fsplit.is_running = lambda: False
sys.modules["mini_cad.split"] = fsplit
body = NS(cad=NS(use_mirror=True, surface_blend="SHARP"))
fui = types.ModuleType("mini_cad.ui"); fui.get_target = lambda c: body; fui.draw_kernel_box = lambda l: None
sys.modules["mini_cad.ui"] = fui
fk = types.ModuleType("mini_cad.kernel"); fk.kernel_available = lambda: True
sys.modules["mini_cad.kernel"] = fk
rs.STATE["area"] = 4242

ra = importlib.import_module("mini_cad.ribbon_actions")
fs = importlib.import_module("mini_cad.ribbon_formspecs")
opened = []
ra.HOOKS["open_form"] = lambda fid, title, icon, spec, width: opened.append((fid, title, spec))
msgs = []
ra.HOOKS["message"] = msgs.append
D = lambda i, kind="TOOL": ra.dispatch(ctx, kind, data.find(i) or {"id": i})

# her düğme bir işleve bağlı mı (planlananlar hariç)
unbound = []
for b in data.all_buttons():
    for it in (b["variants"] or [b]):
        if it["status"] != data.READY:
            continue
        i = it["id"]
        known = (i in ra.DRAW_TOOLS or i in ra.CONS_TOOLS or i in ra.PLANES or i in fs.FORMS or
                 i in ra.SCENE_TOGGLES or i in ra.BOOL_TYPES or i in ra.DRAW_KEYS or
                 i in getattr(ra, "HOLE_KINDS", ()) or i == "HOLE_LIST" or i in (
                     "OPT_SNAP", "SK_START", "SK_FINISH", "SK_UNDO", "SK_CLOSE", "EDIT_ALL",
                     "EDGE_PICK", "PATCH", "PATCH_HOLE", "SPLIT_FACE", "REBUILD", "CONS_SOLVE",
                     "STEP", "DIAG", "REC"))
        if not known:
            unbound.append(i)
check(not unbound, f"bütün hazır düğmeler bağlı {unbound}")
check(len(fs.FORMS) >= 15, f"{len(fs.FORMS)} düğme araç penceresi açar")

# çizim kapalıyken araç: önce çizimi açar, sonra araç
msg = D("RECT3")
op = fdraw._STATE["active"]
check(op is not None and op.tool == "RECT3" and "düzlem" in (msg or ""), "Dikdörtgen 3 nokta: çizim açıldı + araç + düzlem iletisi")
check(ra.active() == "RECT3", "etkin araç şeride yansır")
D("MIRROR2D"); check(op.tool == "MIRROR" and ra.active() == "MIRROR2D", "Ayna: MIRROR aracı ↔ MIRROR2D")
D("DISTANCE"); check(op.tool == "C_DISTANCE" and ra.active() == "DISTANCE", "kısıt aracı C_ önekli")
n_draw = sum(1 for c in calls if c[0] == "minicad.draw")
D("LINE"); check(sum(1 for c in calls if c[0] == "minicad.draw") == n_draw, "çizim açıkken yeniden açılmaz")

# düzlem
op.phase = "PLANE"; D("PL_XZ"); check(op.log[-1] == ("offset", "XZ"), "XZ: düzlem seçimindeyken yüksekliğe geçer")
op.phase = "DRAW"; D("PL_VIEW"); check(op.log[-1] == ("plane", "VIEW"), "Görüş düzlemi")
D("SK_START"); check(op.log[-1] == ("plane", "PICK"), "Eskiz başlat (çizim açık): düzlemi yeniden seçtir")
check(ra.state(data.find("PLANE")) is True, "düzlem seçilirken Düzlem düğmesi açık görünür")

# eskiz
D("SK_FINISH"); check("finish" in op.log, "Bitir")
D("SK_UNDO"); check("undo" in op.log, "Geri al")
D("SK_CLOSE"); check(fdraw._STATE["active"] is None, "Çizimi kapat: minicad.draw yeniden çağrılır (kaydet + kapat)")
check(D("SK_FINISH") and True, "çizim kapalıyken Bitir: ileti")
D("EDIT_ALL"); check(calls[-1][0] == "minicad.edit_sketch", "Çizimi düzenle (tamamı)")

# aç / kapa
D("CONS_SHOW", "TOGGLE"); check(scene.minicad_show_constraints is False, "Kısıtları göster kapandı")
check(ra.state(data.find("CONS_SHOW")) is False, "durum sahneden okunur")
D("OPT_NEW", "TOGGLE"); check(scene.minicad_draw_target == "NEW", "Yeni eğri: hedef NEW")
D("OPT_NEW", "TOGGLE"); check(scene.minicad_draw_target == "ACTIVE", "tekrar: ACTIVE")
check(D("OPT_SNAP", "TOGGLE") is not None, "çizim kapalıyken yakalama: ileti")

# operatörler ve açılır pencereler
D("EDGE_PICK"); check(fpick.run and ra.state(data.find("EDGE_PICK")) is True and opened[-1][0] == "EDGE_PICK", "Kenar seçimi açıldı + penceresi")
D("PATCH"); check(fpick.run and opened[-1][1] == "Kenar seçimi", "Sınır yüzeyi: kenar seçimi penceresi")
D("BOOL_UNION"); check(scene.minicad_bool_type == "UNION" and opened[-1][1] == "Boolean", "Boolean Birleştir: tür + araç penceresi")
check(not any(c[0] == "wm.call_panel" for c in calls), "eski Blender açılır paneli kullanılmıyor")
D("BLEND_G1"); check(body.cad.surface_blend == "TANGENT", "Teğet (G1) gövde ayarı")
D("SWEEP"); check(opened[-1][1] == "Profil süpürme", "Profil süpürme penceresi")
D("REBUILD"); check(calls[-1][0] == "minicad.rebuild", "Yenile")
D("STEP"); check(calls[-1][0] == "minicad.export_step", "STEP")
D("CONS_SOLVE"); check(calls[-1][0] == "minicad.constraint_solve", "Çöz")
check(ra.state(data.find("SYM_BODY")) is True, "Ayna simetrisi açık görünür (gövde ayarı)")
D("WIRE_MESH"); check(opened[-1][0] == "WIRE_MESH", "Mesh'ten tel kafes: pencere")

# hata iletisi (poll)
def _boom(*a, **k): raise RuntimeError("Operator bpy.ops.minicad.split_surface.poll() failed, context is incorrect")
HOOKS["minicad.split_surface"] = _boom
fsplit._STATE = {"active": None}
m = D("SPLIT_FACE"); check(m and "poll" in m, f"poll hatası iletiye döner: {m}")

# kısayol düğmeleri: aynı tuş aracın modal'ına gider
got_ev = []
class KOp(FakeOp):
    def __init__(s):
        super().__init__()
        s.region = NS(x=10, y=20, width=800, height=600); s.mouse = (100.0, 50.0)
    def modal(s, c, ev):
        got_ev.append((ev.type, ev.shift, ev.ctrl, ev.mouse_x, ev.mouse_y)); return {"RUNNING_MODAL"}
fdraw._STATE["active"] = KOp()
D("KEY_G"); check(got_ev[-1] == ("G", False, False, 110.0, 70.0), f"Geçici zemin: G, imleç son konumda {got_ev[-1]}")
D("SK_SURF_NEW"); check(got_ev[-1][:3] == ("F", False, True), "Yeni gövde yüzeyi: Ctrl+F")
D("KEY_COORD"); check(got_ev[-1][:3] == ("TAB", True, False), "Hassas giriş: Shift+Tab")
D("AX_Y"); check(got_ev[-1][0] == "Y", "Eksen kilidi Y")
D("SK_REDO"); check(got_ev[-1][:3] == ("Z", True, True), "Yinele: Ctrl+Shift+Z")
fdraw._STATE["active"].axis_lock = 1
check(ra.state(data.find("AXLOCK")) is True, "eksen kilidi açık görünür")
pk = KOp(); fpick._STATE = {"active": pk}
mod_pick = sys.modules["mini_cad.pick"]; mod_pick._STATE = fpick._STATE
ra.key_pick("B"); check(got_ev[-1][0] == "B", "Fillet uygula düğmesi: kenar seçimine B")
ra.key_pick("RET", ctrl=True); check(got_ev[-1][:3] == ("RET", False, True), "Yeni gövde: Ctrl+Enter")
fdraw._STATE["active"] = None
fdraw._STATE["active"] = None

# şerit: durum kancası + tür eşitleme
rb = ribbon.Ribbon(1.0); rb.state_fn = ra.state; rb.active_fn = ra.active
D("SK_START")      # çizimi aç
fdraw._STATE["active"].tool = "ELLIPSE"
rb.layout(p, 1600, 900)
check(rb.current(rb._btn("CIRCLE"))["id"] == "ELLIPSE" and rb.is_on(rb._btn("CIRCLE")),
      "O ×3 (Elips) klavyeden: Daire düğmesi Elips'i gösterir ve etkin")
got = []
rb.on_action = lambda k, it: (got.append(it["id"]), "ileti")[1]
x0, y0, x1, y1 = rb._rect("btn", "LINE"); rb.press((x0 + x1) / 2, (y0 + y1) / 2, 1.0)
check(got[-1] == "LINE" and rb.toast and rb.toast[0] == "ileti", "tık → on_action, dönen ileti bildirimde")
rb.tab = "HOLE"; rb.layout(p, 1600, 900)
x0, y0, x1, y1 = rb._rect("btn", "THREAD"); rb.press((x0 + x1) / 2, (y0 + y1) / 2, 2.0)
check("planlandı" in rb.toast[0], "planlanan özellik: yakında iletisi")

print("SONUÇ:", "tamam" if not fails else f"{fails} hata")
sys.exit(1 if fails else 0)
