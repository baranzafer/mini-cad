exec(open("t4.py").read().split("# overlapping")[0])
import math, numpy as np
N=32
ringpts=[(math.cos(2*math.pi*k/N),math.sin(2*math.pi*k/N),0.0) for k in range(N)]
sc=pick._Scene.__new__(pick._Scene); sc.refs=[];sc.keys=[];sc.polys=[];sc.ends=[];sc.nodes={}
def add(a,b,key):
    idx=len(sc.keys); sc.keys.append(key); sc.polys.append(None); sc._add_ends(idx,[V(*a),V(*b)])
for k in range(N): add(ringpts[k],ringpts[(k+1)%N],("ring",0,k))
add(ringpts[0],(1,0,2),("dikey",0,0)); add(ringpts[16],(-1,0,2),("dikey",1,0))
ch=sc.chain(3, math.cos(math.radians(30)))
ks=sorted(sc.keys[i][2] for i in ch)
print(f"halkada 3. parçaya tık -> {len(ch)} parça seçildi, aralık {ks[0]}..{ks[-1]} (kesişme noktaları 0 ve 16)")
print("dikey kenara tık ->", [sc.keys[i] for i in sc.chain(N, math.cos(math.radians(30)))])
