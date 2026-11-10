"""Kurulum tanı raporu: OCP kurulumunun içeriğini toplar."""

import importlib
import os
import pkgutil
import sys

from . import kernel


def _listdir(path, limit=60):
    try:
        items = sorted(os.listdir(path))
    except Exception as e:
        return f"(okunamadı: {e})"
    shown = ", ".join(items[:limit])
    more = f" ... (+{len(items) - limit})" if len(items) > limit else ""
    return f"[{len(items)} öğe] {shown}{more}"


def build_report():
    lines = ["=== Mini CAD Tanı Raporu ==="]
    lines.append(f"Python: {sys.version}")
    lines.append(f"Executable: {sys.executable}")
    site = kernel.site_dir()
    lines.append(f"site-packages: {site}")
    lines.append(f"site-packages içeriği: {_listdir(site)}")
    lines.append(f"sys.path'te mi: {site in sys.path}")

    kernel.ensure_path()
    importlib.invalidate_caches()
    try:
        import OCP
        lines.append(f"OCP.__file__: {getattr(OCP, '__file__', None)}")
        lines.append(f"OCP.__path__: {list(getattr(OCP, '__path__', []))}")
        lines.append(f"OCP.__version__: {getattr(OCP, '__version__', '?')}")
        for p in getattr(OCP, "__path__", []):
            lines.append(f"OCP klasörü: {_listdir(p, 80)}")
            try:
                mods = [m.name for m in pkgutil.iter_modules([p])]
                lines.append(f"Alt modül sayısı: {len(mods)}")
                for key in ("TopAbs", "TopoDS", "TColgp", "BRep", "gp", "BRepMesh"):
                    lines.append(f"  {key}: {'VAR' if key in mods else 'YOK'}")
            except Exception as e:
                lines.append(f"iter_modules hatası: {e}")
        attrs = [a for a in dir(OCP) if not a.startswith("__")]
        lines.append(f"OCP öznitelikleri ({len(attrs)}): {', '.join(attrs[:40])}")
    except Exception as e:
        lines.append(f"OCP içe aktarılamadı: {type(e).__name__}: {e}")

    for name in ("OCP.TopAbs", "OCP.TColgp", "OCP.gp", "OCP.TopoDS"):
        try:
            m = importlib.import_module(name)
            lines.append(f"{name}: OK ({getattr(m, '__file__', '?')})")
        except Exception as e:
            lines.append(f"{name}: HATA {type(e).__name__}: {e}")

    log = kernel.install_state().get("log_path") or os.path.join(
        os.path.dirname(site), "mini_cad_install_log.txt")
    if os.path.isfile(log):
        try:
            with open(log, encoding="utf-8") as f:
                txt = f.read()
            lines.append("--- Kurulum günlüğü (son 3000 karakter) ---")
            lines.append(txt[-3000:])
        except Exception as e:
            lines.append(f"Günlük okunamadı: {e}")
    else:
        lines.append(f"Kurulum günlüğü bulunamadı: {log}")
    try:
        from . import jobs
        c = jobs.client()
        lines.append("--- Hesap motoru ---")
        lines.append(f"Durum: {c.describe()} · oturum {c.session} · çökme {len(c.crashes)}")
        lines.append(f"Python yürütücüsü: {c.python or jobs._python_exe()}")
        if c.log_path and os.path.isfile(c.log_path):
            with open(c.log_path, encoding="utf-8", errors="replace") as f:
                txt = f.read()
            lines.append("--- Hesap süreci günlüğü (son 3000 karakter) ---")
            lines.append(txt[-3000:] or "(boş)")
    except Exception as e:
        lines.append(f"Hesap motoru bilgisi alınamadı: {e}")
    return "\n".join(lines)
