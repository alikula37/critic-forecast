# Backtest Metodolojisi

## Walk-Forward Doğrulama

Zaman serisi tahmininde rastgele K-fold geçersizdir (look-ahead sızıntısı). Bunun yerine:

1. Seri zaman sırasıyla **fold**lara bölünür (ör. 3 fold).
2. Her fold için: yalnızca fold başlangıcından önceki veriyle eğitim yapılır.
3. Fold başında **purging boşluğu** bırakılır (indikatör penceresi kadar; örn. 60 bar).
4. Model fold içindeki her gün tahmin üretir; tahminler gerçekleşmeyle karşılaştırılır.

Bu, engine içi `performance` çıktısını besler.

## Metrikler

- **RMSE / MAPE:** P50 tahmininin ortalama karesel / yüzdesel hatası.
- **Hit-rate (yön isabeti):** `sign(gelecek_gün_dönüşü) == sign(tahmin_dönüşü)` oranı.
- **Pinball loss (P10/P90):** `L_q(y, yhat) = (y - yhat) * (q - 1_{y<yhat})` — quantile
  kalibrasyonu; düşük değer = koni dürüst.
- **Aralık kapsama:** gerçek değerin P10-P90 bandına düşme oranı (hedef ~0.80).
- **Sinyal Sharpe:** her modelin günlük yön sinyaline dayalı hayali stratejinin
  ortalama günlük dönüş / std (yıllıklandırılmış), MaxDD ile birlikte.
- **Brier skoru:** yükseliş olasılığı tahmininin gerçekleşme ile karesel uzaklığı.

## Canlı Geri Bildirim Döngüsü

- Her `POST /api/forecast` çıktısı DuckDB'ye yazılır.
- Bir tahminin hedef tarihi geçtiğinde, `forecast_points` gerçek OHLCV ile join edilir ve
  gerçekleşme hataları hesaplanır.
- Hakem, son 180 günde kayan pencerede her modelin live skorunu üretir:
  `live = 0.40*hit_rate_norm + 0.30*rmse_norm + 0.15*pinball_norm + 0.15*sharpe_norm`.
- Nihai skor: `score = 0.6*live + 0.4*engine_backtest` (live veri yoksa yalnız engine skoru).

## Güven Skoru

- `güven = clip(0.5 * ortalama_skor + 0.5 * konsensüs_oranı, 0.05, 0.98)`
- Konsensüs oranı: diverjans matrisinin ortalamasından üretilir; model çelişkisi artarsa
  güven düşer (belirsizlik sinyali).

## Ağırlıklandırma

- `w_i = softmax(score_i / T)`; T = hakem sıcaklığı (env: CRITIC_TEMPERATURE).
- Rejim bonusu: modelin mevcut HMM rejimindeki hata ortalaması, küresel ortalamasından
  iyiyse `* (1 + 0.15)`; kötüyse `* (1 - 0.15)`.
- **QRA (Quantile Regression Averaging):** ≥30 gerçekleşmiş tahmin birikince, her quantile
  (P10/P50/P90) için ayrı bir doğrusal program çözülür:
  `min_w Σ pinball_q(y − X·w)` kısıtları `w ≥ 0, Σw = 1` (scipy linprog/highs). X = model
  quantile tahminleri, y = gerçekleşmiş getiriler. QRA ağırlıkları softmax ağırlıklarının
  yerine geçer; izotonik sıralama (`isotonic_fix`) çakışan quantile'ları düzeltir.
- Meta ayar: RMSE normlarına göre ±30% çarpımsal düzeltme (`meta_adjust`).
- Az gerçekleşme verisinde yalnızca softmax + meta ayar + rejim bonusu kullanılır.

## Gerçekleşme Odaklı Değerlendirme (Degenerasyon Düzeltmesi)

- Yön metriği **fiyat seviyesi** üzerinden değil, `p50 > last_close` (tahmin günü öncesi son
  kapanış) ile hesaplanır; `ensemble_forecasts.last_close` kolonunda saklanır.
- F1/precision/recall, sharpe ve Brier gerçekleşmiş getirilerden üretilir.
- İstatistiksel modeller (MC/ETS/STL) artık sahte momentum puanı yerine kendi konilerinin
  gerçek walk-forward pinball/RMSE/hit-rate/sharpe değerlerini döndürür (`walkforward.py`).
- `skill_from_performance` eksik key'leri 0 puan sayar — şişirilmiş ağırlık engellenir.
- **Canlı skor:** `model_scores` geçmişinin kendi kendine referanslı ortalaması yerine,
  mevcut job'da `compute_model_performance` ile hesaplanan gerçekleşmiş pinball/kalibrasyon
  skoru `combine(live, realized_skill)` ile birleştirilir.
