exec(open("t.py").read().split("def seg(")[0])
from mini_cad import jobs
jobs.client().want_process=False
import types
NS=types.SimpleNamespace
registered=[]
bpy.app.timers=NS(register=lambda f,first_interval=0: registered.append(f), is_registered=lambda f: f in registered)
bpy.data=NS(objects={})
core._transform_running=lambda: False
calls=[]
def bad_rebuild(ob,preview=False):
    calls.append(preview); raise RuntimeError("link_wires patladı")
core._start_build=bad_rebuild
ob=NS(name="CAD",cad=NS(is_cad=True,status=""))
bpy.data.objects={"CAD":ob}
core.schedule(ob,preview=False); print("ilk zamanlayıcı kayıtlı:",len(registered))
r=core._tick(); registered.clear() if r is None else None
print("hata sonrası tick sonucu:",r,"| durum:",ob.cad.status)
core.schedule(ob,preview=False); print("ikinci değişiklikte zamanlayıcı yeniden başladı:",len(registered)==1)
core._tick(); print("hesaplama denemesi sayısı:",len(calls))
