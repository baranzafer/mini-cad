"""BlendCAD şerit (ribbon) içeriği: sekmeler, gruplar, düğmeler ve açıklama kartı metinleri.

bpy / gpu kullanmaz; yalnızca veri. Arayüz bu tabloyu okuyup çizer.

Düğme alanları:
  id      : benzersiz kimlik (ileride işlev bağlanırken kullanılır)
  icon    : simge adı (ribbon_icons.icon_lines)
  title   : kısa ad (kartın başlığı)
  desc    : bir cümlelik açıklama (kartın kısa hali)
  steps   : kullanım adımları (kart uzun süre üzerinde kalınca açılır)
  key     : kısayol (boş olabilir)
  status  : "ready"  = Mini CAD'de karşılığı var, arayüze bağlanacak
            "planned"= yeni özellik, sonraki sürümlerde
  variants: aynı düğmenin açılır listedeki türleri (Inventor'daki gibi; seçilen tür düğmede kalır)
  toggle  : True ise aç / kapa düğmesi (seçenek)
"""

READY = "ready"
PLANNED = "planned"


def B(id, icon, title, desc, steps=(), key="", status=READY, variants=(), toggle=False):
    return {"id": id, "icon": icon, "title": title, "desc": desc, "steps": list(steps),
            "key": key, "status": status, "variants": list(variants), "toggle": toggle}


def V(id, icon, title, desc, steps=(), key="", status=READY):
    return B(id, icon, title, desc, steps, key, status)


# ================================================================ ESKİZ

