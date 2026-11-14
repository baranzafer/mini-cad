# Mini CAD — Geliştirme Notları (v0.25.12)

Bu dosya, projeyi **yeni bir sohbette** kaldığı yerden sürdürmek için yazıldı. Yeni sohbete
başlarken bu dosyayı oku. Kodun tamamını baştan okumak gerekmez; aşağıdaki modül haritası
hangi dosyaya bakılacağını söyler.

---

## 0. Yeni sohbette nasıl başlanır

Kod GitHub'da: `baranzafer/mini-cad` deposu, **`claude/mini-cad-continue-4zvqyj`** dalı.
- Eklenti `mini_cad/` klasöründe, testler ve araçlar `devkit/` klasöründe.
- Kurulum zip'leri `dist/` klasöründe.
- Her sürüm ayrı bir commit.

**A) Claude Code (web) ile — önerilen, zip gerekmez**
1. Yeni oturumu `baranzafer/mini-cad` deposuyla aç.
2. Açılış mesajı: "Mini CAD projesine devam ediyoruz. Kod `claude/mini-cad-continue-4zvqyj`
   dalında; önce o dalı al ve DEVELOPMENT.md'yi oku." Ardından isteklerini yaz.
3. Claude'un yapacağı kurulum:
   - Yeni oturumun kendi çalışma dalı farklı adda olabilir. O dal bu dalın son commit'inden
     başlatılır:
     ```bash
     git fetch origin claude/mini-cad-continue-4zvqyj
     git checkout -B <oturumun dalı> origin/claude/mini-cad-continue-4zvqyj
     ```
   - Başlangıç durumu için testler çalıştırılır:
     ```bash
     bash devkit/run_tests.sh mini_cad
     ```
   - Gerçek OCC denemesi gerekirse:
     ```bash
     python3 -m venv /tmp/occ && /tmp/occ/bin/pip install "cadquery-ocp-novtk>=7.9.3,<8" numpy
     ```
   - Testler `/home/claude/...` yollarını bekler; koşucu kaynağı oraya kendisi kopyalar.
4. Her sürümde:
   - manifestte sürüm artırılır
   - `dist/` zip'leri yenilenir
   - commit ve push yapılır

**B) Zip ile (Claude.ai sohbeti)**
1. `dist/` klasöründeki iki zip'i yükle: `mini_cad_v0.X.zip` (eklenti) ve
   `mini_cad_devkit_v0.X.zip` (testler + araçlar).
2. Açılış mesajı: "Mini CAD projesine devam ediyoruz, önce DEVELOPMENT.md'yi oku."
3. Kurulum:
   ```bash
   mkdir -p /home/claude/mini_cad && cd /home/claude/mini_cad && unzip -o <eklenti zip>
   mkdir -p /home/claude/devkit && cd /home/claude/devkit && unzip -o <devkit zip>
   bash /home/claude/devkit/run_tests.sh /home/claude/mini_cad
   ```

**Beklenen başlangıç:** `t6.py` ve `t14.py` dışındaki her test **geçti** (bu ikisi v0.12'den
beri bayat, "(bilinen)" olarak işaretlenir). `SONUÇ: tamam` görünmeli.

Değişiklikten sonra testler yeniden çalıştırılır. Gerekirse yeni test eklenir (`t69.py` ...),
sürüm artırılır ve paketlenir (§8).

---

## 1. Kullanıcı tercihleri ve kurallar (değişmez)

- **Daha önce düzeltilmiş hiçbir davranış bozulmamalı.** Bir değişiklik eski bir davranışı
  etkileyecekse önce söylenir.
- N panelleri **düz ve ayrı** kalır: her biri `Mini CAD: X` başlıklı (sekme içinde iç içe değil).
- **Canlı güncelleme:** eğri değişince gövde kendiliğinden yeniden hesaplanır, ağır iş arka
  planda yapılır.
- Davranışlar **Inventor / SolidWorks gibi sezgisel** olmalı. Teğet, düzlem seçimi, kısıtlar ve
  yakalamalar Inventor mantığını izler.
- Arayüz metinleri **Türkçe**. Kullanıcıyla Türkçe konuşulur.
- Blender eksen renkleri kullanılır (X kırmızı, Y yeşil, Z mavi). Kısayollar Blender'ınkilerle
  çakışmamalı.
- Kısıt simgeleri **silik** çizilir, üzerine gelince hiçbir şey açılmaz. **Sağ tıkla** küçük
  menü açılır (dondur / sil), yakalama kısıt simgelerine yapışmaz.
- Kullanıcı Windows'ta, **Blender 5.2.3 LTS** (Python 3.13) kullanıyor. GPU çizimleri yalnızca
  gerçek Blender'da görülebilir; buradaki testler stub'larla çalışır.
- Hata raporu için kullanıcı **Ctrl+Alt+R** kaydını (§7) yapıştırır. Rapor geldiğinde önce
  oradaki log ve anlık durum okunur.

---

## 2. Ortam ve bağımlılıklar

- Eklenti: Blender extension (`blender_manifest.toml`, `id = "mini_cad"`, GPL-3.0-or-later).
- Çekirdek: **OCP 7.9** (`cadquery-ocp-novtk>=7.9.3,<8`). OCP 8, TColgp_* adlarını kaldırdığı
  için 7.9'a sabitli. `kernel.py`, eklentinin kendi `site-ocp79` klasörüne pip ile kurar ve
  yükler.
- FORGE v2 (Paul Ogunsola / RenderCraftStudio, GPL) kaynağından uyarlananlar ve başlıkları:
  - geometry.py: boolean güvenlik katmanları, mesh→katı, fillet koruması ve hayalet fillet
    (başlıkta atıf var);
  - snapmath.py: snap_math, GPL başlığıyla birebir kopya.

  Manifest `copyright` satırında atıf var. Kullanıcı ileride Mini CAD'i Forge ile birlikte
  çalıştırmak istiyor.
- Motor testleri sahte geometriyle (`devkit/fake/geometry.py`) gerçek alt süreç üzerinden
  çalışır.
