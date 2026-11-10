import sys, types, math
# --- minimal stubs
class V:
    def __init__(s,*a):
        if len(a)==1: a=tuple(a[0])
        s.v=[float(x) for x in a]
    x=property(lambda s:s.v[0]); y=property(lambda s:s.v[1]); z=property(lambda s:s.v[2])
    def __iter__(s): return iter(s.v)
    def __getitem__(s,i): return s.v[i]
    def __sub__(s,o): return V(*[a-b for a,b in zip(s.v,o.v)])
    def __add__(s,o): return V(*[a+b for a,b in zip(s.v,o.v)])
    def __mul__(s,k): return V(*[a*k for a in s.v])
    def __truediv__(s,k): return V(*[a/k for a in s.v])
    @property
    def length(s): return math.sqrt(sum(a*a for a in s.v))
    def copy(s): return V(*s.v)
bpy=types.ModuleType("bpy")
class _PG: pass
bpy.types=types.SimpleNamespace(PropertyGroup=_PG,Object=object,Curve=object,Operator=object,Panel=object,AddonPreferences=object)
bpy.props=types.SimpleNamespace(**{n:(lambda *a,**k:None) for n in ["PointerProperty","CollectionProperty","StringProperty","EnumProperty","BoolProperty","FloatProperty","IntProperty","FloatVectorProperty"]})
bpy.app=types.SimpleNamespace(handlers=types.SimpleNamespace(persistent=lambda f:f))
h=types.ModuleType("bpy.app.handlers"); h.persistent=lambda f:f
sys.modules.update({"bpy":bpy,"bpy.app":bpy.app,"bpy.app.handlers":h})
sys.path.insert(0,"/home/claude")
import importlib
pkg=types.ModuleType("mini_cad"); pkg.__path__=["/home/claude/mini_cad"]; sys.modules["mini_cad"]=pkg
k=types.ModuleType("mini_cad.kernel"); sys.modules["mini_cad.kernel"]=k
core=importlib.import_module("mini_cad.core")
def seg(a,b,tag,bez=True):
    a,b=V(*a),V(*b)
    p=[a,a+(b-a)/3,a+(b-a)*(2/3),b] if bez else [a,b]
    return {"p":p,"tag":tag}
# square: 4 separate curve objects, shuffled and some reversed, small gaps
s=[seg((0,0,0),(1,0,0),("A",0)), seg((1,1,0),(1,0.0005,0),("B",0)), seg((0,1,0),(0,0,0),("D",0)), seg((1,1,0),(0,1,0),("C",0),False)]
ch=core.chain_loop(s,0.001)
print("order", [c["tag"][0] for c in ch], "closed", (ch[-1]["p"][-1]-ch[0]["p"][0]).length)
print("sides", len(core.split_sides(ch)))
# 6-segment loop, side A has 3 segments
s2=[seg((0,0,0),(1,0,0),("A",0)),seg((1,0,0),(2,0,0),("A",0)),seg((2,0,0),(3,0,0),("A",0)),seg((3,0,0),(3,1,0),("B",0)),seg((3,1,0),(0,1,0),("C",0)),seg((0,1,0),(0,0,0),("D",0))]
# rotate so chain starts mid-A
s2=s2[1:]+s2[:1]
ch=core.chain_loop(s2,1e-3); sd=core.split_sides(ch); print("sides2",len(sd),[len(x) for x in sd])
# single cyclic spline with 4 segments
s3=[seg((0,0,0),(1,0,0),("X",0)),seg((1,0,0),(1,1,0),("X",0)),seg((1,1,0),(0,1,0),("X",0)),seg((0,1,0),(0,0,0),("X",0))]
print("sides3",len(core.split_sides(core.chain_loop(s3,1e-3))))
try: core.chain_loop([seg((0,0,0),(1,0,0),("A",0)),seg((2,0,0),(3,0,0),("B",0))],1e-3)
except Exception as e: print("err ok:",e)
