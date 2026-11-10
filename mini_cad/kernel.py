"""OpenCASCADE (OCP) çekirdeğinin kurulumu ve yüklenmesi."""

import importlib
import os
import subprocess
import sys
import threading

import bpy

# OCP 8 (OCCT 8) eski TColgp_* dizi adlarını kaldırdı; build123d/CadQuery gibi 7.9'a sabitliyoruz.
PACKAGES = ("cadquery-ocp-novtk>=7.9.3,<8", "cadquery-ocp>=7.9.3,<8")
REQUIRED_MAJOR = "7."

# Kütüphane klasörü sürüm adıyla: eski (uyumsuz) kurulumlar yeni klasörü kirletmez.
SITE_NAME = "site-ocp79"
OLD_SITE_NAMES = ("site-packages",)

REQUIRED_MODULES = ("gp", "TopAbs", "TopoDS", "TopExp", "TopLoc", "TColgp", "Geom", "GeomAbs",
                    "BRep", "BRepBuilderAPI", "BRepOffsetAPI", "BRepMesh")

_state = {"running": False, "last": "", "log_path": ""}
_occ = {"ok": None, "error": ""}


def _ext_dir(name, create=False):
    try:
        return bpy.utils.extension_path_user(__package__, path=name, create=create)
    except Exception:
        return bpy.utils.user_resource("SCRIPTS", path="mini_cad_" + name, create=create)


def site_dir(create=False):
    return _ext_dir(SITE_NAME, create=create)


def cleanup_old_sites():
    """Blender açılışında, OCP henüz yüklenmemişken eski kurulum klasörlerini siler."""
    import shutil
    if "OCP" in sys.modules:
        return
    for name in OLD_SITE_NAMES:
        d = _ext_dir(name)
        if d and os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)


def ensure_path():
    d = site_dir(create=False)
    if d and os.path.isdir(d) and d not in sys.path:
        sys.path.append(d)


def kernel_available(force=False):
    if _occ["ok"] is not None and not force:
        return _occ["ok"]
    ensure_path()
    importlib.invalidate_caches()
    try:
        import OCP
        ver = str(getattr(OCP, "__version__", ""))
        if ver and not ver.startswith(REQUIRED_MAJOR):
            _occ["ok"] = False
            _occ["error"] = (f"Uyumsuz OCP {ver} yüklü. Kur'a bas, bitince Blender'ı "
                             "yeniden başlat")
            return False
        for mod in REQUIRED_MODULES:
            importlib.import_module("OCP." + mod)
        _occ["ok"] = True
        _occ["error"] = ""
    except Exception as e:  # ImportError, DLL hataları vb.
        _occ["ok"] = False
        _occ["error"] = str(e)
    return _occ["ok"]


def last_error():
    return _occ["error"]


def install_state():
    return _state


def _run(cmd, log):
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    log.append("> " + " ".join(cmd))
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, creationflags=flags)
    except Exception as e:
        log.append(f"ÇALIŞTIRILAMADI: {e}")
        return -1
    log.append(p.stdout[-6000:])
    log.append(p.stderr[-6000:])
    return p.returncode


def _worker(target):
    py = sys.executable
    log = [f"Python: {sys.version}", f"Hedef: {target}"]
    ok = False
    try:
        _state["last"] = "pip kontrol ediliyor..."
        if _run([py, "-m", "pip", "--version"], log) != 0:
            _state["last"] = "pip kuruluyor..."
            if _run([py, "-m", "ensurepip", "--upgrade"], log) != 0:
                _run([py, "-m", "ensurepip", "--user"], log)
        for pkg in PACKAGES:
            _state["last"] = f"{pkg} indiriliyor, birkaç dakika sürebilir..."
            rc = _run([py, "-m", "pip", "install", "--upgrade", "--no-warn-script-location",
                       "--target", target, pkg], log)
            if rc == 0:
                ok = True
                log.append(f"KURULDU: {pkg}")
                break
        _state["last"] = "Kurulum tamamlandı. Blender'ı yeniden başlat." if ok else \
            "Kurulum başarısız. Günlük dosyasını Claude'a gönder."
    except Exception as e:
        log.append(f"BEKLENMEYEN HATA: {e}")
        _state["last"] = f"Hata: {e}"
    finally:
        try:
            path = os.path.join(os.path.dirname(target), "mini_cad_install_log.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(log))
            _state["log_path"] = path
        except Exception:
            pass
        _occ["ok"] = None
        _state["running"] = False


def _redraw_tick():
    try:
        for win in bpy.context.window_manager.windows:
            for area in win.screen.areas:
                area.tag_redraw()
    except Exception:
        pass
    return 0.5 if _state["running"] else None


def start_install():
    if _state["running"]:
        return
    target = site_dir(create=True)
    _state["running"] = True
    _state["last"] = "Başlatılıyor..."
    threading.Thread(target=_worker, args=(target,), daemon=True).start()
    bpy.app.timers.register(_redraw_tick, first_interval=0.5)
