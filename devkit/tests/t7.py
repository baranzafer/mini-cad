import re, numpy as np
exec(open("t.py").read().split("def seg(")[0])   # stubs + core + V
src=open("/home/claude/mini_cad/geometry.py",encoding="utf-8").read()
ns={"np":np}
for fn in ["_np","_pkey","_ekey","is_straight","plane_of","feature_groups"]:
    m=re.search(r"def %s\(.*?(?=\n\n\ndef |\n\ndef |\nclass |\Z)"%fn, src, re.S); exec(m.group(0), ns)
A,B=V(0,0,0),V(1,0,0)
vec=[A,A+(B-A)/3,A+(B-A)*(2/3),B]
print("straight vector handles:", ns["is_straight"](vec))
print("curved:", ns["is_straight"]([A,V(0.3,0.2,0),V(0.7,0.2,0),B]))
print("overshoot handle:", ns["is_straight"]([A,V(1.5,0,0),V(0.5,0,0),B]))
print("ekey dir-free:", ns["_ekey"](vec)==ns["_ekey"](list(reversed(vec))))
sq=[{"p":[V(0,0,0),V(1,0,0)]},{"p":[V(1,0,0),V(1,1,0)]},{"p":[V(1,1,0),V(0,1,0)]},{"p":[V(0,1,0),V(0,0,0)]}]
print("planar square:", ns["plane_of"](sq) is not None)
sq2=[dict(s) for s in sq]; sq2[1]={"p":[V(1,0,0),V(1.2,0.5,0.3),V(1,0.7,0.2),V(1,1,0)]}
print("bulged not planar:", ns["plane_of"](sq2) is None)
# weld across patches: patch1 edge end at (1,0,0), patch2 starts at (1.0004,0,0)
s1={"p":[V(0,0,0),V(1,0,0)]}; s2={"p":[V(1.0004,0,0),V(1,1,0)]}
core.weld_all([s1,s2],1e-3); print("welded equal:", tuple(s1["p"][1])==tuple(s2["p"][0]), tuple(s1["p"][1]))
# feature_groups with fake edges/vertices
class Vx:
    def __init__(s,i): s.i=i
    def IsSame(s,o): return s.i==o.i
class E:
    def __init__(s,a,b): s.v=[Vx(a),Vx(b)]
ns["_edge_vertices"]=lambda e:e.v
# cube top-back edge (1-2), right vertical (2-6), unrelated bottom-front (4-5), feature w/o edges
g=ns["feature_groups"]([[E(1,2)],[E(2,6)],[E(4,5)],[]])
print("groups:", g)
