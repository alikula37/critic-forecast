# Mimari ve API Kontratları

## Veri Akışı

```
+----------------+    REST+WS     +----------------+      REST      +---------------------+
|  ui-dashboard  | -------------> |  api-gateway   | ------------>  |  deep-learning-engine|
| (React, :8080) |                | (FastAPI, :8000)|                | (PyTorch, :9001)    |
+----------------+                |  + worker(RQ)  |      REST      +---------------------+
                                  |  + critic      | ------------>  | quant-engine         |
                                  |  + provider    |                | (HMM/GARCH/MC, :9002)|
                                  +----------------+                +---------------------+
                                        |  REST
                                        v
                                +----------------+   +---------+
                                | storage (DuckDB)|  | redis   |
                                | (:9000)        |   | (:6379) |
                                +----------------+   +---------+
```

## API Kontratları

### api-gateway (:8000)

| Yöntem | Yol | Açıklama |
|--------|-----|----------|
| GET | /api/health | Servis sağlık durumları |
| GET | /api/assets | Katalog (kripto / hisse / emtia ETF) |
| GET | /api/history?symbol=&interval=&limit= | Ham OHLCV (provider + cache) |
| POST | /api/forecast | {symbol, interval, horizon} -> {job_id} |
| GET | /api/forecast/{job_id} | Job durumu + sonuç |
| GET | /api/forecast/latest?symbol= | Son ensemble sonucu |
| GET | /api/forecast/history?symbol= | Geçmiş tahminler + gerçekleşme karşılaştırması |
| GET | /api/models/registry | Model meta verisi |
| GET | /api/models/scores?symbol= | Hakem skorları, ağırlıklar, çelişki matrisi |
| GET | /api/backtest?symbol= | Kayıtlı backtest özetleri |
| WS | /ws/forecast/{job_id} | Aşama aşama ilerleme akışı |

### deep-learning-engine (:9001)

POST /predict: `{symbol, interval, horizon, points:[{t,o,h,l,c,v}]}`
-> `{models:[{model_id, model_name, line, points:[{date,p10,p50,p90}], up_probability,
    performance:{rmse, hit_rate, pinball, sharpe, regime_errors}, details:{...}}]}`

### quant-engine (:9002)

POST /analyze: `{symbol, interval, horizon, points:[{t,o,h,l,c,v}]}`
-> `{models:[...], regimes:[{date,state,prob}], garch:{vol_forecast, params},
    seasonality:{components, cycles}, mc:{distribution, up_probability, stats}}`

### storage (:9000)

| Yöntem | Yol | Açıklama |
|--------|-----|----------|
| GET | /health | Sağlık |
| POST | /data/ohlcv | Toplu upsert |
| GET | /data/ohlcv?symbol=&interval=&start=&end= | Sorgu |
| GET | /data/ohlcv/latest?symbol=&interval=&limit= | Son N bar |
| POST | /forecasts | Ensemble sonucu + per-model noktalar |
| GET | /forecasts/history?symbol= | Geçmiş tahminler (gerçekleşme join'i dahil) |
| POST | /model-scores | Hakem skorlarını sakla |
| GET | /model-scores?symbol= | Hakem skorları |
| POST | /backtests | Backtest özeti sakla |
| GET | /backtests?symbol= | Backtest özetleri |

## DuckDB Şeması

- `ohlcv(symbol, ts, interval, open, high, low, close, volume)` PK(symbol, ts, interval)
- `ensemble_forecasts(job_id, symbol, interval, horizon, created_at, up_probability, points JSON, critic JSON)`
- `forecast_points(job_id, model_id, ts, p10, p50, p90)`
- `model_scores(symbol, model_id, as_of, score, weight, metrics JSON)`
- `backtests(job_id, symbol, created_at, summary JSON)`

## Tahmin Pipeline Aşamaları (WS olayları)

1. `veri` — OHLCV indirme/cache (Binance veya yfinance)
2. `istatistik` — quant-engine analizi (HMM, GARCH, STL, Monte Carlo)
3. `derin_ogrenme` — Bi-LSTM + Attention eğitimi + tahmini
4. `xgboost` — XGBoost hattı eğitimi + tahmini
5. `hakem` — Critic puanlama, diverjans, meta-learner, ensemble
6. `tamamlandi` — DuckDB yazımı + sonuç

## Determinizm ve LLM Yasağı

- Çalışma zamanında hiçbir LLM API'si veya modeli yoktur; tüm hesaplama PyTorch, sklearn,
  statsmodels, hmmlearn, arch üzerinden yerel ve deterministiktir (sabit tohumlar).
- Piyasa kapanışından sonra tekrarlanan aynı istek, aynı sonucu üretir (eğitim verisi
  değişmediği sürece).
