import re, math, time
src=open("/home/claude/mini_cad/geometry.py",encoding="utf-8").read()
m=re.search(r"def optimize_sizes\(.*?(?=\n\ndef |\Z)", src, re.S); ns={"math":math}; exec(m.group(0), ns)
opt=ns["optimize_sizes"]
mm=1e-3
def mk(limits, pair=None):
    calls=[0]
    def works(s):
        calls[0]+=1
        if any(v>l+1e-12 for v,l in zip(s,limits)): return False
        if pair and s[pair[0]]+s[pair[1]]>pair[2]+1e-12: return False
        return True
    return works, calls
# 1) all ok
w,c=mk([5*mm]*3); print("allok", opt([2*mm]*3,w)[1], c[0])
# 2) edge 2 limit 3mm, requested 5mm; others fine
w,c=mk([9*mm,9*mm,3*mm]); r,st=opt([2*mm,2*mm,5*mm],w,{2}); print("single", [(round(a/mm,2),round(b/mm,2)) for a,b in r], st, c[0])
# 3) corner coupling: e0+e1 <= 6mm, req 5,5 ; hint empty
w,c=mk([9*mm]*3,(0,1,6*mm)); r,st=opt([5*mm,5*mm,2*mm],w,set()); print("coupled", [(round(a/mm,2),round(b/mm,2)) for a,b in r], st, c[0], "final works", w([b for a,b in r]))