- OCC ortamda hazır değil ama **pip ile kurulabiliyor** (v0.15.5'te denendi). Gerçek geometri
  denemesi için:
  ```bash
  python3 -m venv /tmp/occ && /tmp/occ/bin/pip install "cadquery-ocp-novtk>=7.9.3,<8" numpy
  /tmp/occ/bin/python devkit/tools/occ_blend_check.py /home/claude/mini_cad
  ```
  `geometry.py` değişikliklerini bu yolla ölçmek mümkün (OCC bilgisi gereken her iş için önerilir).

---

## 3. Mimari genel bakış

```
Blender (ana iş parçacığı)                         Hesap süreci (engine_host.py)
──────────────────────────                         ─────────────────────────────
eğri / kısıt / özellik verisi
   │ core.gather()  bpy → düz veri (numpy, dict)
   ▼
jobs.Client.submit / call ──── multiprocessing ────► engine.handle(cmd)
   ▲                         (authkey: MINICAD_AUTH)     │ geometry.* (OCC)
   │ poll() (zamanlayıcı)                                 ▼
core._apply()  sonuç → mesh, özellikler, core._display (kenarlar, bool_edges, hayalet)
```

- **Motor** (`engine.py`): bpy kullanmaz. Komutları `build`, `ghost`, `step`, `forget`,
  `forget_tool` ve `ping`. Önbellekleri `_builders`, `_bevel_cache`, `_final`, `_stage_base`,
  `_bool_new`, `_tool_cache` ve `_tool_good`.
- **Süreç** (`jobs.py`): `sys.executable -I -u engine_host.py` ile başlar; Windows'ta
  `CREATE_NO_WINDOW` kullanılır.
  - Modlar: `off`, `starting`, `process`, `inproc`. Süreç açılamazsa Blender içinde senkron
    hesaplar.
  - Çökmede süreç yeniden başlar ve `on_reset` kancaları çalışır.
  - **Aynı anda tek iş** hesaplanır. Sürükleme sırasındaki ara durumlar kendiliğinden atlanır.
- **Canlı güncelleme** (`core.py`):
  - `on_depsgraph_update` → `schedule` → `_tick` / `_next_job` → `_start_build` (asenkron).
  - Operatörler `rebuild()` ile senkron çalışır.
  - Değişim imzası `_signature_parts` (curve / struct / bevel) ile hesaplanır.
  - Sürükleme bitince (`_transform_running`) final hesap yapılır; sürerken önizleme ve hayalet
    fillet gösterilir.
- **Kenar kimliği** (boolean'la oluşan gövde kenarları için):
  - Kayıt `GeoEdge` olarak tutulur: 9 örnek nokta + uzunluk tanımlayıcısı.
  - Çözüm sırasında en yakın tekil eşleşme seçilir; belirsizse reddedilir (yanlış kenarı
    fillet'lemektense hata).
- **Hayalet fillet:** iki yüz normalinden yay şeridi çizilir; içbükey / dışbükey ayrımı katı
  sınıflandırıcıyla yapılır.
- **Delikli yüzey** (v0.22.0, B harfi gibi):
  - Bir yüzeyin segmentleri birden çok kapalı döngü oluşturabilir. `core.chain_loops`
    döngüleri ayırır, `core.nest_loops` iç içeliğe göre gruplar: çift derinlik dış sınır,
    tek derinlik delik, deliğin içindeki adacık ayrı yüz.
  - Döngüler aynı düzlemde olmalı. Ayrı dış döngüler aynı yüzey kaydından ayrı yüzler olur
    (iş `sub` alt indeksiyle).
  - `Builder._holed`: dış telden düzlemsel yüz, delik telleri eklenir. Deliğin dönüş yönü
    dış sınırla aynıysa ters çevrilir (işaretli alan). Kenarlar ortak topolojiden gelir.
  - Ölçüm (`devkit/tools/occ_holes_check.py`): B benzeri model; alan = dış − delikler,
    delik kenarı ortak, iki dönüş yönünde de geçerli.
  - Çizim aracında F: son kapalı çizgiyle iç içe olan (aynı düzlemdeki) bütün kapalı taslak
    çizgileri birlikte gönderilir (`_nested_group`). Delik en son çizilmiş olabilir.
- **Açık kabukta boolean** (v0.25.4, `geometry._boolean_open_shell`): ana gövde kapalı katı
  değilse (kullanıcı: 5 yüzlü, alt yüzü eksik gövde · "Açık kabuk · 4 serbest kenar") önce
  "Ana gövde kapalı katı değil" hatası veriliyordu. Artık yüzey katı araçla budanır: Kesim
  aracın dışındaki, Kesişim içindeki yüzeyleri bırakır (alan değişimiyle denetlenir);
  Birleşim açıklayıcı hatayla reddedilir; yeni kenar yuvarlama yapılmaz. Araç kapalı katı
  olmalı. Ölçüm `devkit/tools/occ_shell_bool_check.py` (delik alanı π·r²).
- **Katlanma denetimi** (v0.25.7, `geometry.face_folded`): tam hesapta her yüz için 13×13
  parametre ızgarasında komşu normaller ters dönüyorsa etikete "UYARI: yüzey kendi üzerine
  katlanıyor" eklenir (yüz yine kurulur; 3D görünüm uyarısında da görünür). Noktaya inen
  kenarlar (koni tepesi) için yalnızca o yandan %5 içeriden örneklenir (yanlış alarm olmasın).
  Tipik sebep: iki uçtaki kenar parçaları birbirine karşılık gelmiyor (bir uçta profilin üst,
  öbüründe alt yarısı) ya da raylar çapraz. Kullanıcı raporu: damla profilli tüp, ortada
  çapraz kırışık. Araç `devkit/tools/occ_fold_check.py`. Kayıt raporu artık her yüzeyin sınırını
  kenar kenar (segment referansları, uç ve orta noktalar) yazar (`recorder._patch_geometry`).
- **Karşılıklı kenar eşleşmesi** (v0.25.8, `geometry._side_params`; kullanıcı: damla profilli
  tüpün yarısı, iki uçtaki profil farklı parçalanmış → çapraz kırışık, Inventor'da sorun yok).
  - Sebep: Coons / sınır yüzeyinde karşılıklı kenarlar parametreyle eşleşir ve her segment
    parametrede EŞİT pay alıyordu (`_bspline_from_side` düğümleri 0, 1, 2 ...). 2 segmentli
    kenarın ilk yarısı, karşıdaki 3 segmentli kenarın ilk 1.5 segmentiyle eşleşiyordu; segment
    boyları farklıysa noktalar çapraz bağlanıyor, yüzey kırışıyor / katlanıyordu.
  - Şimdi eşleşme **yay uzunluğuna göre** (Inventor sınır yüzeyi gibi). Geometri aynen kalır
    (kenarlar ortak topoloji), yalnızca B-spline düğümleri / Hermite parametresi değişir:
    - Her segmentin payı boyuyla orantılı. Hızı düzgün olmayan segment (tutamakları dengesiz
      bezier; hız oranı > `PARAM_SPEED_RATIO` 1.25) de Casteljau ile eşit yay boylu 4 / 8
      parçaya bölünür (`_arc_pieces`); doğru ve daire yayı bölünmez → eski yüzeyler aynı.
    - İki karşı kenarın segment sayısı eşit ve köşeleri yay oranı olarak yakınsa
      (`PARAM_JOINT_TOL` 0.15) köşe köşeye eşlenir (ortak konum iki oranın ortalaması).
    - Noktaya inmiş kenar (3 kenarlı yamanın tepesi) eskisi gibi.
    - `_loop_sides`: kenarları döngü yönüne çevirir (önce `_hermite` içindeydi). `_coons`,
      `_coons_surface`, `_hermite` aynı parametreyi kullanır.
  - **Uydurma denetimi** (`_fit_grid`): OCC'nin `GeomAPI_PointsToBSplineSurface` yaklaşık
    uydurucusu sıkı toleransta bazen yakınsamadan "tamam" diyor: yüzey ızgara noktalarından
    geçiyor ama aralarında salınıyor (yama boyunun %4'ü), kenarlara oturmadığı için yüz
    geçersiz çıkıp Coons / Dolgu'ya düşülüyordu. Sonuç ızgara hücre ortalarında denetlenir
    (7×7, izdüşüm); tutmazsa eş parametreli (`Approx_IsoParametric`) uydurma, sonra tam ara
    değerleme (`Interpolate`) denenir.
  - Ölçüm `devkit/tools/occ_param_check.py` (yarım koni, 2/3, 1/2, 3/3, 4/2 segment): doğru
    yüzeyden sapma 0.09–0.51 → ≤ 0.004 (profil bezierinin kendi hatası düzeyi). Eski ölçümler
    değişmedi (Coons regle sapması 0.0004 → 0.0006, halka teğet kırılması aynı).
- **Kenar Seç ve düzenleme modu** (v0.25.9; kullanıcı raporu: düzenleme moduna geçilemiyor,
  tutamaçlar çoklu / kutuyla seçilemiyor, değişiklikten sonra gövde güncellenmiyor, Yenile de
  üretmiyor). Raporda Kenar Seç açık, aktif obje yoktu.
  - Kenar Seç modali (`pick.py`) düzenleme modunda da çalışıyordu: tutamaç her zaman bir kenarın
    üstünde olduğundan tık kenar seçimi sayılıp yutuluyor, Enter / F / B / Backspace de
    yutuluyordu. Artık `context.mode != "OBJECT"` iken **bekler** (`self.waiting`): her olay
    (Esc dahil) Blender'a geçer, vurgu çizilmez, durum satırı "BEKLİYOR" der; obje moduna
    dönünce seçimiyle birlikte sürer.
  - Kenar Seç açıkken tıklar kenar seçtiği için eğri aktif yapılamıyor, Tab çalışmıyordu (ya da
    tıklanan gövde mesh'i düzenleme moduna giriyordu). **Tab** (`_enter_edit`): üzerinde
    durulan kenarın eğrisini, yoksa hedef gövdenin tel kafesini seçip düzenleme moduna alır.
    Eğri zaten aktif ve seçiliyse Blender'ın kendi Tab'ı çalışır.
  - Gövdenin kendisi (mesh) düzenleme modundayken `write_mesh` etkisiz kalıyor, sonuç sessizce
    kayboluyordu. `_apply` bunu görür: durum "Gövde düzenleme modunda: sonuç yazılamıyor…",
    `_edit_blocked`'a alınır; moddan çıkınca `on_depsgraph_update` tam hesap ister. Yenile
    (`minicad.rebuild`) gövde düzenleme modundaysa önce obje moduna çıkar.
- **Hata uyarısı** (v0.25.4, `bool_overlay.error_lines` / `_draw_errors`, POST_PIXEL): görünür
  CAD gövdelerinde başarısız yüzey / işlemler 3D görünümün sol üstünde kırmızı yazılır (en
  fazla 5 satır). Önce yalnız panelde ve durum satırında ("Hatalı: Kesim 1") görünüyordu.
- **Ortak topoloji ilkesi** (geometry.py): tel kafesteki her segment tek bir OCC kenarı, her
  köşe tek bir OCC köşesi olur. Yüzeyler aynı kenar nesnesini paylaşır.
- **Yüzey birleşimi** (v0.15.5): gövde ayarı `surface_blend` (Keskin / Teğet), yüzey başına
  `patch.blend` (Gövde ayarı / Keskin / Teğet).
  - Keskin (varsayılan, önceki davranış): yüzler ortak kenarda yalnızca buluşur (G0).
  - Teğet: kaynaşan yama `BRepOffsetAPI_MakeFilling` ile kurulur. Önceden kurulmuş komşusuyla
    ortak her kenar `Add(edge, komşu yüz, GeomAbs_G1)` ile bağlanır.
  - Kurma sırası `geometry.blend_order`'dan gelir. Önce sabit yamalar kurulur: keskin,
    düzlemsel, açıkça Düzlem / Coons olanlar. Kaynaşanlar sonra kurulur ve komşularına uyar. Gövdeye
    yine asıl sırayla eklenir.
  - Komşu bilgisi `Builder.edge_owner`'da tutulur. Önbellek anahtarına birleşim ve komşu anahtarları
    eklenir.
  - Kurulamazsa keskine düşülür ve yüzey bilgisine "(teğet (G1) kurulamadı ...)" yazılır.
  - Ölçüm (`occ_blend_check.py`): kare→daire modelinde kenar kırılması 34° → 0,45°. Tekil köşe
    uçlarında birkaç derece kalır. Süre ~3 katı (önizleme ayarlarıyla ~aynı).
  - Eğrilik (G2) yok: OCC 7.9 dolgu aracı kenar kısıtında G2'yi reddediyor ("continuity is
    not G0 G1 or G2").
  - Ayna dikişinde (simetri düzlemi) teğetlik henüz sağlanmıyor.
  - **v0.23.1: ortak teğet şeridi** (`blend_prepare`, `Builder._ribbon`, `_make_ribbon`):
    - Sorun (kullanıcı raporu: yuvarlatılmış dikdörtgen → daire, 8 eğri yama): Teğet seçilince
      motor **çöküyordu** (segfault). Dolgu (`MakeFilling`) yüzü ortak kenarı kullanmaz, kendi
      kopyasını üretir. Sonraki yama G1 kısıtını ortak kenarla verince kenarın komşu yüzde
      pcurve'ü olmuyor, OCC null işaretçiye düşüyordu. Çökmese de sıralı kaynaşmada ilk
      (kısıtsız) dolgu kötü destek olabiliyor: kurma sırasına göre 35°'ye varan kırılma.
    - `_support_edge`: G1 kısıtı için destek yüzündeki kenar, ortak kenarın o yüzde pcurve'ü
      varsa kendisi (düzlemsel komşu: eski davranış), yoksa yüzün geometrice eşleşen kendi
      kenarı; bulunamazsa o kenar C0 kalır (çökme yok).
    - İki **kaynaşan** yamanın ortak kenarı (`builder.ribbon_pairs`, motor `blend_prepare`
      çağırır): iki yamanın keskin hâlleri (`_sharp`, kayıtsız, önizlemede de tam kalite)
      kurulur, kenar boyunca normalleri ortalanır. Kenar eğrisinden bu ortak teğet düzleminde
      kenara dik uzanan dar doğrusal yüzey (şerit, genişlik kenar boyunun %10'u) yapılır;
      iki yama da aynı şeride G1 bağlanır → **kurma sırasından bağımsız** teğetlik.
      Sabit (düzlemsel / keskin / Coons) komşulu kenarlar eskisi gibi komşu yüze bağlanır.
    - Kaynaşan dolguda önizleme de 2 tur (`nbiter`) yapar.
    - Ölçüm (`devkit/tools/occ_blend_ring_check.py`, 4 biçim, 3 kurma sırası): keskin
      4.6–23.5° → teğet en kötü 0.65° (önizleme ≤ 1.9°). Süre: 8 yamada ~50 ms → ~270 ms.
  - **v0.24.0: sınır yüzeyi ve teğet ağırlığı** (kullanıcı: "teğet yüzey balon gibi dışa
    taşıyor, mühendislik programlarının sonucunu vermiyor, değer kontrolü olsun"):
    - Ölçüm: Dolgu (OCC plaka) yamayı Coons sınır yüzeyine göre yama boyunun %1-2'si kadar
      dışa itiyor. Dolgunun başlangıç yüzeyini değiştirmek ya da iç noktalar eklemek
      denendi: dolgu aracı başlangıç biçimini korumuyor, iç noktalarla kenarlarda 80°'ye
      varan salınım ve yine çökme (segfault) oldu → bırakıldı.
    - **Coons düzeltmesi** (`_coons`): yüzeyin parametre yönü tel yönünün tersiyse kırpılan
      yüz geçersiz çıkıyordu; ters tel denenir. Eğri 4 kenarlı yamalar artık (Keskin'de de)
      gerçekten Coons olur (önce hep "Dolgu (Coons geçersizdi)").
    - **Hermite-Coons sınır yüzeyi** (`Builder._hermite`, Teğet + 3 / 4 kenar): bikübik
      Hermite harmanlı Coons. Sınır eğrileri aynen; her kenarda çapraz türev doğrusal
      Coons'unki, komşulu kenarda teğet düzlemine yatırılır (`_side_plane`: kaynaşan çift →
      iki keskin yüzün ortalama normali, sabit komşu → onun yüzü). Böylece G1 yapı gereği.
      - Teğet düzleminde kenara dik bileşen yamanın içine doğru, büyüklük korunur (yüzey
        düzleme dik yaklaşınca izdüşüm sıfıra inip yön kenar boyuna dönmesin).
      - **Teğet ağırlığı**: çapraz türev büyüklüğü kenar ortasında × ağırlık
        (`1 + (w−1)·sin²(πt)`, köşelerde 1).
      - Köşe twist'leri **Gregory** biçiminde (ortalama twist teğet kenarlara ~2° sızdırıyordu).
      - Köşe uyumu: kenarın uçlarındaki %20'de çapraz türev komşu sınır eğrisinin teğetine
        yumuşakça geçer. Köşede teğet düzlemi komşu eğriyi içermiyorsa (üç yüzeye birden
        teğet olunamaz) hata köşede kalır; yoksa Coons harmanlaması hatayı kenarın tamamına
        yayıyordu (kenar ortasında 16°).
      - 3 kenar (`_tri_to_quad`): tepe köşesi noktaya inmiş 4 kenarlı; taban = en eğri kenar.
      - Izgarada örneklenir (25×25, önizleme 13×13), `GeomAPI_PointsToBSplineSurface` ile
        uydurulur, telle kırpılır (ters tel de denenir). Kurulamazsa Coons'tan başlayan
        teğet dolgusuna düşülür (`_filling(..., sides)`: `LoadInitSurface`).
    - Seçenekler: `TANGENT` (sınır yüzeyi, yeni), `TANGENT_FREE` ("Teğet – serbest dolgu",
      v0.23 davranışı). Gövde `tangent_weight` (0.2–2, varsayılan 1), yüzey `own_weight` +
      `tangent_weight`; gather `entry["weight"]` (yalnızca ≠ 1), motor `weight=` gönderir,
      ikisi de imzada. 2.5 üstünde küçük yamalar katlanmaya başlıyor (ölçüldü) → üst sınır 2.
    - Ölçüm (`occ_blend_ring_check.py`): 4 biçim × dörtgen yamalar, Teğet kırılma ≤ 0.02°
      (önizleme ≤ 0.17°), Coons'a göre taşma %±1.7; ağırlık 0.5 / 1 / 2 → ortalama taşma
      içe → ~0 → dışa. Üçgenli model: Keskin 85° → Teğet ≤ 0.41° (kenar ortaları).
      `occ_blend_check.py` (kare → daire): Teğet 3.82° → 0.33°.
    - Süre: 8 yamada tam ~0.8 s, önizleme ~0.5 s (arka plan süreci).
  - **v0.25.1: Coons düzeltmesi** (kullanıcı: küçük ön kemer + büyük arka kemer + iki düz
    kenar; sırt S biçimli). OCC'nin `GeomFill_CoonsStyle`'ı adına rağmen KÜBİK harmanlama
    kullanıyor: yüzey kenarlardan sıfır eğimle ayrılıyor, ortada dikleşiyor. Klasik
    (doğrusal) Coons `GeomFill_StretchStyle` (`_GeomFill_CoonsStyle` adı korundu). Doğru
    yüzeyden (kemerleri birleştiren doğrular) sapma 0.12 → 0.0004. Bütün Coons yolları
    etkilenir: Keskin 4 kenarlı yüzey, Teğet dolgusunun başlangıcı, teğet şeritlerinin
    dayandığı keskin yüzeyler (Teğet'in Coons'a göre taşması %±1.7 → %±0.4).
    Araç `devkit/tools/occ_coons_check.py`.
  - **v0.24.1** (kullanıcı videosu: kare taban → daire, 4 düzlem üçgen + 4 köşe yaması;
    köşede büzülme, dalgalı siluet). Doğru sonuç: köşe yaması tam KONİ (sac geçiş parçası).
    - Köşe uyumu artık yalnızca uçtaki FARKI (uyumlu − ham) yumuşakça ekler; önce türevin
      kendisi uç değerine çekiliyordu → koni %2 bozuluyordu. Şimdi koniden sapma 1e-4.
    - Eğri 3 kenarlı yama Otomatik'te (Keskin dahil) "Coons (3 kenar)": `_hermite(...,
      tangent=False)` (tepesi noktaya inmiş Coons). Önce Dolgu, koniden %5 sapma.
    - Teğet düzlemi normalleri kenarın tam ucundan değil biraz içeriden alınır (uç komşunun
      tekil noktası olabilir: koni tepesi → normal çöp → twist −1123 → yüzey patladı).
      Twist türevi uca dokunmayan tek yönlü farkla.
    - İçeri yönü (D işareti): türev kenara paralelleşince yamanın merkezinden (u=1 / v=1
      kenarlarında türev dışarı bakar: `inward`).
    - `_grid_sane`: sınırların çok dışına taşan ya da katlanan ızgara reddedilir (Dolgu
      yedeğine düşülür). Patlamış bir yüzey OCC üçgenleyicisini **sonsuz döngüye** sokmuştu
      (Blender senkron hesapta donardı).
    - Izgara 25 → 33 (önizleme 13 → 17): ağırlık 2'de uydurma kenar yakınındaki türevi
      kaçırıyordu (6° → ≤ 0.5°). Süre ~%15 arttı.
    - `occ_blend_check.py`: köşe yamasının koniden sapması (Keskin ve Teğet < 1e-3).

---

## 4. Modül haritası

| Dosya | Satır | Görev |
|---|---:|---|
| `__init__.py` | 37 | Kayıt sırası: recorder → kernel → core → constraints → links → ui → panels → pick → draw → split → wire → bool_overlay |
| `kernel.py` | 150 | OCP kurulumu / yükleme |
| `engine.py` | 391 | bpy'siz OCC motoru (komut işleyici, önbellekler) |
| `engine_host.py` | 52 | Alt süreç girişi; paketi sahte `minicad_engine` paketi olarak yükler |
| `jobs.py` | 337 | Süreç istemcisi (ensure / submit / call / control / poll / stop / describe) |
| `errors.py` | 2 | `CadError` |
| `geometry.py` | 2792 | OCC işlemleri: yüzey kurucu, assemble, fillet / chamfer, boolean, mesh→katı, tessellate, STEP, kenar poligonları, hayalet fillet |
| `core.py` | 2028 | PropertyGroup'lar (Feature, GeoEdge, CRef, Constraint, ObjectProps), eğri okuma, gather / _apply / rebuild, canlı güncelleme |
| `solver.py` | 185 | numpy kısıt çözücü: ağırlıklı Gauss-Newton, en az hareket; `residual`, `evaluate`, `solve`, `measure` |
| `constraints.py` | 590 | Kısıt çözümünü çalıştırma (`solve_all`), ekleme / kontrol / silme, canlı tetikleme, operatörler, kayıt |
| `constraints_refs.py` | 100 | Kısıt veri erişimi: referans noktaları, dünya konumu, `all_constraints` |
| `constraints_tangent.py` | 355 | Teğet planlaması (§6) |
| `constraints_arcs.py` | 302 | Yay kısıtları: yay grubu, sanal merkez, yayı yeniden kurma, Pürüzsüz (G2) eğrilik eşleme |
| `draw_dims.py` | 414 | DimMixin: genel Ölçü aracı, ölçü değeri düzenleme, Yatay / Dikey, karışık referanslı seçim |
| `constraints_glyphs.py` | 268 | Kısıt simgesi çizimi, `glyph_at` |
| `draw.py` | 946 | **MINICAD_OT_draw** ana operatör: invoke, durum çubuğu, araç değiştirme, palet olayları, `modal` / `_modal_inner`, kayıt; **MINICAD_OT_edit_sketch** (Çizimi Düzenle) ve menü girişleri |
| `draw_common.py` | 531 | Sabitler / renkler, ölçü ayrıştırma, `_Refs` (yakalama referansları), GPU yardımcıları, `_move_node` / `_move_handle`, araç tabloları |
| `draw_plane.py` | 537 | PlaneMixin: düzlem seçimi (yön, sonra yükseklik), ızgara ve ızgara yakalama, düzleme bakış, geçici zemin (G) |
| `draw_snap.py` | 965 | SnapMixin: nokta yakalama, çıkarım kılavuzları, kilitler, önizleme, T ile iz |
| `draw_sketch.py` | 1012 | SketchMixin: nokta koyma, `_commit`, Bitir (`_finish_sketch`), oto kısıt, yüzey, taslak geri al / yinele |
| `draw_edit.py` | 433 | EditMixin: taslak noktası / tutamaç sürükleme, pivot, sürüklerken yakalama, sürüklerken ölçü yardımcısı |
| `draw_glyphs.py` | 271 | ConstraintUIMixin: kısıt için kenar / nokta seçimi, simge sağ tık menüsü |
| `draw_render.py` | 280 | RenderMixin: 3D / 2D çizim işleyicileri, ölçü giriş kutusu |
| `sketchmath.py` | 1239 | bpy'siz taslak düzenleme matematiği: bezier bölme, varlıklar, kesişimler, Kırp / Uzat / Böl / Ötele / Köşe yuvarla / Pah |
| `draw_modify.py` | 640 | ModifyMixin: Değiştir araçlarının seçimi, önizlemesi, olayları ve çizimi |
| `draw_xform.py` | 684 | TransformMixin: Düzenle / Desen araçları (seçim, temel nokta, hedef, önizleme, ölçü kutusu) |
| `shapemath.py` | 337 | bpy'siz şekil matematiği: dikdörtgen çeşitleri, çokgen, kanallar, yay kanal, elips, 3 doğruya teğet daire, düzleme izdüşüm |
| `draw_shapes.py` | 499 | ShapeMixin: çok tıklamalı şekiller, Nokta, Teğet daire, Geometri yansıt |
| `draw_text.py` | 320 | TextMixin: Metin aracı (yazı → eğri), Taslağa al (Edit Sketch): tek spline (`_edit_load`) ve bütün çizim (`_edit_load_all`, `_edit_plane`) |
| `links.py` | 282 | İlişkisel desen / yansıtma: kopyaları kaynaktan yeniden üretir, adet değişince ekler / siler |
| `draw_skcons.py` | 433 | SketchConsMixin: taslak kısıtları (uid referansı, canlı çözüm, Bitir'de gerçek kısıt), sağ tıkla silme |
| `drawmath.py` | 627 | bpy'siz çizim matematiği: düzlemler, doğru / yay / daire / dikdörtgen, B-spline→Bézier (Boehm), Catmull-Rom, kalem, kılavuz rafinesi |
| `snapmath.py` | 410 | FORGE snap_math (GPL başlıklı kopya) |
| `palette.py` | 615 | Kayan araç paleti (GPU): araç / düzlem / kısıt / taslak / hedef / seçenek düğmeleri, ikon çizgileri |
| `split.py` | 1001 | **Yüzeyi Böl** (v0.25): kenara nokta ekleme (`insert_point`), yüzey sınırı (`PatchGeom`), döngü kesimi halkası (`ring_cuts`), bıçak (`knife_cut`), uygulama (`apply_cuts`, `split_patch`), modal araç `minicad.split_surface` |
| `surfmath.py` | 442 | bpy'siz bölme matematiği: bezier bölme / en yakın parametre, kenar parametresi, Coons (3 / 4 kenar), üçgen ağda en yakın nokta ve ışın (`Mesh`), izdüşüm, bezier zinciri uydurma (`fit_chain`) |
| `pick.py` | 579 | Kenar seçim modu (hover + tık), sarı gövde kenarları, B ile fillet |
| `ui.py` | 590 | Operatörler, tercihler (`background`), `add_feature` (BODY ref) |
| `panels.py` | 566 | N panelleri: Gövde, Seçim ve Tel Kafes, Kısıtlar, Yüzeyler, Simetri, Boolean, Fillet, İşlem Sırası, Ayarlar, Export |
| `bool_overlay.py` | 177 | Boolean vurgusu, CAD kenarları, hayalet çizimi |
| `wire.py` | 308 | Mesh kenarlarından bezier tel kafes |
| `recorder.py` | 533 | Ctrl+Alt+R kayıt / rapor (§7) |
| `diag.py` | 83 | Motor durumu / log metinleri |

**Bölme notu (v0.15.2):**
- `draw.py` mixin'lere, `constraints.py` üç modüle ayrıldı. Kod satırları **birebir taşındı**:
  AST eşdeğerlik kontrolü yapıldı (154 + 54 tanım aynı) ve testler değişmedi.
- Eski adlar geriye dönük uyum için yeniden dışa aktarılıyor: `draw.dm`, `draw.is_running`,
  `draw.cleanup_all`, `draw._STATE`, `draw._axis_col`, `constraints._last_pos`,
  `constraints._glyph_boxes` ...
- **Yeni kod doğru dosyaya yazılır.** Ortak sabit veya yardımcı gerekiyorsa `draw_common.py`'ye
  koy. Mixin'ler birbirini `self.` üzerinden çağırır.
- `core.py` ve `geometry.py` **bilerek bölünmedi:**
  - Testler `core.*` fonksiyonlarını monkeypatch ediyor. Taşınan kod bu yamaları görmez.
  - geometry.py burada (OCC'siz) gerçek olarak test edilemiyor; alt süreç de dosyaları adıyla
    yüklüyor.
  - Bölünmeleri gerekirse ayrı ve dikkatli bir adım olarak yapılır.
- Bölme araçları: `devkit/tools/split_top.py` (üst düzey tanımlar),
  `devkit/tools/equiv.py` (AST eşdeğerlik kontrolü).

---

## 5. Çizim aracı (`MINICAD_OT_draw`, `minicad.draw`)

**Sınıf:** `MINICAD_OT_draw(SnapMixin, PlaneMixin, SketchMixin, EditMixin, ConstraintUIMixin,
RenderMixin, ModifyMixin, TransformMixin, ShapeMixin, DimMixin, TextMixin, SketchConsMixin,
bpy.types.Operator)`. Mixin'lerde **aynı adlı metot olmamalı** (v0.16'da
`_offset_update` çakışması yakalandı). Kontrol:
`grep -ho "^    def [a-zA-Z_0-9]*" draw_*.py draw.py | sort | uniq -d` boş dönmeli.

**Fazlar** (`self.phase`):
- `PLANE`: 1/2 yön seçimi. Eksen düzlemi ya da yüz seçilir; düzlem seçici gri ve silik çizilir.
- `OFFSET`: 2/2 yükseklik. Fare, bir nokta ya da yazılan değerle belirlenir.
- `DRAW`: çizim.

`minicad_pick_plane` kapalıysa doğrudan DRAW fazından başlar.

**Araçlar ve kısayollar:**

| Araç | Kısayol |
|---|---|
| Seç | W |
| Doğru | L |
| Teğet yay | A |
| 3 noktalı yay | E |
| Merkezli yay | M (D: yön) |
| Daire | O |
| Dikdörtgen (R'ye tekrar bas: 3 nokta → merkezden → 3 nokta merkezden) | R |
| Daire (O'ya tekrar bas: Teğet daire → Elips) | O |
| Çokgen (D: iç / dış teğet), Kanallar, Yay kanal, Nokta, Geometri yansıt | palet (ÇİZ) |
| CV spline | S |
| Noktalardan geçen spline | K |
| Kalem | P |
| Kırp (Shift: Uzat) | B |
| Uzat, Böl, Ötele, Köşe yuvarla, Pah | palet (DEĞİŞTİR) |
| Taşı, Kopyala, Döndür, Ölçekle, Esnet, Dikdörtgen / Dairesel desen, Ayna | palet (DÜZENLE · DESEN) |

Diğer kısayollar:
- **Araç geçişi:** Q son iki araç arasında geçiş yapar. Shift+Q düzlemi yeniden seçtirir.
- **Eksen kilidi (v0.25.6):** X / Y / Z — Blender'daki G → X gibi: son noktadan DÜNYA ekseni
  boyunca (Blender gizmosuyla aynı yön, X kırmızı / Y yeşil / Z mavi çizgi). Tekrar basana kadar
  sürer (noktadan noktaya da). Yakalama kilidi bozmaz: yakalanan nokta eksene izdüşer
  ("Uç hizası", `snap_id` yazılmaz); ızgara eksen boyunca; yazılan uzunluk imleç yönünde ('-'
  ile ters). Doğruya otomatik AXIS kısıtı. Şekil araçlarında (daire, dikdörtgen, çok
  tıklamalılar) uygulanmaz. Önce X/Y/Z düzlem seçiyordu (X → YZ: X'e DİK düzlem, kullanıcıyı
  şaşırtıyordu; yakalanan nokta düzlem dışındaysa kilit bozuluyordu). `_axis_point`.
  Sürüklemede (draw_edit) eksen kilidi de artık yakalamayı eksene izdüşürür.
- **v0.25.12: eğriye bağlanan çizgi, kilit öncelikli yakalama** (kullanıcı: iki kapalı eğri
  arasına bağlantı eğrisi; başlangıç ve bitiş eğriye yapışıp eğriye kesişim noktası eklensin,
  Shift+Y / X·Y·Z kilitleri hiçbir yakalamayla bozulmasın, kapatana kadar sürsün).
  - "Yakın" yakalaması artık çoklu çizgi kirişinde değil gerçek bezier'in üstünde
    (`_ref_geo`, `surfmath.bez_ray_closest`; `_Refs.geo` / `_Refs.own`: A/B satırı → tam
    geometri).
  - **Kilitli kesişim** (`_lock_curve_hit`, tür "Eğri", X işareti): eksen kilidinde eksen
    doğrusunun, düzlem kilidinde (Shift+X/Y/Z, V, seçilen düzlem; ilk noktadan sonra)
    düzlemin imlece yakın eğrileri kestiği nokta (`surfmath.bez_line_hits`,
    `bez_plane_hits`, çoklu çizgi için `poly_*`). Nokta hem eğride hem kilitte: kilit
    bozulmaz. Kilit üstündeki uç / orta / merkez yakalaması yine önce gelir; kesişim
    yoksa eski davranış (izdüşüm "hizası"). Düzlemin içindeki eğri kesişim sayılmaz.
  - **Bağlama:** imleç "Yakın" ya da "Eğri" iken konan nokta `attach_pts`'e, çizgi
    taslağa eklenince düğümlerine denk gelenler `st["attach"]`'a yazılır. Bitir'de bütün
    çizgiler yazıldıktan sonra (`_attach_all`) o noktadan geçen tel kafes segmenti bulunur
    (`_wire_hit`, kendi spline'ı hariç; taslaktan yeni yazılan eğriler dahil), oraya
    `split.insert_point` ile nokta eklenir (biçim değişmez, yüzey referansları iki yarıya
    eşlenir) ve uç ona COINCIDENT ile bağlanır. Nokta zaten düğümse yalnız kısıt. Uç
    taslakta taşınmışsa bağlanmaz. "Orta" ve "Kesişim" (iki doğrunun) yakalamaları eskisi
    gibi eğriyi bölmez (ölçü kısıtları bozulmasın).
  - Eksen / düzlem kilidi kapatılana kadar sürer (çizgi bitince de).
- **Düzlem:** Shift+X / Shift+Y / Shift+Z (Blender'daki gibi: o eksen dışındaki düzlem), V.
  - **Düzlem kilidi (v0.25.10;** kullanıcı: "Shift+X YZ'de kilitlemiyor, işe yaramıyor; başka
    yakalamayla karşılaşınca kilit bozulmasın"). Üç ayrı sebep vardı:
    - Düzleme kenarından bakılırken (üstten bakışta Shift+X → YZ) ışın düzlemi kesmiyor, imleç
      donuyor / fırlıyordu. `_plane_hit`: |ışın · normal| < 0.15 ise fare, düzlem başlangıcından
      geçen görünüş düzlemine alınıp kilitli düzleme izdüşürülür (ekranda görünen doğrultuda
      hareket). Yalnızca açıkça seçilen eksen düzlemlerinde.
    - Eksen kilidi (X) açıkken Shift+X etkisizdi (eksen kilidi öncelikli). Düzlem seçmek artık
      eksen kilidini kapatır.
    - Düzlem dışındaki noktaya yakalanınca çizim düzlemden çıkıyordu. `PLANE_LOCK_MODES`
      (XY / XZ / YZ / VIEW) ve kurulu düzlemde yakalanan nokta düzleme izdüşer ("… hizası",
      `snap_id` yazılmaz). Otomatik düzlemde ve seçili (LOCK) düzlemde eski davranış.
    - Taslak sürüklemede (draw_edit) Shift'e bakılmıyor, Shift+X de X ekseni kilidi oluyordu.
      Artık `d["plane_lock"]`: o eksene dik dünya düzlemi (sürüklenen noktadan), yakalama
      düzleme izdüşer; tekrar Shift+X ya da X/Y/Z kapatır (`plane0`'a döner).
- **Geçici zemin (G; v0.25.6'ya kadar U):** çizerken ızgaranın yönü ve yüksekliği değiştirilir
  (aşağıya bakın). Sol el ASD bölgesinde kalsın diye G (Ground).
- **Çizerken:**
  - C: başlangıca dönüp kapatır. F: kapalı çizgiden yüzey (Ctrl+F: yeni gövde).
  - Shift: 15° adım. Ctrl: yakalama kapalı. I: ızgara yakalaması aç / kapa.
  - T: iz; referans noktadan eksenler boyunca kesikli çizgilerle başlangıç noktası tayini.
  - Yazarak ölçü girilir (`25mm`, `30`); Tab sonraki alana geçer.
  - Backspace: son noktayı geri alır.
- **Bitirme:**
  - Sağ tık / Enter: çizgi biter ve **taslağa** eklenir.
  - **Ctrl+Enter = Bitir:** taslak hedef eğriye yazılır.
- **Ctrl+Z / Ctrl+Shift+Z:** taslak aşamasında aracın kendi geçmişini kullanır (`_hist_*`,
  imza tabanlı anlık görüntü). Bitir'den sonra Blender'ın geri alması geçerlidir.
- **Esc:** 1. basış "Seç" aracına geçirip duraklatır; tıklar Blender'a gider. 2. basış aracı
  kapatır.

**Taslak modeli:**
- Çizgiler `self.sketch` içinde hafızada tutulur. Bitir (`_finish_sketch`) hepsini hedef eğriye
  **yeni spline** olarak yazar.
- Hedef `minicad_draw_target` ile seçilir: ACTIVE = mevcut / son eğri, NEW = her Bitir'de yeni
  eğri.
- Var olan spline sırası **asla değişmez**; yüzeylerin kenar referansları buna dayanıyor.
- Oto kısıtlar **yalnızca sağlanıyorsa** yazılır (`constraints.satisfied`).
  `_auto_tangent` ve `_auto_joints` uç birleşimlerini ekler.

**Taslak düzenleme** (draw_edit):
- Noktalar ve tutamaçlar sürüklenir. X/Y/Z eksen kilidiyle 3. eksende de düzenlenebilir.
- Pürüzsüz birleşimde karşı tutamaç hizalı kalır.
- Tıklanan noktada **pivot** çıkar; oklarından sürükleyince o eksende taşınır.
- Sürüklerken tam yakalama ve ızgara geçerlidir (`_drag_apply`, `_point_snap_excluding`).
- **Sürüklerken ölçü yardımcısı** (`_draw_drag_input`, `_dim_anchor`, `_drag_typing`):
  - Ölçü noktası: tutamaçta bağlı olduğu nokta, noktada çizgideki komşu nokta (önceki; yoksa
    sonraki).
  - Çizimdeki gibi uzunluk / açı etiketi ve imleç yanında ölçü kutusu gösterilir.
  - Basılı tutarken yazılan değer kilitler: uzunluk (tutamaçta tutamaç boyu), Tab ile açı.
    Eksen kilidinde (X/Y/Z) yazılan değer eksen boyunca kaydırmadır.
  - Bırakınca ya da Enter ile uygulanır. Sürüklenen öğenin yüksekliği korunur.
- Durum alanları: `sk_hover` / `sk_drag` / `sk_sel`.

**v0.22.0: taslak kısıtları** (`draw_skcons`):
- Kısıt / ölçü aracı seçmek taslağı Bitir'lemez; yalnızca süren çizgi taslağa eklenir.
- Taslak çizgisi kalıcı kimlik `uid` alır (ilk kısıtta). Taşı / Döndür / Ölçekle (kopyasız),
  Esnet ve sürükleme kimliği korur. Yapıyı değiştiren işlemler (Kırp, Böl, Yuvarla...)
  korumaz; o çizgiye bağlı taslak kısıtları "referans kayboldu" olur.
- `self.skc` referansları: `("seg"|"pt", "@sk", uid, sıra)` ya da kaydedilmiş eğri (adla).
  Seçimde taslak ve kayıtlı eğriden imlece yakın olan alınır (`_pick_any`).
- **Canlı** (nokta tabanlı) kısıtlar `_sk_solve` ile taslakta çözülür; kaydedilmiş noktalar
  sabittir. Çözüm ekleyince, sürükleme bitince ve `_set_sketch` sonrasında yapılır.
- **Teğet / Pürüzsüz** (v0.25.5, `GEO`, `_skc_geo`): taslakta ANINDA ve biçimi bozmadan
  (kullanıcı: "teğet çalışmıyor, eğrilerin yuvarlaklığını bozmasın, Inventor gibi"; önce
  Bitir'e kadar bekliyordu). `_sk_solve` = nokta çözümü (`_sk_solve_pts`) + `_skc_geo_all`;
  sürükleme / taslak araçlarından sonra da yeniden uygulanır.
  - Varlık (`_skc_ent`): taslakta segmentlerin kayıtlı türü (sürüklenip bozulan yay da yay
    sayılır), kaydedilmiş eğride geometriden. Uyan varlık: kaydedilmiş sabit; ikisi de
    taslaktaysa eğri > yay > doğru, aynı türdeyse ikinci seçilen.
  - Ortak uçta (J): yay iki ucunu koruyarak J'de teğet çember yayı olarak yeniden kurulur
    (`dm.tangent_arc`, aynı parça sayısı); doğru (iki doğru) J etrafında döner, boyu kalır;
    serbest eğride yalnızca J'deki tutamaç yönü (boyu aynı). Pürüzsüz (G2): eğride 2. kontrol
    noktası eğrilik eşitlenecek şekilde (`_curvature`); doğru / yay arasında G2 olamaz →
    teğet uygulanır, açıklama.
  - Ortak uç yoksa: doğru–yay (doğru kendine paralel kayar), yay–yay (yay kayar, iç / dış
    teğetten yakın olan).
- **Bekleyen** kısıtlar Bitir'de uygulanır: RADIUS, CONCENTRIC, CENTERDIST, yaylarda EQUAL.
- Ölçü aracı taslakta da çalışır (`dim_edit = ("@sk", i)`, `_skc_apply_value`).
- Taslak kısıtları görünümde silik çizilir; sağ tık doğrudan siler.
- Bitir: `_written_uid` ile uid → (obje, spline); `_skc_finish` gerçek kısıt ekler.

**Izgara** (v0.22.0): imleç çevresinde dairesel, kenara doğru yumuşak silikleşen ızgara
(`drawmath.grid_segments` / `grid_falloff`, `POLYLINE_SMOOTH_COLOR`). Ayarlar:
`minicad_grid_alpha` (görünürlük), `minicad_grid_fade` (yumuşaklık), `minicad_grid_size`
(yarıçap, ızgara aralığı cinsinden).

**v0.21.0: taslak ↔ kaydedilmiş eğri bağları**
- **Spline sırası yeniden eşleme** `core.remap_splines(eğri, fn, seg_count)`: bir eğrinin
  spline sırası değişince ona bağlı bütün referanslar güncellenir.
  - Kapsadığı referanslar: yüzey ve özellik segmentleri (`patches/features.segs`), eski
    `bevels`, kısıt `CRef`'leri, ilişkiler (`links`).
  - `fn(eski) → yeni | None`. None: silindi (-1, referans geçersiz). Ayrıca o eğrinin
    `_last_pos` kayıtları silinir.
  - Spline silen / taşıyan her kod bunu çağırmalı (`links.remove_splines`,
    `_edit_load`, Bitir'deki geri yazma).
- **Taslağa al** (`EDITSK`, `_edit_load`, Inventor "Edit Sketch"):
  - Spline taslağa çizgi olarak alınır (doğru / yay / eğri tanınır) ve objeden silinir.
  - Ona bağlı referanslar geçici negatif bir işarete (`token`), sonrakiler bir aşağı eşlenir.
    Çizgi `edit_src = {"obj", "token"}` taşır.
  - Taşı / Döndür / Ölçekle (kopyasız) ve tek çizgi üreten değiştir işlemleri `edit_src`'yi
    korur. Bölünen çizgi korumaz: referanslar geçersiz kalır.
  - Bitir'de çizgi aynı objeye sona yazılır, işaret yeni sıraya eşlenir. Segment sayısının
    dışında kalan referanslar geçersizleşir.
  - Yükleme taslak geçmişini sıfırlar (spline objeden çıktığı için geri alınmaz).
  - Düzenleme sürerken o eğriye bağlı yüzey / kısıtlar geçici olarak "referans kayboldu"
    der (Inventor'da taslak düzenlenirken model güncellenmez).
- **Taslakta bekleyen kısıtlar** `self.sk_cons`: konumla tanımlı referanslar
  (`("seg", A, B, orta)` / `("pt", P)`).
  - Bitir'de `_resolve_geo` kaydedilmiş eğrilerde konumdan bulur ve yalnızca sağlanıyorsa
    yazar. Taslakta düzenlenip geometri değiştiyse düşer.
  - Kullananlar:
    - Ayna: ayna noktaları gerçek bir doğrunun uçlarıysa, düğüm çiftleri için SYMLINE.
    - Köşe yuvarla: aynı oturumda aynı yarıçapla yapılan yaylar ilkine EQUAL (`fillet_eq`).
- **İlişkiler** (`core.MINICAD_Link`, `links.py`, tel kafes eğrisinin `cad.links`'i):
  - Desen: kaynak / kopyalar `pat = (id, "src"|"copy", örnek, j)` etiketi alır, tanım
    `sk_pats[id]`'de tutulur. Bitir'de kaynak ve kopyalar eksiksiz ve aynı objedeyse RPAT /
    CPAT kaydı oluşur. Taslakta düzenlenen kopya etiketini kaybeder → ilişki kurulmaz.
  - Yansıtma: tel kafes segmentinden yansıtılan tek parçalı çizgi `proj` etiketi taşır →
    PROJ kaydı.
  - Güncelleme `links.update_all`:
    - Değer değişince (`_on_link_change`) ve eğri değişince (depsgraph → zamanlayıcı)
      çalışır.
    - Kopyalar kaynaktan yeniden yazılır; değişmeyen yazılmaz, döngü olmaz.
    - Adet artınca sona yeni spline eklenir, azalınca fazlalar silinir ve referanslar
      eşlenir. Kaynağın nokta sayısı değişirse kopya yeniden kurulur.
  - Panel: Kısıtlar panelinde "İlişkiler" (adet / aralık / açı, kaldır: kopyalar bağımsız
    kalır).
- **Metin** (`TEXT`, `draw_text`):
  - Tık: sol alt köşe. Yazılan her karakter metne gider (araç kısayolları çalışmaz).
    Tab: yükseklik, Enter: ekle, Esc: vazgeç.
  - Blender FONT nesnesi geçici olarak oluşturulup `to_curve` ile eğriye çevrilir, her
    spline kapalı taslak çizgisi olur (`_font_splines`).
  - Testte `_font_splines` taklit edilir; gerçek dönüşüm yalnızca Blender'da denenebilir.

**v0.25.0: Yüzeyi Böl** (`split.py`, `surfmath.py`; Gövde paneli "Yüzeyi Böl"):
- Mevcut yüzeylere yeni kenar ekleyip onları böler (kullanıcı isteği: Blender Ctrl+R / bıçak
  gibi; ya da noktadan noktaya çekilen eğrinin yüzeye izdüşümü).
- **Döngü kesimi (R, varsayılan):** bir yüzey kenarının üzerine gelinir. Kesim o kenardan karşı
  kenara gider (4 kenarlı yüzeyin Coons parametre doğrusu, `ring_cuts`). Karşı kenarı paylaşan
  4 kenarlı komşuda sürer: halka (kapanınca ya da 4 kenarlı olmayan / serbest kenarda durur).
  - Konum: fare (kenar boyunca); yazılan oran (`0.3` ya da `30` = %30); C: ortala.
  - Tekerlek / + −: kesim sayısı (eşit aralıklı; imleç bir kenardayken tekerlek görünümü
    yakınlaştırmaz). Tık / Enter: uygula.
- **Bıçak (K):** sınırda iki nokta (köşe > kenar ortası > kenar üstü yakalama). Nokta çifti aynı
  yüzeyin farklı kenarlarında olmalı (köşe iki kenara birden sayılır). 3 / 4 kenarlı yüzeyde
  kesim Coons (u, v) düzleminde düz çizgi; V ile "Görünüş": ekrandaki düz çizginin görünüş
  yönünde yüzeye izdüşümü (diğer yüzeylerde her zaman). Sağ tık: noktaları bırak.
- **v0.25.2: çok yüzeyli bıçak** (`knife_path`; kullanıcı: aradaki kenarlarda duruyordu).
  İki nokta aynı 3 / 4 kenarlı yüzeyde değilse (ya da V ile Görünüş açıksa) ekrandaki A→B
  çizgisi boyunca (96 örnek) görünüş ışınları gövde mesh'ine atılır (önde ilk kesişim; hız
  için yalnızca çizginin ekran kutusundaki üçgenler). Çizginin ekranda kestiği tel kafes
  kenarları kesişim noktası olur; derinlik denetimi: kenar noktası yüzey izine
  `max(10·tol, %2 boyut)` kadar yakın değilse arkada kalan gizli kenardır, sayılmaz. Köşeden
  geçişte aynı noktadaki kesişimler birleşir. Ardışık iki kesişim arası parça, iki ucu farklı
  kenarlarında olan yüzeyin kesimidir; `apply_cuts` hepsini birlikte uygular. Işın boşluğa
  düşerse ("yüzeyin dışına çıkıyor") ya da bir parça tek yüzeye sığmazsa kesim yok, durum
  satırında sebebi yazar (`knife_err`).
- **Kesim eğrisi:** önizlemede Coons; uygularken gövde mesh'ine (`body_mesh`,
  `surfmath.Mesh`) en yakın noktaya / ışınla izdüşürülür, `fit_chain` ile bezier zincirine
  çevrilir (tolerans: `max(join_tol/2, boyut·5e-4, 2·lin_defl)`; mesh'in köşeliliğine
  uydurulmaz) ve kesimin ucundaki kenarın eğri objesine yeni spline olarak yazılır.
- **Kenara nokta ekleme** (`insert_point`): uç kenar ortasına düşüyorsa segment de Casteljau
  ile bölünür (biçim değişmez; düz kenar VECTOR kalır, AUTO / VECTOR tutamaçlar ALIGNED / FREE
  olur). `core.remap_insert`: bağlı yüzey / özellik / bevel segmentleri iki yarıyı alır,
  sonrakiler kayar; kısıtlarda nokta indeksleri kayar, bölünen segmentteki yön / çember
  kısıtları (`SPLIT_SAFE_KINDS`) kalır, ölçü kısıtları devre dışı (bilgi notu). Poly spline ve
  desen / yansıtma ilişkisindeki spline bölünmez (`validate_cuts` önce denetler: hiçbir şey
  değişmeden hata).
- **Yüzeyi ayırma** (`split_patch`): döngü kesim uçlarından ikiye ayrılır; ilk yarı mevcut
  yüzeyde kalır, ikinci yarı ayarları kopyalanmış yeni yüzey (`Ad.2`) olur. Eski "eğrinin
  tamamı" yüzeyleri önce segment referanslarına çevrilir. Halkada sıradaki kesim, önceki
  bölmeden çıkan parçalardan uçları köşe olan parçaya uygulanır (`lineage`).
- Araç açıkken Ctrl / Alt'lı tuşlar (Ctrl+Z dahil) ve tanınmayan tuşlar Blender'a gider; veri
  bir sonraki fare hareketinde yeniden okunur. Eğri düzenleme modundaysa obje moduna geçilir.
- Ölçüm (`devkit/tools/occ_split_check.py`, gerçek OCC): halka modelinin yan yaması ortadan
  bölünüp Teğet ile yeniden kurulunca yeni dikişte kırılma 0.03°, orijinal yüzeyden sapma
  0.0043 (yama boyunun ~%0.14'ü).

**v0.23.0: Çizimi Düzenle** (Inventor "Edit Sketch", bütün çizim):
- Kaydedilmiş (Bitir'lenmiş, "2. aşama") bir çizim, yani eğri objesinin tamamı yeniden taslağa
  ("1. aşama") alınır.
- Giriş yolları:
  - Outliner'da eğriye sağ tık → **Mini CAD: Çizimi Düzenle** (`OUTLINER_MT_object`).
  - 3D görünümde nesne sağ tık menüsü (`VIEW3D_MT_object_context_menu`).
  - Gövde panelinde aktif eğri varken **Çizimi Düzenle: <ad>** düğmesi.
  - Çizim aracında Taslağa al (EDITSK) + **Shift+tık**.
- Komut `minicad.edit_sketch` (`draw.MINICAD_OT_edit_sketch`):
  - Hedef `draw.edit_target`: ad, Outliner seçimi (`selected_ids`), aktif obje, seçili objeler.
  - Önce `ed.undo_push("Mini CAD: Çizimi Düzenle")` yapılır: Bitir'den sonra Ctrl+Z
    düzenleme öncesine döner.
  - Çizim aracı açıksa taslağa eklenir (aynı çizim ikinci kez alınmaz). Kapalıysa en büyük 3D
    görünümde `minicad.draw(edit_curve=ad)` açılır (`_view3d`, `temp_override`).
- `_edit_load_all`:
  - ≥2 noktalı bütün bezier spline'lar sırayla taslağa alınır, her biri kendi `token`ını
    alır (`edit_src`). Tek noktalı (Nokta) ve bezier olmayan spline'lar objede kalır,
    referansları aşağı eşlenir.
  - Bitir'de çizgiler aynı sırayla sona yazılır: kalan spline'lar önce, düzenlenenler aynı
    göreli sırayla sonra gelir; referanslar tokenlardan eşlenir.
  - `self.edit_obj`: düzenleme sürerken çizilen **yeni** çizgiler de hedef ayarından bağımsız
    olarak bu çizime yazılır. Bitir düzenlemeyi bitirir (`edit_obj = None`).
  - Çizim düzlemselse düzlem kilitlenir (`_edit_plane`: SVD; eksen düzlemiyse XY / XZ / YZ,
    değilse "FACE"), faz DRAW olur ve görünüm düzleme çevrilir. Düzlemsel değilse ya da tek
    doğruysa düzlem değişmez.
- v0.23.1: Değiştir araçları `_update`'ten geçmediği için yakalama / sınır referansları
  (`self.refs`) yenilenmiyordu; taslağa alınan spline'lar objeden çıktığı hâlde sınır
  sanılıyor, Kırp / Böl / Uzat kendi gizli kopyasında kesiyordu. `_refs_sync` (draw_snap)
  artık `_mod_update` başında ve taslağa alma sonrasında da çağrılır.
- Ctrl+Z koruması: taslakta `edit_src`'li çizgi varken ve taslak geçmişi boşken Ctrl+Z
  Blender'a gitmez. Gitseydi spline'lar objeye geri gelir, Bitir'de çiftlenirdi.
- Yalnızca düzenlenen çizgilerin olduğu Bitir artık geri alma adımı yazar (`created` artar)
  ve taslak geçmişini temizler.
- **v0.25.11: sınırsız düzenleme** (kullanıcı: "Çizimi Düzenle'den sonra Çizimi Kapat'a basınca
  çizim görünümden kayboluyor"). Sebep: `cleanup_all` aracı yalnızca durduruyordu; taslağa
  alınmış spline'lar objeden silinmiş olduğu için taslakla birlikte gidiyordu.
  - `draw_common.cleanup_all(save=True)`: kapatmadan önce `save_sketch` → `_finish_sketch`
    (Bitir). Paneldeki Çizimi Kapat, Kenar Seç ve Yüzeyi Böl'ün açılması, eklenti kapatma
    bu yoldan geçer. Dosya yüklenirken (`load_pre`) `save=False`.
  - `save_pre`: taslakta `edit_src`'li çizgi varken dosya kaydedilirse önce Bitir'lenir
    (dosyada çizim eksik kalmasın); araç açık kalır. Yalnız yeni çizgiler taslağa dokunulmaz.
  - **Gövde dondurma** (`core.frozen`, `core.edited_curves`, `core._frozen_skip`,
    `core.thaw_edited`): düzenlenen çizime bağlı gövde düzenleme sürerken yeniden
    hesaplanmaz (depsgraph, kuyruk, senkron `rebuild`); son hâli görünür kalır, panelde
    "Çizim düzenleniyor" yazar. Bitir / kapatma sonrası girdi değiştiyse ya da ertelenen iş
    varsa yeniden hesaplanır: yüzeyler tel kafesin yeni hâlini izler. Önce düzenleme
    sürerken yüzeyler "referans kayboldu" hatasıyla kayboluyordu.
  - Düzenle → yüzey (F) → tekrar düzenle → kapat döngüsü sınırsız tekrarlanabilir (t67).

**Oluştur araçları** (v0.18.0; `draw_shapes` + `shapemath`):
- **Çok tıklamalı şekiller** `CLICK_SHAPES` ⊂ `SHAPE_TOOLS` (RECT3, RECTC, RECT3C, POLYGON,
  SLOTCC, SLOTO, SLOTC, ARCSLOT, ELLIPSE).
  - Normal çizim akışını kullanırlar: her tıkta bütün yakalamalar geçerli.
  - Akış: `_place` önce `stage`'e ekler (`_sh_place`, `NEEDED` tık sayısı), son tıkta
    `_write_shape` çağrılır. Önizleme `_make_preview` → `_shape_preview`. Ölçü kutusu
    `shape_rows`'tan gelir.
  - `FIELDS` bu şekiller için `(None, None)`: genel kilit yok, yazılanı şekil kendisi uygular
    (2. tıkta uzunluk / açı, son tıkta genişlik vb.). İmleç kilitli konuma alınır, Enter
    yazılan değerle tıklar.
  - `_lock_anchor` bu şekillerde `stage[-1]`'dir (kılavuzlar son noktaya göre).
  - Dikdörtgenler eksene hizalıysa yatay / dikey, değilse dik / paralel oto kısıt alır. Elips
    tek nesnedir (aynı `grp`).
- **Çokgen:** varsayılan 6 kenar (Kenar alanı, Tab; hatırlanır). D ile iç / dış teğet
  (yalnızca bu araçta; diğerlerinde D merkezli yayın yönü).
- **Teğet daire** (`CIRCT`, `PICK_TOOLS`): `refs.chords`'tan üç doğru seçilir (taslak, tel
  kafes, gövde kenarı). Doğruların üçgeninin iç teğet dairesi hesaplanır; Backspace son seçimi,
  sağ tık hepsini bırakır.
- **Nokta** (`POINT`):
  - `self.sk_points` listesinde tutulur, taslak geçmişine dahildir.
  - `_Refs`'e "Nokta" türünde yakalama noktası olarak eklenir.
  - Bitir'de tek noktalı bezier spline olarak yazılır (`_write_point`). `_Refs` tek noktalı
    spline'ı yine "Nokta" olarak tanır. Bütün spline döngüleri `_seg_count` kullandığı için
    (0 segment) güvenli.
- **Yansıt** (`PROJECT`, `PICK_TOOLS`): CAD gövde kenarı (`core._display` edges) ya da tel
  kafes segmenti düzleme dik izdüşürülür.
  - Tel kafes segmentinin bezier'i tam izdüşer (afin).
  - Gövde kenarı çoklu çizgisinden doğru / daire / yay tanınır, değilse spline uydurulur.
  - Sonuç taslağa normal çizgi olarak eklenir (Inventor'daki gibi ilişkisel, sarı referans
    değil).
- **Merkez noktalı yay kanal** (`SLOTARCC`): merkez, başlangıç, bitiş (D: yön), genişlik.
- **Teğet daire:** üç doğrudan sonra 4. tık yerleştirir; imlece en yakın çözüm (iç / dış
  teğet daireler) seçilir.
- **Hassas giriş** (Shift+Tab, `coord_mode`): ölçü alanları ΔX / ΔY olur (düzlem u / v
  eksenlerinde). İlk noktada mutlak X / Y (dünya merkezine göre) yazılabilir.
  `_coord_lock` uygular. Düzenle araçlarında da geçerlidir (`_xf_point` → `_update`).
  Çok tıklamalı şekiller kendi ölçülerini kullanır.
- **Tuş döngüleri** `TOOL_CYCLES`: aynı araç tuşuna tekrar basınca türler arasında geçilir.

**Değiştir araçları** (v0.16.0, Inventor 2D gibi; `draw_modify` + `sketchmath`):
- **Yalnızca taslak** (Bitir'lenmemiş çizgiler) üzerinde çalışırlar. Araca geçince süren
  çizgi taslağa eklenir. Kaydedilmiş eğriler dokunulmaz (spline sırası ve yüzey
  referansları korunur). Tel kafes eğrileri Kırp / Uzat'ta yalnızca **sınır** olarak kullanılır.
- **Varlık:** aynı `grp` değerli ardışık segmentler (tek doğru / yay / spline) ya da aynı
  çembere ait gruplanmamış yaylar (daire). Değiştirilen parçalar yeni `grp` alır.
- **Kırp (B):**
  - İmlecin altındaki varlık, en yakın iki kesişim arasında silinir; kesişim yoksa tamamı
    silinir.
  - Kapalı varlıkta (daire) başlangıç noktası da kesişim sayılır.
  - Basılı sürükleyince imlecin geçtiği her parça kırpılır (2×yakalama yarıçapı aralıkla).
  - Shift ile Uzat'a geçilir.
- **Uzat:** imlece yakın açık uç (ilk / son varlık) en yakın sınıra uzatılır. Doğru ışın
  boyunca, yay çemberi boyunca uzar; spline uzamaz. Shift ile Kırp'a geçilir.
- **Böl:** açık varlık imlece en yakın kesişimden ikiye ayrılır, çizgi bütün kalır. Kapalı
  varlık imleci çevreleyen iki kesişimde yay parçalarına ayrılır.
- **Ötele:**
  - Seçim: tıklayınca bütün çizgi (döngü), Shift+tık ile tek varlık.
  - Mesafe fareyle verilir ya da yazılır; tık / Enter uygular, sağ tık seçimi bırakır.
  - Öteleme: doğrular kayar, yaylar merkezden ölçeklenir (tam), spline'lar uç teğetleri
    korunarak uydurulur.
  - Köşeler: doğru–doğru kesişime uzar; diğer köşelerde boşluk teğet uzantılarıyla kapanır,
    örtüşme kesişimde kırpılır.
- **Köşe yuvarla / Pah:**
  - Teğet olmayan iç düğüm ya da iki ayrı çizginin çakışan uçları seçilir; ayrı çizgiler
    birleştirilir.
  - Yuvarlama yayı her eğri türünde iki ötelenmiş eğrinin kesişiminden (Newton) bulunur.
  - Değer yazılır, son değer hatırlanır. Yazılmadıysa ilk değer kısa kenarın %20'si.
  - Pah: 1. mesafe köşeden önceki parçaya, Tab ile 2. mesafe sonrakine (boşsa eşit).
- **Ayrı iki doğruda köşe** (`sketchmath.lines_corner`): köşe yoksa iki doğruya tıklanır.
  - Doğrular kesişime uzatılır / kırpılır; tek parçalı doğruda tıklanan taraf kalır.
  - Sonra `join_ends` ile birleşir ve yuvarlama / pah uygulanır.
- Hepsi taslak geçmişine girer (Ctrl+Z / Ctrl+Shift+Z). Oto kısıt referansları (`chain`)
  yeniden eşlenir, uzunluk kısıtı değişen parçada düşer.
  `("@sketch", ...)` teğet referansları `fix_sketch_refs` ile konumdan yeniden bulunur.

**Düzenle / Desen araçları** (v0.17.0; `draw_xform` + `sketchmath` dönüşümleri):
- `XFORM_TOOLS` ⊂ `MODIFY_TOOLS`: aynı yönlendirmeyi kullanırlar (`_mod_update`,
  `_mod_event` ve çizim bunları `_xf_*`'a iletir). Yalnızca taslakta çalışırlar.
- **Adımlar** `self.xf["step"]`: SEL (seçim) → BASE (temel / merkez / ayna 1. nokta) → TGT
  (hedef / açı / ölçek / 1. yön) → DIR2 (yalnız dikdörtgen desen).
  - İşlem bitince seçim korunur, BASE'e dönülür.
  - Sağ tık bir adım geri gider. SEL'de Enter / sağ tık ilerler.
- **Noktalar** (`self.xpts`, `sk_points` sırası; v0.20): tıklayarak ya da kutuyla seçilir,
  bütün düzenle / desen araçlarında çizgilerle birlikte dönüşür (kopyalarda eklenir).
- **Seçim** `self.xsel` (çizgi sıraları), Esnet için `self.xnodes` (çizgi, düğüm).
  - Tık seçer / bırakır; boşluğa tık seçimi temizler (Shift ile korunur).
  - Kutu: soldan sağa tamamen içindekileri, sağdan sola değenleri seçer. Esnet'te kutu
    düğüm seçer.
  - Düzenle araçları arasında geçişte seçim korunur, diğer araçlarda temizlenir.
- **Nokta girişi** `_xf_point`: araç geçici olarak Doğru yapılıp `_update` çalıştırılır. Bütün
  yakalamalar, kılavuzlar, ızgara, geçici zemin ve yazılan uzunluk / açı kilitleri böylece
  aynen geçerli.
- **Dönüşümler** (benzerlik: doğru doğru, yay yay kalır): `T_move`, `T_rotate` (düzlem
  normali etrafında), `T_scale`, `T_mirror`.
  - `apply_xform`: yerinde ya da kopya. Taşınan çizginin dış bağlantıları (`node_ids`,
    `start_tan`) düşer. Oto kısıtlar korunur, geçersiz kalanları Bitir ayıklar.
  - `apply_many`: desenler.
  - `stretch`: düğüm taşır, bağlı tutamaç kayar, doğru düz kalır. Bütün düğümler seçiliyse
    çizgi olduğu gibi taşınır.
- **Döndür:** açı, merkezden seçimin ortasına olan doğrultuya göre ölçülür (fare seçimi
  "tutar"). Shift ile 15° adım, yazılan değer derece. C kopyayı açar / kapar.
- **Ölçekle:** ölçek = imleç uzaklığı / en uzak seçili noktanın uzaklığı. Yazılan değer
  çarpandır. C kopyayı açar / kapar.
- **Dikdörtgen desen:** yön ve aralık fareyle (yazılan Aralık öncelikli), varsayılan Adet 3.
  2. yön isteğe bağlıdır (varsayılan Adet 2); sağ tık 2. yönü atlar.
- **Dairesel desen:** varsayılan 6 adet, 360°. Tam turda eşit bölünür, değilse uçlar dahil.
- **Ayna:** iki nokta (çizim düzleminde doğru) tanımlar; kopyalar eklenir. Simetri kısıtı
  yazılmaz, mevcut SYMMETRIC yalnızca dünya düzlemine göre.

**Yakalama:**
- Yakalanan noktalar: tel kafes ve CAD gövde kenarlarının ucu / ortası, çember ve yay merkezleri,
  kesişimler, kenar üstünde en yakın nokta.
- Kılavuzlar (snapmath): yatay / dikey, paralel / dik, devam, uç / orta / merkez hizası, doğru
  uzantısı, teğet uzantı, yay çemberi boyunca devam.
- Hepsi **zayıf mıknatıs**; çizimi engellemez. Öncelik `PRIORITY` tablosuyla belirlenir.
- Izgara yakalaması da zayıftır. Görünürlüğü `minicad_grid_alpha` ile ayarlanır; yakalama yine
  çalışır.

**Yay ölçü girişi** (v0.25.3; önce yay araçlarında `FIELDS = (None, None)` idi: ölçü kutusu R /
açı gösteriyor ama yazılan hiçbir yere uygulanmıyordu). `_arc_phase` adımı, `_fields` alanları
verir; `_point_lock_fields` noktayı kilitleyen (uzunluk / açı) alanlar, `_arc_typed` yayı
yazılan yarıçap / yay açısıyla yeniden kurar (`_make_preview` → `_make_preview_base` + bu):
- 3 noktalı yay: bitiş noktası Uzunluk / Açı (kiriş); eğrilik Yarıçap (küçük yay; kirişin
  yarısından küçükse yarım daire) / Yay açısı (180° üstü büyük yay). Yan: imleç.
- Merkezli yay: merkez (zincirden: önceki uca göre) Yarıçap / Açı; başlangıç (merkez önce
  seçildiyse merkeze göre, `_lock_anchor` merkez) Yarıçap / Açı; bitiş Yay açısı (yön:
  imlecin önizlemesi).
- Teğet yay: Yarıçap / Yay açısı (yalnız biri yazılırsa öbürü imleçten). Yan: imleç.
- Adım değişince (2. tık) yazılan sıfırlanır. Ölçü kutusu adımın alanlarını ve "Sıradaki"
  satırını gösterir.

**Yeni eğri hedefi** (v0.25.3, `_link_visible`): etkin koleksiyon gizli / hariçse yeni eğri sahne
koleksiyonuna bağlanır; yerel görünümdeyse (numpad /) objeye `local_view_set` yapılır.
Kullanıcı: "Yeni eğri ile Bitir: Outliner'a geliyor ama görünümde yok". Kayıt raporu artık
eğrinin koleksiyonunu ve yerel görünüm durumunu yazar.

**Teğet yay:** ilk tıklamadan çalışır (Inventor gibi). Bir çizginin ucundan başlayınca ona teğet
devam eder; boşlukta başlarsa 3 noktalı yay gibi davranır. `start_tan` iki kaynaktan alınır:
- Kaydedilmiş eğri ucu: `_end_tangent_of(snap_id)`.
- **Taslaktaki** (henüz Bitir'lenmemiş) açık çizginin ucu: `_sketch_end_tangent(nokta)`. Kimlik
  `("@sketch", çizgi, segment, uç)` biçimindedir. Bitir'de `_auto_tangent` bunu yazılan spline'a
  çevirir ve TEĞET kısıtını yazar. Taslakta birleşim ya da teğetlik bozulduysa kısıt yazılmaz.
- v0.15.0–0.15.2'de ikinci kaynak yoktu. Sağ tıkla taslağa eklenen çizginin ucundan başlayan
  teğet yay 3 noktalı yaya düşüyordu (v0.15.3'te düzeltildi).

**Geçici zemin (G)** (`draw_plane`: `_temp_begin`, `_temp_end`, `_temp_cancel`):
- Çizim fazında **U**: süren çizgi taslağa eklenir, iki aşamalı düzlem seçimi açılır.
  - 1/2 yön: eksen düzlemi, yüz ya da X/Y/Z/V. **Sağ tık / Enter: mevcut yön**, sadece
    yükseklik değişir. Esc: iptal, araç açık kalır.
  - 2/2 yükseklik: fare, nokta (taslak noktaları dahil), **ana düzlem** yüksekliği ya da ızgara
    yakalaması; değer de yazılabilir. Ölçü kutusunda yükseklik ve ana düzleme göre fark
    gösterilir. Yakalanan noktadan taban düzlemine hiza çizgisi çizilir.
- Onaylanınca `plane_mode = "LOCK"` olur ve `self.temp = {"saved", "plane", "label", "grid_o"}`
  tutulur. Yükseklik bir noktadan alındıysa ızgara kökeni (`_grid_origin`) o noktaya taşınır.
- Tekrar **G**'ye basılana kadar bütün yeni çizgiler bu zemine çizilir. G: asıl düzleme dönülür
  (`saved`). **Shift+G:** başka bir geçici zemin seçilir, asıl düzlem korunur.
- Açık düzlem seçimi (X/Y/Z/V, palet, Shift+Q) geçici zemini bitirir ve kalıcı olur.
- Ekranın sol altında "Geçici zemin: ..." etiketi görünür; durum çubuğunda da yazar.
- **Zeminde kalma** (`_temp_plane`, `_on_temp`, `_temp_tangent`; v0.15.4):
  - Geçici zemin açıkken eski çizimin bir noktasına yapışılırsa nokta zemine **paralel
    izdüşürülür**. Çizgi yeni yükseklikte başlar ve sürer.
  - Asıl nokta `snap_src`'de tutulur, ondan izdüşüme kesikli hiza çizgisi çizilir.
  - Farklı yükseklikteki noktalar arasında çakışık / teğet kısıtı yazılmaz (`snap_id`
    temizlenir, teğet kaynağı `("@proj", ...)`). Teğet yay için teğet zemine izdüşürülür.
  - Geçici zemin yokken eski davranış sürer: 3D noktaya yapışınca düzlem o noktaya taşınır.
- **Seçim sırasında görünürlük:** yön ve yükseklik seçilirken taslak çizgileri ve noktaları
  çizilmeye devam eder. Yön seçerken noktalara yapışılır (`plane_snap`). **Noktaya tık:** o
  noktadan geçen zemin tek adımda seçilir (yön: üzerindeki düzlem, yoksa mevcut yön). Bu kısayol
  yalnızca geçici zeminde vardır; normal düzlem seçimi iki aşamalı kalır.

**Sahne ayarları:** `minicad_grid_snap`, `minicad_grid_alpha`, `minicad_draw_target`,
`minicad_look_at`, `minicad_pick_plane`, `minicad_auto_constraints`,
`minicad_show_constraints`.

---

## 6. Kısıtlar

- **Saklama ve türler:**
  - İlk referansın eğri objesinde, `obj.cad.constraints` (core.MINICAD_Constraint, CRef ile)
    saklanır.
  - Türler: AXIS, PARALLEL, PERP, COLLINEAR, EQUAL, DISTANCE, ANGLE, FIX, COINCIDENT,
    SYMMETRIC, TANGENT; v0.19: CONCENTRIC, RADIUS, SMOOTH, SYMLINE, PTLINE, LINEDIST.
    Çözücünün içinde ayrıca TLINE, RADIUSN, EQDIST var.
  - DISTANCE iki nokta referansıyla da çalışır (noktalar arası mesafe).
- **Çözüm zamanı:**
  - Kısıt eklenince veya değeri değişince çözüm hemen yapılır.
  - Eğri düzenlemesinde çözüm, kullanıcı **sürüklemeyi bırakınca** yapılır; G/R/S ile çakışmaz.
  - Kullanıcının taşıdığı noktalar yüksek ağırlıkla yerinde tutulur (`prefer`).
- **Çözücü:**
  - Çözüm dünya koordinatında yapılır, sonuç obje uzayına yazılır. Tutamaçlar noktayla birlikte
    taşınır.
  - Ağırlıklı Gauss-Newton; sonlu farklar blok halinde hesaplanır. Takılma algılanır,
    tolerans `1e-8 × ölçek`.
- **Teğet planları** (`constraints_tangent._tangent_plan`):
  - `same`: aynı eğride komşu parçalar; tutamaç türleri hizalı yapılır.
  - `tline`: doğru, eğrinin teğetine döndürülür; eğri / yay noktaları 1e7 ağırlıkla tutulur.
  - `handle`: eğrinin tutamacı doğruya veya öbür eğriye hizalanır.
  - `arcslide` (**Inventor gibi**, varsayılan tercih):
    - Yayın çemberi (yarıçap / merkez) korunur.
    - Birleşim çember üzerinde kayar.
    - Doğru öteler veya kısalır.
    - Yay, yarım daire ya da yamuk biçimi **bozulmaz**.
  - Ayrı spline / ayrı eğriler arasında da ortak uç aranır (`_joint`).
- **Aşama 4 kısıtları** (v0.19.0):
  - **Yay merkezi sanal değişken:** RADIUS / CONCENTRIC'te her yay grubunun merkezi
    `("@c", obje adı, spline, ilk segment)` anahtarıyla çözücüye eklenir.
    - `_kname` / `_kpos` ile gerçek noktalardan ayrılır; `_write` sanal merkezi yazmaz.
    - Grup düğümleri RADIUSN ile merkeze bağlanır. Çözümden sonra `rebuild_group`
      tutamaçları yeni merkez ve uçlardan tam yay olarak kurar (yön korunur).
  - **Yay grubu** (`arc_group`): aynı çembere ait ardışık yay segmentleri; dairede hepsi
    (`closed`: çap gösterilir, `c.axis = 1`).
  - **Eş merkezli:** merkezler COINCIDENT. Ayrıca yarıçap ölçüsü yoksa grubun mevcut yarıçapı
    korunur (Inventor gibi boyut değişmez). Bu olmadan çözücü merkezi uzağa taşıyıp düğümleri
    büyük çembere kaydırıyordu (t53'te yakalandı).
  - **Pürüzsüz (G2):** teğet planı (`_tangent_plan`) uygulanır, ardından `smooth_post`
    serbest spline'ın 2. kontrol noktasını teğete dik kaydırarak birleşimdeki eğrilik
    vektörünü komşusununkine eşitler. Doğru–doğru ya da doğru–yay reddedilir.
    Teğet gibi uçların çakışık olması gerekir.
  - **Simetrik (çizgi)** `SYMLINE (p, q, a, b)`: orta nokta doğru üzerinde, p-q doğruya dik.
    Doğru da serbestse o da hareket edebilir.
  - **Nokta-doğru** `PTLINE`, **doğru-doğru** `LINEDIST` (paralel kalır: iki uç da aynı
    uzaklıkta).
  - **Yatay / Dikey** (`C_HORIZ`, `C_VERT`): çizim düzlemi bir eksen düzlemiyse onun u / v
    eksenine AXIS kısıtı yazılır; değilse uyarır.
  - **Karışık seçim** `constraints_refs.MIXED` / `slot_type`: SYMLINE (nokta, nokta, kenar),
    PTLINE (nokta, kenar).
- **v0.20.0 eklemeleri:**
  - **Referans (driven) ölçü** `c.driven`: çözüme girmez, `_set_measured` ile değeri
    geometriden ölçülür; parantezli gösterilir, panelde açılır / kapanır.
    - Ölçü aracı yeni ölçüyü önce `solve_all(dry=True)` ile dener. Kuru çözüm geometriyi
      değiştirmez. Çelişirse ölçü referans yapılır.
    - Referans ölçüye değer yazmak onu sürücü yapar. Çelişirse referans kalır.
  - **Merkez mesafesi** `CENTERDIST (yay, yay | nokta | doğru)`: yay merkezi sanal
    değişken; ölçüsüz yayların yarıçapı korunur (`center(..., keep_radius=True)`).
  - **Eşit (yay–yay):** iki referans da yaysa yarıçap eşitliği (Inventor gibi). Doğrularda
    eskisi gibi boy eşitliği.
  - **Otomatik ölçü** (`C_AUTODIM`): tıklanan spline'ın ölçüsüz doğrularına uzunluk,
    yay / dairelerine yarıçap / çap eklenir.
  - **Ölçü çizgileri** (`constraints_glyphs.dim_geometry` / `dim_layout`):
    - Doğrusal: uzatma çizgileri ve oklu ölçü çizgisi.
    - Yarıçap / çap: merkezden ok.
    - Açı: yay.
    - Değer kutusu çizginin üstündedir; tıklanınca düzenlenir.
  - **Düğüm dağıtma** (`_respace`): sanal merkezli çözümde düğümler çember boyunca
    kayabiliyordu (dairenin parçaları eşitsiz → yay tanınmıyordu).
    `rebuild_group` artık daire düğümlerini eski açı aralıklarıyla, açık yayın ara
    düğümlerini eski oranlarla yerleştirir.
- **Ölçü aracı** (`C_DIM`, `draw_dims`):
  - Seçim: köşe / uç noktası önce, yay / daire / spline ortasındaki pürüzsüz ara düğüm kenar
    sayılır (`_smooth_node`).
  - Tek kenar + Enter / sağ tık: doğru → DISTANCE, yay → RADIUS, daire → RADIUS (çap).
  - İki doğru: ANGLE, paralelse LINEDIST. İki nokta: DISTANCE. Nokta + doğru: PTLINE.
  - Oluşunca `dim_edit`: yazılan değer Enter ile uygulanır (çapta yazılan çaptır), sağ tık /
    Esc ölçülen değeri bırakır. Ölçü değerine tıklayınca (`glyph_at`) aynı düzenleme açılır.
- **Simgeler:**
  - Silik çizilir: 13 px, alfa 0.42, kutu alfası 0.3.
  - Üzerine gelince hiçbir şey olmaz. Sağ tıkta küçük menü açılır: çöp (sil) ve kar tanesi
    (dondur).

---

## 7. Kayıt / rapor (Ctrl+Alt+R)

- `recorder.py` stdout ve stderr'i bir halka tampona yansıtır (`_Tee`).
- Ctrl+Alt+R'ye basılınca:
  - `minicad_rec_seconds` (varsayılan 3) saniye kayıt yapılır.
  - Son 60 saniyelik log ve anlık durum toplanır. Anlık durum: CAD gövdeleri, eğriler,
    kısıtlar, çizim aracının faz / taslak / iz / sürükleme durumu.
- Rapor panoya kopyalanır ve eklentinin `reports` klasörüne .txt olarak yazılır.
- `minicad_rec_shot` açıksa ekran görüntüsü de alınır.

---

## 8. Test, doğrulama ve paketleme iş akışı

```bash
bash /home/claude/devkit/run_tests.sh /home/claude/mini_cad
```

Betiğin yaptıkları:
- `/tmp/fk/fakepkg` sahte motor paketini hazırlar: gerçek engine / jobs + sahte geometri.
- Testleri `/home/claude/test` altına kopyalar. Testler bu yolları sabit bekler.
- AST taraması (tanımsız ad), `py_compile` ve bütün `t*.py` testlerini çalıştırır.

| Test | Kapsam |
|---|---|
| t2–t16 | Eski çekirdek / tel kafes / yüzey testleri. t6 ve t14 bayat, bilinen hata. |
| t20 | Gerçek alt süreç taşıma, çökme / yeniden başlama |
| t21, t23 | core: gather → motor → _apply, canlı güncelleme, hayalet yolu |
| t22 | Gövde (boolean) kenarı seçimi, B ile fillet |
| t30 | drawmath |
| t31, t32 | Çizim modal simülasyonu, kayıt aracı |
| t40 | Kısıt çözücü |
| t41 | Palet, araçlar, kısıtlar, düzlem, ızgara, seç, simge menüsü, Q |
| t42 | Teğet senaryoları (arcslide dahil) |
| t43 | Taslak, sürükleme, T izi, geri al / yinele, pivot, tutamaç yakalama, yeni hedef |
| t44 | Taslak çizgisinin ucundan teğet yay, sürüklerken ölçü yardımcısı, geçici zemin (G) |
| t45 | Geçici zeminde eski çizime yapışınca zeminde kalma, seçim sırasında taslak görünürlüğü, noktadan zemin |
| t46 | Yüzey birleşimi: gather → motor kurma sırası, gövde sırası, imza, eski dosya |
| t47 | Değiştir araçları modal: Kırp (sürükleme, Shift), Uzat, Böl, Ötele, Köşe yuvarla, Pah, ayrı uçları birleştirme, Bitir, çizim |
| t48 | sketchmath: kesişim, kırpma (daire dahil), uzatma, bölme, öteleme, yuvarlama, pah |
| t49 | Düzenle / Desen modal: seçim (tık, pencere / kesişen kutu), Taşı, Kopyala, Döndür (+kopya), Ölçekle, Esnet, desenler, Ayna, seçim koruma, Bitir, çizim |
| t50 | sketchmath dönüşümleri: yay korunumu, kopya grupları, desen açıları, esnetme |
| t51 | shapemath: dikdörtgenler, çokgen, kanallar, yay kanal, elips, teğet daire, yansıtma |
| t53 | Aşama 4 modal: Ölçü (uzunluk, açı, paralel uzaklık, nokta mesafesi, nokta-doğru, yarıçap, çap, değer düzenleme), Eş merkezli, Yatay / Dikey, Simetrik (çizgi), Pürüzsüz (G2) |
| t54 | solver: SYMLINE, PTLINE, LINEDIST, RADIUSN, EQDIST |
| t57 | Delikli yüzey: chain_loops / nest_loops (delik, adacık, ayrı döngüler, düzlemsel olmayan), gather → motor (delik sayısı, alt yüzler) |
| t59 | (G: v0.23.1 taslağa alınan çizimde Kırp / Böl / Uzat) Çizimi Düzenle: bütün çizimi taslağa alma (sıra, nokta, referanslar, düzlem kilidi, yeni çizgi aynı çizime), Ctrl+Z koruması, düzlem tanıma, Shift+tık, komut (açık / kapalı araç, Outliner seçimi), `edit_curve` ile açılış |
| t58 | Taslak kısıtları (Bitir'lememe, canlı çözüm, ölçü, sürükleme / taşıma, geri al, silme, Bitir, karışık ve yay kısıtları), F ile iç içe çizgiler, dairesel ızgara |
| tools/occ_holes_check.py | GERÇEK OCC ile delikli yüz (alan, ortak kenar, iki yön) |
| t56 | 2. parti: ayna simetri kısıtları, yuvarlamada eşit, ilişkisel dikdörtgen / dairesel desen (adet / aralık / kaynak izleme / silme ve remap), ilişkisel yansıtma, taslağa al (remap, taşıma, geri yazma), metin |
| t55 | Eksikler 1. parti: referans ölçü (kuru çözüm), merkez mesafesi, yaylarda eşit, otomatik ölçü, ölçü çizgileri ve çizimi, ayrı doğrularda köşe, X / Y hassas giriş, merkez noktalı yay kanal, düzenle araçlarında noktalar |
| t52 | Oluştur modal: R / O döngüleri, yazarak şekiller, çokgen D, kanallar, teğet daire, Nokta (yakalama, geri al, Bitir), Yansıt, Bitir |
| tools/occ_blend_check.py | GERÇEK OCC ile teğet birleşim ölçümü (test koşucusunda değil, OCP gerekir) |
| tools/occ_blend_ring_check.py | GERÇEK OCC ile halka biçimli teğet birleşim (8 eğri yama, 4 biçim, kurma sırasından bağımsızlık, önizleme, Coons'a göre taşma, teğet ağırlığı, üçgenli model) |
| t62 | Ölçü girişi: 3 noktalı yay (kiriş, yarıçap, 180° / 270°), merkezli yay (merkez → başlangıç → bitiş, zincirden, 200°), teğet yay (R + açı, yalnız R), doğru, daire, dikdörtgen, CV, spline, kalem; yeni eğrinin gizli koleksiyon / yerel görünüm bağlanması |
| t61 | (F–H: v0.25.2 çok yüzeyli bıçak: üç kareyi tek çizgiyle kesme, boşluktan geçen çizgi, gizli kenarlar) Yüzeyi Böl: iki kare yüzeyde halka döngü kesimi (nokta ekleme, referans / kısıt / fillet eşleme, 4 parça), bıçak (köşe → kenar ortası, aynı kenar reddi), yarım silindirde kesimin yüzeyde kalması, ilişkili spline reddi (değişiklik yok), modal araç (hover, tekerlek, oran, tık, bıçak, Esc) |
| t65 | (G–J: v0.25.10 düzlem kilidi: eksen kilidini kapatma, düzlem dışı yakalamanın izdüşümü, sürüklemede Shift+X, kenardan bakış)  Eksen kilidi: X / Y (dünya ekseni), yakalama eksene izdüşer (kilit bozulmaz), sonraki noktada sürer, tekrar basınca kapanır, üstten Z ile dikey, otomatik AXIS, Shift+X düzlem, sürüklemede yakalama izdüşümü |
| t64 | Taslakta Teğet / Pürüzsüz: doğru + 3 noktalı yay (doğru aynı, yay uçları yerinde, gerçek yay, kırılma 15.8° → 0), sürükleme sonrası, G2 doğru–yay açıklaması, doğru + spline (yalnız tutamaç), yay + spline G2 (eğrilik eşit), daireye teğet doğru, Bitir |
| t63 | Hesaplanamayan yüzey / işlem uyarı satırları (gizli gövde, kapalı / başarılı işlem yok, kısaltma, en fazla 5 satır) |
| tools/occ_fold_check.py | GERÇEK OCC ile katlanma denetimi (zıt yarılar, kelebek; doğru yüzeyde yanlış alarm yok) |
| tools/occ_param_check.py | GERÇEK OCC ile karşılıklı kenar eşleşmesi: iki uçta farklı parçalanmış profil (2/3, 1/2, 3/3, 4/2 segment, dengesiz tutamak) doğru yüzeyi verir, katlanmaz; sınır yüzeyi (Hermite) yolu dahil |
| tools/occ_shell_bool_check.py | GERÇEK OCC ile açık kabukta Kesim / Kesişim / Birleşim reddi / değmeyen araç |
| tools/occ_coons_check.py | GERÇEK OCC ile Coons sınır yüzeyi: iki kemer + iki düz kenar düz çizgili (regle) olmalı (Keskin / Teğet / serbest) |
| tools/occ_split_check.py | GERÇEK OCC ile bölünen eğri yüzeyin biçimi ve yeni dikişteki teğetlik |
| t66 | Kenar Seç düzenleme modunda bekler (tık / Enter / F / B / Esc Blender'a), Tab tel kafesi düzenlemeye alır, gövde mesh'i düzenleme modundayken sonuç yazılmaz ve çıkınca yeniden hesaplanır |
| t68 | Eğriye bağlanan çizgi: X kilidiyle iki kare arası (Yakın başlangıç, eksen ∩ eğri, köşe yakınında kilit, nokta ekleme, kısıtlar, biçim), XY kilidinde dik kare (düzlem ∩ eğri), kilitsiz çok parçalı, taslaktaki kareye, taşınmış uç, daire hedef (bezier üstünde, biçim), surfmath kesişimleri |
| t67 | Çizimi Düzenle → Çizimi Kapat geri yazma, 4 kez düzenle / kapat / Bitir döngüsü (referanslar, konumlar), gövde dondurma (depsgraph / kuyruk / rebuild, yüzey referansı, çözülünce yeniden hesap, değişiklik yoksa hesap yok), save_pre, load_pre |
| t60 | Teğet ağırlığı (gövde / yüzey, imza, motora iletim, eski dosya) ve Teğet – serbest dolgu |

**Test yazma kalıbı:**
- t41–t43, `exec(open("t.py")...)` ile stub'ları yükler. Üstten ortografik görünüm
  simüle edilir; px = p × 50 + 500.
- `draw = importlib.import_module("mini_cad.draw")` ile içe aktarılır.
- Olaylar `SimpleNamespace` ile üretilir.

**Paketleme** (sürümü manifestte artır):
```bash
cd /home/claude/mini_cad && sed -i 's/^version = ".*"/version = "0.15.X"/' blender_manifest.toml
find . -name __pycache__ -prune -exec rm -rf {} +
cd /home/claude && rm -f mini_cad_v0.15.X.zip && (cd mini_cad && zip -qr ../mini_cad_v0.15.X.zip .)
```
Zip'in kökünde doğrudan `blender_manifest.toml` olmalı (klasör sarmalayıcı yok). Kullanıcı
Blender'da Preferences → Get Extensions → Install from Disk ile kurar.

**Düzenleme ipucu:** büyük değişikliklerde Python düzenleme betiğini `/tmp/editNN.py` olarak
kaydedip çalıştır. Çapa bulunamazsa betik hata versin; sessizce geçmesin.

---

## 9. Korunması gereken davranışlar (regresyon listesi)

- Yeni çizgi her zaman **yeni spline** olarak eklenir; mevcut spline sırası değişmez.
- Kenar seçim modu açıkken G/R/S, Tab, panel ve geri alma çalışmaya devam eder.
- Canlı güncellemede tek iş kuralı geçerlidir. Sürükleme sırasında hayalet fillet, bırakınca
  final hesap yapılır.
- Belirsiz gövde kenarı eşleşmesi **reddedilir**, tahmin edilmez.
- Teğet arcslide: yay geometrisi korunur, doğru uyum sağlar.
- Teğet yay ilk tıklamadan çalışır; taslaktaki çizginin ucundan başlayınca da teğettir.
- Geçici zemin: G ile girilir, G ile asıl düzleme dönülür (v0.25.6'ya kadar U). Seçilirken Esc aracı kapatmaz.
- Geçici zeminde her nokta zeminde kalır: eski çizimin noktalarına yapışılır ama izdüşürülür.
- Düzlem / zemin seçilirken taslak görünür kalır.
- Yüzey birleşimi varsayılanı Keskin'dir. v0.24'ten beri Keskin'de eğri 4 kenarlı yamalar
  (önce hatayla Dolgu'ya düşen) Coons olur; geçerli Coons'lar ve diğer yamalar aynı kalır.
- Teğet (G1) eski dolgu davranışı "Teğet – serbest dolgu" seçeneğinde korunur (v0.24).
- Değiştir araçları kaydedilmiş eğrilere dokunmaz; yalnızca taslağı değiştirir.
- Kısıt / ölçü araçları taslağı Bitir'lemez (v0.22).
- Bütün çizim araçlarında (yaylar dahil) her adımda ölçü yazılabilir (v0.25.3).
- Yüzeyi Böl: kenara eklenen nokta biçimi değiştirmez; bölünemeyecek kesimde hiçbir şey
  değişmez (önce doğrulama). Bölünen segmentteki ölçü kısıtları devre dışı kalır (v0.25).
- Çizimi Düzenle: Bitir'de spline'lar aynı göreli sırayla geri yazılır, bağlı yüzey / kısıt
  referansları korunur; düzenleme sürerken Blender Ctrl+Z'si engellenir (v0.23).
- Tek döngülü yüzeyler eskisi gibi hesaplanır. Çoklu döngü desteği yalnızca eskiden hata
  veren durumu açar.
- Taslak sürüklerken ölçü kutusu görünür. Yazılan değer kilitler, X/Y/Z hâlâ eksen kilididir.
- Kısıt simgesine hover'da hiçbir şey açılmaz, menü yalnızca sağ tıkla açılır. Yakalama
  simgelere yapışmaz.
- Esc iki aşamalıdır: önce Seç / duraklat, sonra kapat.
- Q son iki araç arasında geçiş yapar.
- Düzlem seçimi iki aşamalıdır: yön, sonra yükseklik.
- Oto kısıt yalnızca sağlanıyorsa yazılır.
- Taslakta Ctrl+Z / Ctrl+Shift+Z aracın kendi geçmişini kullanır.
- Izgara yakalaması sürüklemede de geçerlidir, Ctrl ile kapanır.
- `pick` modu açılınca çizim aracı kapatılır (`draw.cleanup_all`); ikisi aynı anda çalışmaz.
- Eksen / düzlem kilidi hiçbir yakalamayla bozulmaz; kilitliyken eğri yakalaması kilitle
  kesişimdir (v0.25.12). "Orta" yakalaması hedef eğriyi bölmez.
- Çizim aracı hangi yoldan kapanırsa kapansın (Çizimi Kapat, Esc, palet, başka mod) taslak
  önce kaydedilir; taslağa alınmış çizim asla kaybolmaz (v0.25.11). Yalnız dosya yüklenirken
  yazılmaz.
- Motor süreci açılamazsa Blender içinde hesaplamaya düşülür, hata verip durmaz.

---

## 10. Bilinen sınırlar / açık konular

- Yüzeyi Böl sınırları (v0.25): döngü kesimi yalnızca 4 kenarlı yüzeylerde ilerler (3 kenarlı
  ya da çok kenarlıda halka durur; bıçak her yüzeyde çalışır). Delikli yüzey bölünmez. Kesim
  eğrisi gövde mesh'inden (sapma ayarı kadar doğrulukla) uydurulur; çok yüzeyli bıçak ekrandaki
  düz çizginin görünüş izdüşümüdür (yüzeyin akışını izlemez); aynalı gövdede yalnızca
  asıl yarı bölünür (ayna kopyası kendiliğinden gelir).
- GPU görselleri (palet, pivot, kılavuzlar, simgeler) yalnızca stub'larla test edildi.
  Görünüşe dair geri bildirim kullanıcıdan gelir.
- t6 / t14 bayat testler; istenirse güncellenebilir.
- `core.py` (1950) ve `geometry.py` (2792) hâlâ büyük; bölünmemesinin nedeni §4'te.
- Aşama 2 kısıtları çalışıyor. Simetrik / açı gibi kısıtların Inventor'daki tüm etkileşimleri
  henüz incelenmedi.

---

- **Inventor 2D çizim araçları yol haritası** (kullanıcı isteği; 3–4 aşama):
  1. **(0.16.0, yapıldı)** Değiştir: Kırp, Uzat, Böl, Ötele; 2D Köşe yuvarla / Pah.
  2. **(0.17.0, yapıldı)** Taşı, Kopyala, Döndür, Ölçekle, Esnet; Desen: dikdörtgen,
     dairesel, Ayna. Eksikler: Ayna için simetri kısıtı (çizgiye göre), desenin ilişkisel
     (düzenlenebilir) olması, Inventor'daki "Hassas giriş" penceresi (x / y yazma).
  3. **(0.18.0, yapıldı)** Dikdörtgen: 3 nokta, merkezden, 3 nokta merkezden; Çokgen;
     Kanal: merkezden merkeze, toplam boy, merkez noktalı, 3 noktalı yay; Elips; Teğet daire
     (3 doğru); Nokta; Geometri yansıt.
     Eksikler:
     - Metin (Text) yok.
     - Merkez noktalı yay kanal yok.
     - Yansıtılan geometri ilişkisel değil (kaynak değişince güncellenmez).
     - Teğet daire yalnızca iç teğeti üretir.
     - Noktalar Düzenle / Değiştir araçlarına girmez (taşınmaz).
  4. **(0.19.0, yapıldı)** Genel Ölçü aracı, Yatay / Dikey, Eş merkezli, Yarıçap / Çap,
     Pürüzsüz (G2), Simetrik (çizgiye göre), nokta-doğru ve doğru-doğru uzaklığı.
     Eksikler (v0.20.0'da kapandı: otomatik ölçü, referans ölçü, ölçü çizgileri, merkez
     mesafesi).
     - Yay kısıtları taslakta değil, kaydedilmiş eğrilerde çalışır (diğer kısıtlar gibi).
     - Otomatik ölçü konum ölçüsü (merkeze göre) eklemez, yalnızca boyutları ölçer.
  - Bitir'lenmiş eğriyi taslağa geri alma (Inventor "Edit Sketch"): v0.21.0'da tek spline
    (Taslağa al aracı), v0.23.0'da bütün çizim (Çizimi Düzenle, Outliner'dan).
  - Autodesk yardım sayfaları bu ortamın ağ ayarlarında kapalıydı. Davranışlar Inventor
    bilgisinden uygulandı.
- **Eksikler 2. parti:** v0.21.0'da yapıldı (metin, taslağa al, ayna simetrisi, ilişkisel
  desen ve yansıtma, yuvarlamada eşit yarıçap). Sınırlar:
  - Metin yalnızca Blender'ın varsayılan yazı tipiyle (seçim yok).
  - Yansıtma ilişkisi yalnızca tel kafes segmentlerinde; gövde kenarlarında kopya.
  - İlişkili kopyalar elle düzenlenince bir sonraki güncellemede kaynağa döner (Inventor gibi).
- 2D Köşe yuvarla / Pah: v0.20'den beri ayrı iki doğruda da çalışıyor (yay / spline'larda
  yalnızca birleşik köşe).

## 11. Sürüm geçmişi (kısa)

- **0.12:** gövde (boolean) kenarı seçimi + fillet, hayalet fillet, arka plan OCC süreci.
- **0.13:** çizim aracı (Aşama 1): yakalamalar, sezgisel kılavuzlar, dinamik ölçüler; kayıt
  aracı (Ctrl+Alt+R).
- **0.14:** kayan palet, yaylar, CV / fit spline, kalem; kısıtlar (Aşama 2) ve çözücü; düzlem
  seçimi; ızgara; Seç aracı; sağ tık simge menüsü; Blender eksen renkleri; kısayollar; Q;
  Inventor gibi teğet (arcslide); ızgara görünürlüğü.
- **0.15:** iki aşamalı düzlem, T izi, taslak + Bitir, nokta / tutamaç düzenleme (3. eksen),
  hedef seçimi (mevcut / yeni eğri).
- **0.15.1:** taslak geri al / yinele, pivot, tutamaçlarda tam yakalama + ızgara.
- **0.15.2:** yapısal bölme, davranış değişikliği yok:
  - `draw.py` → 7 modül, `constraints.py` → 4 modül;
  - DEVELOPMENT.md ve devkit (testler + koşucu + araçlar) eklendi.
- **0.15.3:**
  - Taslak noktası / tutamacı sürüklerken ölçü yardımcısı: uzunluk, açı, yazarak değer.
  - Teğet yay, taslaktaki çizginin ucundan başlayınca yeniden teğet çalışıyor; Bitir'de TEĞET
    kısıtı yazılıyor.
  - Geçici zemin (U / Shift+U): ızgara yönü, yükseklik ve kökeni; yükseklikte nokta, ana düzlem
    ve ızgara yakalamaları ile ölçü kutusu.
- **0.15.4:**
  - Geçici zeminde eski çizimin noktalarına yapışınca çizgi zeminde kalıyor (nokta zemine
    paralel izdüşürülür, hiza çizgisi gösterilir).
  - Zemin seçilirken taslak çizgileri kaybolmuyor. Yön seçerken noktalara yapışılıyor;
    noktaya tıklayınca o noktadan geçen zemin seçiliyor.
- **0.15.5:** yüzey birleşimi.
  - Yüzeyler panelinde "Yüzey Birleşimi" (Keskin / Teğet G1) ve yüzey başına "Birleşim".
  - Teğette eğri yüzeyler komşularına kaynaşır, kenar çizgisi kaybolur.
  - devkit'e gerçek OCC ölçüm aracı eklendi.
- **0.16.0:** Inventor 2D araçları, 1. aşama.
  - DEĞİŞTİR paleti: Kırp (B, sürükleme, Shift: Uzat), Uzat, Böl, Ötele, Köşe yuvarla, Pah.
  - Yeni modüller `sketchmath.py` ve `draw_modify.py`; testler t47, t48.
- **0.17.0:** Inventor 2D araçları, 2. aşama.
  - DÜZENLE · DESEN paleti: Taşı, Kopyala, Döndür, Ölçekle, Esnet, Dikdörtgen desen,
    Dairesel desen, Ayna.
  - Ortak seçim: tık ve pencere / kesişen kutu. Nokta girişinde çizimin bütün yakalamaları
    geçerli.
  - Yeni modül `draw_xform.py`; testler t49, t50.
- **0.18.0:** Inventor 2D araçları, 3. aşama.
  - Dikdörtgen çeşitleri (R döngüsü), Çokgen, dört kanal türü, Elips, Teğet daire (O döngüsü),
    Nokta, Geometri yansıt.
  - Yeni modüller `shapemath.py` ve `draw_shapes.py`; testler t51, t52.
- **0.19.0:** Inventor 2D araçları, 4. aşama (yol haritası tamam).
  - Ölçü aracı (uzunluk / açı / yarıçap / çap / mesafe / uzaklık; değer düzenleme).
  - Yatay, Dikey, Eş merkezli, Yarıçap, Pürüzsüz (G2), Simetrik (çizgi), Nokta-doğru,
    Doğru-doğru.
  - Yeni modüller `constraints_arcs.py` ve `draw_dims.py`; testler t53, t54.
- **0.20.0:** eksikler 1. parti.
  - Ölçüler: referans ölçü (çelişen ölçü otomatik referans olur), merkez mesafesi,
    otomatik ölçü, ölçü çizgileri.
  - Kısıtlar: yaylarda eşit yarıçap; çözümde kayan yay düğümleri düzeltildi.
  - Çizim: ayrı iki doğruda köşe yuvarla / pah, X / Y hassas giriş (Shift+Tab), merkez
    noktalı yay kanal, teğet dairede çözüm seçimi, düzenle araçlarında noktalar.
  - Test t55.
- **0.21.0:** eksikler 2. parti.
  - Araçlar: Metin, Taslağa al (Edit Sketch).
  - Ayna simetri kısıtları; köşe yuvarlamada eşit yarıçap.
  - İlişkisel dikdörtgen / dairesel desen ve yansıtma (panelden düzenlenir, kaynağı izler).
  - Spline sırası yeniden eşleme altyapısı.
  - Yeni modüller `links.py` ve `draw_text.py`; test t56.
- **0.22.0:**
  - Kısıt / ölçü araçları taslağı kaydetmeden taslak çizgilerine uygulanır.
  - Delikli yüzey: B harfi gibi dış sınır + delikler; F iç içe çizgileri birlikte alır.
  - Izgara: spot ışığı gibi yumuşak geçişli daire (yumuşaklık ve yarıçap ayarlanır).
  - Yeni modül `draw_skcons.py`; testler t57, t58; araç `occ_holes_check.py`.
- **0.23.0:** Çizimi Düzenle (Inventor "Edit Sketch", bütün çizim).
  - Outliner / 3D sağ tık menüsü ve Gövde panelinden kaydedilmiş çizim yeniden taslağa alınır;
    Taslağa al aracında Shift+tık.
  - Düzlem çizimden alınır; yeni çizgiler aynı çizime yazılır; Ctrl+Z koruması.
  - Test t59.
- **0.23.1:**
  - Taslağa alınan çizimde Kırp / Uzat / Böl düzeldi (eski spline'lar sınır sayılıyordu).
  - Yüzey birleşimi Teğet: komşusu da kaynaşan yamalarda motor çöküyordu (segfault) ve
    teğetlik kurma sırasına bağlıydı; artık ortak teğet şeridi (kırılma ≤ 0.65°).
  - Araç `occ_blend_ring_check.py`.
- **0.24.0:** sınır yüzeyi ve teğet ağırlığı.
  - Teğet (G1): 3 / 4 kenarlı yamalar Hermite-Coons sınır yüzeyi (balon etkisi yok, G1
    yapı gereği); "Teğet Ağırlığı" (gövde ve yüzey başına) ile dolgunluk ayarı.
  - "Teğet – serbest dolgu" seçeneği (eski davranış).
  - Coons düzeltmesi: ters yönlü yüzeyde kırpma hatası (Keskin'de de etkili).
  - Test t60; araçlar genişletildi.
- **0.25.7:** katlanan yüzey uyarısı (panel + 3D görünüm); kayıt raporunda yüzey sınırları.
- **0.25.8:** karşılıklı kenarlar yay uzunluğuna göre eşleşir (iki uçta farklı parçalanmış profilde çapraz kırışık / katlanma düzeltmesi); sınır yüzeyi uydurma denetimi.
- **0.25.9:** Kenar Seç düzenleme modunda bekler (tutamaç çoklu / kutu seçimi), Tab ile tel kafesi düzenleme, gövde düzenleme modundayken kaybolan güncelleme.
- **0.25.10:** Shift+X/Y/Z düzlem kilidi: kenardan bakışta çalışır, eksen kilidini kapatır, yakalama düzleme izdüşer; taslak sürüklemede de düzlem kilidi.
- **0.25.6:** X / Y / Z Blender gibi eksen kilidi (dünya ekseni, yakalama bozmaz, tekrar
  basana kadar); düzlem Shift+X/Y/Z; geçici zemin U → G. Test t65.
- **0.25.5:** taslakta Teğet / Pürüzsüz anında ve biçimi bozmadan (yay yeniden kurulur, doğru
  korunur, eğride yalnız tutamaç). Test t64.
- **0.25.4:** açık kabuk (yüzey) gövdede boolean: Kesim / Kesişim yüzeyi budar; başarısız
  yüzey / işlemler 3D görünümde kırmızı uyarı olarak görünür. Test t63.
- **0.25.3:** yay araçlarında ölçü girişi (3 noktalı, merkezli, teğet; her adım); yeni eğri
  gizli koleksiyon / yerel görünümde de görünür; kayıt raporuna koleksiyon bilgisi. Test t62.
- **0.25.2:** Bıçak birden çok yüzeyi tek çizgiyle keser (görünüş izdüşümü, gizli kenarlar
  sayılmaz).
- **0.25.1:** Coons yüzeyi gerçek (doğrusal) Coons: OCC'nin "CoonsStyle"ı kübik harmanlamayla
  S biçimli yüzey veriyordu; StretchStyle'a geçildi. Araç `occ_coons_check.py`.
- **0.25.0:** Yüzeyi Böl.
  - Döngü kesimi (Ctrl+R gibi halka, adet / oran) ve bıçak (iki sınır noktası, yüzey ya da
    görünüş izdüşümü); kesim gerçek yüzeye izdüşürülüp tel kafese eğri olarak yazılır.
  - Kenara biçim bozmadan nokta ekleme ve bütün referansların eşlenmesi (`core.remap_insert`).
  - Yeni modüller `split.py` ve `surfmath.py`; test t61; araç `occ_split_check.py`.
- **0.24.1:** köşe yaması tam koni (köşe uyumu düzeltmesi), eğri 3 kenarlı yama Coons,
  tekil köşede patlayan yüzey ve üçgenleyici donması düzeltildi, ızgara 33.
