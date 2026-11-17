"""BlendCAD şeridinin paylaşılan durumu (bpy'siz içe aktarılabilir).

Çizim (draw), kenar seçimi (pick) ve yüzey bölme (split) kalıcı operatörleri, fare şeridin
üzerindeyken olayı kendileri işlemeyip şeride bırakmak için over_ribbon() kullanır.
"""

STATE = {"running": False, "close": False, "ribbon": None, "area": None, "text": None,
         "capture": False}

MOUSE_EVENTS = {"MOUSEMOVE", "INBETWEEN_MOUSEMOVE", "LEFTMOUSE", "RIGHTMOUSE", "MIDDLEMOUSE",
                "WHEELUPMOUSE", "WHEELDOWNMOUSE"}


def is_running():
    return bool(STATE["running"])


def palette_allowed():
    """Çizimin eski kayan paleti yalnızca 'Eski N panellerini göster' açıkken (geçiş dönemi)
    görünür. Tercih okunamıyorsa (testler) eski davranış."""
    try:
        import bpy
        for k, a in bpy.context.preferences.addons.items():
            if k.split(".")[-1] == "mini_cad":
                return bool(getattr(a.preferences, "legacy_panels", False))
    except Exception:
        return True
    return True


def find_area(context, ptr):
    if not ptr:
        return None
    for win in context.window_manager.windows:
        for a in win.screen.areas:
            if a.as_pointer() == ptr:
                return a
    return None


def window_region(area):
    for r in area.regions:
        if r.type == "WINDOW":
            return r
    return None


def over_ribbon(event):
    """Fare olayı açık şeridin (ya da açılır listesinin) üzerinde mi?"""
    rb = STATE["ribbon"]
    if not STATE["running"] or rb is None:
        return False
    if getattr(getattr(rb, "menu", None), "is_open", lambda: False)() and \
            event.type in MOUSE_EVENTS:
        return True                           # sağ tık menüsü açık: fare menünün
    if STATE.get("capture"):              # araç penceresinde yazılıyor / sürükleniyor
        return event.type not in ("TIMER", "TIMER_REPORT", "NONE")
    if event.type not in MOUSE_EVENTS:
        return False
    try:
        import bpy
        area = find_area(bpy.context, STATE["area"])
        region = window_region(area) if area is not None else None
        if region is None:
            return False
        mx, my = event.mouse_x - region.x, event.mouse_y - region.y
        if rb.contains(mx, my):
            return True
        from . import notify                      # sol alttaki bildirim merkezi
        return notify.CENTER.contains(mx, my)
    except Exception:
        return False


def insets(area, overlap=True):
    """(sol, sağ, üst) piksel: pencere bölgesinin üstüne binen bölgeler.

    Blender 4.x / 5.x'te 3D görünümün başlığı ve araç başlığı saydamdır ve pencere bölgesinin
    üst kısmına biner; şerit ve başlatıcı bunların altına yerleşmeli. Araç çubuğu (T) ve N
    paneli yalnızca bölge örtüşmesi açıkken yan boşluk ister.
    """
    left = right = 0.0
    win = window_region(area)
    if win is None:
        return 0.0, 0.0, 0.0
    wtop = win.y + win.height
    limit = wtop
    for r in area.regions:
        if r.width <= 1 or r.height <= 1:
            continue
        if r.type in ("HEADER", "TOOL_HEADER"):
            if r.y >= win.y + win.height * 0.5 and r.y < limit:
                limit = r.y
        elif overlap and r.type == "TOOLS":
            left = float(r.width)
        elif overlap and r.type == "UI":
            right = float(r.width)
    return left, right, float(max(0.0, wtop - limit))
