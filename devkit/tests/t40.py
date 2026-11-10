import sys, types, numpy as np, math
sys.path.insert(0, "/home/claude")
pkg = types.ModuleType("mini_cad"); pkg.__path__ = ["/home/claude/mini_cad"]; sys.modules["mini_cad"] = pkg
from mini_cad import solver as S
# kare: 0-1-2-3, kullanıcı 2'yi çekti
x0 = np.array([(0,0,0),(1,0,0),(1.3,1.2,0),(0,1,0)], float)
cons = [("AXIS",(0,1),{"axis":0}),("AXIS",(1,2),{"axis":1}),("AXIS",(2,3),{"axis":0}),("AXIS",(3,0),{"axis":1})]
X, ok, per = S.solve(x0, cons, weights=[1,1,1e4,1])
print("eksen kısıtlı kare, 2 çekildi:", ok, np.round(X,4).tolist())
x0 = np.array([(0,0,0),(2,0.3,0),(0,1,0),(1,1.5,0.2)], float)
X, ok, per = S.solve(x0, [("PARALLEL",(0,1,2,3),{}),("EQUAL",(0,1,2,3),{}),("DISTANCE",(0,1),{"value":2.0})])
d1, d2 = X[1]-X[0], X[3]-X[2]
print("paralel+eşit+uzunluk:", ok, "| boylar", round(np.linalg.norm(d1),6), round(np.linalg.norm(d2),6), "| çapraz", np.round(np.cross(d1,d2),8))
X, ok, per = S.solve(x0, [("PERP",(0,1,2,3),{}),("ANGLE",(0,1,2,3),{"value":45})])
print("çelişki (dik + 45°):", ok, np.round(per,4))
X, ok, per = S.solve(np.array([(0,0,0),(1,0.1,0),(3,0.2,0),(4,-0.1,0)]), [("COLLINEAR",(0,1,2,3),{}),("FIX",(0,),{"pos":(0,0,0)})])
print("doğrusal:", ok, np.round(X,4).tolist())
X, ok, per = S.solve(np.array([(-1,0.2,0),(1.3,0,0.1)]), [("SYMMETRIC",(0,1),{"axis":0,"offset":0})])
print("simetrik:", ok, np.round(X,4).tolist())
import time; n=40; x0=np.random.rand(n*2,3); cons=[("DISTANCE",(2*i,2*i+1),{"value":1.0}) for i in range(n)]+[("PARALLEL",(2*i,2*i+1,2*i+2,2*i+3),{}) for i in range(n-1)]
t=time.time(); X, ok, per = S.solve(x0, cons); print("80 nokta 79 kısıt:", ok, "%.0f ms" % ((time.time()-t)*1000))
