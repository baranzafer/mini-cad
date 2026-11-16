# v0.25.11: Çizimi Düzenle → "Çizimi Kapat" çizimi kaybetmez; sınırsız düzenle / kapat / tekrar
# düzenle; düzenleme sürerken bağlı gövde dondurulur, bitince tel kafese göre yeniden hesaplanır
exec(open("t59.py").read().split('print("A) Bütün')[0])
dc = importlib.import_module("mini_cad.draw_common")

def open_tool():
    o = draw.MINICAD_OT_draw.__new__(draw.MINICAD_OT_draw); o.report = lambda *a: None
    o.invoke(ctx, NS())
    return o

def press_close():
    """Paneldeki "Çizimi Kapat": araç açıkken minicad.draw yeniden çağrılır."""
    o = draw.MINICAD_OT_draw.__new__(draw.MINICAD_OT_draw); o.report = lambda *a: None
    return o.invoke(ctx, NS())

print("A) Düzenle → Çizimi Kapat: çizim objeye geri yazılır")
reset()
op._set_tool(ctx, "RECT"); click((0, 0)); click((2, 1)); finish()
line((3, 0), (4, 0)); finish()
cmod.add("DISTANCE", [("seg", curve, 0, 0)], solve=False)
cmod.add("DISTANCE", [("seg", curve, 1, 0)], solve=False)
c_rect, c_line = cons()
op._edit_load_all(ctx, "Tel")
check(len(cu.splines) == 0 and len(op.sketch) == 2, "çizim taslakta, objede yok")
r = press_close()
check(r == {"CANCELLED"} and draw._STATE["active"] is None and op.stop_request, "araç kapandı")
check(len(cu.splines) == 2, f"çizim geri yazıldı ({len(cu.splines)} spline)")
check(c_rect.refs[0].spline == 0 and c_line.refs[0].spline == 1, f"referanslar geri eşlendi: {c_rect.refs[0].spline}, {c_line.refs[0].spline}")
check(np.allclose(co(0, 0), (0, 0, 0)) and np.allclose(co(1, 0), (3, 0, 0)), "konumlar doğru")

print("B) Sınırsız döngü: düzenle → değiştir → kapat → yeniden aç → düzenle ...")
for k in range(4):
    op = open_tool(); op._set_plane("XY"); op.dirty = True
    n = op._edit_load_all(ctx, "Tel")
    check(n == 2 and len(cu.splines) == 0, f"{k + 1}. düzenleme: 2 çizgi taslakta")
    op._set_tool(ctx, "MOVE"); click((3.5 + k, 0)); key("RET"); click((3 + k, 0)); click((4 + k, 0))
    if k % 2:
        press_close()
    else:
        finish()                                     # Bitir de aynı yere yazar
        check(op.edit_obj is None, "Bitir düzenlemeyi bitirdi")
        press_close()
    check(len(cu.splines) == 2 and draw._STATE["active"] is None, f"{k + 1}. kapatma: çizim yerinde")
    check(c_rect.refs[0].spline == 0 and c_line.refs[0].spline == 1, "referanslar korunuyor")
    check(np.allclose(co(1, 0), (4 + k, 0, 0)), f"değişiklik kaldı: {co(1, 0)}")
cmod.solve_all(ctx.scene, force=True)
check(c_rect.ok and c_line.ok, "kısıtlar geçerli")

print("C) Gövde: düzenleme sürerken dondurulur, bitince yeniden hesaplanır")
op = open_tool(); op._set_plane("XY"); op.dirty = True
body = NS(name="Gövde", type="MESH", cad=NS(is_cad=True, live=True, preview=False, status="",
          patches=[NS(curves=[], segs=[NS(obj=curve, spline=1, seg=0)])], curves=[],
          features=[], mirror_center=None, bevels=[], constraints=[], links=[]))
ctx.scene.objects = Objs({"Tel": curve, "Gövde": body})
bpy.data.objects = Objs({"Tel": curve, "Gövde": body})
check(not corem.frozen(body.cad), "düzenleme yokken dondurulmamış")
pref = body.cad.patches[0].segs[0]
sched = []
corem.schedule = lambda ob, preview=False: sched.append(ob.name)
corem.input_signature = lambda p: 42
corem._last_sig["Gövde"] = 41
op._edit_load_all(ctx, "Tel")
check(corem.edited_curves() == {"Tel"} and corem.frozen(body.cad), "düzenlenen çizime bağlı gövde donduruldu")
check(pref.spline < -1000, "yüzey referansı geçici işarette")
check(corem.rebuild(body) is False and "Bitir" in body.cad.status, "senkron hesap da ertelendi")
corem._dirty["Gövde"] = True
check(corem._next_job() is None and "Gövde" in corem._frozen_skip, "kuyruktaki hesap ertelendi")
other = NS(name="Diğer", type="MESH", cad=NS(patches=[], curves=[], features=[], mirror_center=None))
check(not corem.frozen(other.cad), "başka gövde etkilenmez")
press_close()
check(not corem.frozen(body.cad) and pref.spline == 1, f"kapatınca çözüldü, yüzey referansı geri geldi ({pref.spline})")
check(sched == ["Gövde"] and "Gövde" not in corem._frozen_skip, f"gövde yeniden hesaplanmak üzere sıraya alındı: {sched}")
sched.clear()
op = open_tool(); op._set_plane("XY"); op.dirty = True
op._edit_load_all(ctx, "Tel")
corem._last_sig["Gövde"] = 42
finish()                                             # Bitir: girdi aynı → gereksiz hesap yok
check(not corem.frozen(body.cad) and sched == [], f"değişiklik yoksa hesap yok: {sched}")
op._edit_load_all(ctx, "Tel")
corem._last_sig["Gövde"] = 41
finish()
check(sched == ["Gövde"], f"Bitir'den sonra yeniden hesap: {sched}")

print("D) Dosya kaydedilirken düzenlenen çizim Bitir'lenir, araç açık kalır")
op._edit_load_all(ctx, "Tel")
check(len(cu.splines) == 0, "taslakta")
draw._on_save_pre(None)
check(len(cu.splines) == 2 and draw._STATE["active"] is op and not op.sketch, "kaydetmeden önce geri yazıldı, araç açık")
line((6, 0), (7, 0))
op._commit(ctx)
draw._on_save_pre(None)
check(len(op.sketch) == 1, "yalnızca yeni çizgi varken kaydetme taslağa dokunmaz")
op.sketch.clear()

print("E) Dosya yüklenirken (load_pre) yazılmaz")
op._edit_load_all(ctx, "Tel")
draw._on_load_pre(None)
check(draw._STATE["active"] is None and len(cu.splines) == 0, "eski sahneye yazılmadı")
print("t66 bitti")
