exec(open("t.py").read().split("def seg(")[0])
import types
class M:  # identity matrix
    def __matmul__(s,v): return V(*v)
class BP:
    def __init__(s,co,sel=False): s.co=V(*co); s.handle_left=V(*co); s.handle_right=V(*co); s.select_control_point=sel
def bez(pts):
    # vector-like handles: 1/3 toward neighbors
    return pts
def spline(cos,cyclic,sels):
    bps=[BP(c,s) for c,s in zip(cos,sels)]
    n=len(bps)
    for i,b in enumerate(bps):
        nx=bps[(i+1)%n].co; pv=bps[i-1].co
        b.handle_right=b.co+(nx-b.co)/3; b.handle_left=b.co+(pv-b.co)/3
    return types.SimpleNamespace(type="BEZIER",bezier_points=bps,use_cyclic_u=cyclic)
A,B,C,D=(0,0,0),(1,0,0),(1,1,0),(0,1,0)
sq=spline([A,B,C,D],True,[1,1,1,0])
diag=spline([A,C],False,[1,1])
ob=types.SimpleNamespace(name="Tel",matrix_world=M(),data=types.SimpleNamespace(splines=[sq,diag]))
refs=core.selected_segment_refs([ob]); print("refs",[(r[1],r[2]) for r in refs])
segs=[core._spline_segment(o,si,o.data.splines[si],i,o.matrix_world) for o,si,i in refs]
ch=core.chain_loop(segs,1e-3); sd=core.split_sides(ch); print("triangle sides",len(sd))
# whole square selected + diagonal -> extra segment error
for b in sq.bezier_points: b.select_control_point=True
refs=core.selected_segment_refs([ob]); segs=[core._spline_segment(o,si,o.data.splines[si],i,o.matrix_world) for o,si,i in refs]
try: core.chain_loop(segs,1e-3); print("no error?!")
except Exception as e: print("err:",e)
# square only (deselect diag)
for b in diag.bezier_points: b.select_control_point=False
refs=core.selected_segment_refs([ob]); segs=[core._spline_segment(o,si,o.data.splines[si],i,o.matrix_world) for o,si,i in refs]
print("square sides", len(core.split_sides(core.chain_loop(segs,1e-3))))
