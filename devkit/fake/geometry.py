import os, time
import numpy as np
from .errors import CadError
LAST_FAILED = 0
CALLS = []
BLENDS = []
HOLES = []
class Builder:
    def __init__(s, prev=None): s.face_keys = []
    def face(s, chain, sides, method, preview, blend="SHARP", holes=None):
        s.face_keys.append(len(chain))
        BLENDS.append((len(chain), method, blend))
        HOLES.append((len(chain), [len(h) for h in (holes or ())]))
        if method == "BAD": raise CadError("kötü yüz")
        if method == "CRASH": os._exit(3)
        return ("face", len(chain)), "Düzlem"
def assemble(faces, mirrors, sew_tol, make_solid): return ["solid"], "Kapalı katı · 1 katı"
def _reflect(q, o, n): return q
def mirror_copies(t, m): return [t]
def mesh_to_solid(v, p): return ("tool", len(v))
class E:
    def __init__(s, P): s.P = np.asarray(P, float)
def apply_boolean(shape, tools, op, es, em, tol, smooth=True, preview=False):
    if os.environ.get("FAKE_SLOW"): time.sleep(float(os.environ["FAKE_SLOW"]))
    return shape + ["bool"], True, "uygulandı"
def boolean_new_edges(shape, before, tools, mode, tol):
    t = np.linspace(0, 2*np.pi, 65)
    c1 = E(np.c_[np.cos(t), np.sin(t), np.zeros_like(t)])
    c2 = E(np.c_[np.cos(t)+5, np.sin(t), np.zeros_like(t)])
    return [c1, c2]
def edge_records(edges):
    out = []
    for e in edges:
        P = e.P
        out.append({"edge": e, "poly": P, "s": P[::8].copy(),
                    "len": float(np.linalg.norm(np.diff(P, axis=0), axis=1).sum())})
    return out
def edge_dense(e, tol): return e.P
def apply_features(shape, feats, mirrors, tol, cm, fac, sm, fast=False):
    CALLS.append([(f["size"], len(f["polys"]), len(f.get("geo_polys", ()))) for f in feats])
    return shape + ["bev"], [(True, "uygulandı")] * len(feats)
def match_edges(shape, polys, tol): return [E(p) for p in polys]
def two_face_filter(shape): return lambda e: True
def fillet_ghost(shape, edges, kind, size):
    if not edges: return None
    v = np.zeros((3, 3), np.float32); v[1, 0] = size; v[2, 1] = size
    return v, np.array([[0, 1, 2]], np.int32), np.zeros((2, 3), np.float32)
def tessellate(shape, lin, ang):
    if "crash" in shape: os._exit(3)
    return [(0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 1, 2)], None
def shape_edge_polylines(shape): return [[(0, 0, 0), (1, 0, 0)]]
def write_step(shape, path, scale):
    open(path, "w").write("STEP %s %s" % (shape, scale))
def blend_order(patches):
    return sorted(patches, key=lambda p: 0 if p.get("blend", "SHARP") == "SHARP" or
                  p["method"] in ("PLANE", "COONS") else 1)
