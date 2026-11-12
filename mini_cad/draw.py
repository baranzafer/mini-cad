"""Çizim aracı: 3D görünüm içinde kayan bir araç penceresiyle tel kafese çizer.

Araçlar   Seç (W) · Doğru (L) · Teğet yay (A) · 3 noktalı yay (E) · Merkezli yay (M, D: yön) ·
          Daire (O) · Dikdörtgen (R) · Spline: kontrol noktalı (S) · noktalardan geçen (K) ·
          Kalem (P) · Q: son iki araç arasında geçiş · Shift+Q: düzlem seç
Değiştir  Kırp (B, Shift: Uzat) · Uzat · Böl · Ötele · Köşe yuvarla · Pah (taslak üzerinde;
          bkz. draw_modify.py)
Düzenle   Taşı · Kopyala · Döndür · Ölçekle · Esnet · Desen: dikdörtgen, dairesel · Ayna
          (seç → temel nokta → hedef; bkz. draw_xform.py)
Düzlem    Oto · XY · XZ · YZ · Görünüş (X / Y / Z / V tuşları)
Kısıtlar  Eksen · Paralel · Dik · Doğrusal · Eşit · Çakışık · Sabit · Teğet · Simetrik ·
          Uzunluk · Açı (pencereden seç, sonra kenar / noktalara tıkla)

  Sol tık           nokta koy          Sağ tık / Enter   çizgiyi bitir: TASLAĞA eklenir
  Ctrl+Enter        Bitir: taslaktaki bütün çizgiler eğri objesine kaydedilir (hedef:
                    mevcut eğri ya da yeni eğri; pencerede seçilir)
  Taslak düzenleme  taslağın noktalarını ve eğri tutamaçlarını sürükle; X/Y/Z eksen kilidi
                    (3. eksende düzenleme); pürüzsüz birleşimde karşı tutamaç hizalı kalır.
                    Tıklanan noktada pivot çıkar; oklarından sürükleyince o eksende taşınır.
                    Sürüklerken uç / orta / merkez, kılavuzlar ve ızgara yakalaması geçerli;
                    ölçü yardımcısı uzunluk / açıyı gösterir, yazarak değer girilir (Tab).
  Ctrl+Z / Ctrl+Shift+Z  taslak aşamasında geri al / yinele (Bitir'den sonra Blender'ınki)
  T                 iz: referans noktadan eksenler boyunca (ölçü yazarak) başlangıç noktası
  Düzlem seçimi     1/2 yön (eksen düzlemi ya da yüz), 2/2 yükseklik (fare / nokta / yazarak)
  U                 geçici zemin: ızgaranın yönünü / yüksekliğini değiştir (sağ tık: yön aynı,
                    sadece yükseklik); tekrar U'ya basılana kadar yeni çizgiler bu zemine
                    çizilir, sonra asıl düzleme dönülür. Shift+U: başka bir geçici zemin
  Rakam yaz         ölçü; Tab ile sonraki alan; Enter ile noktayı koy (ör. 25mm, 30)
  C                 başlangıca dönüp kapat      F  kapalı çizgiden yüzey (Ctrl+F: yeni gövde)
  Shift             15° adımlar        Ctrl  yakalamayı kapat        Backspace  geri al
  Kısıt simgesi     sağ tık: dondur / sil (simgeler bilerek silik çizilir)
  Esc               duraklat: "Seç" aracına geçer, tıklamalar Blender'a gider; ikinci Esc kapatır

Yakalama: tel kafes ve CAD gövdesi kenarlarının ucu, ortası, çember merkezi, kesişim ve
kenar üzerinde en yakın nokta, yay merkezleri. Sezgisel kılavuzlar (FORGE snap_math):
yatay / dikey, mevcut doğrulara paralel / dik, önceki parçanın devamı, uç / orta / merkez
noktalarıyla hiza, doğru uzantısı, eğri ve yay uçlarından teğet uzantı, yayın çemberi
boyunca devam. Hepsi zayıf mıknatıstır; çizimi engellemez (Ctrl ile kapanır).
"Oto kısıt" açıksa yakalanan yatay/dikey, paralel/dik, uç çakışması ve yazılan uzunluk
kısıt olarak kaydedilir.

Çizilen her çizgi / şekil eğri objesine YENİ bir spline olarak eklenir; var olan
spline'ların sırası değişmez, böylece yüzeylerin kenar referansları bozulmaz.
"""

