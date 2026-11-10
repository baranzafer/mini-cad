"""Blender tarafı: hesap sürecini başlatır, işleri gönderir, sonuçları ana iş parçacığında
dağıtır. Süreç açılamazsa her şey eskisi gibi Blender içinde (senkron) hesaplanır.

Kural: bir anda en fazla BİR iş hesaplanır. Canlı güncelleme yeni işi ancak önceki bitince
hazırlar; böylece sürüklerken araya giren ara durumlar kendiliğinden atlanır ve her zaman
en güncel eğri verisi gönderilir.
"""

import os
import queue
import subprocess
import sys
import threading
import time
import traceback

START_TIMEOUT = 90.0     # OCP'nin ilk yüklenişi yavaş diskte uzun sürebilir

CRASH_TEXT = ("Hesap süreci beklenmedik şekilde kapandı (OCC çökmesi olabilir; Blender "
              "etkilenmedi). Son değişikliği geri al ya da değeri değiştir")


def _python_exe():
    cands = [sys.executable]
    pre = sys.prefix
    ver = f"{sys.version_info[0]}.{sys.version_info[1]}"
    cands += [os.path.join(pre, "bin", "python.exe"), os.path.join(pre, "bin", "python" + ver),
              os.path.join(pre, "bin", "python3"), os.path.join(pre, "bin", "python"),
              os.path.join(pre, "python.exe")]
    for c in cands:
        if c and os.path.isfile(c) and os.path.basename(c).lower().startswith("python"):
            return c
    return None