_SKETCH = [
    ("Eskiz", [
        B("SK_START", "SKETCH_NEW", "Eskiz başlat",
          "Bir düzlem ya da gövde yüzü seçip 2B çizime başlar.",
          ["Eksen düzlemine (XY / XZ / YZ) ya da bir gövde yüzüne tıkla",
           "Yüksekliği fareyle ya da değer yazarak ver",
           "Çizim araçlarıyla taslağı çiz"], key="Shift+Q"),
        B("SK_FINISH", "FINISH", "Eskizi bitir",
          "Taslağı eğri objesine kaydeder; bağlı yüzey ve gövdeler güncellenir.",
          ["Taslaktaki bütün çizgiler hedef eğriye yazılır",
           "Hedef: Mevcut eğri ya da Yeni eğri (eskiz ayarları)"], key="Ctrl+Enter"),
        B("SK_EDIT", "EDITSK", "Taslağa al",
          "Kaydedilmiş bir eğriyi yeniden taslakta düzenlemeye açar (Edit Sketch).",
          ["Kaydedilmiş eğriye tıkla", "Taslakta düzenle", "Bitir ile aynı objeye geri yazılır"]),
    ]),
    ("Oluştur", [
        B("LINE", "LINE", "Doğru", "Noktadan noktaya doğru parçaları çizer.",
          ["İlk noktaya tıkla", "Sonraki noktalara tıkla (uzunluk / açı yazılabilir, Tab)",
           "Sağ tık ya da Enter: çizgiyi bitir", "C: başlangıca dönüp kapat"], key="L"),
        B("ARC", "ARC3", "Yay", "Üç noktalı, teğet ya da merkezli yay çizer.",
          ["Türü açılır listeden seç", "Noktaları sırayla ver"], key="E",
          variants=[
              V("ARC3", "ARC3", "3 noktalı yay", "Başlangıç, bitiş ve eğrilik noktası.",
                ["Başlangıç noktası", "Bitiş noktası", "Eğriliği belirleyen nokta"], key="E"),
              V("TARC", "TARC", "Teğet yay", "Bir çizgi ucundan teğet devam eden yay.",
                ["Çizgi ucuna tıkla", "Yayın bitiş noktasını ver"], key="A"),
              V("CARC", "CARC", "Merkezli yay", "Merkez, başlangıç ve bitişle yay.",
                ["Merkez", "Başlangıç (yarıçap)", "Bitiş (D: yön değiştir)"], key="M"),
          ]),
        B("CIRCLE", "CIRCLE", "Daire", "Merkez ve yarıçapla daire; teğet daire ve elips de burada.",
          ["Merkeze tıkla", "Yarıçap için ikinci noktayı ver ya da çap yaz"], key="O",
          variants=[
              V("CIRCLE", "CIRCLE", "Daire", "Merkez ve yarıçap.",
                ["Merkez", "Yarıçap noktası ya da değer"], key="O"),
              V("CIRCT", "CIRCT", "Teğet daire", "Üç doğruya teğet daire.",
                ["Üç doğruya sırayla tıkla", "4. tık: çözümlerden birini yerleştir"], key="O ×2"),
              V("ELLIPSE", "ELLIPSE", "Elips", "Merkez, 1. eksen ucu ve 2. yarı eksen.",
                ["Merkez", "1. eksen ucu", "2. yarı eksen"], key="O ×3"),
          ]),
        B("RECT", "RECT", "Dikdörtgen", "İki köşeli, 3 noktalı ya da merkezden dikdörtgen.",
          ["Türü açılır listeden seç", "Köşeleri ver (genişlik / yükseklik yazılabilir)"], key="R",
          variants=[
              V("RECT", "RECT", "İki köşe", "Karşılıklı iki köşe.", ["1. köşe", "2. köşe"], key="R"),
              V("RECT3", "RECT3", "3 nokta", "Bir kenar ve genişlik.",
                ["Kenarın başı", "Kenarın sonu", "Genişlik"], key="R ×2"),
              V("RECTC", "RECTC", "Merkezden", "Merkez ve bir köşe.", ["Merkez", "Köşe"],
                key="R ×3"),
              V("RECT3C", "RECT3C", "3 nokta merkezden", "Merkez, kenar ortası ve köşe.",
                ["Merkez", "Kenar ortası", "Köşe"], key="R ×4"),
          ]),
        B("POLYGON", "POLYGON", "Çokgen", "Düzgün çokgen; kenar sayısı yazılabilir.",
          ["Merkeze tıkla", "Köşeyi ver", "Tab: kenar sayısı · D: iç / dış teğet"]),
        B("SLOT", "SLOTCC", "Kanal", "Düz ve yay kanallar (slot).",
          ["Türü açılır listeden seç", "Merkezleri / uçları ver", "Son tık: genişlik"],
          variants=[
              V("SLOTCC", "SLOTCC", "Merkezden merkeze", "İki yay merkezi ve genişlik."),
              V("SLOTO", "SLOTO", "Toplam boy", "İki uç ve genişlik."),
              V("SLOTC", "SLOTC", "Merkez noktalı", "Merkez, yay merkezi ve genişlik."),
              V("ARCSLOT", "ARCSLOT", "Yay kanal: 3 nokta", "Başlangıç, bitiş, yay noktası."),
              V("SLOTARCC", "SLOTARCC", "Yay kanal: merkezli", "Merkez, başlangıç, bitiş (D: yön)."),
          ]),
        B("SPLINE", "CV", "Spline", "Kontrol noktalı ya da noktalardan geçen eğri; kalem.",
          ["Türü açılır listeden seç", "Noktalara tıkla", "Enter: bitir"], key="S",
          variants=[
              V("CV", "CV", "Kontrol noktalı (CV)", "Noktalar eğriyi çeker.", key="S"),
              V("FIT", "FIT", "Noktalardan geçen", "Eğri her noktadan geçer.", key="K"),
              V("PEN", "PEN", "Kalem", "Tıkla-sürükle ile bezier tutamacı.", key="P"),
          ]),
        B("POINT", "POINT", "Nokta", "Yakalanabilen yardımcı nokta koyar.",
          ["Tıklanan yere nokta konur", "Bitir'de eğriye kaydedilir"]),
        B("TEXT", "TEXT", "Metin", "Yazıyı harf çizgilerine çevirip taslağa ekler.",
          ["Sol alt köşeye tıkla", "Yaz (Tab: yükseklik)", "Enter: ekle · Esc: vazgeç"]),
        B("PROJECT", "PROJECT", "Geometri yansıt",
          "Gövde kenarını ya da tel kafes eğrisini çizim düzlemine izdüşürür.",
          ["Kenara ya da eğriye tıkla", "Sonuç taslağa normal çizgi olarak eklenir"]),
    ]),
    ("Değiştir", [
        B("TRIM", "TRIM", "Kırp", "Parçayı en yakın kesişimler arasında siler.",
          ["Silinecek parçaya tıkla", "Sürükle: çoklu kırpma", "Shift: Uzat'a geç"], key="B"),
        B("EXTEND", "EXTEND", "Uzat", "Çizgi ucunu en yakın sınıra kadar uzatır.",
          ["Uca yakın yerden çizgiye tıkla", "Shift: Kırp'a geç"]),
        B("SPLIT", "SPLIT", "Böl", "Nesneyi kesişim noktasında ikiye ayırır.",
          ["Bölünecek nesneye kesişime yakın tıkla"]),
        B("OFFSET", "OFFSET", "Ötele", "Çizgiyi verilen mesafede paralel kopyalar.",
          ["Çizgiye tıkla (Shift+tık: tek nesne)", "Mesafeyi fareyle ya da yazarak ver"]),
        B("CORNER", "FILLET2D", "Köşe yuvarla", "Köşeyi yay ile yuvarlar; pah da burada.",
          ["Yarıçap yaz", "Köşeye tıkla"],
          variants=[
              V("FILLET2D", "FILLET2D", "Köşe yuvarla", "Yarıçap yaz, köşeye tıkla."),
              V("CHAMFER2D", "CHAMFER2D", "Pah", "Mesafe yaz (Tab: 2. mesafe), köşeye tıkla."),
          ]),
    ]),
    ("Düzenle", [
        B("MOVE", "MOVE", "Taşı", "Seçilen çizgileri temel noktadan hedefe taşır.",
          ["Çizgileri seç", "Temel nokta", "Hedef (uzunluk / açı yazılabilir)"]),
        B("COPY", "COPY", "Kopyala", "Seçilen çizgilerin kopyasını yerleştirir.",
          ["Çizgileri seç", "Temel nokta", "Hedef"]),
        B("ROTATE", "ROTATE", "Döndür", "Seçilen çizgileri bir merkez etrafında döndürür.",
          ["Çizgileri seç", "Merkez", "Açı (Shift: 15° · C: kopya)"]),
        B("SCALE", "SCALE", "Ölçekle", "Seçilen çizgileri temel noktaya göre ölçekler.",
          ["Çizgileri seç", "Temel nokta", "Ölçek (C: kopya)"]),
        B("STRETCH", "STRETCH", "Esnet", "Kutuyla seçilen noktaları taşıyarak şekli esnetir.",
          ["Noktaları kutuyla seç", "Temel nokta", "Hedef"]),
    ]),
    ("Desen", [
        B("RPAT", "RPAT", "Dikdörtgen desen", "Seçimi iki yönde satır / sütun olarak çoğaltır.",
          ["Seç", "Başlangıç", "1. yön (adet, aralık)", "2. yön"]),
        B("CPAT", "CPAT", "Dairesel desen", "Seçimi bir merkez etrafında çoğaltır.",
          ["Seç", "Merkez", "Adet ve açı"]),
        B("MIRROR2D", "MIRROR", "Ayna", "Seçimin bir çizgiye göre aynalı kopyasını ekler.",
          ["Seç", "Ayna çizgisinin iki noktası"]),
    ]),
]

