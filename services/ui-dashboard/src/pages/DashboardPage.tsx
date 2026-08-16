import React, { useCallback, useEffect, useRef, useState } from "react";
import { api, isNotFound, streamForecast } from "../api/client";
import { PriceChart } from "../components/chart/PriceChart";
import { CriticPanel } from "../components/critic/CriticPanel";
import { DetailExplorer } from "../components/detail/DetailExplorer";
import { GlassCard, ProgressBar, StatBlock } from "../components/layout/GlassCard";
import { MonteCarloPanel } from "../components/montecarlo/MonteCarloPanel";
import { ModelRaceTable } from "../components/race/ModelRaceTable";
import { SeasonalityPanel } from "../components/seasonality/SeasonalityPanel";
import { StrategyLab } from "../components/strategies/StrategyLab";
import type { Asset, ForecastResult, JobEvent, ModelPerf, OHLCV } from "../types";

const fmt = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 4 });

type Phase = "idle" | "running" | "done" | "cached" | "error";

export function DashboardPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [symbol, setSymbol] = useState("BTC");
  const [horizon, setHorizon] = useState(30);
  const [history, setHistory] = useState<OHLCV[]>([]);
  const [result, setResult] = useState<ForecastResult | null>(null);
  const [perf, setPerf] = useState<ModelPerf[]>([]);
  const [phase, setPhase] = useState<Phase>("idle");
  const [progress, setProgress] = useState(0);
  const [stageMsg, setStageMsg] = useState("");
  const [error, setError] = useState("");
  const [loadingHistory, setLoadingHistory] = useState(true);
  const [checkingCache, setCheckingCache] = useState(true);
  const [perfWarn, setPerfWarn] = useState(false);
  const [visibleModels, setVisibleModels] = useState<Set<string>>(new Set());
  const wsCloseRef = useRef<(() => void) | null>(null);
  const historyAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .assets()
      .then((a) => {
        if (!cancelled) setAssets(a);
      })
      .catch(() => {
        if (!cancelled) setError("Varlık listesi yüklenemedi — sunucuya erişilemiyor.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const loadHistory = useCallback(async (sym: string) => {
    historyAbortRef.current?.abort();
    const ctrl = new AbortController();
    historyAbortRef.current = ctrl;
    setLoadingHistory(true);
    try {
      const res = await api.history(sym, 3000, ctrl.signal);
      setHistory(res.points);
    } catch {
      if (ctrl.signal.aborted) return;
      setError("Geçmiş veri yüklenemedi — lütfen sayfayı yenileyin.");
    } finally {
      if (!ctrl.signal.aborted) setLoadingHistory(false);
    }
  }, []);

  useEffect(() => {
    wsCloseRef.current?.();
    wsCloseRef.current = null;
    historyAbortRef.current?.abort();
    setResult(null);
    setPerf([]);
    setPerfWarn(false);
    setPhase("idle");
    setError("");
    setVisibleModels(new Set());
    let cancelled = false;
    setCheckingCache(true);
    loadHistory(symbol);
    api
      .forecastLatest(symbol, horizon)
      .then((r) => {
        if (cancelled) return;
        setResult(r);
        setPhase("cached");
      })
      .catch((e) => {
        if (cancelled) return;
        if (!isNotFound(e)) {
          setError("Kayıtlı tahmin kontrol edilemedi — sunucuya erişilemiyor.");
        }
        setPhase("idle");
      })
      .finally(() => {
        if (!cancelled) setCheckingCache(false);
      });
    api
      .modelPerformance(symbol)
      .then((r) => {
        if (!cancelled) setPerf(r.models);
      })
      .catch(() => {
        if (!cancelled) setPerfWarn(true);
      });
    return () => {
      cancelled = true;
      wsCloseRef.current?.();
      wsCloseRef.current = null;
    };
  }, [symbol, horizon, loadHistory]);

  const startForecast = async () => {
    wsCloseRef.current?.();
    setPhase("running");
    setError("");
    setProgress(3);
    setStageMsg("İstek kuyruğa alındı...");
    try {
      const res = await api.forecast(symbol, horizon, true);
      if (res.cached && res.result) {
        setResult(res.result);
        setPhase("cached");
        setProgress(100);
        return;
      }
      const jobId = res.job_id;
      const onEvent = (ev: JobEvent) => {
        setProgress(ev.progress);
        setStageMsg(ev.message);
        if (ev.payload) {
          setResult(ev.payload);
          setVisibleModels(new Set());
          setPhase("done");
        }
      };
      wsCloseRef.current = streamForecast(
        jobId,
        onEvent,
        () => {
          api
            .job(jobId)
            .then((j) => {
              if (j.state === "finished" && j.result) {
                setResult(j.result);
                setPhase("done");
                setProgress(100);
              } else if (j.state === "failed") {
                setPhase("error");
                setError("Tahmin işlemi başarısız oldu. Konsola bakın.");
              }
            })
            .catch(() => {
              setPhase("error");
              setError("Sunucuya ulaşılamadı — tahmin durumu bilinmiyor. Sayfayı yenileyin.");
            });
        },
        (s) => {
          if (s === "connecting") setStageMsg("Sunucuya bağlanıyor...");
          else if (s === "open") setStageMsg("Bağlandı, tahmin sonucu bekleniyor...");
        }
      );
    } catch (e) {
      setPhase("error");
      setError(e instanceof Error ? e.message : "İstek başarısız");
    }
  };

  const toggleModel = (id: string) => {
    setVisibleModels((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const groups: Record<string, Asset[]> = { kripto: [], hisse: [], emtia: [] };
  for (const a of assets) groups[a.type].push(a);

  const last = history[history.length - 1];
  const change =
    last && history.length > 1
      ? ((last.c - history[history.length - 2].c) / history[history.length - 2].c) * 100
      : 0;

  return (
    <div className="mx-auto max-w-[1440px] space-y-6 px-6 py-8">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <div className="eyebrow mb-1">Kontrol Merkezi</div>
          <h1 className="text-3xl font-medium tracking-tight text-platinum">Tahminleme Konsolu</h1>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <label className="text-xs text-silver">
            <div className="eyebrow mb-1">Varlık</div>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              disabled={phase === "running"}
              className="rounded-md border border-white/20 bg-kelp px-4 py-2.5 text-sm text-platinum outline-none focus:border-teal"
            >
              {(["kripto", "hisse", "emtia"] as const).map((g) => (
                <optgroup key={g} label={{ kripto: "Kripto", hisse: "Hisse Senedi", emtia: "Emtia ETF" }[g]}>
                  {groups[g].map((a) => (
                    <option key={a.symbol} value={a.symbol}>
                      {a.symbol} — {a.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </label>
          <label className="text-xs text-silver">
            <div className="eyebrow mb-1">Ufuk (gün)</div>
            <select
              value={horizon}
              onChange={(e) => setHorizon(Number(e.target.value))}
              disabled={phase === "running"}
              className="rounded-md border border-white/20 bg-kelp px-4 py-2.5 text-sm text-platinum outline-none focus:border-teal"
            >
              {[7, 14, 30, 60, 90].map((h) => (
                <option key={h} value={h}>
                  {h} gün
                </option>
              ))}
            </select>
          </label>
          <button
            className="btn-primary mt-4"
            onClick={startForecast}
            disabled={phase === "running" || !history.length}
          >
            {phase === "running"
              ? "Çalışıyor..."
              : loadingHistory
                ? "Veri yükleniyor..."
                : phase === "cached" || phase === "done"
                  ? "Yeniden Tahmin Et"
                  : "Tahmini Başlat"}
          </button>
        </div>
      </div>

      {phase === "running" && (
        <div className="glass-deep p-5">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="pulse-glow text-mist">{stageMsg}</span>
            <span className="tabular text-silver">%{progress.toFixed(0)}</span>
          </div>
          <ProgressBar value={progress} color="linear-gradient(90deg,#2dd4bf,#fde9ff)" />
        </div>
      )}

      {phase === "cached" && result?.created_at && (
        <div className="glass-deep flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
          <span className="text-mist">
            <span className="mr-2 text-teal">●</span>Kayıtlı tahmin gösteriliyor —{" "}
            <b className="tabular text-platinum">
              {new Date(result.created_at).toLocaleString("tr-TR")}
            </b>{" "}
            tarihinde üretildi. Değişen piyasa koşulları için yeniden hesaplatabilirsiniz.
          </span>
          <button className="btn-ghost" onClick={startForecast}>
            Yeniden Hesapla
          </button>
        </div>
      )}

      {(phase === "error" || error) && (
        <div className="glass-deep border-danger/40 p-5 text-sm text-danger">
          {error || "Beklenmeyen bir hata oluştu."}
        </div>
      )}

      {loadingHistory ? (
        <div className="grid gap-6">
          <div className="glass p-4">
            <div className="skeleton h-8 w-56 rounded-md" />
            <div className="skeleton mt-4 h-64 w-full rounded-md" />
          </div>
          <div className="flex gap-8">
            <div className="skeleton h-14 w-40 rounded-md" />
            <div className="skeleton h-14 w-40 rounded-md" />
            <div className="skeleton h-14 w-40 rounded-md" />
          </div>
        </div>
      ) : (
        <>
          {last && (
            <div className="flex flex-wrap gap-8">
              <StatBlock label="Son Kapanış" value={fmt.format(last.c)} accent />
              <StatBlock label="Günlük Değişim" value={`%${change.toFixed(2)}`} sub="son bar" />
              <StatBlock label="Barlar" value={String(history.length)} sub="günlük, DB'den cache" />
            </div>
          )}

          {history.length > 0 && (
            <PriceChart
              history={history}
              regimes={result?.regimes.states ?? []}
              ensemble={result?.critic.ensemble.points ?? []}
              rawModels={result?.raw_models ?? []}
              visibleModels={visibleModels}
              onToggleModel={toggleModel}
            />
          )}

          {!result && checkingCache && (
            <div className="glass-deep p-4 text-center text-sm text-slate-deep">
              <span className="pulse-glow">Kayıtlı tahmin kontrol ediliyor...</span>
            </div>
          )}

          {!result && !checkingCache && (
            <div className="glass-deep p-6 text-center">
              <div className="eyebrow mb-2">Henüz Tahmin Yok</div>
              <p className="mx-auto max-w-xl text-sm text-slate-deep">
                Bu sembol için kayıtlı bir tahmin bulunamadı. "Tahmini Başlat" ile 6 model paralel
                eğitilir, hakem motoru birleştirir ve P10/P50/P90 konisi buraya çizilir.
              </p>
            </div>
          )}

          {result && perfWarn && (
            <div className="glass-deep p-3 text-xs text-silver">
              Canlı performans (F1) verisi alınamadı — sunucuya erişilemiyor. Tahmin ekranı
              etkilenmez.
            </div>
          )}
        </>
      )}

      {result && (
        <>
          <ModelRaceTable
            models={result.critic.models}
            rawModels={result.raw_models}
            perf={perf}
            visible={visibleModels}
            onToggle={toggleModel}
          />
          <CriticPanel critic={result.critic} />
          <div className="grid gap-6 xl:grid-cols-2">
            <MonteCarloPanel result={result} />
            <SeasonalityPanel result={result} />
          </div>
          <DetailExplorer result={result} perf={perf} />
        </>
      )}

      <StrategyLab symbol={symbol} />
    </div>
  );
}
