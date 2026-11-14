# v0.25.4: hesaplanamayan yüzey / işlem uyarısı (3D görünümde, önce yalnız panelde)
exec(open("t42.py").read().split("def tang():")[0])
bo = importlib.import_module("mini_cad.bool_overlay")

def check(cond, msg):
    print(("  tamam  " if cond else "  HATA   ") + msg)
    if not cond:
        raise SystemExit(1)

def body(name, vis=True, patches=(), feats=()):
    return NS(name=name, visible_get=lambda: vis, cad=NS(is_cad=True,
              patches=[NS(name=n, enabled=e, ok=o, info=i) for n, e, o, i in patches],
              features=[NS(name=n, enabled=e, ok=o, info=i) for n, e, o, i in feats]))
b1 = body("CAD_Govde", feats=[("Kesim 1", True, False, "Ana gövde açık kabuk (yüzey): katıyla birleştirilemez"),
                              ("Fillet", True, True, "uygulandı"), ("Kapalı", False, False, "x")])
b2 = body("Gizli", vis=False, patches=[("Y", True, False, "hata")])
b3 = body("CAD_Govde.001", patches=[("Yüzey 2", True, False, "Döngü kapanmıyor" + " uzun" * 60)])
sc = NS(objects=[b1, b2, b3, NS(name="Eğri", cad=NS(is_cad=False))])
L = bo.error_lines(sc)
check(L[0].startswith("CAD_Govde · Kesim 1: Ana gövde açık kabuk"), f"başarısız boolean görünür: {L[0][:60]}")
check(len(L) == 2 and L[1].startswith("CAD_Govde.001 · Yüzey 2") and len(L[1]) <= 140, "yüzey hatası, uzun metin kısaltıldı")
check(not any("Gizli" in t or "Kapalı" in t or "Fillet" in t for t in L), "gizli gövde, kapalı ve başarılı işlemler yok")
many = body("Çok", feats=[(f"İşlem {i}", True, False, "e") for i in range(9)])
L = bo.error_lines(NS(objects=[many]), limit=5)
check(len(L) == 5 and "5 hata daha" in L[-1], f"en fazla 5 satır: {L[-1]}")
check(bo.error_lines(NS(objects=[body("Temiz")])) == [], "hata yoksa uyarı yok")
w = body("Uyarılı", patches=[("Yüzey 1", True, True, "Coons · UYARI: yüzey kendi üzerine katlanıyor (karşılıklı kenar parçaları birbirine uymuyor olabilir)")])
L = bo.error_lines(NS(objects=[w]))
check(len(L) == 1 and L[0].startswith("Uyarılı · Yüzey 1: UYARI: yüzey kendi üzerine katlanıyor"), f"katlanma uyarısı da görünür: {L}")
print("t63 bitti")
