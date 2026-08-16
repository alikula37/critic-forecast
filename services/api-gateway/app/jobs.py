import json
import uuid

import httpx
import redis

from . import config
from .critic import ensembler, qra
from .data import provider
from .metrics.historical import compute_model_performance

_r = None
_rq_conn = None


def get_redis():
    global _r
    if _r is None:
        _r = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    return _r


def get_rq_conn():
    global _rq_conn
    if _rq_conn is None:
        _rq_conn = redis.Redis.from_url(config.REDIS_URL)
    return _rq_conn


def publish(job_id, stage, progress, message, payload=None):
    evt = {
        "job_id": job_id,
        "stage": stage,
        "progress": progress,
        "message": message,
        "payload": payload,
    }
    get_redis().publish(f"job:{job_id}", json.dumps(evt, default=str))
    get_redis().hset(f"jobstate:{job_id}", mapping={"state": "running", "stage": stage, "progress": progress})


def _finish(job_id, result, failed=False):
    key = f"jobstate:{job_id}"
    if failed:
        get_redis().hset(key, mapping={"state": "failed"})
        get_redis().publish(f"job:{job_id}", json.dumps({"job_id": job_id, "stage": "hata", "progress": 100, "message": str(result)}))
        return
    get_redis().hset(key, mapping={"state": "finished", "result": json.dumps(result, default=str)})
    get_redis().publish(
        f"job:{job_id}",
        json.dumps({"job_id": job_id, "stage": "tamamlandi", "progress": 100, "message": "Tahmin tamamlandı", "payload": result}, default=str),
    )


def _post(url, path, payload, timeout):
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url + path, json=payload)
        resp.raise_for_status()
        return resp.json()


def run_forecast(job_id, payload):
    symbol = payload["symbol"]
    interval = payload.get("interval", config.DEFAULT_INTERVAL)
    horizon = int(payload.get("horizon", config.DEFAULT_HORIZON))
    try:
        publish(job_id, "veri", 5, "Veri indiriliyor ve cache'leniyor...")
        points = provider.get_ohlcv(symbol, interval, config.MAX_BARS)
        if len(points) < config.MIN_BARS:
            raise RuntimeError(f"Yetersiz veri: {len(points)} bar")
        train_points = points[-config.TRAIN_BARS:]
        last_close = points[-1]["c"]
        import numpy as np

        closes = np.asarray([p["c"] for p in points], dtype=float)
        rets = np.abs(np.diff(np.log(closes)))
        ret_scale = float(np.mean(rets[-120:])) + 1e-12
        price_scale = float(np.mean(closes[-60:])) + 1e-12

        body = {"symbol": symbol, "interval": interval, "horizon": horizon, "points": train_points}

        publish(job_id, "istatistik", 15, "İstatistiksel hat: HMM + GARCH + STL + Monte Carlo...")
        quant = _post(config.QUANT_URL, "/analyze", body, 600)
        publish(job_id, "istatistik_ok", 35, "İstatistiksel hat tamamlandı.")
        if quant.get("regime_series"):
            body["regime_probs"] = [s["probs"] for s in quant["regime_series"]]

        publish(job_id, "derin_ogrenme", 40, "Bi-LSTM + Attention eğitiliyor (quantile)...")
        dl = _post(config.DEEP_LEARNING_URL, "/predict", body, 1800)
        publish(job_id, "xgboost", 60, "XGBoost hattı eğitiliyor...")
        publish(job_id, "hakem", 75, "Hakem motoru: puanlama, çelişki tespiti, ensemble...")

        models = dl["models"] + quant["models"]
        model_inputs = []
        for m in models:
            model_inputs.append(
                {
                    "model_id": m["model_id"],
                    "model_name": m["model_name"],
                    "line": m["line"],
                    "points": m["points"],
                    "up_probability": float(m.get("up_probability", 0.5)),
                    "performance": m.get("performance"),
                }
            )

        live_histories = _fetch_live_histories(symbol)
        current_regime = quant["regimes"]["current"]["label"]
        model_ids = [m["model_id"] for m in models]
        qra_weights = qra.build_qra_weights(symbol, interval, model_ids)
        try:
            realized_perf = compute_model_performance(symbol, interval)
        except Exception:
            realized_perf = None
        critic = ensembler.build_critic_state(
            model_inputs,
            price_scale,
            ret_scale,
            current_regime,
            live_histories,
            config.CRITIC_TEMPERATURE,
            qra_weights=qra_weights,
            realized_perf=realized_perf,
        )

        result = {
            "job_id": job_id,
            "symbol": symbol,
            "interval": interval,
            "horizon": horizon,
            "created_at": None,
            "last_close": last_close,
            "critic": critic,
            "regimes": quant["regimes"],
            "garch": quant["garch"],
            "seasonality": quant["seasonality"],
            "mc": quant["mc"],
            "raw_models": [
                {"model_id": m["model_id"], "model_name": m["model_name"], "line": m["line"], "points": m["points"], "up_probability": m.get("up_probability"), "performance": m.get("performance"), "details": m.get("details", {})}
                for m in models
            ],
        }
        _persist(symbol, interval, horizon, result, points)
        publish(job_id, "kayit", 95, "Sonuç DuckDB'ye yazıldı.")
        _finish(job_id, result)
        return result
    except Exception as e:
        _finish(job_id, f"{type(e).__name__}: {e}", failed=True)
        raise