# ================================================================ KISIT

_CONSTRAIN = [
    ("Ölçü", [
        B("DIM", "DIM", "Ölçü",
          "Seçime göre uzunluk, yarıçap, çap, açı ya da mesafe ölçüsü ekler.",
          ["Doğru → uzunluk · yay → yarıçap · daire → çap",
           "2 doğru → açı · 2 nokta → mesafe",
           "Ölçüye tıkla: değeri düzenle"], key="D"),
        B("AUTODIM", "AUTODIM", "Otomatik ölçü",
          "Ölçüsüz doğrulara uzunluk, yaylara yarıçap ölçüsü verir.",
          ["Eğriye tıkla"]),
    ]),
    ("Geometrik", [
        B("HORIZ", "HORIZ", "Yatay", "Kenarı çizim düzleminin yatay eksenine hizalar.",
          ["1 kenar seç"]),
        B("VERT", "VERT", "Dikey", "Kenarı çizim düzleminin dikey eksenine hizalar.",
          ["1 kenar seç"]),
        B("PARALLEL", "PARALLEL", "Paralel", "İki kenarı paralel yapar.", ["2 kenar seç"]),
        B("PERP", "PERP", "Dik", "İki kenarı birbirine dik yapar.", ["2 kenar seç"]),
        B("COLLINEAR", "COLLINEAR", "Doğrusal", "İki kenarı aynı doğru üzerine alır.",
          ["2 kenar seç"]),
        B("EQUAL", "EQUAL", "Eşit", "İki kenarın boyunu ya da iki yayın yarıçapını eşitler.",
          ["2 kenar / yay seç"]),
        B("COINCIDENT", "COINCIDENT", "Çakışık", "İki noktayı üst üste getirir.",
          ["2 nokta seç"]),
        B("FIX", "FIX", "Sabitle", "Noktayı yerinde kilitler.", ["1 nokta seç"]),
        B("TANGENT", "TANGENT", "Teğet", "Aynı noktada birleşen iki kenarı teğet yapar.",
          ["2 kenar seç"]),
        B("SMOOTH", "SMOOTH", "Pürüzsüz (G2)", "Spline ile komşusunu teğet ve eş eğrilikli yapar.",
          ["Spline ve komşu kenarı seç"]),
        B("CONCENTRIC", "CONCENTRIC", "Eş merkezli", "İki yay / dairenin merkezini birleştirir.",
          ["2 yay / daire seç"]),
        B("SYM", "SYMMETRIC", "Simetrik", "İki noktayı bir çizgiye ya da eksen düzlemine göre "
          "simetrik yapar.", ["2 nokta seç", "Simetri çizgisini seç"],
          variants=[
              V("SYMLINE", "SYMMETRIC", "Çizgiye göre", "2 nokta + simetri doğrusu."),
              V("SYMMETRIC", "SYMMETRIC", "Eksen düzlemine göre", "2 nokta, dünya eksen düzlemi."),
          ]),
    ]),
    ("Görünüm", [
        B("CONS_SHOW", "SHOW", "Kısıtları göster", "Kısıt simgelerini görünümde açar / kapatır.",
          ["Simgeye sağ tık: dondur / sil"], toggle=True),
        B("CONS_AUTO", "AUTOCONS", "Oto kısıt",
          "Çizerken yakalanan yatay / dikey, paralel, dik ve çakışmaları kısıt olarak kaydeder.",
          toggle=True),
        B("LINKS", "LINKS", "İlişkiler",
          "Desen ve yansıtma ilişkilerini (adet / aralık / açı) listeler ve düzenler."),
    ]),
]

