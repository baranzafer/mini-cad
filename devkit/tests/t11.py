exec(open("t4.py").read().split("# overlapping")[0])
import types
NS=types.SimpleNamespace
op=pick.MINICAD_OT_pick_edges.__new__(pick.MINICAD_OT_pick_edges)
win=NS(type="WINDOW",x=0,y=0,width=1000,height=800)
ui=NS(type="UI",x=750,y=0,width=250,height=800)   # yan panel pencerenin üstüne biniyor
op.area=NS(regions=[win,ui],tag_redraw=lambda:None); op.region=win; op.rv3d=None
class FakeScene:
    keys=[("Tel",0,0)]; refs=["ref0"]
    def pick(s,r,rv,x,y,rad): return 0 if (x<100) else None
op.scene=FakeScene(); op.selected=[]; op.hover=None; op.created=0; op.radius=10; op.dirty=False
op._status=lambda c,m="":None; op.report=lambda *a:None; op._refresh_used=lambda c:None
op._finish=lambda c:None; op.stop_request=False; pick._STATE['active']=op
ctx=NS()
def ev(t,x,y,val="PRESS",ctrl=False): return NS(type=t,value=val,mouse_x=x,mouse_y=y,ctrl=ctrl,alt=False)
print("panel üstünde tık   :", op.modal(ctx,ev("LEFTMOUSE",800,400)))
print("kenar üstünde tık   :", op.modal(ctx,ev("LEFTMOUSE",50,400)), op.selected)
print("boşluğa tık         :", op.modal(ctx,ev("LEFTMOUSE",400,400)), "dirty=",op.dirty)
print("G tuşu (taşı)       :", op.modal(ctx,ev("G",400,400)))
called={}
import mini_cad
uimod=types.ModuleType("mini_cad.ui")
def apply_surface(c,k,refs,new_body=False): called["new"]=new_body; return True,"ok"
uimod.apply_surface=apply_surface; sys.modules["mini_cad.ui"]=uimod
op.dirty=False; op.selected=[("Tel",0,0)]
print("Ctrl+Enter          :", op.modal(ctx,ev("RET",400,400,ctrl=True)), "yeni gövde=",called.get("new"))
op.selected=[("Tel",0,0)]
print("Enter               :", op.modal(ctx,ev("RET",400,400)), "yeni gövde=",called.get("new"))
print("F (seçim yok)       :", op.modal(ctx,ev("F",400,400)))