def run_backtest(job_id, payload):
    symbol = payload["symbol"]
    interval = payload.get("interval", config.DEFAULT_INTERVAL)
    horizon = int(payload.get("horizon", config.DEFAULT_HORIZON))
    try:
        publish(job_id, "veri", 10, "Backtest verisi hazırlanıyor...")
        points = provider.get_ohlcv(symbol, interval, config.MAX_BARS)
        body = {"symbol": symbol, "interval": interval, "horizon": horizon, "points": points}
        publish(job_id, "istatistik", 35, "Walk-forward backtest: İstatistiksel hat...")
        quant = _post(config.QUANT_URL, "/analyze", body, 600)
        if quant.get("regime_series"):
            body["regime_probs"] = [s["probs"] for s in quant["regime_series"]]
        publish(job_id, "derin_ogrenme", 70, "Walk-forward backtest: Bi-LSTM...")
        dl = _post(config.DEEP_LEARNING_URL, "/predict", body, 1800)
        summary = {
            "models": [
                {"model_id": m["model_id"], "model_name": m["model_name"], "line": m["line"], "performance": m.get("performance")}
                for m in dl["models"] + quant["models"]
            ]
        }
        with httpx.Client(timeout=30) as client:
            client.post(
                f"{config.STORAGE_URL}/backtests",
                json={"job_id": job_id, "symbol": symbol, "summary": summary},
            )
        _finish(job_id, {"job_id": job_id, "symbol": symbol, "summary": summary})
        return summary
    except Exception as e:
        _finish(job_id, f"{type(e).__name__}: {e}", failed=True)
        raise


def run_strategy_backtest(job_id, payload):
    symbol = payload["symbol"]
    interval = payload.get("interval", config.DEFAULT_INTERVAL)
    strategy_id = payload["strategy_id"]
    params = payload.get("params", {})
    try:
        publish(job_id, "veri", 10, "Geçmiş veri ve tahmin konileri yükleniyor...")
        points = provider.get_ohlcv(symbol, interval, config.MAX_BARS)
        with httpx.Client(timeout=60) as client:
            resp = client.get(
                f"{config.STORAGE_URL}/results",
                params={"symbol": symbol, "interval": interval, "limit": 300, "include_backfilled": True},
            )
            if resp.status_code != 200:
                raise RuntimeError("Depolama servisine ulaşılamadı")
            rows = resp.json()
        cones = []
        regimes = {}
        full_regime_states = []
        signal_source = params.get("signal_source", "ensemble")
        for r in rows:
            payload = r["payload"]
            critic = payload.get("critic", {})
            regime = critic.get("current_regime")
            source_points = []
            if signal_source == "ensemble":
                source_points = critic.get("ensemble", {}).get("points", [])
            else:
                for m in payload.get("raw_models", []):
                    if m.get("model_id") == signal_source:
                        source_points = m.get("points", [])
                        break
            for p in source_points:
                cones.append({"date": p["date"], "p10": p.get("p10"), "p50": p.get("p50"), "p90": p.get("p90")})
                if regime:
                    regimes.setdefault(p["date"], regime)
            for s in payload.get("regimes", {}).get("states", []):
                full_regime_states.append((s["date"], s["state"]))
        if not full_regime_states:
            full_regime_states = sorted(regimes.items())
        for date, label in full_regime_states:
            regimes.setdefault(date[:10], label)
        if not cones:
            raise RuntimeError("Bu sembol için kayıtlı tahmin konisi yok — önce tahmin çalıştırın")
        publish(job_id, "backtest", 40, "VectorBT ile strateji backtesti çalışıyor...")
        body = {
            "symbol": symbol,
            "interval": interval,
            "strategy_id": strategy_id,
            "params": params,
            "points": points,
            "cones": cones,
            "regimes": regimes,
        }
        res = _post(config.QUANT_URL, "/backtest", body, 300)
        publish(job_id, "kayit", 85, "Sonuç DuckDB'ye yazılıyor...")
        with httpx.Client(timeout=30) as client:
            client.post(
                f"{config.STORAGE_URL}/strategies/backtests",
                json={
                    "job_id": job_id,
                    "symbol": symbol,
                    "interval": interval,
                    "strategy_id": strategy_id,
                    "params": params,
                    "metrics": res.get("metrics"),
                    "equity": res.get("equity", []),
                    "trades": res.get("trades", []),
                    "benchmark": res.get("benchmark", []),
                },
            )
        res["job_id"] = job_id
        res["symbol"] = symbol
        _finish(job_id, res)
        return res
    except Exception as e:
        _finish(job_id, f"{type(e).__name__}: {e}", failed=True)
        raise