# ================================================================ TEL KAFES · YÜZEY

_SURFACE = [
    ("Tel kafes", [
        B("WIRE_MESH", "WIRE_MESH", "Mesh'ten tel kafes",
          "Seçili mesh kenarlarından bezier tel kafes eğrileri üretir.",
          ["Mesh objesinde kenarları seç", "Düğmeye bas: eğriler oluşur"]),
        B("EDGE_PICK", "EDGE_PICK", "Kenar seçimi",
          "Gövde kenarlarını üzerine gelip tıklayarak seçer (sarı vurgulu).",
          ["Kenarın üzerine gel", "Tık: seç · Shift: ekle", "B: seçili kenarlara fillet"]),
        B("SKETCH3D", "SKETCH3D", "3B eskiz",
          "Uzayda doğru / spline çizer; yüzey ve kenarlara bağlanır.",
          ["Nokta, kenar ya da yüzey üzerinden başla", "Eksen kilitleriyle uzayda ilerle"],
          status=PLANNED),
    ]),
    ("Yüzey", [
        B("PATCH", "PATCH", "Sınır yüzeyi",
          "Kapalı tel kafes döngüsünden yüzey yaması kurar (ortak kenarlarla).",
          ["Döngüyü oluşturan eğrileri seç", "F: yüzey · Ctrl+F: yeni gövde"], key="F"),
        B("PATCH_HOLE", "PATCH_HOLE", "Delikli yüzey",
          "İç içe kapalı döngülerden delikli düzlemsel yüz kurar (B harfi gibi).",
          ["Dış döngü ve delik döngülerini aynı düzlemde çiz", "F ile birlikte gönder"]),
        B("BLEND", "BLEND", "Yüzey birleşimi",
          "Komşu yüzeylerin ortak kenarda keskin (G0) ya da teğet (G1) buluşmasını seçer.",
          ["Yüzeyi seç", "Keskin / Teğet seç"],
          variants=[
              V("BLEND_G0", "BLEND_G0", "Keskin (G0)", "Yüzler yalnızca kenarda buluşur."),
              V("BLEND_G1", "BLEND", "Teğet (G1)", "Komşu yüze teğet kaynaşır."),
          ]),
        B("SPLIT_FACE", "SPLIT_FACE", "Yüzeyi böl",
          "Yüzeyi bir tel kafes eğrisi boyunca ikiye ayırır.",
          ["Yüzeyi seç", "Bölecek eğriye tıkla"]),
        B("LOFT_SURF", "LOFT", "Loft yüzeyi",
          "Sırayla seçilen kesit eğrilerinden geçen yüzey kurar.",
          ["Kesitleri sırayla seç", "İsteğe bağlı kılavuz eğriler ekle"], status=PLANNED),
        B("RULED", "RULED", "Çizgisel yüzey",
          "Bir kenardan dik / teğet doğrultuda şerit yüzey uzatır.",
          ["Kenarı seç", "Doğrultu ve mesafe ver"], status=PLANNED),
        B("STITCH", "STITCH", "Dikiş (Stitch)",
          "Ayrı yüzeyleri ortak kenarlarından dikip kapalıysa katıya çevirir.",
          ["Yüzeyleri seç", "Tolerans ver"], status=PLANNED),
        B("THICKEN", "THICKEN", "Kalınlaştır",
          "Yüzeye kalınlık vererek katı kabuk üretir.",
          ["Yüzeyi seç", "Kalınlık ve yön ver"], status=PLANNED),
    ]),
    ("Simetri", [
        B("SYM_BODY", "MIRROR_BODY", "Ayna simetrisi",
          "Gövdeyi bir eksen düzlemine göre aynalayıp ortadan birleştirir.",
          ["Simetri eksenini seç (X / Y / Z)", "Dikiş kenarı ortak olur"], toggle=True),
    ]),
]

