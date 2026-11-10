import re, numpy as np
src=open("/home/claude/mini_cad/geometry.py",encoding="utf-8").read()
ns={"np":np}
m=re.search(r"def _corner_candidates\(.*?(?=\n\n\ndef )", src, re.S); exec(m.group(0), ns)
class S:
    def __init__(s,name,center=None,verts=()): s.name=name; s.center=center; s.verts=list(verts)
    def IsSame(s,o): return s is o
    def __repr__(s): return s.name
V=S("V"); V2=S("V2"); V3=S("V3"); V4=S("V4")
pts={id(V):np.array([0,0,0.]), id(V2):np.array([2,0,0.]), id(V3):np.array([0,2,0.]), id(V4):np.array([0,0,2.])}
e1,e2,e3=S("e1",verts=[V,V2]),S("e2",verts=[V,V3]),S("e3",verts=[V,V4])
before=[S("f1"),S("f2"),S("f3")]
mod={b.name:S(b.name+"'",center=np.array([1,1,1.])) for b in before}
stripes={"e1":S("s1",center=np.array([1,.1,.1])),"e2":S("s2",center=np.array([.1,1,.1])),"e3":S("s3",center=np.array([.1,.1,1]))}
corner=S("corner",center=np.array([.1,.1,.1]))
after=list(mod.values())+list(stripes.values())+[corner]
class MK:
    def __init__(s,gen_ok=True): s.gen_ok=gen_ok
    def IsDeleted(s,f): return False
    def Modified(s,f): return [mod[f.name]]
    def Generated(s,e): return [stripes[e.name]] if s.gen_ok else []
ns.update(_edge_vertices=lambda e:e.verts, _vertex_point=lambda v:pts[id(v)],
          _shape_faces=lambda sh: sh, _list_shapes=lambda l:list(l), _face_center=lambda f:f.center)
edges_r=[(e1,0.1),(e2,0.3),(e3,0.3)]
print("Generated çalışıyor  :", ns["_corner_candidates"](MK(True),before,after,edges_r))
print("Generated boş dönerse:", ns["_corner_candidates"](MK(False),before,after,edges_r))
