import re, numpy as np
src=open("/home/claude/mini_cad/geometry.py",encoding="utf-8").read()
m=re.search(r"def apply_features\(.*?(?=\n\n# ======)", src, re.S)
log=[]
def fake_try(cur, idxs, feats, polys, tol, *a):
    # rule: joint (len>1) fails; sequential: small(0) after big fails in HISTORY? emulate: feature 0 must come first
    if len(idxs)>1: log.append(("joint",tuple(idxs))); return None
    i=idxs[0]
    if i==1 and 0 not in cur: log.append(("seq-fail",i)); return None
    log.append(("seq",i)); return cur+[i]
ns={"np":np,"fail_reason":lambda d="":"neden","_FILLET_MODE":{"fast":False},"_BRepAdaptor_Curve":1,"_MakeFillet":1,"_MakeChamfer":1,"CadError":Exception,
    "_reflect":lambda q,o,n:q,"match_edges":lambda s,p,t:["e"],"feature_groups":lambda el:[[0,1,2],[3]],
    "_try_apply":fake_try}
exec(m.group(0), ns)
feats=[{"kind":"FILLET","size":s,"polys":[]} for s in (0.001,0.003,0.003,0.002)]
ns["_apply_edgewise"]=lambda cur,i,f,p,t: cur+[("e",i)]
for mode in ["HISTORY","BIG_FIRST","JOINT","EDGEWISE"]:
    log.clear(); shape,res=ns["apply_features"]([],feats,[],1e-3,mode)
    print(mode, "->", shape, [r[1] for r in res]); print("   ", log)
