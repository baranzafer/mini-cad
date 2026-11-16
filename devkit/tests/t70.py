# v0.26.0: Profil Süpürme işlemi (gather → motor → _apply) ve başarısızlık teşhisi bağlantısı
# Kullanıcı: "bevel oluşamayan eğriyi seçip ikinci bir eğriyi profil olarak kullanıp o ilk eğri
# boyunca pah yapmak / gövdeden çıkarmak" (Inventor Süpür) ve "hata verirken model mi çekirdek
# mi olduğu belirtilsin".
exec(open("t46.py").read().split('print("A) Gövde ayarı Teğet')[0])
import math
# sahte süpürme modülü (gerçeği OCC ister; geometri devkit/tools/occ_sweep_check.py'de ölçülür)
sw = types.ModuleType("mini_cad.sweep")
SW_CALLS = []
def make_tool(shape, pieces, prof, params, tol):
    SW_CALLS.append({"pieces": pieces, "prof": prof, "params": dict(params)})
    if params.get("_fail"):
        raise core.CadError("Çekirdek sınırı (OCC): profil yol boyunca süpürülemedi")
    return [("tool", len(pieces))], f"yol {len(pieces)} · profil kenarı izliyor"
sw.make_tool = make_tool
sys.modules["mini_cad.sweep"] = sw
BOOLS = []
def apply_boolean(shape, tools, op, es, em, tol, smooth=True, preview=False, **kw):
    BOOLS.append({"op": op, "tools": tools, "kw": kw})
    return shape + ["bool"], True, "uygulandı · hacim -1.0%"
geo.apply_boolean = apply_boolean
core.profile_spec = lambda ob: {"segs": [[(0, 0, 0), (1, 0, 0)]], "origin": (0, 0, 0),
                                "axes": [(1, 0, 0), (0, 1, 0), (0, 0, 1)]}

def sweep_feat(name="Süpürme 1", profile="Profil"):
    f = feat(name, "SWEEP")
    f.profile = NS(name=profile) if profile else None
    f.sw_place, f.sw_ref, f.sw_close = "AUTO", "FACES", "ORIGIN"
    f.sw_angle, f.sw_off_x, f.sw_off_y, f.sw_scale = 0.0, 0.0, 0.0, 1.0
    f.sw_flip = f.sw_reverse = False
    f.sw_extend_auto, f.sw_extend = True, 0.0
    return f

props.diag_uid = ""
props.features = [feat("Kesim 1", "BOOLEAN"), sweep_feat()]
print("A) Süpürme: yol + profil + işlem motora gider, boolean ile uygulanır")
ok = core.rebuild(obj, preview=False)
f = props.features[1]
check(ok and f.ok, f"hesaplandı: {f.info}")
check(len(SW_CALLS) == 1 and SW_CALLS[0]["pieces"][0][0] == "bez", "yol tel kafes segmentinden")
p = SW_CALLS[0]["params"]
check(p["place"] == "AUTO" and p["ref"] == "FACES" and p["close"] == "ORIGIN" and p["extend_auto"],
      f"yerleşim parametreleri: {p}")
check([b["op"] for b in BOOLS] == ["CUT", "CUT"], f"önce Kesim 1, sonra süpürme (sıra): {BOOLS}")
check(BOOLS[-1]["tools"] == [("tool", 1)], "süpürme aracı boolean'a gitti")
check("uygulandı" in f.info and "profil kenarı izliyor" in f.info, f"bilgi: {f.info}")
check(f.uid in core._display["CAD"].get("sweeps", {}), "araç telleri görünüm için saklandı")

print("B) Ayar / profil değişince imza değişir (canlı güncelleme)")
s0 = core._signature_parts(props)
f.sw_angle = math.radians(30)
s1 = core._signature_parts(props)
check(s1 != s0, "açı imzada")
f.profile = NS(name="Profil.001")
check(core._signature_parts(props) != s1, "profil objesi imzada")
f.profile = NS(name="Profil")
n0 = len(SW_CALLS)
core.rebuild(obj, preview=False)
check(len(SW_CALLS) == n0 + 1 and abs(SW_CALLS[-1]["params"]["angle"] - 30.0) < 1e-9,
      "açı derece olarak gider")

