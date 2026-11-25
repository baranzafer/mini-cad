"""BlendCAD (eski adı Mini CAD; paket kimliği hâlâ mini_cad): Blender içinde OpenCASCADE
tabanlı, eğri güdümlü hard-surface modelleme.

Tel kafes -> yüzeyler (ortak topoloji) -> katı gövde -> bevel.
"""

from . import (blendcad, bool_overlay, constraints, core, draw, extrude, health, hole, kernel, links, opacity,
               panels, pick, recorder,
               split, thread, ui, wire)


def register():
    recorder.register()
    kernel.cleanup_old_sites()
    kernel.ensure_path()
    core.register()
    constraints.register()
    links.register()
    ui.register()
    panels.register()
    blendcad.register()
    health.register()
    hole.register()
    thread.register()
    extrude.register()
    opacity.register()
    pick.register()
    draw.register()
    split.register()
    wire.register()
    bool_overlay.register()


def unregister():
    bool_overlay.unregister()
    wire.unregister()
    split.unregister()
    draw.unregister()
    pick.unregister()
    opacity.unregister()
    extrude.unregister()
    thread.unregister()
    hole.unregister()
    health.unregister()
    blendcad.unregister()
    panels.unregister()
    ui.unregister()
    links.unregister()
    constraints.unregister()
    core.unregister()
    recorder.unregister()
