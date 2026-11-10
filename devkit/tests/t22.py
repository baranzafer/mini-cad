# Seçim modu: boolean'ın oluşturduğu gövde kenarları görünür, seçilir, B ile fillet'e gider
exec(open("t4.py").read().split("# overlapping")[0])
import types, math
NS = types.SimpleNamespace
target = NS(name="CAD", visible_get=lambda: True)
pick.core_target = lambda c: target
t = np.linspace(0, 2*math.pi, 65)
circ = np.c_[0.5 + 0.2*np.cos(t), 0.5 + 0.2*np.sin(t), np.zeros_like(t)]
half1 = np.c_[0.5 + 0.2*np.cos(t/2), 0.5 + 0.2*np.sin(t/2), np.full_like(t, 0.0)]
half2 = np.c_[0.5 + 0.2*np.cos(math.pi + t/2), 0.5 + 0.2*np.sin(math.pi + t/2), np.full_like(t, 0.0)]
core._display["CAD"] = {"bool_edges": [("B1", half1, False), ("B1", half2, True)]}
ob.type = "CURVE"; ctx = NS(visible_objects=[ob])
sc = pick._Scene(ctx)
print("toplam:", len(sc.refs), "| tür:", sc.kinds.count("wire"), "tel +", sc.kinds.count("body"), "gövde | fillet'li:", len(sc.body_used))
P = np.array([[2/3,0,0,-1/3],[0,2/3,0,-1/3],[0,0,-1,0],[0,0,0,1]])
region = NS(width=300, height=300); rv3d = NS(perspective_matrix=P.tolist())
def px(x, y): return ((x*2/3-1/3)+1)*150, ((y*2/3-1/3)+1)*150
h = sc.pick(region, rv3d, *px(0.5, 0.7), 10)
print("yarım çembere tık ->", sc.keys[h][0], "| zincir (teğet devam):", len(sc.chain(h, math.cos(math.radians(30)))), "parça")
w = sc.pick(region, rv3d, *px(1.0, 0.5), 10)
print("tel kafes kenarı zincire karışmıyor:", all(sc.kinds[i] == "wire" for i in sc.chain(w, 0.86)))
r = sc.refs[h]; print("referans:", r[0], r[1], r[2].shape, "| gövde ref mi:", pick.is_body_ref(r), pick.is_body_ref((ob, 0, 1)))
core._display["CAD"] = {"bool_edges": [("B1", half1, False), ("B1", half2, True)]}
sc2 = pick._Scene(ctx); print("yeniden okununca anahtar aynı:", sc2.keys[h] == sc.keys[h])
d = json.loads(core.geo_desc_json(half1)) if 'json' in dir() else __import__("json").loads(core.geo_desc_json(half1))
print("kalıcı tanım: 9 nokta =", len(d["s"]), "| boy ≈ %.4f (π·0.2 = %.4f)" % (d["len"], math.pi*0.2))
