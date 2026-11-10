"""Mini CAD hesap süreci. Blender'ın kendi Python'u ile ayrı bir süreç olarak başlatılır:

    python -I -u engine_host.py <bağlantı adresi> <eklenti klasörü> <OCP klasörü>

Blender ile bir boru (named pipe / unix socket) üzerinden konuşur; eklenti paketinin
__init__.py'si (bpy ister) çalıştırılmadan sadece engine/geometry modülleri yüklenir.
"""

import importlib
import os
import sys
import types


def main():
    addr, pkg_dir, site = sys.argv[1], sys.argv[2], sys.argv[3]
    auth = bytes.fromhex(os.environ.get("MINICAD_AUTH", ""))
    if site and os.path.isdir(site) and site not in sys.path:
        sys.path.append(site)
    pkg = types.ModuleType("minicad_engine")
    pkg.__path__ = [pkg_dir]
    sys.modules["minicad_engine"] = pkg

    from multiprocessing.connection import Client
    conn = Client(addr, authkey=auth)
    engine = None
    try:
        engine = importlib.import_module("minicad_engine.engine")
        hello = engine.handle("ping", {})
    except Exception as e:
        hello = {"ok": False, "error": f"Hesap modülü yüklenemedi: {e}"}
    conn.send(("hello", hello, os.getpid()))
    if engine is None or not hello.get("ok"):
        return
    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            break                      # Blender kapandı
        if msg is None:
            break
        mid, cmd, data = msg
        res = engine.handle(cmd, data)
        if mid is not None:
            try:
                conn.send((mid, res))
            except (EOFError, OSError):
                break


if __name__ == "__main__":
    main()
