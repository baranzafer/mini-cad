exec(open("t.py").read().split("def seg(")[0])
import types, numpy as np
NS=types.SimpleNamespace
class Mat:
    def __init__(s,a): s.a=np.array(a,float)
    def __getitem__(s,i): return s.a[i]
    def __iter__(s): return iter(s.a)
    def inverted(s): return Mat(np.linalg.inv(s.a))
    def to_3x3(s): return Mat(s.a[:3,:3])
    def __array__(s,dtype=None,copy=None): return s.a
    def copy(s): return Mat(s.a.copy())
# gövde X'te 2 birim taşınmış ve Z etrafında 90° döndürülmüş
M=Mat([[0,-1,0,2],[1,0,0,0],[0,0,1,0],[0,0,0,1]])
obj=NS(matrix_world=M)
verts=[(2,1,0)]; normals=[(0,1,0)]     # dünya
lv,ln=core._to_local(obj,verts,normals)
print("yerel nokta:",np.round(lv[0],6)," yerel normal:",np.round(ln[0],6),"  (beklenen: (1,0,0) ve (1,0,0))")
# parent bağlama
class Ob(NS): pass
w=Ob(type="CURVE",parent=None,matrix_world=Mat(np.eye(4)),name="Tel")
cad=Ob(name="CAD",parent=None,matrix_world=M,cad=NS(patches=[NS(curves=[],segs=[NS(obj=w)])],features=[]))
core.link_wires(cad); print("tel kafes gövdeye bağlandı:", w.parent is cad)
w2=Ob(type="CURVE",parent="baskaobje",matrix_world=Mat(np.eye(4)),name="T2")
cad.cad.patches[0].segs.append(NS(obj=w2)); core.link_wires(cad); print("başka objeye bağlı olana dokunulmadı:", w2.parent=="baskaobje")