def _cached_ohlcv(symbol, interval):
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            f"{config.STORAGE_URL}/data/ohlcv",
            params={"symbol": symbol, "interval": interval},
        )
        if resp.status_code != 200:
            raise RuntimeError(f"Depolama verisine ulaşılamadı ({symbol})")
        points = resp.json()
    if not points:
        raise RuntimeError(f"Cache'te {symbol} verisi yok — önce Panel'den veri yükleyin")
    return points


def run_backfill(job_id, payload):
    symbol = payload["symbol"]
    interval = payload.get("interval", config.DEFAULT_INTERVAL)
    horizon = int(payload.get("horizon", config.DEFAULT_HORIZON))
    days = int(payload.get("days", config.BACKFILL_DAYS))
    end_offset = int(payload.get("end_offset", 0))
    skip_wf = bool(payload.get("skip_wf", True))
    import numpy as np

    try:
        publish(job_id, "veri", 3, "Cache'ten geçmiş veri yükleniyor...")
        points = _cached_ohlcv(symbol, interval)
        all_dates = sorted({p["t"][:10] for p in points})
        if len(all_dates) < config.MIN_BARS:
            raise RuntimeError(f"Backfill için yetersiz veri: {len(all_dates)} bar")
        targets = all_dates[-(days + end_offset):-end_offset] if end_offset else all_dates[-days:]
        done = skipped = 0
        for i, d in enumerate(targets):
            pts_d = [p for p in points if p["t"][:10] <= d]
            if len(pts_d) < config.MIN_BARS:
                skipped += 1
                continue
            train_points = pts_d[-config.TRAIN_BARS:]
            closes = np.asarray([p["c"] for p in pts_d], dtype=float)
            rets = np.abs(np.diff(np.log(closes)))
            ret_scale = float(np.mean(rets[-120:])) + 1e-12
            price_scale = float(np.mean(closes[-60:])) + 1e-12
            body = {"symbol": symbol, "interval": interval, "horizon": horizon, "points": train_points}
            quant = _post(config.QUANT_URL, "/analyze", body, 600)
            if quant.get("regime_series"):
                body["regime_probs"] = [s["probs"] for s in quant["regime_series"]]
            body["skip_wf"] = skip_wf
            dl = _post(config.DEEP_LEARNING_URL, "/predict", body, 1800)
            models = dl["models"] + quant["models"]
            model_inputs = [
                {
                    "model_id": m["model_id"],
                    "model_name": m["model_name"],
                    "line": m["line"],
                    "points": m["points"],
                    "up_probability": float(m.get("up_probability", 0.5)),
                    "performance": m.get("performance"),
                }
                for m in models
            ]
            current_regime = quant["regimes"]["current"]["label"]
            critic = ensembler.build_critic_state(
                model_inputs, price_scale, ret_scale, current_regime, {}, config.CRITIC_TEMPERATURE
            )
            bjob = f"backfill_{symbol}_{d}"
            result = {
                "job_id": bjob,
                "symbol": symbol,
                "interval": interval,
                "horizon": horizon,
                "created_at": None,
                "last_close": pts_d[-1]["c"],
                "critic": critic,
                "regimes": quant["regimes"],
                "garch": quant["garch"],
                "seasonality": quant["seasonality"],
                "mc": quant["mc"],
                "raw_models": [
                    {"model_id": m["model_id"], "model_name": m["model_name"], "line": m["line"], "points": m["points"], "up_probability": m.get("up_probability"), "performance": m.get("performance"), "details": m.get("details", {})}
                    for m in models
                ],
            }
            _persist(symbol, interval, horizon, result, pts_d, backfilled=True, store_scores=False)
            done += 1
            publish(job_id, "backfill", 5 + int(90 * (i + 1) / max(len(targets), 1)), f"{d} tahmin edildi ({i + 1}/{len(targets)})")
        summary = {"job_id": job_id, "symbol": symbol, "days": done, "skipped": skipped}
        _finish(job_id, summary)
        return summary
    except Exception as e:
        _finish(job_id, f"{type(e).__name__}: {e}", failed=True)
        raise