# ================================================================ KATI

_SOLID = [
    ("Gövde", [
        B("BODY_NEW", "BODY", "Yeni gövde",
          "Seçili yüzeylerden yeni bir CAD gövdesi oluşturur.",
          ["Yüzeyleri seç", "Ctrl+Enter: yeni gövde"], key="Ctrl+Enter"),
        B("REBUILD", "REBUILD", "Yenile",
          "Gövdeyi yeniden hesaplar (canlı güncelleme zaten açıktır)."),
    ]),
    ("Oluştur", [
        B("EXTRUDE", "EXTRUDE", "Ekstrüzyon",
          "Kapalı eskiz profilini bir doğrultuda uzatarak katı / yüzey üretir.",
          ["Profili seç", "Mesafe ya da 'sonraki yüze kadar'", "Birleştir / Kes / Kesişim"],
          status=PLANNED),
        B("REVOLVE", "REVOLVE", "Döndürme",
          "Profili bir eksen etrafında döndürerek katı üretir.",
          ["Profili seç", "Ekseni seç", "Açı ver (varsayılan 360°)"], status=PLANNED),
        B("SWEEP", "SWEEP", "Profil süpürme",
          "Kapalı profili bir yol eğrisi boyunca süpürür.",
          ["Profil eğrisini seç", "Yol eğrisini seç", "Yön: sabit / yola dik"]),
        B("LOFT", "LOFT", "Loft",
          "Birden çok kesit arasında katı geçiş üretir.",
          ["Kesitleri sırayla seç", "Kılavuz ya da merkez çizgisi ekle"], status=PLANNED),
    ]),
    ("Boolean", [
        B("BOOL", "BOOL_DIFF", "Boolean",
          "Bir gövdeyi diğeriyle birleştirir, çıkarır ya da kesişimini alır.",
          ["Hedef gövdeyi seç", "Araç gövdeyi seç", "İşlem türünü seç"],
          variants=[
              V("BOOL_UNION", "BOOL_UNION", "Birleştir", "İki gövde tek gövde olur."),
              V("BOOL_DIFF", "BOOL_DIFF", "Çıkar", "Araç gövde hedeften oyulur."),
              V("BOOL_INT", "BOOL_INT", "Kesişim", "Yalnızca ortak hacim kalır."),
          ]),
    ]),
    ("Kenar", [
        B("FILLET", "FILLET3D", "Fillet",
          "Seçili gövde kenarlarını verilen yarıçapla yuvarlar.",
          ["Kenar seçimi modunda kenarları seç", "Yarıçap ver", "B: uygula"], key="B"),
        B("CHAMFER", "CHAMFER3D", "Pah",
          "Seçili gövde kenarlarına pah kırar.",
          ["Kenarları seç", "Mesafe ver"]),
        B("SHELL", "SHELL", "Kabuk",
          "Katının içini boşaltır; seçilen yüzleri açık bırakır.",
          ["Açık kalacak yüzleri seç", "Et kalınlığı ver"], status=PLANNED),
    ]),
    ("Desen", [
        B("PAT3D", "PAT3D_R", "Özellik deseni",
          "Gövde özelliklerini doğrusal ya da dairesel olarak çoğaltır.",
          ["Özelliği seç", "Yön / eksen seç", "Adet ve aralık ver"], status=PLANNED,
          variants=[
              V("PAT3D_R", "PAT3D_R", "Dikdörtgen", "İki yönde satır / sütun.",
                status=PLANNED),
              V("PAT3D_C", "PAT3D_C", "Dairesel", "Bir eksen etrafında.", status=PLANNED),
          ]),
    ]),
    ("Geçmiş", [
        B("ORDER", "ORDER", "İşlem sırası",
          "Gövdeye uygulanan işlemleri sırasıyla gösterir; sıralanır, kapatılır.",
          ["Listeden işlemi seç", "Yukarı / aşağı taşı", "Göz: geçici kapat"]),
    ]),
]