import copy
import math
import traceback
import blf
import bpy
import gpu
import numpy as np
from bpy_extras import view3d_utils
from gpu_extras.batch import batch_for_shader
from mathutils import Vector
from . import constraints, core, palette
from . import drawmath as dm

# Ortak adlar draw_common'da; burada geriye dönük uyum için yeniden dışa aktarılır.
from .draw_common import (
    AXIS_COLS, AXIS_OF, CHAIN_TOOLS, COL_ACTIVE, COL_BOX, COL_DONE, COL_GRID, COL_GUIDE,
    COL_REF, COL_RUBBER, COL_SNAP, COL_TEXT, COL_U, COL_V, FIELDS, GRID_MIN_PX, GRID_PX,
    GUIDE_PX, MODIFIERS, PASS_KEYS, PLANE_COLS, PRIORITY, REF_PX, SHAPE_TOOLS, SNAP_PX,
    TOOL_KEYS, _HANDLES, _LAST, _Refs, _STATE, _UNIT_SUFFIX, _axis_col, _bezier, _dashed,
    _line_thirds, _marker, _move_handle, _move_node, _poly, _project, _rect, _remove_handle,
    _seg_px_dist, _shader, _text, cleanup_all, is_running, parse_angle, parse_length,
)
from .draw_plane import PlaneMixin
from .draw_snap import SnapMixin
from .draw_sketch import SketchMixin
from .draw_edit import EditMixin
from .draw_glyphs import ConstraintUIMixin
from .draw_render import RenderMixin
from .draw_modify import MOD_HELP, ModifyMixin
from .draw_xform import TransformMixin
from .draw_common import MODIFY_TOOLS, XFORM_TOOLS


