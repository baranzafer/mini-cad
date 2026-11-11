# Mini CAD — Geliştirme Notları (v0.15.5)

Bu dosya, projeyi **yeni bir sohbette** kaldığı yerden sürdürmek için yazıldı. Yeni sohbete
başlarken bu dosyayı oku. Kodun tamamını baştan okumak gerekmez; aşağıdaki modül haritası
hangi dosyaya bakılacağını söyler.

---

## 0. Yeni sohbette nasıl başlanır

1. İki dosyayı yükle: `mini_cad_v0.15.5.zip` (eklenti) ve `mini_cad_devkit_v0.15.5.zip`
   (testler + araçlar).
2. Açılış mesajında şunu söyle: "Mini CAD projesine devam ediyoruz, önce DEVELOPMENT.md'yi oku."
   Ardından isteklerini yaz. Mümkünse birkaç isteği tek mesajda topla.
3. Claude'un yapacağı kurulum:
   ```bash
   mkdir -p /home/claude/mini_cad && cd /home/claude/mini_cad && unzip -o <eklenti zip>
   mkdir -p /home/claude/devkit && cd /home/claude/devkit && unzip -o <devkit zip>
   bash /home/claude/devkit/run_tests.sh /home/claude/mini_cad      # başlangıç durumu
   ```
   Beklenen sonuç: `t6.py` ve `t14.py` dışındaki her test **geçti** (bu ikisi v0.12'den beri
   bayat; "(bilinen)" olarak işaretlenir). `SONUÇ: tamam` görünmeli.
4. Değişiklikten sonra testleri yeniden çalıştır. Gerekirse yeni test ekle (`t47.py` ...),
   sürümü artır ve paketle (§8).
5. Kod GitHub'da da tutuluyor: `baranzafer/mini-cad` deposunda eklenti `mini_cad/`, testler ve
   araçlar `devkit/` klasöründe. Her sürüm ayrı bir commit olarak eklenir. Kurulum zip'leri
   `dist/` klasörüne konur; kullanıcı onları GitHub'dan indirir (dal:
   `claude/nice-albattani-hfscvj`).

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

---

## 4. Modül haritası

