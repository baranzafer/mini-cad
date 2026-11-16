# v0.25.13: silinip yeniden eklenen fillet motor önbelleğinden eski uid'nin sonucunu alıp
# "başarılı" sanılıyordu (kullanıcı: 1. B "ölçüyü küçült", 2. B panele eklendi ama uygulanmadı,
# durum satırında "Hatalı: 12562b42c5fc")
exec(open("t46.py").read().split('print("A) Gövde ayarı Teğet')[0])
fail = {"on": True}
def apply_features(shape, feats, mirrors, tol, cm, fac, sm, fast=False):
    geo.CALLS.append([f["size"] for f in feats])
    if fail["on"]:
        return shape, [(False, "Hesaplanamadı: sonuç bozuk geometri üretti")] * len(feats)
    return shape + ["bev"], [(True, "uygulandı")] * len(feats)
geo.apply_features = apply_features
props.features = [feat("Fillet 1", "BEVEL", 0.05)]
print("A) İlk fillet başarısız")
core.rebuild(obj, preview=False)
f1 = props.features[0]
check(f1.ok is False and f1.uid, f"başarısız: {f1.info}")
print("B) Silinip aynı kenar / ölçüyle yeniden eklenince yeniden hesaplanır, başarısız kalır")
props.features = [feat("Fillet 1", "BEVEL", 0.05)]
n0 = len(geo.CALLS)
core.rebuild(obj, preview=False)
f2 = props.features[0]
check(f2.uid and f2.uid != f1.uid, "yeni uid")
check(len(geo.CALLS) == n0 + 1, f"önbellek kullanılmadı, yeniden hesaplandı ({len(geo.CALLS) - n0})")
check(f2.ok is False, f"yeni fillet başarısız görünüyor: {f2.info!r}")
check(f1.uid not in props.status and "Fillet 1" in props.status, f"durumda ad var, eski uid yok: {props.status}")
print("C) Aynı özellikle tekrar: önbellek yine çalışır")
n0 = len(geo.CALLS)
core.forget_cache = getattr(core, "forget_cache")
core.rebuild(obj, preview=False)
check(len(geo.CALLS) == n0 and props.features[0].ok is False, "değişiklik yoksa önbellekten")
print("D) Kayıt raporu kontrol noktalarını yazar, kısa tutamağı işaretler")
rec = importlib.import_module("mini_cad.recorder")
class M:
    def __matmul__(s, v): return tuple(v)
def bpt(co, hl, hr, t="ALIGNED"):
    return NS(co=co, handle_left=hl, handle_right=hr, handle_left_type=t, handle_right_type=t)
sp = NS(use_cyclic_u=True, bezier_points=[bpt((0, 0, 0), (-0.3, 0, 0), (0.3, 0, 0)),
                                          bpt((1, 0, 0), (0.999, 0, 0), (1.3, 0, 0)),
                                          bpt((1, 1, 0), (1.3, 1, 0), (0.7, 1, 0))])
lines = rec._bezier_points(NS(matrix_world=M()), sp, [400])
print("\n".join(lines))
check(len(lines) == 3 and "n1: (1, 0, 0) sol (0.999, 0, 0)" in lines[1], "noktalar ve tutamaçlar yazıldı")
check("KISA sol" in lines[1] and "KISA" not in lines[0] + lines[2], "kısa tutamaç işaretlendi")
check(rec._bezier_points(NS(matrix_world=M()), sp, [0]) == ["      (nokta listesi kısaltıldı)"], "sınır")
print("t69 bitti")
