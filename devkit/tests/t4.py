exec(open("t2.py").read().split("refs=core.selected_segment_refs")[0])
import types, sys, numpy as np
for n in ["gpu","gpu_extras","gpu_extras.batch"]:
    m=types.ModuleType(n); sys.modules[n]=m
sys.modules["gpu_extras.batch"].batch_for_shader=None
bpy.types.Operator=object; bpy.types.SpaceView3D=object
pick=importlib.import_module("mini_cad.pick")
# overlapping: closed square edge AB and a second spline duplicating AB slightly higher z (closer to camera)
dup=spline([A,B],False,[0,0])
for b in dup.bezier_points: b.co.v[2]=0.1; b.handle_left.v[2]=0.1; b.handle_right.v[2]=0.1
ob.data.splines.append(dup)
ob.type="CURVE"; ctx=types.SimpleNamespace(visible_objects=[ob])
sc=pick._Scene(ctx); print("segments",len(sc.refs),sc.keys)
# orthographic top view: map x,y in [-1,2] to pixels 0..300; perspective_matrix maps to ndc; z: camera looks down -z, closer = higher z -> smaller ndc z
P=np.array([[2/3,0,0,-1/3],[0,2/3,0,-1/3],[0,0,-1,0],[0,0,0,1]])
region=types.SimpleNamespace(width=300,height=300)
rv3d=types.SimpleNamespace(perspective_matrix=P.tolist())
def px(x,y): return ((x*2/3-1/3)+1)*150, ((y*2/3-1/3)+1)*150
for pt,label in [((0.5,0.0),"AB (dup üstte olmalı)"),((1.0,0.5),"BC"),((0.5,0.5),"AC diag"),((0.5,0.3),"boş")]:
    h=sc.pick(region,rv3d,*px(*pt),10); print(label,"->",None if h is None else sc.keys[h])
print("lines",len(pick._lines(sc.polys[:1])))
