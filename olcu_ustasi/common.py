# SPDX-License-Identifier: GPL-3.0-or-later
from mathutils import Matrix, Vector

from .props import PIVOT_ITEMS

PIVOT_LABEL = {i[0]: i[1] for i in PIVOT_ITEMS}

NAV_EVENTS = {
    'MIDDLEMOUSE', 'WHEELUPMOUSE', 'WHEELDOWNMOUSE', 'WHEELINMOUSE', 'WHEELOUTMOUSE',
    'TRACKPADPAN', 'TRACKPADZOOM', 'MOUSEROTATE', 'MOUSESMARTZOOM',
    'NDOF_MOTION', 'NDOF_BUTTON_MENU', 'NDOF_BUTTON_FIT', 'NDOF_BUTTON_TOP', 'NDOF_BUTTON_BOTTOM',
    'NDOF_BUTTON_LEFT', 'NDOF_BUTTON_RIGHT', 'NDOF_BUTTON_FRONT', 'NDOF_BUTTON_BACK',
    'NDOF_BUTTON_ISO1', 'NDOF_BUTTON_ISO2', 'NDOF_BUTTON_ROLL_CW', 'NDOF_BUTTON_ROLL_CCW',
    'NDOF_BUTTON_SPIN_CW', 'NDOF_BUTTON_SPIN_CCW', 'NDOF_BUTTON_TILT_CW', 'NDOF_BUTTON_TILT_CCW',
    'NDOF_BUTTON_ROTATE', 'NDOF_BUTTON_PANZOOM', 'NDOF_BUTTON_DOMINANT', 'NDOF_BUTTON_PLUS',
    'NDOF_BUTTON_MINUS',
}
NUMPAD_NAV = {
    'NUMPAD_0', 'NUMPAD_1', 'NUMPAD_2', 'NUMPAD_3', 'NUMPAD_4', 'NUMPAD_5', 'NUMPAD_6',
    'NUMPAD_7', 'NUMPAD_8', 'NUMPAD_9', 'NUMPAD_PERIOD', 'NUMPAD_SLASH', 'NUMPAD_ASTERIX',
    'NUMPAD_MINUS', 'NUMPAD_PLUS', 'HOME',
}
NUMPAD_CHARS = {
    'NUMPAD_0': "0", 'NUMPAD_1': "1", 'NUMPAD_2': "2", 'NUMPAD_3': "3", 'NUMPAD_4': "4",
    'NUMPAD_5': "5", 'NUMPAD_6': "6", 'NUMPAD_7': "7", 'NUMPAD_8': "8", 'NUMPAD_9': "9",
    'NUMPAD_PERIOD': ".", 'NUMPAD_SLASH': "/", 'NUMPAD_ASTERIX': "*", 'NUMPAD_MINUS': "-",
    'NUMPAD_PLUS': "+",
}
TYPE_CHARS = set("0123456789.,+-*/()% \"'") | set("mcdkinfty")


def region_under_mouse(area, event):
    """Fare altındaki 3B görünüm penceresi bölgesi (dörtlü görünüm desteği)."""
    if area is None:
        return None, None
    best = None
    for r in area.regions:
        if r.type != 'WINDOW':
            continue
        if r.x <= event.mouse_x < r.x + r.width and r.y <= event.mouse_y < r.y + r.height:
            return r, r.data
        if best is None:
            best = r
    return None, None


def first_window_region(area):
    for r in area.regions:
        if r.type == 'WINDOW':
            return r
    return None


def frame_with_axis(axis):
    """Ekseni ilk sütun yapan dik çerçeve."""
    a = Vector(axis).normalized()
    t = Vector((0, 0, 1)) if abs(a.z) < 0.9 else Vector((1, 0, 0))
    b = a.cross(t).normalized()
    c = a.cross(b).normalized()
    M = Matrix((a, b, c)).transposed()
    return M


def resolve_pivot(mode, context, box=None, point_a=None, group=None):
    if mode == 'BOX_BOTTOM' and box is not None:
        return box.bottom_center()
    if mode == 'BOX_CENTER' and box is not None:
        return box.center
    if mode == 'POINT_A' and point_a is not None:
        return Vector(point_a)
    if mode == 'CURSOR':
        return context.scene.cursor.location.copy()
    if mode == 'ACTIVE':
        ob = context.active_object
        if ob is None and group is not None and group.roots:
            ob = group.roots[0]
        if ob is not None:
            return ob.matrix_world.translation.copy()
    if mode == 'WORLD':
        return Vector((0, 0, 0))
    if box is not None:
        return box.bottom_center()
    if point_a is not None:
        return Vector(point_a)
    return context.scene.cursor.location.copy()


def set_status(context, area, header=None, status=None):
    try:
        if area is not None:
            area.header_text_set(header)
    except (AttributeError, ReferenceError, TypeError):
        pass
    try:
        if context.workspace is not None:
            context.workspace.status_text_set(status)
    except (AttributeError, ReferenceError, TypeError):
        pass


def tag_redraw_all(context):
    try:
        for win in context.window_manager.windows:
            for a in win.screen.areas:
                if a.type == 'VIEW_3D':
                    a.tag_redraw()
    except (AttributeError, ReferenceError):
        pass