print("C) Profil yoksa: kaynak = model, diğer işlemler sürer")
props.features = [sweep_feat(profile=None)]
core.rebuild(obj, preview=False)
f = props.features[0]
check(not f.ok and f.info.startswith("Model kaynaklı"), f"hata: {f.info}")

print("D) Çekirdek hatası işleme yazılır, gövde bozulmaz")
props.features = [sweep_feat()]
props.features[0].sw_extend = 0.5
_mt = sw.make_tool
sw.make_tool = lambda *a: (_ for _ in ()).throw(core.CadError("Çekirdek sınırı (OCC): x"))
core.rebuild(obj, preview=False)
check(not props.features[0].ok and "Çekirdek sınırı" in props.features[0].info,
      f"hata: {props.features[0].info}")
sw.make_tool = _mt

print("E) Ayrıntılı teşhis: istenen işlemin uid'si motora 'deep' olarak gider")
props.features = [feat("Kesim 1", "BOOLEAN"), sweep_feat()]
core.rebuild(obj, preview=False)
uid = props.features[1].uid
BOOLS.clear()
props.diag_uid = uid
core.rebuild(obj, preview=False)
props.diag_uid = ""
check(BOOLS and BOOLS[-1]["kw"].get("deep") is True and BOOLS[0]["kw"].get("deep") is False,
      f"deep yalnız istenen işlemde: {[b['kw'] for b in BOOLS]}")
BOOLS.clear()
core.rebuild(obj, preview=False)
check(BOOLS and BOOLS[-1]["kw"].get("deep") is False,
      "sonraki normal hesap deep olmadan (ayrıntılı sonuç geometri önbelleğinde kalır)")

print("F) Fillet ile karışmaz: süpürme bevel sayılmaz")
check(core.is_bevel(feat("b", "BEVEL")) and not core.is_bevel(sweep_feat())
      and not core.is_bevel(feat("k", "BOOLEAN")), "is_bevel")
_, job = core.gather(obj, preview=False)
check([st["op"] for st in job["stages"]] == ["BOOL", "SWEEP"], f"aşamalar: {job['stages']}")

print("G) Boolean'dan önce fillet varsa ipucu bayrağı (after_bevel)")
fa = feat("Fillet 1", "BEVEL", 0.05)
props.features = [fa, feat("Kesim 2", "BOOLEAN")]
def apply_features(shape, feats, mirrors, tol, cm, fac, sm, fast=False):
    return shape + ["bev"], [(True, "uygulandı")] * len(feats)
geo.apply_features = apply_features
BOOLS.clear()
core.rebuild(obj, preview=False)
check(BOOLS and BOOLS[-1]["kw"].get("after_bevel") is True, "fillet sonrası boolean işaretlendi")
props.features = [feat("Kesim 2", "BOOLEAN"), fa]
BOOLS.clear()
core.rebuild(obj, preview=False)
check(BOOLS and BOOLS[-1]["kw"].get("after_bevel") is False, "fillet önce değilse işaret yok")

print("H) Görünüm uyarısı kısa biçim: kaynak başta")
for _n in ("gpu", "gpu_extras", "gpu_extras.batch"):      # çizim modülü yalnız metin için
    sys.modules.setdefault(_n, types.ModuleType(_n))
sys.modules["gpu_extras.batch"].batch_for_shader = None
bo = importlib.import_module("mini_cad.bool_overlay")
t = bo.short_error("kesim uygulandı ama 14 yeni kenar yuvarlanamadı (0.2) · Çekirdek sınırı "
                   "(OCC): fillet 0.02 gibi küçük bir ölçüyle bile kurulamıyor · ayrıca: x")
check(t.startswith("[Çekirdek sınırı (OCC)] kesim uygulandı") and "ayrıca" not in t, t)
t = bo.short_error("Hesaplanamadı: Model kaynaklı: 1 kenarda iki yan yüz teğet · çıkar")
check(t == "[Model kaynaklı] 1 kenarda iki yan yüz teğet", t)
check(bo.short_error("eski metin") == "eski metin", "kaynaksız metin aynen")
print("t70 bitti")