class MINICAD_OT_draw(SnapMixin, PlaneMixin, SketchMixin, EditMixin, ConstraintUIMixin, RenderMixin,
                      ModifyMixin, TransformMixin, bpy.types.Operator):
    bl_idname = "minicad.draw"

    bl_label = "Tel Kafes Çiz"

    bl_description = ("Çizim penceresini açar: doğru, yaylar, daire, dikdörtgen, spline, kalem; "
                      "çalışma düzlemi; paralel / dik / eşit / sabit gibi kısıtlar")

    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.type == "VIEW_3D"

    # ------------------------------------------------------------ yaşam döngüsü

    def invoke(self, context, event):
        if _STATE["active"] is not None:
            cleanup_all()
            self.report({"INFO"}, "Çizim kapatıldı")
            return {"CANCELLED"}
        try:
            from . import pick
            pick.cleanup_all()                 # iki mod aynı anda çalışmasın
        except Exception:
            pass
        self.stop_request = False
        self.area = context.area
        self.region = next((r for r in self.area.regions if r.type == "WINDOW"), None)
        self.rv3d = self.area.spaces.active.region_3d
        if self.region is None or self.rv3d is None:
            self.report({"ERROR"}, "3D görünüm bulunamadı")
            return {"CANCELLED"}
        self.ui_scale = context.preferences.system.ui_scale
        self.radius = SNAP_PX * self.ui_scale
        self.sketch = []                 # Bitir'e kadar hafızada tutulan çizgiler
        self.refs = _Refs(context)
        self.dirty = False
        self.plane_mode = "AUTO"
        self.tool = "LINE"
        self.segs = []
        self.start = None
        self.plane = None
        self.tmp_plane = None
        self.cursor = None
        self.preview = []
        self.snap_kind = None
        self.snap_id = None
        self.info = None
        self.typed = ["", ""]
        self.field = 0
        self.mouse = (0.0, 0.0)
        self.shift = self.ctrl = False
        self.last_closed = None
        self.arc_info = None
        self._grp = 0
        self.stage = []
        self.shape_plane = None
        self.pen = None
        self.out_h = None
        self.carc_flip = False
        self.node_ids = {}
        self.c_refs = []
        self.c_hover = None
        self._cur_chords = []
        self.snap_on = True
        sc = context.scene
        self.grid_on = bool(getattr(sc, "minicad_grid_snap", True))
        self.locked = None
        self.hover_plane = None
        self.gmenu = None
        self.prev_tool = None
        self.start_tan = None
        self.sk_hover = None
        self.sk_drag = None
        self.sk_sel = None               # seçili taslak noktası / tutamacı (pivot gösterilir)
        self.hist, self.redo = [], []    # taslak aşamasının geri al / yinele geçmişi
        self._hsnap = None
        self._hsig = None
        self.track = None
        self.off = None
        self.temp = None                 # geçici zemin (U): {"saved", "plane", "label", "grid_o"}
        self.temp_pick = None            # geçici zemin seçiliyor: {"saved"}
        self.snap_src = None             # geçici zeminde izdüşürülen yakalamanın asıl noktası
        self.snap_src_id = None
        self.plane_snap = None           # düzlem seçerken yakalanan nokta (konum, tür)
        self._mod_init()                 # değiştir araçları (draw_modify)
        self._xf_init()                  # düzenle / desen araçları (draw_xform)
        self.phase = "PLANE" if getattr(sc, "minicad_pick_plane", True) else "DRAW"
        self.palette = palette.Palette(self.ui_scale)
        self.created = 0
        self.msg = ""
        self._h3 = bpy.types.SpaceView3D.draw_handler_add(self._draw3d, (), "WINDOW",
                                                          "POST_VIEW")
        self._h2 = bpy.types.SpaceView3D.draw_handler_add(self._draw2d, (), "WINDOW",
                                                          "POST_PIXEL")
        _HANDLES.extend([self._h3, self._h2])
        _STATE["active"] = self
        context.window_manager.modal_handler_add(self)
        self._status(context)
        self.area.tag_redraw()
        return {"RUNNING_MODAL"}

    def _finish(self, context):
        for h in (getattr(self, "_h3", None), getattr(self, "_h2", None)):
            if h is not None:
                _remove_handle(h)
        self._h3 = self._h2 = None
        if _STATE["active"] is self:
            _STATE["active"] = None
        try:
            context.workspace.status_text_set(None)
        except Exception:
            pass
        try:
            self.area.tag_redraw()
        except Exception:
            pass

    def _tool_name(self):
        if self.tool.startswith("C_"):
            return "Kısıt: " + next((n for k, n in palette.CONSTRAINTS
                                     if k == self.tool[2:]), self.tool)
        return next((n for k, n, _ in palette.DRAW_TOOLS + palette.MODIFY_TOOLS +
                     palette.XFORM_TOOLS + palette.PATTERN_TOOLS if k == self.tool), self.tool)

    def _status(self, context, msg=None):
        if msg is not None:
            self.msg = msg
        plane = "Otomatik" if self.plane_mode == "AUTO" else dm.PLANE_LABELS[self.plane_mode]
        if self.plane is not None:
            plane += f" → {dm.PLANE_LABELS.get(self.plane.name, self.plane.name)}"
        if self.phase == "OFFSET":
            txt = ("DÜZLEM YÜKSEKLİĞİ: fareyi normal boyunca gezdir (noktalara / ızgaraya "
                   "yapışır) ya da değer yaz · Tık / Enter: onayla · Sağ tık: sıfır · "
                   "Esc: yöne geri dön")
            try:
                context.workspace.status_text_set(txt)
            except Exception:
                pass
            return
        if self.phase == "PLANE" and getattr(self, "temp_pick", None) is not None:
            txt = ("GEÇİCİ ZEMİN (1/2: yön): eksen düzlemine ya da gövde yüzüne tıkla  |  X/Y/Z/V: "
                   "eksen / görünüş düzlemi  |  Noktaya tık: o noktadan geçen zemin  |  Sağ tık / Enter: "
                   "mevcut yön, sadece yükseklik  |  Esc: iptal")
            try:
                context.workspace.status_text_set(txt)
            except Exception:
                pass
            return
        if self.phase == "PLANE":
            txt = ("ÇİZİM DÜZLEMİNİ SEÇ (1/2: yön): eksen düzlemine ya da gövde yüzüne tıkla  |  X/Y/Z/V: "
                   "eksen / görünüş düzlemi  |  Sağ tık / Enter: atla (otomatik)  |  Esc: çık")
            if self.msg:
                txt = f"{self.msg}   —   {txt}"
            try:
                context.workspace.status_text_set(txt)
            except Exception:
                pass
            return
        if self.tool == "SELECT":
            txt = ("Seç / duraklat  |  Blender normal çalışır (seçim, G/R/S, edit mod)  |  "
                   "Kısıt simgesine sağ tık: dondur / sil  |  Q: son çizim aracına dön"
                   "  |  Esc: çizimi kapat")
            if self.msg:
                txt = f"{self.msg}   —   {txt}"
            try:
                context.workspace.status_text_set(txt)
            except Exception:
                pass
            return
        if self.tool.startswith("C_"):
            n, is_pt = constraints.needed(self.tool[2:])
            txt = (f"{self._tool_name()}  |  {len(self.c_refs)}/{n} "
                   f"{'nokta' if is_pt else 'kenar'} seçildi  |  Sağ tık: çizime dön  |  "
                   "Simgeye sağ tık: dondur / sil  |  Esc: duraklat")
        else:
            tz = getattr(self, "temp", None)
            if tz is not None:
                plane = f"GEÇİCİ ZEMİN {tz['label']} (U: normale dön, Shift+U: başka zemin)"
            txt = (f"{self._tool_name()} · düzlem: {plane}  |  Tık: nokta  |  Sağ tık/Enter: "
                   "bitir  |  Yaz: ölçü, Tab: sonraki alan  |  W/L/A/E/M/O/R/S/K/P: araç  |  B: kırp  |  Q: önceki "
                   "araç  |  C: kapat  "
                   "|  F: yüzey  |  Ctrl+Z / Ctrl+Shift+Z: taslakta geri al / yinele  |  Shift+Q: düzlem seç  |  U: geçici zemin  |  X/Y/Z/V: düzlem  |  I: ızgara "
                   f"{'açık' if self.grid_on else 'kapalı'}  |  Shift: 15°  |  Ctrl: yakalama "
                   "yok  |  Esc: duraklat")
        if self.msg:
            txt = f"{self.msg}   —   {txt}"
        try:
            context.workspace.status_text_set(txt)
        except Exception:
            pass

    def _set_tool(self, context, tool):
        if tool == self.tool and tool == "TARC":
            tool = "LINE"
        if tool != self.tool:
            self.prev_tool = self.tool
        self._finalize_stage()
        if tool.startswith("C_") and (self.segs or self.sketch):
            self._finish_sketch(context)          # kısıtlar kaydedilmiş eğrilere uygulanır
        if tool == "SELECT" and self.segs:
            self._commit(context)
        if tool in MODIFY_TOOLS and (self.segs or self.start is not None or self.stage):
            self._commit(context)                 # değiştir araçları taslak üzerinde çalışır
        self._mod_init()
        self.mod, self.off_sel, self.mod_drag = None, None, False
        if tool.startswith("C_") or tool == "SELECT" or tool in MODIFY_TOOLS:
            self.preview = []
            self.cursor = None
            self.info = None
            self.snap_kind = None
        self.tool = tool
        self.c_refs, self.c_hover = [], None
        self.typed, self.field = ["", ""], 0
        msg = ""
        if tool == "SELECT":
            msg = "Duraklatıldı: tıklamalar Blender'a gidiyor · çizmek için pencereden araç seç"
        if tool in XFORM_TOOLS:
            msg = self._xf_begin(context, tool, keep=self.prev_tool in XFORM_TOOLS)
            if not self.sketch:
                msg += " · taslakta çizgi yok (bu araçlar taslakta çalışır)"
        elif tool in MODIFY_TOOLS:
            msg = MOD_HELP[tool] if self.sketch else (MOD_HELP[tool] + " · taslakta çizgi yok "
                                                      "(değiştir araçları taslakta çalışır)")
        if tool not in XFORM_TOOLS:
            self.xf, self.xprev = None, []
            if tool not in MODIFY_TOOLS:
                self.xsel, self.xnodes = set(), set()
        if tool == "TARC" and not self.segs and self.start_tan is None:
            msg = ("Teğet yay: bir çizginin ucundan başlarsan ona teğet devam eder; boşlukta "
                   "başlarsan 3 noktalı yay gibi çizer")
        self._status(context, msg)

    # ------------------------------------------------------------ olaylar

    OVERLAY_REGIONS = {"UI", "TOOLS", "HEADER", "TOOL_HEADER", "ASSET_SHELF",
                       "ASSET_SHELF_HEADER", "NAVIGATION_BAR", "HUD", "FOOTER"}

    MOVE_EVENTS = {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE", "TIMER", "TIMER_REPORT",
                   "TIMERREGION", "NONE", "WINDOW_DEACTIVATE"}

    def _mouse_in_region(self, event):
        r = self.region
        x, y = event.mouse_x - r.x, event.mouse_y - r.y
        inside = 0 <= x < r.width and 0 <= y < r.height
        if inside:
            for o in self.area.regions:
                if o.type in self.OVERLAY_REGIONS and o.width > 1 and o.height > 1:
                    ox, oy = event.mouse_x - o.x, event.mouse_y - o.y
                    if 0 <= ox < o.width and 0 <= oy < o.height:
                        inside = False
                        break
        return inside, x, y

    def _refresh(self, context):
        try:
            self._update(context, *self.mouse)
        except Exception as e:
            print("[Mini CAD] çizim güncellenemedi:", e)
        self._status(context)
        self.area.tag_redraw()

    def _palette_event(self, context, event, mx, my, press):
        """Pencere olaylarını işler; olay pencereye aitse True."""
        pal = self.palette
        if pal.drag is not None:
            if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
                pal.move(mx, my)
                self.area.tag_redraw()
                return True
            if event.type == "LEFTMOUSE" and event.value == "RELEASE":
                pal.release()
                return True
        if not pal.contains(mx, my):
            if pal.hover is not None:
                pal.hover = None
                self.area.tag_redraw()
            return False
        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            if pal.move(mx, my):
                self.area.tag_redraw()
            return True
        if event.type == "LEFTMOUSE":
            if not press:
                return True
            h = pal.press(mx, my)
            if h is None:
                return True
            kind, ident = h
            if kind == "close":
                self.stop_request = True
            elif kind == "tool":
                self._set_tool(context, ident)
            elif kind == "cons":
                self._set_tool(context, "C_" + ident)
            elif kind == "sk":
                if ident == "FINISH":
                    self._finish_sketch(context)
                else:
                    self._undo_last(context)
            elif kind == "tgt":
                context.scene.minicad_draw_target = ident
            elif kind == "plane":
                if ident in dm.AXIS_PLANES and self.phase == "PLANE":
                    self._start_offset(context, ident, dm.Plane.axis(ident, (0.0, 0.0, 0.0)))
                else:
                    self._set_plane(ident)
            elif kind == "opt":
                sc = context.scene
                if ident == "auto":
                    sc.minicad_auto_constraints = not sc.minicad_auto_constraints
                elif ident == "show":
                    sc.minicad_show_constraints = not sc.minicad_show_constraints
                elif ident == "snap":
                    self.snap_on = not self.snap_on
                elif ident == "grid":
                    self.grid_on = not self.grid_on
                    sc.minicad_grid_snap = self.grid_on
                elif ident == "look":
                    sc.minicad_look_at = not sc.minicad_look_at
                elif ident == "first":
                    sc.minicad_pick_plane = not sc.minicad_pick_plane
            self._status(context)
            self.area.tag_redraw()
            return True
        return event.type in {"RIGHTMOUSE", "MIDDLEMOUSE"} and False

    def modal(self, context, event):
        # Taslak aşaması için kendi geri al / yinele (Blender'ın geri alması hafızadaki
        # taslağı bilmez). Taslak yoksa Ctrl+Z Blender'a gider.
        if event.type == "Z" and event.value == "PRESS" and event.ctrl and \
                not event.alt and self.sk_drag is None and \
                getattr(self, "phase", "DRAW") == "DRAW" and _STATE["active"] is self:
            self._hist_sync()
            if event.shift and self.redo:
                self._hist_step(context, self.redo, self.hist, "Yinelendi")
                return {"RUNNING_MODAL"}
            if not event.shift and self.hist:
                self._hist_step(context, self.hist, self.redo, "Geri alındı")
                return {"RUNNING_MODAL"}
        r = self._modal_inner(context, event)
        if event.type not in self.MOVE_EVENTS and _STATE["active"] is self:
            try:
                self._hist_sync()
            except Exception:
                traceback.print_exc()
        return r

    def _modal_inner(self, context, event):
        if getattr(self, "stop_request", False) or _STATE["active"] is not self:
            self._finish(context)
            return {"CANCELLED"}
        try:
            self.area.regions[0]
        except Exception:
            self._finish(context)
            return {"CANCELLED"}
        inside, mx, my = self._mouse_in_region(event)
        press = event.value == "PRESS"
        self.shift, self.ctrl = event.shift, event.ctrl

        if event.type == "ESC" and press and self.sk_drag is not None:
            self._drag_cancel()
            return {"RUNNING_MODAL"}
        if event.type == "ESC" and press and self.sk_sel is not None:
            self.sk_sel = None
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type == "ESC" and press and self.track is not None:
            self.track = None
            self._status(context, "İz iptal edildi")
            self._refresh(context)
            return {"RUNNING_MODAL"}
        if event.type == "ESC" and press and self.phase == "OFFSET":
            self.phase, self.off = "PLANE", None
            self._status(context)
            self.area.tag_redraw()
            return {"RUNNING_MODAL"}
        if event.type == "ESC" and press and self.phase == "PLANE" and \
                getattr(self, "temp_pick", None) is not None:
            self._temp_cancel(context)
            self._refresh(context)
            return {"RUNNING_MODAL"}
        if event.type == "ESC" and press:
            self._finalize_stage()
            if len(self.segs):
                self._commit(context)
            if self.tool != "SELECT" and self.phase != "PLANE":
                self._set_tool(context, "SELECT")   # önce duraklat, ikinci Esc kapatır
                self.area.tag_redraw()
                return {"RUNNING_MODAL"}
            self._finish_sketch(context)          # çıkarken taslak kaybolmasın
            self._finish(context)
            return {"FINISHED"} if self.created else {"CANCELLED"}

        if event.type in MODIFIERS:
            if self.sk_drag is not None:
                if self.sk_drag["moved"]:
                    self._drag_apply(*self.mouse)
                self.area.tag_redraw()
                return {"RUNNING_MODAL"}
            self._refresh(context)
            return {"PASS_THROUGH"}

        if inside and self._palette_event(context, event, mx, my, press):
            if getattr(self, "stop_request", False):
                self._finish_sketch(context)
                self._finish(context)
                return {"FINISHED"}
            return {"RUNNING_MODAL"}

        if inside and self.phase == "DRAW" and self.sk_drag is None and self.track is None and \
                self.tool not in MODIFY_TOOLS:
            if self._sketch_event(context, event, mx, my, press):
                return {"RUNNING_MODAL"}
        if self.sk_drag is not None:
            return self._drag_event(context, event, mx, my, press)

        if inside and self.phase == "DRAW":
            if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
                if self._glyph_menu_hover(mx, my):
                    self.area.tag_redraw()
            elif event.type == "LEFTMOUSE" and self.gmenu is not None:
                if press:
                    x0, y0, x1, y1 = self.gmenu["box"]
                    if x0 <= mx <= x1 and y0 <= my <= y1:
                        self._glyph_menu_click(context, mx, my)
                    else:
                        self.gmenu = None          # dışarı tık: sadece menüyü kapat
                    self.area.tag_redraw()
                return {"RUNNING_MODAL"}
            elif event.type == "RIGHTMOUSE":
                if press and self._glyph_menu_open(mx, my):
                    self.area.tag_redraw()
                    return {"RUNNING_MODAL"}
                if not press and self.gmenu is not None:
                    return {"RUNNING_MODAL"}

        if self.tool == "SELECT" and self.phase == "DRAW":
            if event.type == "Q" and press and not (event.ctrl or event.alt or event.shift):
                self._set_tool(context, self.prev_tool or "LINE")
                self._refresh(context)
                return {"RUNNING_MODAL"}
            if event.type not in self.MOVE_EVENTS:
                self.dirty = True                  # kullanıcı bir şey değiştirmiş olabilir
            return {"PASS_THROUGH"}

        if not inside or event.type in PASS_KEYS:
            if event.type not in self.MOVE_EVENTS:
                self.dirty = True
            return {"PASS_THROUGH"}

        if self.phase == "PLANE":
            return self._modal_plane(context, event, mx, my, press)
        if self.phase == "OFFSET":
            return self._modal_offset(context, event, mx, my, press)
        if self.tool in MODIFY_TOOLS:
            r = self._mod_event(context, event, mx, my, press)
            if r is not None:
                return r
        if self.track is not None:
            r = self._track_event(context, event, mx, my, press)
            if r is not None:
                return r

        if event.type in {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE"}:
            try:
                if self.pen is not None:
                    self._pen_drag(mx, my)
                else:
                    self._update(context, mx, my)
            except Exception as e:
                print("[Mini CAD] çizim güncellenemedi:", e)
            self.area.tag_redraw()
            return {"PASS_THROUGH"}

        if event.type == "LEFTMOUSE" and not press:
            if self.pen is not None:
                self._pen_release(context)
                self._refresh(context)
            return {"RUNNING_MODAL"}

        if not press:
            return {"RUNNING_MODAL"} if event.type == "RIGHTMOUSE" else {"PASS_THROUGH"}

        if event.type == "LEFTMOUSE":
            self._update(context, mx, my)
            if self.tool.startswith("C_"):
                self._click_constraint(context)
            elif self.tool == "PEN":
                self.pen = {"co": self.cursor.copy(), "h": None, "id": self.snap_id,
                            "kind": self.snap_kind}
            else:
                self._place(context)
            self._refresh(context)
            return {"RUNNING_MODAL"}

        if event.type in {"RET", "NUMPAD_ENTER"} and event.ctrl:
            self._finish_sketch(context)
            self._refresh(context)
            return {"RUNNING_MODAL"}
        if event.type == "RIGHTMOUSE" or event.type in {"RET", "NUMPAD_ENTER"}:
            if self.tool.startswith("C_"):
                if self.c_refs:
                    self.c_refs = []
                else:
                    self._set_tool(context, "LINE")
            elif event.type != "RIGHTMOUSE" and any(self.typed) and \
                    self._lock_anchor() is not None:
                self._update(context, mx, my)
                self._place(context)              # yazılan değerle noktayı koy
            else:
                self._commit(context)
            self._refresh(context)
            return {"RUNNING_MODAL"}

        if event.type == "DEL" or (event.type == "X" and event.ctrl):
            g = constraints.glyph_at(mx, my)
            if g is not None:
                constraints.remove(bpy.data.objects.get(g[0]), g[1])
                try:
                    bpy.ops.ed.undo_push(message="Mini CAD: Kısıt sil")
                except Exception:
                    pass
                self._status(context, "Kısıt silindi")
                self.area.tag_redraw()
                return {"RUNNING_MODAL"}

        if event.type == "TAB":
            self.field = 1 - self.field
            self._refresh(context)
            return {"RUNNING_MODAL"}

        if event.type == "BACK_SPACE":
            if event.type == "BACK_SPACE" and self.typed[self.field]:
                self.typed[self.field] = self.typed[self.field][:-1]
            elif self.tool.startswith("C_") and self.c_refs:
                self.c_refs.pop()
            else:
                self._undo_last(context)
            self._refresh(context)
            return {"RUNNING_MODAL"}

        ch = event.unicode or ""
        typing = bool(self.typed[self.field])
        if ch and not event.ctrl and (ch in "0123456789.,-+°" or
                                      (typing and (ch.isalpha() or ch in "'\""))):
            if (self._lock_anchor() is not None or (self.track and self.track["pts"])) and \
                    not self.tool.startswith("C_"):
                self.typed[self.field] += ch
                self._refresh(context)
            else:
                self._status(context, "Önce ilk noktayı koy, sonra ölçü yaz")
            return {"RUNNING_MODAL"}           # rakamlar Blender'a gitmesin (koleksiyon gizleme)

        if not event.ctrl and not event.alt:
            if event.type == "A":
                self._set_tool(context, "TARC")
                self._refresh(context)
                return {"RUNNING_MODAL"}
            if event.type in TOOL_KEYS:
                self._set_tool(context, TOOL_KEYS[event.type])
                self._refresh(context)
                return {"RUNNING_MODAL"}
            if event.type in {"X", "Y", "Z", "V"}:
                mode = {"X": "YZ", "Y": "XZ", "Z": "XY", "V": "VIEW"}[event.type]
                self._set_plane("AUTO" if self.plane_mode == mode else mode)
                self._refresh(context)
                return {"RUNNING_MODAL"}
            if event.type == "T" and not self.tool.startswith("C_") and self.tool != "PEN":
                self.track = {"pts": []}
                self.typed, self.field = ["", ""], 0
                self._status(context, "İz: referans noktaya tıkla, sonra eksen boyunca ilerle "
                                      "(ölçü yazabilirsin) · her tık yeni bacak · Enter / sağ tık:"
                                      " son noktayı kullan · Esc: iptal")
                self._refresh(context)
                return {"RUNNING_MODAL"}
            if event.type == "U" and not self.tool.startswith("C_"):
                if self.temp is not None and not event.shift:
                    self._temp_end(context)            # asıl düzleme dön
                else:
                    self._temp_begin(context)          # geçici zemin seç (Shift+U: başkası)
                self._refresh(context)
                return {"RUNNING_MODAL"}
            if event.type == "Q" and event.shift:
                self._set_plane("PICK")
                self._refresh(context)
                return {"RUNNING_MODAL"}
            if event.type == "Q":
                self._set_tool(context, self.prev_tool or "SELECT")
                self._refresh(context)
                return {"RUNNING_MODAL"}
            if event.type == "I":
                self.grid_on = not self.grid_on
                try:
                    context.scene.minicad_grid_snap = self.grid_on
                except Exception:
                    pass
                self._status(context, f"Izgara yakalama {'açık' if self.grid_on else 'kapalı'}")
                self._refresh(context)
                return {"RUNNING_MODAL"}
            if event.type == "D":
                self.carc_flip = not self.carc_flip
                self._refresh(context)
                return {"RUNNING_MODAL"}
            if event.type == "C":
                self._close(context)
                self._refresh(context)
                return {"RUNNING_MODAL"}
        if event.type == "F" and not event.alt:
            self._surface(context, new_body=event.ctrl)
            self._refresh(context)
            return {"RUNNING_MODAL"}

        if event.type not in self.MOVE_EVENTS:
            self.dirty = True
        return {"PASS_THROUGH"}


classes = (MINICAD_OT_draw,)


@bpy.app.handlers.persistent
def _on_load_pre(_dummy):
    cleanup_all()


def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.minicad_grid_snap = bpy.props.BoolProperty(
        name="Izgara Yakalama", description="Çizerken ızgaraya hafif yakalama (I)", default=True)
    bpy.types.Scene.minicad_draw_target = bpy.props.EnumProperty(
        name="Çizim Hedefi", description="Bitir'e basınca taslak nereye kaydedilsin",
        items=[("ACTIVE", "Mevcut eğri", "Aktif / son kullanılan eğri objesine yeni spline "
                "olarak eklenir"),
               ("NEW", "Yeni eğri", "Her Bitir'de yeni bir eğri objesi oluşturulur")],
        default="ACTIVE")
    bpy.types.Scene.minicad_grid_alpha = bpy.props.FloatProperty(
        name="Izgara Görünürlüğü", description="Çizerken imleç çevresindeki ızgara çizgilerinin "
        "belirginliği (0 = gizli; yakalama yine çalışır)", default=0.22, min=0.0, max=1.0,
        subtype="FACTOR")
    bpy.types.Scene.minicad_look_at = bpy.props.BoolProperty(
        name="Düzleme Bak", description="Çizim düzlemi seçilince görünümü düzleme çevir",
        default=True)
    bpy.types.Scene.minicad_pick_plane = bpy.props.BoolProperty(
        name="Önce Düzlem Seç", description="Çizim açılınca önce çizim düzlemini seçtir "
        "(Inventor gibi)", default=True)
    bpy.app.handlers.load_pre.append(_on_load_pre)


def unregister():
    cleanup_all()
    if _on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load_pre)
    for name in ("minicad_grid_snap", "minicad_grid_alpha", "minicad_draw_target",
                 "minicad_look_at",
                 "minicad_pick_plane"):
        try:
            delattr(bpy.types.Scene, name)
        except Exception:
            pass
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
