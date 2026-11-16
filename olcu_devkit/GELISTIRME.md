# Ölçü Ustası — Geliştirme Notları (v1.0.0)

Mini CAD'den bağımsız ayrı bir Blender eklentisi (`olcu_ustasi/`, extension id `olcu_ustasi`).
Kurulum zip'i: `dist/olcu_ustasi_v1.0.0.zip` (dosyalar zip kökünde).

## Modül haritası
| Dosya | İş |
|---|---|
| `units.py` | Birim biçimleme, güvenli ifade çözümleyici (`4.5m`, `1m 20cm`, `150%`, `*2`). bpy'siz. |
| `geom.py` | `View` (yalnız perspektif matrisinden izdüşüm / ışın — testte sahte kurulur), doğru/ışın/düzlem, ölçek matrisleri, `Box` (yönelimli kutu). |
| `selection.py` | `Group`: seçim → kökler + hiyerarşi. `group_box`: depsgraph örnekleri dahil sıkı kutu (numpy). Animasyon eğrisi erişimi (4.4+ katmanlı Action ve eski API). |
| `snapping.py` | `Snapper`: imleç çevresine ~17 BVH ışını (`scene.ray_cast`), çarpılan yüzlerin köşe/kenar/orta/merkezleri, kutu ve köken noktaları (ışınla görünürlük sınaması), yüzsüz mesh'ler için numpy. |
| `scaling.py` | `Scaler`: önizleme / geri yükleme / `finalize` (kök başına DIRECT · FCURVE · EMPTY). `apply_scale`: ölçeği veriye güvenli aktarma (kutupsal ayrışım W = T·R·L). |
| `op_measure.py` | Modal "Ölç ve Ölçekle" (A → B → hedef; REF_C/REF_D referans). |
| `op_cage.py` | Modal "Kutu ile Ölçekle" (yüz/köşe tutamaçları, yazarak değer, Ctrl yapışma). |
| `ops_misc.py` | Panel işlemleri + `olcu_dim_x/y/z` canlı boyut alanları (önbellek + depsgraph işleyicisi). |
| `pins.py` | Sabit ölçüler ve kalıcı çizim işleyicisi. |
| `props.py`, `ui.py`, `draw.py`, `common.py` | Ayarlar, paneller/menüler, GPU çizim yardımcıları, ortak yardımcılar. |

## Tasarım kuralları
- Ölçek **yalnız köklere**: `W_kök' = M @ W_kök`. Alt nesnelere, ebeveyn ters matrislerine,
  verilere hiç dokunulmaz → ilişki bozulmaz.
- Eşit olmayan ölçek doğrudan atamada kesin değilse (dönük/eğik) → `Olcek_Koku` Empty, eski
  ebeveyninin altına; kökün `matrix_parent_inverse`'i dünya konumunu koruyacak şekilde kurulur.
- Fare başına iş sabit olmalı: tam mesh taraması yok. Yeni yakalama türü eklerken aday sayısını
  çarpılan yüzlerle ya da az sayıdaki referans noktasıyla sınırla.
- Arayüz Türkçe, Blender eksen renkleri.

## Test
```bash
bash olcu_devkit/run_tests.sh                 # pip bpy==5.2.3 ile 26 test
OLCU_HEAVY=1 bash olcu_devkit/run_tests.sh    # 2M+ yüz performans
bash olcu_devkit/run_tests.sh --shots /tmp/s  # arayüz ekran görüntüleri (yazılımsal GPU)
```
Modal operatörler sahte olay / bağlam nesneleriyle uçtan uca sürülür (`Ctx`, `ev`, `_make_op`).
Ölçülen: 2.05M yüzde fare başına ~0.5 ms yakalama.
