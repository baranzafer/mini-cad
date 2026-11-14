# v0.25.6: X / Y / Z eksen kilidi (Blender G → X gibi): dünya ekseni boyunca, yakalama kilidi
# bozmaz (eksene izdüşer), tekrar basana kadar sürer; Shift+X/Y/Z düzlem; geçici zemin G
exec(open("t42.py").read().split("def tang():")[0])
ctx.region = region

def check(cond, msg):
    print(("  tamam  " if cond else "  HATA   ") + msg)
    if not cond:
        raise SystemExit(1)

def typ2(t):
    for ch in t:
        op.modal(ctx, ev("ONE", None, uni=ch))

op.sketch.clear(); op._hist_reset(); op._set_plane("XY"); op._set_tool(ctx, "LINE"); op.dirty = True
ctx.scene.minicad_grid_snap = False; op.grid_on = False
click((2.0, 2.0)); click((3.0, 3.0)); key("RET")          # yakalanacak taslak çizgisi
op.dirty = True
print("A) X kilidi: yalnızca X doğrultusunda")
click((0.5, -1.0))
key("X")
check(op.axis_lock == 0, "X: eksen kilidi")
move((2.5, 0.7))
check(np.allclose(op.cursor, (2.5, -1.0, 0)), f"imleç X ekseninde: {op.cursor}")
check(op.info and op.info.get("axis") == 0, f"kılavuz: {op.info}")
print("B) Yakalama kilidi bozmaz: çizgi ucuna (2, 2) gelince X'e izdüşer")
move((2.0, 2.0))
check(np.allclose(op.cursor, (2.0, -1.0, 0)) and op.snap_id is None, f"köşe hizası, kilit sürüyor: {op.cursor} · {op.info['kind']}")
move((2.12, 2.04))
check(np.allclose(op.cursor, (2.0, -1.0, 0)) and "hizası" in op.info["kind"], f"köşenin yanında: köşe hizasına çekildi {op.cursor} · {op.info['kind']}")
click((2.12, 2.04))
check(np.allclose(op.segs[-1]["p"][3], (2.0, -1.0, 0)), "nokta eksen üzerinde kondu")
check(("AXIS", 0) in op.segs[-1].get("auto", []), f"otomatik eksen kısıtı: {op.segs[-1].get('auto')}")
print("C) Kilit sonraki noktada da sürer; Y'ye geç, tekrar Y: kapanır")
move((3.0, 1.0))
check(np.allclose(op.cursor, (3.0, -1.0, 0)), "kilit sonraki noktada da sürüyor")
key("Y"); move((3.0, 1.0))
check(op.axis_lock == 1 and np.allclose(op.cursor, (2.0, 1.0, 0)), f"Y kilidi: {op.cursor}")
key("Y"); move((3.0, 1.0))
check(op.axis_lock is None and np.allclose(op.cursor[:2], (3.0, 1.0)), "tekrar Y: kilit kapandı, serbest")
print("D) Üstten bakışta Z kilidi: yazılan değerle dikey çizgi")
key("Z"); typ2("1.5"); key("RET")
check(np.allclose(op.segs[-1]["p"][3], (3.0, 1.0, 1.5)) or np.allclose(op.segs[-1]["p"][3], (2.0, -1.0, 1.5)), f"Z boyunca 1.5: {op.segs[-1]['p'][3]}")
key("Z")
print("E) Shift+X: YZ düzlemi (eski X davranışı)")
key("X", shift=True)
check(op.plane_mode == "YZ" and op.axis_lock is None, "Shift+X: YZ düzlemi")
op._set_plane("XY")
print("F) Sürüklemede eksen kilidi: yakalama eksene izdüşer")
key("RET")
st = op.sketch[-1]
n0 = np.asarray(st["segs"][0]["p"][0], float)
op._set_tool(ctx, "SELECT"); op.dirty = True
move(tuple(n0[:2])); op.modal(ctx, ev("LEFTMOUSE", tuple(n0[:2])))
move((n0[0] + 0.3, n0[1] + 0.1))
if op.sk_drag is not None:
    key("Y"); move((2.0, 2.0))
    p = op.sk_drag.get("cur") if isinstance(op.sk_drag, dict) else None
    q = np.asarray(op.sketch[-1]["segs"][0]["p"][0], float)
    check(abs(q[0] - n0[0]) < 1e-9 and abs(q[1] - 2.0) < 1e-6, f"Y kilitli sürükleme köşe hizasına (y = 2): {q}")
    op.modal(ctx, ev("LEFTMOUSE", (2.0, 2.0), val="RELEASE"))
else:
    print("  (sürükleme başlamadı, atlandı)")
