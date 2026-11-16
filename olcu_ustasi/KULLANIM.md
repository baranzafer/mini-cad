# Ölçü Ustası — Kullanım

Çok parçalı modelleri (araç, mobilya, makine…) **join yapmadan, boş küp/plane'e sürüklemeden**
tek bütün olarak ölçer ve ölçekler. Parçalar arasındaki ilişki (ebeveyn, ters matris, paylaşılan
mesh, değiştirici, kısıt, animasyon) bozulmaz.

Kurulum: *Düzen › Tercihler › Eklentiler › ⌄ › Diskten Yükle* → `olcu_ustasi_v1.x.zip`.
Araçlar: **N paneli › Ölçü** sekmesi, 3B görünümde **sağ tık menüsü**, *Nesne › Dönüşüm* menüsü
ve F3 araması. Sık kullanıyorsan butona sağ tıklayıp *Hızlı Favorilere Ekle* (Q).

## Seçim = tek bütün
- Outliner'da ya da görünümde istediğin kadar nesne seç. Ebeveyni seçmen yeterli: alt nesneler,
  koleksiyon örnekleri (linked asset) ve geometri düğümü örnekleri de bütüne dahildir.
- Ölçek yalnızca **kök** nesnelere uygulanır; alt nesneler ebeveynleriyle birlikte gelir.
  Böylece hiçbir parça kaymaz, dönmez, eğilmez.

## Ölç ve Ölçekle
1. **A** noktasını tıkla, **B** noktasını tıkla. Yakalama hedefleri:
   köşe, kenar, kenar ortası, yüzey, yüz merkezi, **dik ayak**, seçimin ve imleç altındaki
   nesnenin **sınır kutusu** (köşe / kenar / kenar ortası / yüz merkezi / merkez), köken, 3B imleç.
2. B'yi seçerken **X / Y / Z** ile eksene kilitle (ikinci basış: yerel eksen),
   **Shift+X/Y/Z** ile düzleme kilitle → **izdüşümsel** ölçü (ör. iki tekerlek arası yalnız X).
3. Hedefi yaz, **Enter**. Model canlı önizlenir:
   - `450` (varsayılan birim), `4.5m`, `1m 20cm`, `2*30cm`, `1,5` (virgül olur)
   - `150%`, `*2`, `x0.5`, `/4` → çarpan
   - **R**: başka bir yerden iki nokta ölç, model o ölçüye eşitlensin (referansa eşitle)
   - **P**: pivot (Kutu altı · Kutu merkezi · A noktası · 3B imleç · Aktif köken · Dünya)
   - **U**: yalnız kilitli eksende ölçekle (oran bozulur, eğiklik oluşmaz)
   - **A**: bitince ölçeği veriye uygula (ölçek 1 olur)
   - **K**: ölçüyü sahnede sabitle ve yeni ölçüme geç · **Ctrl+C** ölçüyü kopyala
   - Sağ tık / Geri: bir adım geri · Esc: iptal (model eski haline döner)

Diğer tuşlar (nokta seçerken): **Ctrl** basılıyken yapışma kapalı (serbest yüzey noktası),
**1–8** yakalama türlerini aç/kapat, **S** yalnız seçime yapış (öndeki nesnelerin arkasını görür),
**O** kutu yönü (dünya / aktif nesnenin yerel ekseni). Arkada kalan kutu köşeleri için
**X-ray** (Alt+Z) aç.

## Kutu ile Ölçekle
Seçimin dış kutusu tutamaçlarıyla görünür.
- **Yüz tutamacı** (eksen renginde): o yöndeki boyu değiştirir. Varsayılan *oranlı*;
  **Shift** basılıyken ya da **U** ile yalnız o eksen.
- **Köşe tutamacı** (beyaz): oranlı büyüt / küçült.
- Sürüklerken **Ctrl**: başka nesnelerin köşe / kenar / yüzeyine yapış (ör. aracı bir referans
  küpün ucuna kadar uzat). Sürüklerken **değer yaz** (`3m`, `150%`): tam boyut.
- **C** merkezden ölçekle · **G** zemini koru (yan tutamaçlarda alt yüz yerinde kalır)
- **Ctrl+Z** son adımı geri al · **Enter / Boşluk** bitir · **Esc** iptal

## Panel
- **Seçim Boyutu**: bütünün X / Y / Z boyları. Birini yaz → tüm seçim ölçeklenir
  (kilit açıkken yalnız o eksen). Hızlı çarpanlar ve içe aktarma birim düzeltmeleri
  (mm→m, cm→m, in→m, ft→m…).
- **Sığdır ve Yerleştir**: önce modeli, en son referans nesneyi seç →
  *Sığdır* (hiçbir boyut taşmaz) / *Kapla* / *Esnet* / *X·Y·Z boyu*. Zemine indir, merkeze /
  imlece al.
- **Ölçeği Güvenle Uygula**: tüm hiyerarşide ölçeği 1 yapar; ölçek mesh'e, eğri kalınlığına,
  yazı boyutuna, ışık/boş nesne boyutuna ve değiştirici değerlerine (bevel, solidify, array,
  mirror, weld, displace, screw…) aktarılır. Paylaşılan mesh bir kez dönüştürülür; aynalı
  (negatif ölçekli) nesnelerde normaller korunur. Sonucu bozacak durumlarda (eşit olmayan ölçek +
  bevel, hook, mesh deform, geometri düğümleri, parçacık, animasyonlu ölçek…) o nesne
  dokunulmadan bırakılır ve raporda neden yazılır.
- **Sabit Ölçüler**: K ile sabitlenenler; nesnelere bağlıdır, model değişince değer canlı güncellenir.

## Kesinlik garantileri
- Eşit ölçekte doğrudan matris; eşit olmayan ölçekte dönük / eğik parçalar varsa kökler bir
  `Olcek_Koku` Empty'nin altına alınır (eski ebeveyni korunur) → sonuç birebir kesin.
- Konumu anahtarlanmış (animasyonlu) ebeveynsiz kökte anahtarlar da ölçeklenir; diğer animasyonlu
  durumlarda Empty yöntemi kullanılır → her karede doğru.
- Bağlı (linked) nesneler taşınmaz, raporda belirtilir.
