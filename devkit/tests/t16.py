exec(open("t.py").read().split("def seg(")[0])
from mini_cad import jobs
jobs.client().want_process=False
import types, time
NS=types.SimpleNamespace
registered=[]
bpy.app.timers=NS(register=lambda f,first_interval=0: registered.append(f), is_registered=lambda f: f in registered)
core._transform_running=lambda: True     # sürükleme algılaması "takılı" senaryosu
calls=[]
core._start_build=lambda ob,preview=False: calls.append("önizleme" if preview else "TAM")
core.input_signature=lambda p: 42
ob=NS(name="CAD",cad=NS(is_cad=True,status=""))
bpy.data=NS(objects={"CAD":ob})
core.schedule(ob,preview=True)
t0=time.time()
while time.time()-t0<3:
    r=core._tick()
    if r is None: break
    time.sleep(r)
print("hesaplama sırası:",calls,"| geçen süre ≈",round(time.time()-t0,1),"sn")