print("t65 bitti")
# ---- v0.25.10: düzlem kilidi (Shift+X/Y/Z) — eksen kilidini kapatır, yakalama bozmaz
print("G) Shift+Z eksen kilidi açıkken: eksen kilidi kapanır, düzlem etkin")
if op.sk_drag is not None:
    op.modal(ctx, ev("LEFTMOUSE", (2.0, 2.0), val="RELEASE"))
op.sk_drag = None
op.sketch.clear(); op._hist_reset(); op._set_plane("AUTO"); op._set_tool(ctx, "LINE"); op.dirty = True
op.axis_lock = None
click((2.0, 2.0)); click((3.0, 3.0)); key("RET")
op.sketch[-1]["segs"][0]["p"] = tuple(np.asarray(q, float) + (0, 0, 0.8) for q in op.sketch[-1]["segs"][0]["p"])
op.dirty = True                                    # yakalanacak çizgi z = 0.8'de (düzlem dışı)
click((0.5, -1.0))
key("X"); check(op.axis_lock == 0, "X kilidi açık")
key("Z", shift=True)
check(op.plane_mode == "XY" and op.axis_lock is None, "Shift+Z: XY düzlemi, eksen kilidi kapandı")
move((1.7, 0.4))
check(np.allclose(op.cursor, (1.7, 0.4, 0)), f"imleç serbest, düzlemde: {op.cursor}")
print("H) Düzlem dışındaki noktaya yakalama: düzleme izdüşer, kilit bozulmaz")
P_end = np.asarray(op.sketch[-1]["segs"][0]["p"][0], float)
move(tuple(P_end[:2]))
check(abs(P_end[2] - 0.8) < 1e-9 and np.allclose(op.cursor, (P_end[0], P_end[1], 0.0)) and op.snap_id is None
      and "hizası" in (op.info or {}).get("kind", ""), f"uç hizası, z = 0 kaldı: {op.cursor} · {op.info}")
click(tuple(P_end[:2]))
check(abs(op.segs[-1]["p"][3][2]) < 1e-9, "nokta düzlemde kondu")
key("Z", shift=True)
check(op.plane_mode == "AUTO", "tekrar Shift+Z: düzlem kilidi kapandı")
move(tuple(P_end[:2]))
check(abs(op.cursor[2] - 0.8) < 1e-9, f"kilitsiz: yakalama noktanın kendisine gider (eski davranış): {op.cursor}")
key("RET")
print("I) Sürüklemede Shift+X: YZ düzlem kilidi (önce X ekseni kilidi oluyordu)")
st = op.sketch[-1]
n0 = np.asarray(st["segs"][0]["p"][0], float)
op._set_tool(ctx, "SELECT"); op.dirty = True
move(tuple(n0[:2])); op.modal(ctx, ev("LEFTMOUSE", tuple(n0[:2])))
move((n0[0] + 0.3, n0[1] + 0.1))
check(op.sk_drag is not None, "sürükleme başladı")
key("X", shift=True)
d = op.sk_drag
check(d["axis"] is None and d.get("plane_lock") == 0 and d["plane"].name == "YZ", "Shift+X: YZ düzlem kilidi, eksen kilidi değil")
move((n0[0] + 0.7, n0[1] + 0.4))
q = np.asarray(op.sketch[-1]["segs"][0]["p"][0], float)
check(abs(q[0] - n0[0]) < 1e-9, f"X sabit kaldı: {q}")
move(tuple(P_end[:2]))                             # başka çizginin ucu: x farklı
q = np.asarray(op.sketch[-1]["segs"][0]["p"][0], float)
check(abs(q[0] - n0[0]) < 1e-9, f"yakalamada da X sabit (düzleme izdüşüm): {q} · {op.info}")
key("X", shift=True)
check(op.sk_drag.get("plane_lock") is None and op.sk_drag["plane"].name != "YZ", "tekrar Shift+X: kilit kapandı")
key("X")
check(op.sk_drag["axis"] == 0, "X: eksen kilidi hâlâ çalışıyor")
print("J) Çizimde üstten bakarken Shift+X (düzleme kenarından bakış): imleç donmaz, X sabit")
op.modal(ctx, ev("LEFTMOUSE", (2.0, 2.0), val="RELEASE")); op.sk_drag = None
op.sketch.clear(); op._hist_reset(); op._set_plane("AUTO"); op._set_tool(ctx, "LINE"); op.dirty = True
click((0.5, -1.0))
key("X", shift=True)
check(op.plane_mode == "YZ", "Shift+X: YZ")
move((1.9, 0.7))
check(abs(op.cursor[0] - 0.5) < 1e-9 and abs(op.cursor[1] - 0.7) < 1e-6, f"X sabit, Y fareyi izliyor: {op.cursor}")
move((2.4, -0.3))
check(abs(op.cursor[0] - 0.5) < 1e-9 and abs(op.cursor[1] + 0.3) < 1e-6, f"hareket sürüyor: {op.cursor}")
op._set_plane("AUTO")
print("SONUÇ: tamam")
