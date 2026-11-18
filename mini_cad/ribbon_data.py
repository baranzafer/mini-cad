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
  small   : küçük düğme (simge + kısa ad, iki satırlık sütunlarda; seçenekler için)
  short   : küçük düğmenin kısa adı
  action  : işlevin türü (blendcad.py bağlar): "tool" çizim aracı, "op" operatör, "panel"
            açılır ayar paneli ... — boşsa düğme kimliğine göre bağlanır
"""

READY = "ready"
PLANNED = "planned"


def B(id, icon, title, desc, steps=(), key="", status=READY, variants=(), toggle=False,
      small=False, short=""):
    return {"id": id, "icon": icon, "title": title, "desc": desc, "steps": list(steps),
            "key": key, "status": status, "variants": list(variants), "toggle": toggle,
            "small": small, "short": short or title}


def V(id, icon, title, desc, steps=(), key="", status=READY):
    return B(id, icon, title, desc, steps, key, status)


# ================================================================ ESKİZ

_SKETCH = [
    ("Eskiz", [
        B("SK_START", "SKETCH_NEW", "Eskiz başlat",
          "Çizimi açar; önce bir düzlem ya da gövde yüzü seçilir. Çizim açıkken düzlemi "
          "yeniden seçtirir.",
          ["Eksen düzlemine (XY / XZ / YZ) ya da bir gövde yüzüne tıkla",
           "Yüksekliği fareyle ya da değer yazarak ver",
           "Çizim araçlarıyla taslağı çiz"], key="Shift+Q"),
        B("SELECT", "SELECT", "Seç / duraklat",
          "Çizim açık kalır ama tıklamalar Blender'a gider (seçim, G / R / S).",
          ["Çizime dönmek için bir çizim aracı seç ya da Q"], key="W · Esc"),
        B("SK_FINISH", "FINISH", "Eskizi bitir",
          "Taslağı eğri objesine kaydeder; bağlı yüzey ve gövdeler güncellenir.",
          ["Taslaktaki bütün çizgiler hedef eğriye yazılır",
           "Hedef: Mevcut eğri ya da Yeni eğri (Seçenekler)"], key="Ctrl+Enter"),
        B("SK_UNDO", "SK_UNDO", "Geri al",
          "Taslakta son noktayı / çizgiyi geri alır; geri al / yinele geçmişi de burada.",
          ["Türü seç: son nokta, geçmişte geri al ya da yinele"], key="Backspace",
          variants=[
              V("SK_UNDO", "SK_UNDO", "Son noktayı geri al",
                "Süren çizginin son noktasını, yoksa son çizgiyi geri alır.", key="Backspace"),
              V("SK_HIST_UNDO", "SK_UNDO", "Taslakta geri al",
                "Taslak geçmişinde bir adım geri (Bitir'den önce).", key="Ctrl+Z"),
              V("SK_REDO", "SK_REDO", "Taslakta yinele",
                "Taslak geçmişinde bir adım ileri.", key="Ctrl+Shift+Z"),
          ]),
        B("SK_SURF", "SK_SURF", "Yüzey oluştur",
          "Son kapalı çizgiden (iç içe olanlarla birlikte: delikli) yüzey yapar.",
          ["Kapalı bir çizgi çiz (C: başa dönüp kapat)", "Yüzey: mevcut gövdeye · "
           "Yeni gövde: ayrı gövde"], key="F",
          variants=[
              V("SK_SURF", "SK_SURF", "Yüzey", "Mevcut gövdeye yüzey ekler.", key="F"),
              V("SK_SURF_NEW", "BODY", "Yeni gövde", "Yüzeyle yeni bir gövde başlatır.",
                key="Ctrl+F"),
          ]),
        B("DELETE_SK", "DELETE", "Sil",
          "Taslaktaki nesnenin (doğru, yay, spline, daire...) ya da noktanın tamamını siler; "
          "Kırp'tan farklı olarak kesişimlere bakmaz.",
          ["Silinecek nesnenin üzerine gel (kırmızı vurgulanır)", "Tıkla · sürükleyerek çoklu",
           "Kaydedilmiş eğri için önce Taslağa al"], key="Del"),
        B("SK_EDIT", "EDITSK", "Taslağa al",
          "Kaydedilmiş eğriyi taslakta düzenlemeye açar (Inventor: Edit Sketch).",
          ["Türü seç", "Kaydedilmiş eğriye tıkla ya da aktif çizimin tamamını aç"],
          variants=[
              V("EDITSK", "EDITSK", "Eğriyi taslağa al",
                "Tıklanan kaydedilmiş eğri taslağa alınır; Bitir'de geri yazılır.",
                ["Kaydedilmiş eğriye tıkla", "Taslakta düzenle", "Bitir"]),
              V("EDIT_ALL", "EDIT_ALL", "Çizimi düzenle (tamamı)",
                "Aktif eğri objesinin (çizimin) tamamını taslağa alır.",
                ["Eğri objesini seç (aktif)", "Düğmeye bas", "Bitir / Çizimi kapat"]),
          ]),
        B("SK_CLOSE", "SK_CLOSE", "Çizimi kapat",
          "Taslağı kaydedip çizim aracını kapatır.", key="Esc ×2"),
    ]),
    ("Düzlem", [
        B("PLANE", "PLANE_PICK", "Çizim düzlemi",
          "Çizim düzlemini seçer: görünümde seç, otomatik, eksen düzlemleri ya da ekrana paralel.",
          ["Türü açılır listeden seç", "Eksen düzleminde yüksekliği ver"],
          variants=[
              V("PL_PICK", "PLANE_PICK", "Görünümde seç",
                "Eksen düzlemi ya da gövde yüzü tıklanarak seçilir.", key="Shift+Q"),
              V("PL_AUTO", "PLANE_AUTO", "Otomatik",
                "Görüşe göre eksen düzlemi; gövde yüzüne tıklarsan yüz düzlemi."),
              V("PL_XY", "PLANE_XY", "Üst (XY)", "Z yukarı bakan düzlem.", key="Shift+Z"),
              V("PL_XZ", "PLANE_XZ", "Ön (XZ)", "Y'ye dik düzlem.", key="Shift+Y"),
              V("PL_YZ", "PLANE_YZ", "Yan (YZ)", "X'e dik düzlem.", key="Shift+X"),
              V("PL_VIEW", "PLANE_VIEW", "Ekrana paralel", "Görüş düzlemi.", key="V"),
          ]),
        B("AXLOCK", "AXIS_X", "Eksen kilidi",
          "İmleci bir eksen boyunca kilitler (çizerken ve taslak noktası sürüklerken). Tekrar "
          "basınca kalkar.", ["Türü (X / Y / Z) seç", "Noktayı eksen boyunca ver"],
          key="X / Y / Z",
          variants=[
              V("AX_X", "AXIS_X", "X ekseni", "X boyunca kilitle.", key="X"),
              V("AX_Y", "AXIS_Y", "Y ekseni", "Y boyunca kilitle.", key="Y"),
              V("AX_Z", "AXIS_Z", "Z ekseni", "Z boyunca kilitle.", key="Z"),
          ]),
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
    ("Yardımcı", [
        B("KEY_G", "TEMP_GROUND", "Geçici zemin",
          "Çizerken ızgaranın yönünü / yüksekliğini geçici değiştirir; tekrar basınca asıl "
          "düzleme döner.", ["Bir düzleme / yüze tıkla, yüksekliği ver", "Tekrar: normale dön"],
          key="G", toggle=True, small=True, short="Geçici zemin"),
        B("KEY_T", "TRACE", "İz", "Referans noktadan eksenler boyunca kesikli kılavuzla "
          "başlangıç noktası bulur.", ["Referans noktaya gel", "Eksen boyunca adım ver"],
          key="T", toggle=True, small=True),
        B("KEY_C", "CLOSE_LOOP", "Başa kapat", "Süren çizgiyi başlangıç noktasına bağlar.",
          key="C", small=True, short="Kapat"),
        B("KEY_Q", "PREV_TOOL", "Önceki araç", "Son iki araç arasında geçer.", key="Q",
          small=True, short="Önceki"),
        B("KEY_D", "FLIP_DIR", "Yön", "Merkezli yayın yönünü, çokgende iç / dış teğeti "
          "değiştirir.", key="D", small=True),
        B("KEY_COORD", "COORD", "Hassas giriş", "Ölçü alanları ΔX / ΔY olur (ilk noktada mutlak "
          "X / Y).", key="Shift+Tab", toggle=True, small=True, short="Hassas"),
    ]),
    ("Seçenekler", [
        B("OPT_SNAP", "SNAP", "Yakalama", "Uç / orta / kesişim yakalama ve kılavuzlar.",
          ["Ctrl basılıyken geçici olarak kapalı"], toggle=True, small=True),
        B("OPT_GRID", "GRID", "Izgara", "Izgaraya hafif yakalama; aralık yakınlaştırmaya göre "
          "değişir.", key="I", toggle=True, small=True),
        B("OPT_LOOK", "LOOK", "Düzleme bak", "Düzlem seçince görünüm düzleme döner.",
          toggle=True, small=True, short="Bak"),
        B("OPT_FIRST", "PLANE_PICK", "Önce düzlem",
          "Çizim açılınca önce düzlem seçtirir (Inventor gibi).", toggle=True, small=True),
        B("OPT_NEW", "TARGET_NEW", "Yeni eğriye yaz",
          "Açık: her Bitir yeni eğri objesi oluşturur · Kapalı: aktif / son eğriye ekler.",
          toggle=True, small=True, short="Yeni eğri"),
        B("OPT_GHOST", "OPACITY", "Çizerken saydam",
          "Çizim açıkken gövdeler saydam görünür: arkadaki referans görsele bakarak çizmeye "
          "devam edilir. Opaklık: Katı → Saydamlık.", toggle=True, small=True, short="Saydam"),
    ]),
]

# ================================================================ DEĞİŞTİR (eskiz düzenleme)

_MODIFY = [
    ("Değiştir", [
        B("DELETE", "DELETE", "Sil",
          "Taslaktaki nesnenin (doğru, yay, spline, daire...) ya da noktanın tamamını siler; "
          "Kırp'tan farklı olarak kesişimlere bakmaz.",
          ["Silinecek nesnenin üzerine gel (kırmızı vurgulanır)", "Tıkla · sürükleyerek çoklu",
           "Kaydedilmiş eğri için önce Taslağa al"], key="Del"),
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
           "Ölçüye tık: değeri düzenle"]),
        B("AUTODIM", "AUTODIM", "Otomatik ölçü",
          "Ölçüsüz doğrulara uzunluk, yaylara yarıçap ölçüsü verir.",
          ["Eğriye tıkla"]),
        B("DIMFIX", "DISTANCE", "Ölçü kısıtı",
          "Tek tür ölçü kısıtı: uzunluk, açı ya da yarıçap / çap.",
          ["Türü seç", "Kenar(lar)ı seç", "Değeri Kısıt listesinden düzenle"],
          variants=[
              V("DISTANCE", "DISTANCE", "Uzunluk", "1 kenarın boyu."),
              V("ANGLE", "ANGLE", "Açı", "2 kenar arasındaki açı."),
              V("RADIUS", "RADIUS", "Yarıçap / çap", "1 yay / daire."),
          ]),
    ]),
    ("Geometrik", [
        B("HORIZ", "HORIZ", "Yatay", "Kenarı çizim düzleminin yatay eksenine hizalar.",
          ["1 kenar seç"]),
        B("VERT", "VERT", "Dikey", "Kenarı çizim düzleminin dikey eksenine hizalar.",
          ["1 kenar seç"]),
        B("AXIS", "AXIS", "Eksene hizala", "Kenarı en yakın dünya eksenine (yatay / dikey) "
          "hizalar.", ["1 kenar seç"]),
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
              V("SYMLINE", "SYMLINE", "Çizgiye göre", "2 nokta + simetri doğrusu."),
              V("SYMMETRIC", "SYMMETRIC", "Eksen düzlemine göre", "2 nokta, dünya eksen düzlemi."),
          ]),
    ]),
    ("Yönet", [
        B("CONS_SOLVE", "SOLVE", "Çöz", "Bütün kısıtları yeniden çözer."),
        B("CONS_LIST", "CONS_LIST", "Kısıt listesi",
          "Kısıtları ve ilişkileri (desen / yansıtma) listeler: aç / kapa, değer, sil.",
          ["Değerleri listeden düzenle", "Otomatik kısıtları toplu sil"]),
    ]),
    ("Görünüm", [
        B("CONS_SHOW", "SHOW", "Kısıtları göster", "Kısıt simgelerini görünümde açar / kapatır.",
          ["Simgeye sağ tık: dondur / sil"], toggle=True, small=True, short="Göster"),
        B("CONS_AUTO", "AUTOCONS", "Oto kısıt",
          "Çizerken yakalanan yatay / dikey, paralel, dik ve çakışmaları kısıt olarak kaydeder.",
          toggle=True, small=True),
    ]),
]

# ================================================================ TEL KAFES · YÜZEY

_SURFACE = [
    ("Tel kafes", [
        B("WIRE_MESH", "WIRE_MESH", "Mesh'ten tel kafes",
          "Seçili mesh kenarlarından bezier tel kafes eğrileri üretir.",
          ["Mesh objesinde kenarları seç", "Düğmeye bas: eğriler oluşur"]),
        B("EDGE_PICK", "EDGE_PICK", "Kenar seçimi",
          "Tel kafes ve gövde kenarlarını seçer; seçimden yüzey, yeni gövde, fillet ya da "
          "süpürme yapılır (pencerede).",
          ["Kenarın üzerine gel, tıkla (Alt+tık: tek parça)",
           "Pencereden: Yüzey · Yeni gövde · Fillet · Süpürme"], key="Enter / B / P"),
        B("SKETCH3D", "SKETCH3D", "3B eskiz",
          "Uzayda doğru / spline çizer; yüzey ve kenarlara bağlanır.",
          ["Nokta, kenar ya da yüzey üzerinden başla", "Eksen kilitleriyle uzayda ilerle"],
          status=PLANNED),
    ]),
    ("Yüzey", [
        B("PATCH", "PATCH", "Sınır yüzeyi",
          "Kapalı tel kafes döngüsünden yüzey yaması kurar (ortak kenarlarla). Kenar seçimini "
          "açar.",
          ["Döngünün kenarlarına tıkla (Alt+tık: tek parça)", "Enter: yüzey",
           "Ctrl+Enter: yeni gövde"], key="Enter"),
        B("PATCH_HOLE", "PATCH_HOLE", "Delikli yüzey",
          "İç içe kapalı döngülerden delikli düzlemsel yüz kurar (B harfi gibi). Çizimde F.",
          ["Dış döngü ve delikleri aynı düzlemde çiz", "Son kapalı çizgide F: yüzey",
           "Ctrl+F: yeni gövde"], key="F"),
        B("SURF_LIST", "SURF_LIST", "Yüzey listesi",
          "Gövdenin yüzeyleri: durum, eğrilerini seç, sil, yüzey başına birleşim.",
          ["Listeden yüzeyi seç", "Birleşim / teğet ağırlığı ayarla"]),
        B("BLEND", "BLEND", "Yüzey birleşimi",
          "Komşu yüzeylerin ortak kenarda keskin (G0) ya da teğet (G1) buluşmasını seçer.",
          ["Yüzeyi seç", "Keskin / Teğet seç"],
          variants=[
              V("BLEND_G0", "BLEND_G0", "Keskin (G0)", "Gövde ayarı: yüzler kenarda buluşur."),
              V("BLEND_G1", "BLEND", "Teğet (G1)", "Gövde ayarı: komşu yüze teğet kaynaşır."),
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
          "Gövdeyi bir eksen düzlemine göre aynalayıp ortadan birleştirir (ayar penceresi).",
          ["Simetriyi aç", "Eksenleri seç (X / Y / Z)", "Dikiş kenarı ortak olur"]),
    ]),
]

# ================================================================ KATI

_SOLID = [
    ("Gövde", [
        B("BODY", "BODY", "Gövde",
          "Çalışılan gövdeyi seçer; durum ve hesap bilgisini gösterir.",
          ["Listeden gövdeyi seç ya da aktif objeyi gövde yap",
           "Yeni gövde: Kenar seçiminde Ctrl+Enter"]),
        B("REBUILD", "REBUILD", "Yenile",
          "Gövdeyi yeniden hesaplar (canlı güncelleme zaten açıktır)."),
        B("OPACITY", "OPACITY", "Saydamlık",
          "Gövdenin opaklığını ayarlar: arkasındaki referans görsel ve tel kafes görünür, "
          "yeni eğrileri görsele göre çizmeye devam edilir. Hesaba etkisi yoktur.",
          ["Gövdeyi seç", "Opaklığı sürükle ya da hazır değere bas",
           "İstersen: Çizerken saydam (yalnız çizim açıkken)"]),
    ]),
    ("Oluştur", [
        B("EXTRUDE", "EXTRUDE", "Ekstrüzyon",
          "Gövde yüzünü uzatır: yüzeyin üzerine gelince ok belirir, tıkla, oku sürükle. "
          "Başlarken sorar: Doğrusal (tek yön) ya da Kalınlaştır (yüzey normalleri boyunca, "
          "geometrik şekli korur).",
          ["Türü seç: Doğrusal / Kalınlaştır", "Yüzeye tıkla (Shift: yüz ekle)",
           "Oku sürükle ya da ölçü yaz · F: yön", "Birleştir / Kes / Kesişim · Enter"],
          variants=[
              V("EXTRUDE", "EXTRUDE", "Ekstrüzyon (sor)",
                "Başlarken türü sorar.", ["Türü seç", "Yüzeye tıkla", "Oku sürükle"]),
              V("EXT_LINEAR", "EXTRUDE", "Doğrusal",
                "Yüz, normali doğrultusunda tek yöne uzar (prizma).",
                ["Yüzeye tıkla", "Oku sürükle"]),
              V("EXT_THICK", "THICKEN", "Kalınlaştır",
                "Yüz kendi normalleri boyunca kalınlık kazanır; eğri yüzeyde şekli korunur "
                "(kabuk ekstrüzyonu). Açık yüzey gövdesi böylece katılaşır.",
                ["Yüzeye tıkla", "Kalınlığı sürükle / yaz"]),
              V("EXT_LIST", "ORDER", "Ekstrüzyonlar",
                "Gövdedeki ekstrüzyonların listesi ve ayarları."),
          ]),
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
              V("BOOL_DIFF", "BOOL_DIFF", "Çıkar", "Araç gövde hedeften oyulur."),
              V("BOOL_UNION", "BOOL_UNION", "Birleştir", "İki gövde tek gövde olur."),
              V("BOOL_INT", "BOOL_INT", "Kesişim", "Yalnızca ortak hacim kalır."),
          ]),
    ]),
    ("Kenar", [
        B("FILLET", "FILLET3D", "Fillet / pah",
          "Seçili gövde kenarlarını yuvarlar ya da pah kırar. Kenar seçimini ve ayarları açar.",
          ["Kenarları seç", "B: uygula (yeni fillet ölçüsü ayarlardan)",
           "Listeden fillet'i seçip türünü Pah yapabilirsin"], key="B",
          variants=[
              V("FILLET_R", "FILLET3D", "Fillet", "Kenarı yarıçapla yuvarlar."),
              V("CHAMFER", "CHAMFER3D", "Pah", "Kenara pah kırar (fillet listesinde tür: Pah)."),
          ]),
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
          "Gövde yüzüne tıklayarak düz, havşa başlı (kademeli) ya da havşalı delik açar; eskiz "
          "noktasına ve daire merkezine yakalar.",
          ["Türü seç (açılır liste)", "Yüzeye ya da eskiz noktasına tıkla (birden çok delik)",
           "Ölçüleri Delik penceresinden ver: vida ölçüsü, çap, mesafe / tümüyle geçen",
           "Enter: bitir · Backspace: son deliği geri al · Esc: vazgeç"], key="H",
          variants=[
              V("HOLE", "HOLE", "Düz delik", "Çap; mesafe (matkap ucu açılı) ya da tümüyle "
                "geçen."),
              V("HOLE_CBORE", "HOLE_CBORE", "Havşa başlı (kademeli)",
                "İmbus vida için baş yuvası çapı ve derinliği ile."),
              V("HOLE_CSK", "HOLE_CSK", "Havşalı", "Havşa başlı vida için havşa çapı ve açısı."),
          ]),
        B("TAPPED", "TAPPED", "Dişli delik",
          "ISO metrik ölçüye göre (M2–M24) kılavuz matkabı çapında delik; diş ölçüsü "
          "saklanır.",
          ["Vida ölçüsünü seç (M6 → 5 mm matkap)", "Yüzeye tıkla", "Mesafe ya da tümüyle geçen"]),
        B("HOLE_LIST", "ORDER", "Delikler",
          "Gövdedeki delikleri listeler: seç, ölçüleri değiştir, yer ekle, sil.",
          ["Listeden deliği seç", "Ölçüleri değiştir (canlı güncellenir)",
           "Yer ekle: yüzeye tıkla"]),
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
        B("REPAIR", "ADVICE", "Öneriler",
          "Model denetimi: her işlem bitince gizli uyuşmazlıkları bulur ve onaylı düzeltme "
          "önerir (yüzey onarımı, tel kafes, fillet, boolean).",
          ["Yüzey / fillet / boolean başarısız olunca kendiliğinden açılır",
           "Öneriyi oku, düzeltme düğmesine bas", "Yeniden denetle: hepsini şimdi tara"]),
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
    ("MODIFY", "Değiştir", _MODIFY),
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
