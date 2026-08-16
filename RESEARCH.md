# Derin Araştırma ve Mimari Raporu

Bu rapor; zaman serisi mimarileri, hakem/ensemble puanlama sistemleri ve tasarım seçimlerinin
teknik gerekçelerini belgeler.

## 1. Zaman Serisi Mimarileri — Karşılaştırma ve Seçim

### 1.1 Temporal Fusion Transformer (TFT) [1]

- **Nedir:** Google Research'in çok-ufuklu tahmin mimarisi. LSTM katmanları kısa vadeli yerel
  işlemler, interpretable self-attention uzun vadeli bağımlılıklar için kullanılır. Gated
  Residual Network'ler gereksiz bileşenleri bastırır; variable selection özellik seçimi yapar.
- **Avantaj:** Quantile çıktı katmanı (P10/P50/P90) doğal belirsizlik konisi üretir; attention
  ağırlıkları yorumlanabilirlik verir; karışık rejimlerde güçlüdür.
- **Maliyet:** Tam kurulum `pytorch-forecasting` + `pytorch-lightning` bağımlılık zinciri
  gerektirir; eğitim süresi uzundur; 500-1500 barlık veride avantajı azalır.
- **Karar:** TFT'nin üç kritik fikri özel Bi-LSTM uygulamamıza aktarılır:
  1. Quantile çıktı kafaları + pinball loss,
  2. Gating ile artık bağlantı,
  3. Attention ile zaman adımı önceliklendirmesi.
  Tam TFT kurulumu bu ölçekte orantısız bağımlılık riski taşır.

### 1.2 Bi-LSTM + Attention (Seçilen ana DL modeli)

- **Gerekçe:** Finansal getiriler zayıf dönem bağımlılığı taşır. Çift yönlü LSTM her adımda hem
  geçmiş hem gelecek-filtreli bağlamı temsil eder (denoising). Additive attention, hangi tarihsel
  pencerelerin tahmin için kritik olduğunu öğrenir; momentum ve seviye kırılımlarına benzer
  davranışları veriden öğrenir.
- **Overfit kontrolü:** dropout + weight decay + erken durdurma + purged walk-forward bölme +
  deterministik tohum. Tek model "kazanmak" zorunda değildir; hakem sistemi rejime göre ağırlık verir.
- **Belirsizlik:** P10/P50/P90 kafaları pinball loss ile eğitilir.

### 1.3 N-BEATS [2]

Blok tabanlı, özellik mühendisliği gerektirmeyen model. Deterministik öngörü üretir; quantile
aralık vermez; finansal getirilerde LSTM+attention karşısında tutarlı üstünlük kanıtı yoktur.
Raporlanır, kurulmaz.

### 1.4 Gradient Boosting (XGBoost) [3]

- **Gerekçe:** Teknik indikatör + rejim özelliklerinden oluşan tabular vektörde ayrımcılık
  gücü yüksektir; küçük veride derin modellerden daha stabil; `reg:quantileerror` hedefi ile
  quantile aralık üretebilir; feature importance ile yorumlanabilir.
- **Karar:** İki çıktılı hat: yön sınıflandırıcısı (up_probability) + çok-ufuklu quantile
  regresörü (P10/P50/P90).

### 1.5 İstatistiksel Katman (HMM + GARCH + STL + Monte Carlo)

- **HMM [4]:** Getirilerin gizli rejimlerle üretildiğini varsayar. GaussianHMM (3 durum) log
  getiri + mutlak getiri özellikleriyle eğitilir; rejim olasılıkları ve Viterbi yolu ile tarihsel
  rejim etiketleri üretilir (Boğa / Ayı / Yatay).
- **GARCH [5]:** Volatilite kümelenmesini modeller; GARCH(1,1) koşullu varyans öngörüsü Monte
  Carlo simülasyonunun sigma yolunu besler.
- **STL [6]:** Log fiyatın trend/sezonluk/kalıntı ayrıştırması + FFT periodogram ile döngü
  uzunlukları tespiti (döngüsellik hattı).
