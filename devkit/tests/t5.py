import numpy as np, re
src=open("/home/claude/mini_cad/geometry.py",encoding="utf-8").read()
ns={"np":np}
for fn in ["_reflect","_min_dist"]:
    m=re.search(r"def %s\(.*?(?=\n\ndef |\Z)"%fn, src, re.S); exec(m.group(0), ns)
# target: cubic bezier sampled 64 (straight-ish curve along x from 0..1 with bulge)
t=np.linspace(0,1,64)[:,None]; u=1-t
p0,p1,p2,p3=[np.array(v,float) for v in [(0,0,0),(0.3,0.2,0),(0.7,0.2,0),(1,0,0)]]
poly=u**3*p0+3*u*u*t*p1+3*u*t*t*p2+t**3*p3
A,B=poly[:-1],poly[1:]
# edge = same curve sampled 9 at different param (simulate OCC param) -> should match
t9=np.linspace(0,1,9)[:,None]**1.3; u9=1-t9
edge=u9**3*p0+3*u9*u9*t9*p1+3*u9*t9*t9*p2+t9**3*p3
_min_dist=ns["_min_dist"]
print("same curve max dist", _min_dist(edge,A,B).max())
# partial (trimmed by fillet) edge -> still on curve
print("trimmed", _min_dist(edge[2:7],A,B).max())
# adjacent edge sharing endpoint going up -> no match
adj=np.stack([np.array([1,0,0])+k*np.array([0,0,0.1]) for k in range(9)])
print("adjacent", _min_dist(adj,A,B).max())
# mirror across x=0 plane
mp=ns["_reflect"](poly,(0,0,0),(1,0,0)); print("mirror x of end", mp[-1])