# ================================================================ DELİK · VİDA

_HOLE = [
    ("Delik", [
        B("HOLE", "HOLE", "Delik",
          "Yüzeye düz, havşalı ya da havşa başlı (kademeli) delik açar.",
          ["Yüzeye ya da eskiz noktasına tıkla", "Türü ve ölçüleri ver",
           "Derinlik: mesafe / tümüyle geçen"], key="H", status=PLANNED,
          variants=[
              V("HOLE", "HOLE", "Düz delik", "Çap ve derinlik.", status=PLANNED),
              V("HOLE_CBORE", "HOLE_CBORE", "Havşa başlı (kademeli)",
                "Baş çapı ve baş derinliği ile.", status=PLANNED),
              V("HOLE_CSK", "HOLE_CSK", "Havşalı", "Havşa çapı ve açısı ile.",
                status=PLANNED),
          ]),
        B("TAPPED", "TAPPED", "Dişli delik",
          "Standart vida ölçüsüne göre (M3, M4, ...) dişli delik açar.",
          ["Konumu seç", "Standart ve ölçü seç (ISO metrik)", "Diş derinliği ver"],
          status=PLANNED),
    ]),
    ("Vida", [
        B("THREAD", "THREAD", "Diş",
          "Silindirik yüze dış ya da iç diş açar (görsel ya da gerçek geometri).",
          ["Silindirik yüzü seç", "Adım ve uzunluk ver", "Görsel / modellenmiş seç"],
          status=PLANNED),
        B("BOLT", "BOLT", "Vida oluştur",
          "Standart ölçülerden vida gövdesi üretir (altıgen başlı, imbus, havşa başlı).",
          ["Standart ve ölçü seç", "Boy ver", "Baş tipini seç"], status=PLANNED),
        B("NUT", "NUT", "Somun", "Standart ölçülerden somun üretir.",
          ["Ölçü seç", "Konumu seç"], status=PLANNED),
    ]),
]

# ================================================================ ARAÇLAR

_TOOLS = [
    ("Dışa aktar", [
        B("STEP", "STEP", "STEP dışa aktar",
          "Gövdeyi STEP (.step) olarak başka CAD programlarına aktarır.",
          ["Gövdeyi seç", "Dosya yolunu seç"]),
    ]),
    ("Tanı", [
        B("DIAG", "DIAG", "Tanı raporu",
          "Hesap motoru ve gövde durumunu, başarısızlık kaynağıyla raporlar.",
          ["Rapor panoya kopyalanır"]),
        B("REC", "REC", "Kayıt → Claude",
          "Birkaç saniyelik olay kaydı ve durum raporu hazırlar (hata bildirimi için).",
          ["Kaydı başlat", "Sorunu tekrar yap", "Raporu sohbete yapıştır"], key="Ctrl+Alt+R"),
    ]),
    ("Ayarlar", [
        B("SETTINGS", "SETTINGS", "Ayarlar",
          "Önizleme kalitesi, toleranslar, ızgara ve yakalama ayarları."),
        B("KERNEL", "KERNEL", "Çekirdek",
          "OpenCASCADE çekirdeğinin kurulum ve motor durumunu gösterir.",
          ["Kurulu değilse 'Kur' ile indirilir"]),
    ]),
]

TABS = [
    ("SKETCH", "Eskiz", _SKETCH),
    ("CONSTRAIN", "Kısıt", _CONSTRAIN),
    ("SURFACE", "Yüzey", _SURFACE),
    ("SOLID", "Katı", _SOLID),
    ("HOLE", "Delik · Vida", _HOLE),
    ("TOOLS", "Araçlar", _TOOLS),
]


def all_buttons():
    for _tid, _lbl, groups in TABS:
        for _g, btns in groups:
            for b in btns:
                yield b


def find(ident):
    """id ile düğme ya da tür (variant) bul."""
    for b in all_buttons():
        if b["id"] == ident:
            return b
        for v in b["variants"]:
            if v["id"] == ident:
                return v
    return None
