exec(open("t2.py").read().split("refs=core.selected_segment_refs")[0])
# patch1 = triangle ABC
p1=[(ob,0,0),(ob,0,1),(ob,1,0)]
# user selects C, D, A on square -> segs CD (0,2), DA (0,3)
for b,s in zip(sq.bezier_points,[1,0,1,1]): b.select_control_point=s
for b in diag.bezier_points: b.select_control_point=False
sel=core.selected_segment_refs([ob]); print("sel",[(r[1],r[2]) for r in sel])
full,added=core.complete_loop(sel,p1,1e-3); print("full",[(r[1],r[2]) for r in full],"added",added)
segs=[core._ref_segment(r) for r in full]; ch=core.chain_loop(segs,1e-3); print("loop ok, sides",len(core.split_sides(ch)))
# closed selection returns as-is
print(core.complete_loop(p1,[],1e-3)[1])
# unreachable
try: core.complete_loop(sel,[],1e-3)
except Exception as e: print("err:",e)
