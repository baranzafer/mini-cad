# Hesap süreci taşıma testi: gerçek alt süreç + sahte geometri
import sys, time, os, numpy as np
sys.path.insert(0, "/tmp/fk")
os.environ["FAKE_SLOW"] = "0.6"
from fakepkg import jobs
c = jobs.client(); c.log_path = "/tmp/fk/engine_log.txt"
resets = []; c.on_reset.append(lambda: resets.append(1))
def seg(a, b): return {"p": [np.array(a, float), np.array(b, float)], "tag": ("w", 0), "ref": ("w", 0, 0)}
ch = [seg((0,0,0),(1,0,0)), seg((1,0,0),(1,1,0)), seg((1,1,0),(0,0,0))]
def job(name, method="AUTO", preview=False, stages=None):
    return {"name": name, "preview": preview, "patches": [{"idx": 0, "name": "Y1", "chain": ch, "sides": [[s] for s in ch], "method": method}],
            "errors": [], "tol": 1e-3, "mirrors": [], "sew_tol": 1e-4, "make_solid": True, "run_bevels": not preview,
            "ghost": preview, "stages": stages or [], "corner_mode": "JOINT", "factor": 3.0, "smooth": True, "lin": 1e-3, "ang": 0.1,
            "feature_names": {}}
t0 = time.time(); c.ensure(); print("başlangıç modu:", c.mode)
while c.mode == "starting": c.poll(); time.sleep(0.02)
print("hazır:", c.mode, "| süre %.2fs" % (time.time() - t0), "| oturum", c.session)
boolst = {"op": "BOOL", "uid": "B1", "bool_type": "CUT", "tool": {"kind": "mesh", "name": "T", "key": 1, "verts": [(0,0,0)]*4, "polys": [[0,1,2]]},
          "edge_size": 0.0, "edge_mode": "SECTION", "mirror_tool": False, "want_edges": True, "key": ("B",)}
got = []
ok = c.submit("build", job("A", stages=[boolst]), lambda r: got.append(r))
t1 = time.time(); ticks = 0
while c.busy():
    c.poll(); ticks += 1; time.sleep(0.01)
print("asenkron iş: gönderildi", ok, "| beklerken ana döngü", ticks, "kez döndü (donma yok) | %.2fs" % (time.time() - t1))
r = got[0]
print("sonuç:", r["ok"], r["shape_info"], r["tris"].shape, "| boolean kenarları:", len(r["display"]["bool_edges"]), r["features"])
# gövde kenarı referansı: 2. çember (x=5) hafif kaymış tanımla
P = r["display"]["bool_edges"][1][1].astype(float); desc = {"s": P[::8] + 0.05, "len": 6.2}
bev = {"op": "BEVEL", "items": [{"uid": "F1", "kind": "FILLET", "size": 0.1, "polys": [], "geo": [{"id": "g1", "src": "B1", "desc": desc}]}], "key": ("F",), "skey": ("F1",)}
r2 = c.call("build", job("A", stages=[boolst, bev]))
print("gövde kenarı fillet:", r2["features"].get("F1"), "| tanım güncellendi:", "g1" in r2["geo_updates"].get("F1", {}),
      "| kullanılan kenar işaretli:", [u for _, _, u in r2["display"]["bool_edges"]])
g = c.call("ghost", {"name": "A", "tol": 1e-3, "mirrors": [], "stages": [dict(bev, items=[dict(bev["items"][0], size=0.3)])]})
print("hayalet (sadece ölçü):", g["ok"], g["ghost"]["verts"].shape if g.get("ghost") else None, "| genişlik", float(g["ghost"]["verts"][1,0]))
c.control("forget", {"name": "A"})
g2 = c.call("ghost", {"name": "A", "tol": 1e-3, "mirrors": [], "stages": [bev]})
print("unutulduktan sonra hayalet:", g2)
print("STEP:", c.call("step", {"name": "A", "path": "/tmp/fk/x.step", "scale": 1000.0}))
r3 = c.call("build", job("B")); print("B tam kalite:", r3["ok"])
print("STEP:", c.call("step", {"name": "B", "path": "/tmp/fk/x.step", "scale": 1000.0}), open("/tmp/fk/x.step").read()[:30])
# çökme
pid = c.pid
r4 = c.call("build", job("C", method="CRASH"))
print("çökme sonucu:", r4["ok"], r4.get("crashed"), "| mod:", c.mode, "| reset çağrıldı:", len(resets))
r5 = c.call("build", job("D"))
print("çökmeden sonra yeni süreç:", r5["ok"], "| pid değişti:", c.pid != pid, "| oturum", c.session)
bad = c.call("build", job("E", method="BAD")); print("hatalı yüz:", bad["ok"], bad["error"], bad["patches"])
c.stop(); print("durduruldu:", c.mode)