| Dosya | Satır | Görev |
|---|---:|---|
| `__init__.py` | 32 | Kayıt sırası: recorder → kernel → core → constraints → ui → panels → pick → draw → wire → bool_overlay |
| `kernel.py` | 150 | OCP kurulumu / yükleme |
| `engine.py` | 382 | bpy'siz OCC motoru (komut işleyici, önbellekler) |
| `engine_host.py` | 52 | Alt süreç girişi; paketi sahte `minicad_engine` paketi olarak yükler |
| `jobs.py` | 337 | Süreç istemcisi (ensure / submit / call / control / poll / stop / describe) |
| `errors.py` | 2 | `CadError` |
| `geometry.py` | 2123 | OCC işlemleri: yüzey kurucu, assemble, fillet / chamfer, boolean, mesh→katı, tessellate, STEP, kenar poligonları, hayalet fillet |
| `core.py` | 1610 | PropertyGroup'lar (Feature, GeoEdge, CRef, Constraint, ObjectProps), eğri okuma, gather / _apply / rebuild, canlı güncelleme |
| `solver.py` | 155 | numpy kısıt çözücü: ağırlıklı Gauss-Newton, en az hareket; `residual`, `evaluate`, `solve`, `measure` |
| `constraints.py` | 402 | Kısıt çözümünü çalıştırma (`solve_all`), ekleme / kontrol / silme, canlı tetikleme, operatörler, kayıt |
| `constraints_refs.py` | 86 | Kısıt veri erişimi: referans noktaları, dünya konumu, `all_constraints` |
| `constraints_tangent.py` | 355 | Teğet planlaması (§6) |
| `constraints_glyphs.py` | 98 | Kısıt simgesi çizimi, `glyph_at` |
| `draw.py` | 714 | **MINICAD_OT_draw** ana operatör: invoke, durum çubuğu, araç değiştirme, palet olayları, `modal` / `_modal_inner`, kayıt |
| `draw_common.py` | 448 | Sabitler / renkler, ölçü ayrıştırma, `_Refs` (yakalama referansları), GPU yardımcıları, `_move_node` / `_move_handle`, araç tabloları |
| `draw_plane.py` | 537 | PlaneMixin: düzlem seçimi (yön, sonra yükseklik), ızgara ve ızgara yakalama, düzleme bakış, geçici zemin (U) |
| `draw_snap.py` | 634 | SnapMixin: nokta yakalama, çıkarım kılavuzları, kilitler, önizleme, T ile iz |
| `draw_sketch.py` | 611 | SketchMixin: nokta koyma, `_commit`, Bitir (`_finish_sketch`), oto kısıt, yüzey, taslak geri al / yinele |
| `draw_edit.py` | 426 | EditMixin: taslak noktası / tutamaç sürükleme, pivot, sürüklerken yakalama, sürüklerken ölçü yardımcısı |
| `draw_glyphs.py` | 197 | ConstraintUIMixin: kısıt için kenar / nokta seçimi, simge sağ tık menüsü |
| `draw_render.py` | 251 | RenderMixin: 3D / 2D çizim işleyicileri, ölçü giriş kutusu |
| `drawmath.py` | 585 | bpy'siz çizim matematiği: düzlemler, doğru / yay / daire / dikdörtgen, B-spline→Bézier (Boehm), Catmull-Rom, kalem, kılavuz rafinesi |
| `snapmath.py` | 410 | FORGE snap_math (GPL başlıklı kopya) |
| `palette.py` | 424 | Kayan araç paleti (GPU): araç / düzlem / kısıt / taslak / hedef / seçenek düğmeleri, ikon çizgileri |
| `pick.py` | 579 | Kenar seçim modu (hover + tık), sarı gövde kenarları, B ile fillet |
| `ui.py` | 590 | Operatörler, tercihler (`background`), `add_feature` (BODY ref) |
| `panels.py` | 532 | N panelleri: Gövde, Seçim ve Tel Kafes, Kısıtlar, Yüzeyler, Simetri, Boolean, Fillet, İşlem Sırası, Ayarlar, Export |
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
RenderMixin, bpy.types.Operator)`.

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
| Dikdörtgen | R |
| CV spline | S |
| Noktalardan geçen spline | K |
| Kalem | P |

Diğer kısayollar:
- **Araç geçişi:** Q son iki araç arasında geçiş yapar. Shift+Q düzlemi yeniden seçtirir.
- **Düzlem:** X / Y / Z / V.
- **Geçici zemin (U):** çizerken ızgaranın yönü ve yüksekliği değiştirilir (aşağıya bakın).
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

**Yakalama:**
- Yakalanan noktalar: tel kafes ve CAD gövde kenarlarının ucu / ortası, çember ve yay merkezleri,
  kesişimler, kenar üstünde en yakın nokta.
- Kılavuzlar (snapmath): yatay / dikey, paralel / dik, devam, uç / orta / merkez hizası, doğru
  uzantısı, teğet uzantı, yay çemberi boyunca devam.
- Hepsi **zayıf mıknatıs**; çizimi engellemez. Öncelik `PRIORITY` tablosuyla belirlenir.
- Izgara yakalaması da zayıftır. Görünürlüğü `minicad_grid_alpha` ile ayarlanır; yakalama yine
  çalışır.

**Teğet yay:** ilk tıklamadan çalışır (Inventor gibi). Bir çizginin ucundan başlayınca ona teğet
devam eder; boşlukta başlarsa 3 noktalı yay gibi davranır. `start_tan` iki kaynaktan alınır:
- Kaydedilmiş eğri ucu: `_end_tangent_of(snap_id)`.
- **Taslaktaki** (henüz Bitir'lenmemiş) açık çizginin ucu: `_sketch_end_tangent(nokta)`. Kimlik
  `("@sketch", çizgi, segment, uç)` biçimindedir. Bitir'de `_auto_tangent` bunu yazılan spline'a
  çevirir ve TEĞET kısıtını yazar. Taslakta birleşim ya da teğetlik bozulduysa kısıt yazılmaz.
- v0.15.0–0.15.2'de ikinci kaynak yoktu. Sağ tıkla taslağa eklenen çizginin ucundan başlayan
  teğet yay 3 noktalı yaya düşüyordu (v0.15.3'te düzeltildi).

**Geçici zemin (U)** (`draw_plane`: `_temp_begin`, `_temp_end`, `_temp_cancel`):
- Çizim fazında **U**: süren çizgi taslağa eklenir, iki aşamalı düzlem seçimi açılır.
  - 1/2 yön: eksen düzlemi, yüz ya da X/Y/Z/V. **Sağ tık / Enter: mevcut yön**, sadece
    yükseklik değişir. Esc: iptal, araç açık kalır.
  - 2/2 yükseklik: fare, nokta (taslak noktaları dahil), **ana düzlem** yüksekliği ya da ızgara
    yakalaması; değer de yazılabilir. Ölçü kutusunda yükseklik ve ana düzleme göre fark
    gösterilir. Yakalanan noktadan taban düzlemine hiza çizgisi çizilir.
- Onaylanınca `plane_mode = "LOCK"` olur ve `self.temp = {"saved", "plane", "label", "grid_o"}`
  tutulur. Yükseklik bir noktadan alındıysa ızgara kökeni (`_grid_origin`) o noktaya taşınır.
- Tekrar **U**'ya basılana kadar bütün yeni çizgiler bu zemine çizilir. U: asıl düzleme dönülür
  (`saved`). **Shift+U:** başka bir geçici zemin seçilir, asıl düzlem korunur.
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
    SYMMETRIC, TANGENT. Çözücünün içinde ayrıca TLINE var.
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
| t44 | Taslak çizgisinin ucundan teğet yay, sürüklerken ölçü yardımcısı, geçici zemin (U) |
| t45 | Geçici zeminde eski çizime yapışınca zeminde kalma, seçim sırasında taslak görünürlüğü, noktadan zemin |
| t46 | Yüzey birleşimi: gather → motor kurma sırası, gövde sırası, imza, eski dosya |
| tools/occ_blend_check.py | GERÇEK OCC ile teğet birleşim ölçümü (test koşucusunda değil, OCP gerekir) |

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
- Geçici zemin: U ile girilir, U ile asıl düzleme dönülür. Seçilirken Esc aracı kapatmaz.
- Geçici zeminde her nokta zeminde kalır: eski çizimin noktalarına yapışılır ama izdüşürülür.
- Düzlem / zemin seçilirken taslak görünür kalır.
- Yüzey birleşimi varsayılanı Keskin'dir; mevcut modeller aynı hesaplanır.
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
- Motor süreci açılamazsa Blender içinde hesaplamaya düşülür, hata verip durmaz.

---

## 10. Bilinen sınırlar / açık konular

- GPU görselleri (palet, pivot, kılavuzlar, simgeler) yalnızca stub'larla test edildi.
  Görünüşe dair geri bildirim kullanıcıdan gelir.
- t6 / t14 bayat testler; istenirse güncellenebilir.
- `core.py` (1610) ve `geometry.py` (2123) hâlâ büyük; bölünmemesinin nedeni §4'te.
- Aşama 2 kısıtları çalışıyor. Simetrik / açı gibi kısıtların Inventor'daki tüm etkileşimleri
  henüz incelenmedi.

---

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