- **Monte Carlo:** Rejim koşullu drift + GARCH sigma ile 10.000 yapısal yol; Student-t kuyruk
  kalınlığı; ampirik quantile'lar ile günlük koni ve yükseliş olasılığı.

## 2. Hakem ve Meta-Learner Sistemi (The Critic)

Basit ortalamadan farklı olarak dinamik ağırlıklı birleştirme uygulanır:

### 2.1 Puanlama Eksenleri

Her model için 4 eksende skor üretilir (0-1 normalize):

| Eksen | Metrik | Rol |
|-------|--------|-----|
| Doğruluk | RMSE, MAPE, yön isabet oranı | Tahmin hatası düzeyi |
| Kalibrasyon | P10/P90 pinball loss, aralık kapsama oranı | Belirsizlik konisinin dürüstlüğü |
| Risk-ayarlı | Sinyal stratejisi kayan Sharpe + MaxDD | Piyasada para kazanma yeteneği |
| Rejim uyumu | HMM rejimine koşullu hata tablosu | "Şu anki rejimde kim daha iyi?" |

### 2.2 Canlı geri bildirim döngüsü

Her tahminin gerçekleşmesi, DuckDB `forecast_points` ile gerçek fiyata join edilerek son 6 aylık
kayan pencerede skorlanır. Bu "live" skor, engine içi walk-forward doğrulama skoruyla
`0.6 * live + 0.4 * backtest` ağırlığında birleştirilir.

### 2.3 Diverjans (çelişki) tespiti

Model P50 eğrileri arasındaki pairwise ortalama mutlak uzaklık, ortalama fiyata bölünerek
normalize edilir. Yüksek çelişki -> güven cezası; konsensüs -> bonus.

### 2.4 Ağırlıklandırma ve meta-learner

- `score = softmax((live*0.6 + backtest*0.4) / T)`; T sıcaklık (config).
- Rejim uyumu bonusu: modelin mevcut rejimdeki hatası ortalamadan iyiyse artır.
- Ridge meta-learner, tarihsel model hatalarından lineer düzeltme öğrenir (stacking).
- Final koni: günlük `Pq = sum(w_i * q_i)`, yükseliş olasılığı `sum(w_i * up_i)`.

## 3. Backtest Metodolojisi

- **Walk-forward:** Genişleyen pencere; train/validation arasında purging boşluğu; her fold
  yalnızca geçmiş veriyle eğitilir (look-ahead yok).
- **Causality:** Tüm indikatörler yalnızca geçmiş/su anki barı kullanır; scaler yalnızca eğitim
  diliminde uydurulur.
- **Metrikler:** RMSE, MAPE, hit-rate, pinball P10/P90, sinyal Sharpe, MaxDD, Brier skoru.
- **Canlı doğrulama:** Stored forecast -> gerçekleşme karşılaştırması (kayan 6 ay).

## 4. Tasarım Kararı (Refero / Auros)

`styles.refero.design` incelendi; koyu temalı finansal terminaller arasında Auros
("Abyssal terminal") seçildi: obsidyen teal canvas `#012624`, yüzey hiyerarşisi
`#011d1c -> #003734`, fosfor vurgu `#fde9ff`, teal->pembe gradyan, 16px kart/6px buton,
büyük harf izli etiketler. Kullanıcının "dark obsidian + glassmorphism" talebiyle birebir
örtüşür. Glass kartlar: `rgba(255,255,255,0.04)` + backdrop-blur + 1px hairline.

## 5. Kaynakça

[1] Lim, Arik, Loeff, Pfister — "Temporal Fusion Transformers", arXiv:1912.09363 (2020).
[2] Oreshkin et al. — "N-BEATS", arXiv:1905.10437 (2019).
[3] Chen, Guestrin — "XGBoost", KDD 2016.
[4] Rabiner — "A Tutorial on HMM", IEEE 1989.
[5] Bollerslev — "GARCH", Journal of Econometrics 1986.
[6] Cleveland et al. — "STL", JOS 1990.
