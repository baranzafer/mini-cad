exec(open("t.py").read().split("def seg(")[0])
import math, types, numpy as np
V.normalized=lambda s: s/(s.length)
V.dot=lambda s,o: sum(a*b for a,b in zip(s.v,o.v))
V.__neg__=lambda s: V(*[-a for a in s.v])
V.xyz=property(lambda s: s)
V.length_squared=property(lambda s: sum(a*a for a in s.v))
class M:
    def __matmul__(s,v): return V(*v)
NS=types.SimpleNamespace
def poly(points,cyclic): return NS(type="POLY",points=[NS(co=V(*p)) for p in points],use_cyclic_u=cyclic)
N=32; R=1.0
ring=[(R*math.cos(2*math.pi*k/N),R*math.sin(2*math.pi*k/N),0) for k in range(N)]
sp=poly(ring,True); ob=NS(name="Tel")
seg=core._spline_segment(ob,0,sp,0,M())
# max radial error of smoothed segment vs true circle
p=[np.array(tuple(q)) for q in seg["p"]]
t=np.linspace(0,1,50)[:,None]; u=1-t
B=u**3*p[0]+3*u*u*t*p[1]+3*u*t*t*p[2]+t**3*p[3]
err=np.abs(np.linalg.norm(B[:,:2],axis=1)-R).max()
P=np.array([ring[0],ring[1]]); chord=np.linspace(P[0],P[1],50); cerr=np.abs(np.linalg.norm(chord[:,:2],axis=1)-R).max()
print(f"32 parçalı çember: düz parça sapması {cerr*1000:.2f} mm/m, yumuşatılmış sapma {err*1000:.3f} mm/m")
sq=poly([(0,0,0),(1,0,0),(1,1,0),(0,1,0)],True)
print("kare köşeleri korunuyor:", len(core._spline_segment(ob,0,sq,0,M())["p"])==2)
# --- zincir seçimi: alt halka + 2 dikey çizgi (halkanın 0. ve 16. noktasına bağlı)
pk=importlib.import_module("mini_cad.pick") if False else None
