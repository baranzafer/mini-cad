# Mini CAD — Geliştirme Notları (v0.20.0)

Bu dosya, projeyi **yeni bir sohbette** kaldığı yerden sürdürmek için yazıldı. Yeni sohbete
başlarken bu dosyayı oku. Kodun tamamını baştan okumak gerekmez; aşağıdaki modül haritası
hangi dosyaya bakılacağını söyler.

---

## 0. Yeni sohbette nasıl başlanır

1. İki dosyayı yükle: `mini_cad_v0.20.0.zip` (eklenti) ve `mini_cad_devkit_v0.20.0.zip`
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
4. Değişiklikten sonra testleri yeniden çalıştır. Gerekirse yeni test ekle (`t56.py` ...),
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
| `core.py` | 1620 | PropertyGroup'lar (Feature, GeoEdge, CRef, Constraint, ObjectProps), eğri okuma, gather / _apply / rebuild, canlı güncelleme |
| `solver.py` | 185 | numpy kısıt çözücü: ağırlıklı Gauss-Newton, en az hareket; `residual`, `evaluate`, `solve`, `measure` |
| `constraints.py` | 590 | Kısıt çözümünü çalıştırma (`solve_all`), ekleme / kontrol / silme, canlı tetikleme, operatörler, kayıt |
| `constraints_refs.py` | 100 | Kısıt veri erişimi: referans noktaları, dünya konumu, `all_constraints` |
| `constraints_tangent.py` | 355 | Teğet planlaması (§6) |
| `constraints_arcs.py` | 302 | Yay kısıtları: yay grubu, sanal merkez, yayı yeniden kurma, Pürüzsüz (G2) eğrilik eşleme |
| `draw_dims.py` | 363 | DimMixin: genel Ölçü aracı, ölçü değeri düzenleme, Yatay / Dikey, karışık referanslı seçim |
| `constraints_glyphs.py` | 268 | Kısıt simgesi çizimi, `glyph_at` |
| `draw.py` | 784 | **MINICAD_OT_draw** ana operatör: invoke, durum çubuğu, araç değiştirme, palet olayları, `modal` / `_modal_inner`, kayıt |
| `draw_common.py` | 481 | Sabitler / renkler, ölçü ayrıştırma, `_Refs` (yakalama referansları), GPU yardımcıları, `_move_node` / `_move_handle`, araç tabloları |
| `draw_plane.py` | 537 | PlaneMixin: düzlem seçimi (yön, sonra yükseklik), ızgara ve ızgara yakalama, düzleme bakış, geçici zemin (U) |
| `draw_snap.py` | 663 | SnapMixin: nokta yakalama, çıkarım kılavuzları, kilitler, önizleme, T ile iz |
| `draw_sketch.py` | 648 | SketchMixin: nokta koyma, `_commit`, Bitir (`_finish_sketch`), oto kısıt, yüzey, taslak geri al / yinele |
| `draw_edit.py` | 427 | EditMixin: taslak noktası / tutamaç sürükleme, pivot, sürüklerken yakalama, sürüklerken ölçü yardımcısı |
| `draw_glyphs.py` | 215 | ConstraintUIMixin: kısıt için kenar / nokta seçimi, simge sağ tık menüsü |
| `draw_render.py` | 277 | RenderMixin: 3D / 2D çizim işleyicileri, ölçü giriş kutusu |
| `sketchmath.py` | 1232 | bpy'siz taslak düzenleme matematiği: bezier bölme, varlıklar, kesişimler, Kırp / Uzat / Böl / Ötele / Köşe yuvarla / Pah |
| `draw_modify.py` | 627 | ModifyMixin: Değiştir araçlarının seçimi, önizlemesi, olayları ve çizimi |
| `draw_xform.py` | 621 | TransformMixin: Düzenle / Desen araçları (seçim, temel nokta, hedef, önizleme, ölçü kutusu) |
| `shapemath.py` | 337 | bpy'siz şekil matematiği: dikdörtgen çeşitleri, çokgen, kanallar, yay kanal, elips, 3 doğruya teğet daire, düzleme izdüşüm |
| `draw_shapes.py` | 480 | ShapeMixin: çok tıklamalı şekiller, Nokta, Teğet daire, Geometri yansıt |
| `drawmath.py` | 585 | bpy'siz çizim matematiği: düzlemler, doğru / yay / daire / dikdörtgen, B-spline→Bézier (Boehm), Catmull-Rom, kalem, kılavuz rafinesi |
| `snapmath.py` | 410 | FORGE snap_math (GPL başlıklı kopya) |
| `palette.py` | 607 | Kayan araç paleti (GPU): araç / düzlem / kısıt / taslak / hedef / seçenek düğmeleri, ikon çizgileri |
| `pick.py` | 579 | Kenar seçim modu (hover + tık), sarı gövde kenarları, B ile fillet |
| `ui.py` | 590 | Operatörler, tercihler (`background`), `add_feature` (BODY ref) |
| `panels.py` | 536 | N panelleri: Gövde, Seçim ve Tel Kafes, Kısıtlar, Yüzeyler, Simetri, Boolean, Fillet, İşlem Sırası, Ayarlar, Export |
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
RenderMixin, ModifyMixin, TransformMixin, ShapeMixin, DimMixin, bpy.types.Operator)`. Mixin'lerde **aynı adlı metot olmamalı** (v0.16'da
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
| t44 | Taslak çizgisinin ucundan teğet yay, sürüklerken ölçü yardımcısı, geçici zemin (U) |
| t45 | Geçici zeminde eski çizime yapışınca zeminde kalma, seçim sırasında taslak görünürlüğü, noktadan zemin |
| t46 | Yüzey birleşimi: gather → motor kurma sırası, gövde sırası, imza, eski dosya |
| t47 | Değiştir araçları modal: Kırp (sürükleme, Shift), Uzat, Böl, Ötele, Köşe yuvarla, Pah, ayrı uçları birleştirme, Bitir, çizim |
| t48 | sketchmath: kesişim, kırpma (daire dahil), uzatma, bölme, öteleme, yuvarlama, pah |
| t49 | Düzenle / Desen modal: seçim (tık, pencere / kesişen kutu), Taşı, Kopyala, Döndür (+kopya), Ölçekle, Esnet, desenler, Ayna, seçim koruma, Bitir, çizim |
| t50 | sketchmath dönüşümleri: yay korunumu, kopya grupları, desen açıları, esnetme |
| t51 | shapemath: dikdörtgenler, çokgen, kanallar, yay kanal, elips, teğet daire, yansıtma |
| t53 | Aşama 4 modal: Ölçü (uzunluk, açı, paralel uzaklık, nokta mesafesi, nokta-doğru, yarıçap, çap, değer düzenleme), Eş merkezli, Yatay / Dikey, Simetrik (çizgi), Pürüzsüz (G2) |
| t54 | solver: SYMLINE, PTLINE, LINEDIST, RADIUSN, EQDIST |
| t55 | Eksikler 1. parti: referans ölçü (kuru çözüm), merkez mesafesi, yaylarda eşit, otomatik ölçü, ölçü çizgileri ve çizimi, ayrı doğrularda köşe, X / Y hassas giriş, merkez noktalı yay kanal, düzenle araçlarında noktalar |
| t52 | Oluştur modal: R / O döngüleri, yazarak şekiller, çokgen D, kanallar, teğet daire, Nokta (yakalama, geri al, Bitir), Yansıt, Bitir |
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
- Değiştir araçları kaydedilmiş eğrilere dokunmaz; yalnızca taslağı değiştirir.
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
- `core.py` (1620) ve `geometry.py` (2123) hâlâ büyük; bölünmemesinin nedeni §4'te.
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
  - Ayrıca değerlendirilecek: Bitir'lenmiş eğriyi taslağa geri alma (Inventor "Edit
    Sketch"). Spline sırası / yüzey referansları nedeniyle dikkatli tasarım gerekir.
  - Autodesk yardım sayfaları bu ortamın ağ ayarlarında kapalıydı. Davranışlar Inventor
    bilgisinden uygulandı.
- **Eksikler 2. parti (sıradaki):**
  - Metin aracı (Text).
  - Kaydedilmiş eğriyi taslağa geri açma (Inventor "Edit Sketch"; spline sırası / yüzey ve
    kısıt referansları yeniden eşlenmeli).
  - Ayna için çizgiye göre simetri kısıtı.
  - İlişkisel (düzenlenebilir) desen.
  - İlişkisel yansıtma.
  - Fillet'te eşit yarıçap kısıtı (aynı oturumdaki yuvarlamalar).
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