def _fetch_live_histories(symbol):
    histories = {}
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{config.STORAGE_URL}/model-scores", params={"symbol": symbol, "limit": 200})
            if resp.status_code == 200:
                for e in resp.json():
                    histories.setdefault(e["model_id"], []).append(e)
    except Exception:
        pass
    return histories


def _persist(symbol, interval, horizon, result, points, backfilled=False, store_scores=True):
    critic = result["critic"]
    model_points = []
    for m in critic["models"]:
        raw = next((r for r in result["raw_models"] if r["model_id"] == m["model_id"]), None)
        if raw is not None:
            model_points.append({"model_id": m["model_id"], "points": raw["points"]})
    payload = {
        "job_id": result["job_id"],
        "symbol": symbol,
        "interval": interval,
        "horizon": horizon,
        "up_probability": critic["ensemble"]["up_probability"],
        "last_close": result["last_close"],
        "backfilled": backfilled,
        "points": critic["ensemble"]["points"],
        "critic": {
            "models": [
                {k: v for k, v in m.items() if k != "performance"}
                for m in critic["models"]
            ],
            "ensemble": critic["ensemble"],
            "consensus": critic["consensus"],
            "current_regime": critic["current_regime"],
        },
        "model_points": model_points,
    }
    with httpx.Client(timeout=60) as client:
        resp = client.post(f"{config.STORAGE_URL}/forecasts", json=payload)
        resp.raise_for_status()
    full = dict(result)
    full["data_range"] = {"bars": len(points), "start": points[0]["t"], "end": points[-1]["t"]}
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            f"{config.STORAGE_URL}/results",
            json={
                "job_id": result["job_id"],
                "symbol": symbol,
                "interval": interval,
                "horizon": horizon,
                "payload": full,
                "backfilled": backfilled,
            },
        )
        resp.raise_for_status()
    if not store_scores:
        return
    score_rows = [
        {
            "symbol": symbol,
            "model_id": m["model_id"],
            "score": m["score"],
            "weight": m["weight"],
            "metrics": {"confidence": m["confidence"], "divergence": m["divergence"], "up_probability": m["up_probability"]},
        }
        for m in critic["models"]
    ]
    with httpx.Client(timeout=60) as client:
        resp = client.post(f"{config.STORAGE_URL}/model-scores", json=score_rows)
        resp.raise_for_status()


def enqueue(job_type, payload, timeout=7200):
    job_id = str(uuid.uuid4())
    get_redis().hset(f"jobstate:{job_id}", mapping={"state": "queued", "stage": "kuyruk"})
    from rq import Queue

    q = Queue("forecast-jobs", connection=get_rq_conn())
    q.enqueue(job_type, job_id, payload, job_timeout=timeout, result_ttl=86400)
    return job_id


def find_cached(symbol, interval, horizon):
    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{config.STORAGE_URL}/results",
                params={"symbol": symbol, "interval": interval, "horizon": horizon, "limit": 1},
            )
            if resp.status_code != 200:
                return None
            rows = resp.json()
        if not rows:
            return None
        row = rows[0]
        row["payload"]["created_at"] = row["created_at"]
        return {"job_id": row["job_id"], "result": row["payload"]}
    except Exception:
        return None
