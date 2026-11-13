"""Mini CAD: Blender içinde OpenCASCADE tabanlı, eğri güdümlü hard-surface modelleme.

Tel kafes -> yüzeyler (ortak topoloji) -> katı gövde -> bevel.
"""

from . import (bool_overlay, constraints, core, draw, kernel, links, panels, pick, recorder,
               split, ui, wire)


def register():
    recorder.register()
    kernel.cleanup_old_sites()
    kernel.ensure_path()
    core.register()
    constraints.register()
    links.register()
    ui.register()
    panels.register()
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
    panels.unregister()
    ui.unregister()
    links.unregister()
    constraints.unregister()
    core.unregister()
    recorder.unregister()