class Client:
    def __init__(self):
        self.want_process = True
        self.mode = "off"        # off | starting | process | inproc
        self.reason = ""         # süreç neden kullanılmıyor
        self.site = ""           # OCP kütüphane klasörü
        self.log_path = ""
        self.proc = None
        self.conn = None
        self.listener = None
        self.q = queue.Queue()
        self.cbs = {}
        self.inflight = None
        self.next_id = 1
        self.session = 0         # her yeni süreçte artar (süreç tarafı önbellekler sıfırlanır)
        self.pid = None
        self.started_at = 0.0
        self.crashes = []
        self.on_reset = []       # süreç (ve önbellekleri) kaybolunca çağrılır
        self.python = ""
        self.log = None          # olay günlüğü (Blender tarafı ayarlar)

    def _log(self, msg):
        if self.log is not None:
            try:
                self.log("motor", msg)
            except Exception:
                pass

    # ------------------------------------------------------------ durum

    def busy(self):
        return self.mode == "starting" or self.inflight is not None

    def describe(self):
        if self.mode == "process":
            return f"Arka plan süreci çalışıyor (pid {self.pid})"
        if self.mode == "starting":
            return "Arka plan süreci başlatılıyor…"
        if self.mode == "inproc":
            return "Blender içinde" + (f" — {self.reason}" if self.reason else "")
        return "Beklemede (ilk hesapta başlar)"

    # ------------------------------------------------------------ başlatma / durdurma

    def ensure(self):
        if self.mode in ("process", "inproc", "starting"):
            return
        if not self.want_process:
            self._inproc("arka plan hesaplama kapalı")
            return
        self._start()

    def _start(self):
        try:
            from multiprocessing.connection import Listener
            py = _python_exe()
            if not py:
                raise RuntimeError("Blender'ın Python yürütücüsü bulunamadı")
            self.python = py
            host = os.path.join(os.path.dirname(os.path.abspath(__file__)), "engine_host.py")
            auth = os.urandom(16)
            lst = Listener(authkey=auth)
            env = dict(os.environ)
            env["MINICAD_AUTH"] = auth.hex()
            log = subprocess.DEVNULL
            if self.log_path:
                try:
                    log = open(self.log_path, "w", encoding="utf-8")
                except Exception:
                    log = subprocess.DEVNULL
            flags = 0x08000000 if os.name == "nt" else 0          # CREATE_NO_WINDOW
            try:
                proc = subprocess.Popen(
                    [py, "-I", "-u", host, str(lst.address), os.path.dirname(host),
                     self.site or ""],
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, env=env,
                    creationflags=flags)
            finally:
                if log is not subprocess.DEVNULL:
                    log.close()
        except Exception as e:
            self._inproc(f"süreç başlatılamadı: {e}")
            return
        self.mode, self.proc, self.listener = "starting", proc, lst
        self._log("hesap süreci başlatılıyor")
        self.started_at = time.time()
        gen = self.session + 1
        threading.Thread(target=self._accept, args=(lst, gen), daemon=True).start()

    def _accept(self, lst, gen):
        try:
            conn = lst.accept()
            tag, hello, pid = conn.recv()
            self.q.put(("ready", gen, conn, hello, pid))
        except Exception as e:
            self.q.put(("fail", gen, f"bağlantı kurulamadı: {e}"))

    def _reader(self, conn, gen):
        while True:
            try:
                msg = conn.recv()
            except Exception:
                self.q.put(("dead", gen))
                return
            self.q.put(("msg", gen) + tuple(msg))

    def _inproc(self, reason):
        self._log(f"Blender içinde hesaplanacak: {reason}")
        self.mode, self.reason = "inproc", reason
        self.session += 1                # süreç tarafı önbellek bilgisi artık geçersiz
        self._reset()
        print("[Mini CAD] hesap Blender içinde yapılacak:", reason)

    def _kill(self):
        conn, proc, lst = self.conn, self.proc, self.listener
        self.conn = self.proc = self.listener = None
        try:
            if conn is not None:
                try:
                    conn.send(None)
                except Exception:
                    pass
                conn.close()
        except Exception:
            pass
        if proc is not None:
            try:
                proc.wait(timeout=0.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if lst is not None:
            try:
                lst.close()
            except Exception:
                pass

    def _reset(self):
        for fn in list(self.on_reset):
            try:
                fn()
            except Exception:
                traceback.print_exc()

    def _start_failed(self, reason):
        self._kill()
        self._inproc(reason + (f" (günlük: {self.log_path})" if self.log_path else ""))

    def _died(self):
        self._log(f"hesap süreci kapandı (iş {self.inflight})")
        self._kill()
        self.mode = "off"
        self.crashes.append(time.time())
        mid, self.inflight = self.inflight, None
        cbs, self.cbs = self.cbs, {}
        self._reset()
        cb = cbs.get(mid)
        if cb is not None:
            try:
                cb({"ok": False, "error": CRASH_TEXT, "crashed": True})
            except Exception:
                traceback.print_exc()

    def stop(self):
        """Süreci kapatır; bir sonraki işte yeniden başlar."""
        had = self.mode == "process"
        self._kill()
        self.mode, self.inflight, self.cbs = "off", None, {}
        if had:
            self._reset()

    # ------------------------------------------------------------ olay döngüsü

    def _dispatch(self, item):
        kind, gen = item[0], item[1]
        if kind == "ready":
            _, _, conn, hello, pid = item
            if self.mode != "starting" or gen != self.session + 1:
                try:
                    conn.close()
                except Exception:
                    pass
                return
            if not hello.get("ok"):
                self._start_failed(hello.get("error") or "çekirdek yüklenemedi")
                return
            self.conn, self.pid, self.mode, self.reason = conn, pid, "process", ""
            self._log(f"hesap süreci hazır (pid {pid}, {time.time() - self.started_at:.1f} sn)")
            self.session = gen
            threading.Thread(target=self._reader, args=(conn, gen), daemon=True).start()
        elif kind == "fail":
            if self.mode == "starting" and gen == self.session + 1:
                self._start_failed(item[2])
        elif kind == "dead":
            if self.mode == "process" and gen == self.session:
                self._died()
        elif kind == "msg":
            if gen != self.session:
                return
            mid, res = item[2], item[3]
            if mid == self.inflight:
                self.inflight = None
            cb = self.cbs.pop(mid, None)
            if cb is not None:
                try:
                    cb(res)
                except Exception:
                    traceback.print_exc()

    def _check(self):
        if self.mode == "starting":
            if self.proc is not None and self.proc.poll() is not None:
                self._start_failed("süreç açılırken kapandı")
            elif time.time() - self.started_at > START_TIMEOUT:
                self._start_failed("süreç zamanında yanıt vermedi")
        elif self.mode == "process" and self.proc is not None and self.proc.poll() is not None:
            self.q.put(("dead", self.session))

    def poll(self):
        """Biten işlerin geri çağrılarını ANA iş parçacığında çalıştırır."""
        while True:
            try:
                item = self.q.get_nowait()
            except queue.Empty:
                break
            self._dispatch(item)
        self._check()

    def _wait_step(self, dt=0.05):
        try:
            self._dispatch(self.q.get(timeout=dt))
        except queue.Empty:
            pass
        self._check()

    # ------------------------------------------------------------ iş gönderme

    def _run_inproc(self, cmd, data):
        from . import engine
        return engine.handle(cmd, data)

    def submit(self, cmd, data, cb):
        """İşi gönderir; sonuç poll() içinde cb(sonuç) ile gelir. Blender içinde hesaplanıyorsa
        cb hemen çağrılır. Süreç meşgulse False döner (önce busy() kontrol edilmeli)."""
        self.ensure()
        if self.mode == "inproc":
            cb(self._run_inproc(cmd, data))
            return True
        if self.mode != "process" or self.inflight is not None:
            return False
        mid = self.next_id
        self.next_id += 1
        self.cbs[mid] = cb
        self.inflight = mid
        try:
            self.conn.send((mid, cmd, data))
        except Exception:
            self._died()
        return True

    def control(self, cmd, data):
        """Yanıt beklenmeyen kısa komut (önbellek temizliği gibi); sıradaki işten önce işlenir."""
        if self.mode == "inproc":
            self._run_inproc(cmd, data)
        elif self.mode == "process" and self.conn is not None:
            try:
                self.conn.send((None, cmd, data))
            except Exception:
                self._died()
        # süreç yoksa: yeni süreç zaten temiz başlar

    def call(self, cmd, data):
        """Senkron çağrı (operatörler için): önceki iş bitene kadar bekler, sonra bu işi
        hesaplatıp sonucunu döndürür."""
        for _ in range(3):
            self.ensure()
            while self.busy():
                self._wait_step()
            if self.mode == "inproc":
                return self._run_inproc(cmd, data)
            if self.mode == "process":
                break
        else:
            return {"ok": False, "error": "Hesap süreci başlatılamadı"}
        box = {}
        if not self.submit(cmd, data, lambda r: box.setdefault("r", r)):
            return {"ok": False, "error": "Hesap süreci kullanılamıyor"}
        while "r" not in box:
            self._wait_step()
            if self.mode != "process" and "r" not in box:
                break
        return box.get("r") or {"ok": False, "error": CRASH_TEXT, "crashed": True}


_CLIENT = Client()


def client():
    return _CLIENT
