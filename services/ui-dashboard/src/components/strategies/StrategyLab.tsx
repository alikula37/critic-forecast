import React, { useCallback, useEffect, useRef, useState } from "react";
import { ColorType, type IChartApi, type ISeriesApi, type UTCTimestamp, createChart } from "lightweight-charts";
import { api } from "../../api/client";
import { MODEL_NAMES } from "../../types";
import type { StrategyBacktest, StrategyCatalogItem, StrategyParamDef } from "../../types";
import { ProgressBar } from "../layout/GlassCard";

const fmt = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2 });
const pct = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 2, style: "percent" });
const toTime = (iso: string): UTCTimestamp => Math.floor(Date.parse(iso) / 1000) as UTCTimestamp;

const SOURCES = [
  "ensemble",
  "bilstm_attention",
  "xgboost_quantile",
  "lightgbm_quantile",
  "monte_carlo",
  "ets_baseline",
  "stl_seasonality",
];

const sourceName = (id: string) =>
  id === "ensemble" ? "Kritik (Ensemble)" : MODEL_NAMES[id] ?? id;

const defaultsFor = (catalog: StrategyCatalogItem[], id: string): Record<string, number | string> => {
  const s = catalog.find((c) => c.strategy_id === id);
  if (!s) return {};
  const out: Record<string, number | string> = {};
  for (const [k, v] of Object.entries(s.params)) out[k] = v.default;
  return out;
};

function ParamControl({
  name,
  def,
  value,
  onChange,
  disabled,
}: {
  name: string;
  def: StrategyParamDef;
  value: number | string;
  onChange: (v: number | string) => void;
  disabled: boolean;
}) {
  const val = typeof value === "string" ? parseFloat(value) : value;
  const label = def.label;
  if (def.type === "select" && def.options) {
    return (
      <label className="block text-xs text-silver">
        <div className="eyebrow mb-1">{label}</div>
        <select
          value={String(value)}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className="w-full rounded-md border border-white/20 bg-kelp px-3 py-2 text-sm text-platinum outline-none focus:border-teal"
        >
          {def.options.map((o) => (
            <option key={o} value={o}>
              {o === "flat" ? "Yüzde (%)" : o === "per_trade" ? "Sabit ücret (işlem başına)" : sourceName(o)}
            </option>
          ))}
        </select>
      </label>
    );
  }
  return (
    <label className="block text-xs text-silver">
      <div className="eyebrow mb-1">{label}</div>
      <input
        type="range"
        min={def.min}
        max={def.max}
        step={def.step}
        value={val}
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={disabled}
        className="w-full accent-teal"
      />
      <span className="tabular text-sm text-platinum">
        {name === "fees"
          ? `%${(val * 100).toFixed(2)}`
          : name === "slippage_bps"
            ? `${val} bps`
            : name === "max_position"
              ? `%${(val * 100).toFixed(0)}`
              : val}
      </span>
    </label>
  );
}

function EquityChart({ record }: { record: StrategyBacktest }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const stratRef = useRef<ISeriesApi<"Line"> | null>(null);
  const benchRef = useRef<ISeriesApi<"Line"> | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#c9dcda",
        fontFamily: "'Inter Tight Variable', sans-serif",
        fontSize: 11,
      },
      grid: { vertLines: { color: "rgba(255,255,255,0.07)" }, horzLines: { color: "rgba(255,255,255,0.07)" } },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.18)" },
      timeScale: { borderColor: "rgba(255,255,255,0.18)" },
      crosshair: { vertLine: { color: "rgba(233,252,251,0.35)", labelBackgroundColor: "#003734" } },
      autoSize: true,
    });
    chartRef.current = chart;
    stratRef.current = chart.addLineSeries({ color: "#2dd4bf", lineWidth: 2, priceFormat: { type: "price", precision: 2, minMove: 0.01 } });
    benchRef.current = chart.addLineSeries({ color: "#8b7cf6", lineWidth: 1, lineStyle: 2, priceFormat: { type: "price", precision: 2, minMove: 0.01 } });
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current) return;
    stratRef.current?.setData(
      record.equity.map((p) => ({ time: toTime(p.date), value: p.value }))
    );
    benchRef.current?.setData(
      (record.benchmark.length ? record.benchmark : []).map((p) => ({
        time: toTime(p.date),
        value: p.value,
      }))
    );
    chartRef.current.timeScale().fitContent();
  }, [record]);

  return <div ref={containerRef} className="h-64 w-full" />;
}

function MetricCell({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div>
      <div className="eyebrow mb-1">{label}</div>
      <div className={`tabular text-lg font-medium ${good ? "text-teal" : "text-platinum"}`}>{value}</div>
    </div>
  );
}

export function StrategyLab({ symbol }: { symbol: string }) {
  const [catalog, setCatalog] = useState<StrategyCatalogItem[]>([]);
  const [records, setRecords] = useState<StrategyBacktest[]>([]);
  const [selected, setSelected] = useState<string>("cone_trend");
  const [params, setParams] = useState<Record<string, number | string>>({});
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [stageMsg, setStageMsg] = useState("");
  const [error, setError] = useState("");
  const [catError, setCatError] = useState("");
  const [recordsLoading, setRecordsLoading] = useState(false);
  const [backfillMsg, setBackfillMsg] = useState("");
  const bulkRef = useRef(false);
  const pollRef = useRef<number | null>(null);

  const startBackfill = async () => {
    setBackfillMsg("");
    setError("");
    try {
      const res = await api.backfill(symbol, 60);
      setBackfillMsg(
        `Geçmiş koni üretimi başladı (${res.job_id.slice(0, 8)}…) — 60 gün için ~1 saat sürer.`
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Backfill başlatılamadı");
    }
  };

  const loadCatalog = () => {
    setCatError("");
    api
      .strategiesCatalog()
      .then((cat) => {
        setCatalog(cat);
        setParams(defaultsFor(cat, selected));
      })
      .catch(() => setCatError("Strateji kataloğu yüklenemedi — sunucuya erişilemiyor."));
  };

  useEffect(() => {
    loadCatalog();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    return () => {
      if (pollRef.current != null) window.clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, []);

  const recordsSeqRef = useRef(0);

  const loadRecords = useCallback(() => {
    const seq = ++recordsSeqRef.current;
    setRecordsLoading(true);
    api
      .strategyBacktests(symbol)
      .then((r) => {
        if (seq === recordsSeqRef.current) setRecords(r);
      })
      .catch(() => {
        if (seq === recordsSeqRef.current)
          setError("Backtest kayıtları yüklenemedi — sunucuya erişilemiyor.");
      })
      .finally(() => {
        if (seq === recordsSeqRef.current) setRecordsLoading(false);
      });
  }, [symbol]);

  useEffect(() => {
    setRecords([]);
    loadRecords();
  }, [loadRecords]);

  const selectStrategy = (id: string) => {
    setSelected(id);
    setParams(defaultsFor(catalog, id));
  };

  const setParam = (name: string, v: number | string) => {
    setParams((prev) => ({ ...prev, [name]: v }));
  };

  const run = async (sourceOverride?: string) => {
    setRunning(true);
    setError("");
    setProgress(3);
    setStageMsg("İstek kuyruğa alındı...");
    try {
      const effective = sourceOverride
        ? { ...params, signal_source: sourceOverride }
        : params;
      const res = await api.strategyBacktest(symbol, selected, effective);
      const jobId = res.job_id;
      await new Promise<void>((resolve, reject) => {
        const timer = window.setInterval(async () => {
          try {
            const j = await api.job(jobId);
            setProgress(Number(j.progress ?? 0));
            setStageMsg(j.stage ?? "");
            if (j.state === "finished") {
              window.clearInterval(timer);
              resolve();
            } else if (j.state === "failed") {
              window.clearInterval(timer);
              reject(new Error("Backtest başarısız oldu"));
            }
          } catch (e) {
            window.clearInterval(timer);
            reject(e instanceof Error ? e : new Error("İstek başarısız"));
          }
        }, 2000);
        pollRef.current = timer;
      });
      await loadRecords();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Backtest başarısız");
    } finally {
      if (!bulkRef.current) setRunning(false);
    }
  };

  const runAllSources = async () => {
    bulkRef.current = true;
    setRunning(true);
    setError("");
    try {
      for (const src of SOURCES) {
        await run(src);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Karşılaştırma başarısız");
    } finally {
      bulkRef.current = false;
      setRunning(false);
    }
  };

  const selectedCatalog = catalog.find((c) => c.strategy_id === selected);
  const selectedRecord = records.find((r) => r.strategy_id === selected) ?? null;

  const comparison = SOURCES.map((src) => {
    const recs = records.filter((r) => r.strategy_id === selected && r.params.signal_source === src);
    return { source: src, record: recs[0] ?? null };
  }).filter((c) => c.record?.metrics);
  const bestReturn = Math.max(...comparison.map((c) => c.record!.metrics!.total_return ?? -Infinity), -Infinity);

  return (
    <div className="glass overflow-hidden">
      <div className="border-b border-white/15 px-6 py-4">
        <div className="eyebrow mb-1">VectorBT — Strateji Laboratuvarı</div>
        <h2 className="text-xl font-medium tracking-tight text-platinum">Tahmin Konisi ile Strateji Backtesti</h2>
        <p className="mt-1 text-xs text-slate-deep">
          Kayıtlı tahmin konileri (P10/P50/P90) sinyal kaynağı olarak kullanılır; komisyon, slippage ve risk
          kısıtları dahil gerçekçi performans buy&amp;hold ile karşılaştırılır. Sonuçlar DuckDB'de saklanır.
        </p>
      </div>

      <div className="grid gap-6 p-6 lg:grid-cols-3">
        <div className="space-y-3">
          {catError && (
            <div className="rounded-md border border-danger/40 p-3 text-xs text-danger">
              {catError}
              <button className="ml-2 underline" onClick={loadCatalog}>
                Tekrar dene
              </button>
            </div>
          )}
          {!catError && catalog.length === 0 && (
            <div className="skeleton h-24 w-full rounded-lg" />
          )}
          {catalog.map((s) => (
            <button
              key={s.strategy_id}
              onClick={() => selectStrategy(s.strategy_id)}
              disabled={running}
              className={`w-full rounded-lg border p-4 text-left transition-colors ${
                selected === s.strategy_id
                  ? "border-teal/70 bg-teal/10"
                  : "border-white/15 bg-kelp hover:border-white/30"
              }`}
            >
              <div className="mb-1 flex items-center justify-between">
                <span className="text-sm font-medium text-platinum">{s.name}</span>
                <span className="text-[10px] text-teal">{s.strategy_id}</span>
              </div>
              <p className="text-xs leading-relaxed text-slate-deep">{s.description}</p>
            </button>
          ))}
        </div>

        <div className="space-y-4">
          {selectedCatalog &&
            Object.entries(selectedCatalog.params).map(([name, def]) => (
              <ParamControl
                key={name}
                name={name}
                def={def}
                value={params[name] ?? def.default}
                onChange={(v) => setParam(name, v)}
                disabled={running}
              />
            ))}
          <button className="btn-primary w-full" onClick={() => run()} disabled={running}>
            {running ? "Çalışıyor..." : "Stratejiyi Backtest Et"}
          </button>
          <button
            className="btn-ghost w-full"
            onClick={runAllSources}
            disabled={running}
          >
            {running ? "Çalışıyor..." : "Tüm Modelleri Karşılaştır (7 kaynak)"}
          </button>
          <button
            className="btn-ghost w-full !text-[11px]"
            onClick={startBackfill}
            disabled={running || !!backfillMsg}
            title="Geçmiş 60 iş günü için tahmin konilerini yeniden üretir — backtest kapsamını ve QRA verisini büyütür"
          >
            {backfillMsg ? "Backfill çalışıyor (arkada)..." : "Geçmiş Konileri Doldur (60 gün)"}
          </button>
          {backfillMsg && (
            <p className="rounded-md border border-teal/30 bg-teal/5 p-3 text-[11px] leading-relaxed text-mist">
              {backfillMsg}
            </p>
          )}
          {running && (
            <div>
              <div className="mb-1 flex justify-between text-xs">
                <span className="pulse-glow text-mist">{stageMsg}</span>
                <span className="tabular text-silver">%{progress.toFixed(0)}</span>
              </div>
              <ProgressBar value={progress} color="linear-gradient(90deg,#2dd4bf,#8b7cf6)" />
            </div>
          )}
          {error && <div className="rounded-md border border-danger/40 p-3 text-xs text-danger">{error}</div>}
          {recordsLoading && !running && (
            <div className="flex items-center gap-2 text-xs text-slate-deep">
              <span className="pulse-glow">Backtest kayıtları yükleniyor...</span>
            </div>
          )}
          {!records.length && !running && !recordsLoading && (
            <p className="text-xs text-slate-deep">
              Henüz sonuç yok. İlk backtesti başlatın — sinyaller bu sembolün kayıtlı tahmin konilerinden
              üretilir.
            </p>
          )}
        </div>

        <div className="grid content-start grid-cols-2 gap-3">
          <MetricCell
            label="Toplam Getiri"
            value={selectedRecord?.metrics?.total_return != null ? pct.format(selectedRecord.metrics.total_return) : "—"}
            good={!!(selectedRecord?.metrics?.total_return != null && selectedRecord.metrics.total_return > 0)}
          />
          <MetricCell
            label="Buy & Hold"
            value={selectedRecord?.metrics?.benchmark_return != null ? pct.format(selectedRecord.metrics.benchmark_return) : "—"}
          />
          <MetricCell
            label="Sharpe"
            value={selectedRecord?.metrics?.sharpe != null ? fmt.format(selectedRecord.metrics.sharpe) : "—"}
            good={!!(selectedRecord?.metrics?.sharpe != null && selectedRecord.metrics.sharpe > 1)}
          />
          <MetricCell
            label="Max Drawdown"
            value={selectedRecord?.metrics?.max_drawdown != null ? pct.format(selectedRecord.metrics.max_drawdown) : "—"}
          />
          <MetricCell
            label="Alpha (yıllık)"
            value={selectedRecord?.metrics?.alpha != null ? `${(selectedRecord.metrics.alpha * 100).toFixed(2)}%` : "—"}
            good={!!(selectedRecord?.metrics?.alpha != null && selectedRecord.metrics.alpha > 0)}
          />
          <MetricCell
            label="Beta (vs B&H)"
            value={selectedRecord?.metrics?.beta != null ? fmt.format(selectedRecord.metrics.beta) : "—"}
          />
          <MetricCell
            label="Kazanma Oranı"
            value={selectedRecord?.metrics?.win_rate != null ? pct.format(selectedRecord.metrics.win_rate) : "—"}
          />
          <MetricCell
            label="İşlem"
            value={selectedRecord?.metrics?.n_trades != null ? String(selectedRecord.metrics.n_trades) : "—"}
          />
          <MetricCell
            label="Profit Factor"
            value={selectedRecord?.metrics?.profit_factor != null ? fmt.format(selectedRecord.metrics.profit_factor) : "—"}
          />
          <MetricCell
            label="Pozisyon Süresi"
            value={selectedRecord?.metrics?.coverage != null ? pct.format(selectedRecord.metrics.coverage) : "—"}
          />
        </div>
      </div>

      {comparison.length > 1 && (
        <div className="border-t border-white/15 p-6">
          <div className="eyebrow mb-3">Model Karşılaştırması — {selectedCatalog?.name}</div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="text-left text-xs text-silver">
                  <th className="py-2 pr-4">Sinyal Kaynağı</th>
                  <th className="py-2 pr-4">Getiri</th>
                  <th className="py-2 pr-4">Sharpe</th>
                  <th className="py-2 pr-4">Alpha</th>
                  <th className="py-2 pr-4">Beta</th>
                  <th className="py-2 pr-4">Max DD</th>
                  <th className="py-2 pr-4">İşlem</th>
                  <th className="py-2 pr-4">Kapsam</th>
                </tr>
              </thead>
              <tbody>
                {comparison.map(({ source, record }) => {
                  const m = record!.metrics!;
                  const isBest = m.total_return != null && m.total_return === bestReturn;
                  return (
                    <tr key={source} className="border-t border-white/10">
                      <td className="py-2 pr-4">
                        <span className="flex items-center gap-2">
                          <span
                            className="inline-block h-2.5 w-2.5 rounded-full"
                            style={{ background: source === "ensemble" ? "#2dd4bf" : MODEL_NAMES[source] ? "#8b7cf6" : "#f5a97f" }}
                          />
                          <span className={`font-medium ${isBest ? "text-teal" : "text-platinum"}`}>
                            {sourceName(source)}
                          </span>
                        </span>
                      </td>
                      <td className={`tabular py-2 pr-4 ${isBest ? "text-teal" : "text-platinum"}`}>
                        {m.total_return != null ? pct.format(m.total_return) : "—"}
                      </td>
                      <td className="tabular py-2 pr-4 text-platinum">{m.sharpe != null ? fmt.format(m.sharpe) : "—"}</td>
                      <td className="tabular py-2 pr-4 text-platinum">
                        {m.alpha != null ? `${(m.alpha * 100).toFixed(2)}%` : "—"}
                      </td>
                      <td className="tabular py-2 pr-4 text-platinum">{m.beta != null ? fmt.format(m.beta) : "—"}</td>
                      <td className="tabular py-2 pr-4 text-platinum">
                        {m.max_drawdown != null ? pct.format(m.max_drawdown) : "—"}
                      </td>
                      <td className="tabular py-2 pr-4 text-platinum">{m.n_trades}</td>
                      <td className="tabular py-2 pr-4 text-platinum">
                        {m.coverage != null ? pct.format(m.coverage) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {selectedRecord?.equity.length ? (
        <div className="border-t border-white/15 p-6">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="eyebrow mb-1">Equity Eğrisi — son çalıştırma</div>
              <span className="text-xs text-slate-deep">
                {new Date(selectedRecord.created_at).toLocaleString("tr-TR")}
                {selectedRecord.metrics?.slippage_bps
                  ? ` · slippage ${selectedRecord.metrics.slippage_bps} bps`
                  : ""}
                {selectedRecord.metrics?.max_position && selectedRecord.metrics.max_position < 1
                  ? ` · max poz ${(selectedRecord.metrics.max_position * 100).toFixed(0)}%`
                  : ""}
              </span>
            </div>
            <div className="flex gap-4 text-xs text-silver">
              <span>
                <span className="mr-1 inline-block h-2 w-2 rounded-full bg-teal" />
                Strateji
              </span>
              <span>
                <span className="mr-1 inline-block h-2 w-2 rounded-full bg-[#8b7cf6]" />
                Buy & Hold
              </span>
            </div>
          </div>
          <EquityChart record={selectedRecord} />
          {selectedRecord.trades.length > 0 && (
            <details className="mt-4">
              <summary className="cursor-pointer text-xs text-silver hover:text-mist">
                Son {selectedRecord.trades.length} işlem
              </summary>
              <div className="mt-2 max-h-48 overflow-y-auto rounded-lg border border-white/15">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-kelp text-silver">
                    <tr>
                      <th className="px-3 py-2 text-left">Giriş</th>
                      <th className="px-3 py-2 text-left">Çıkış</th>
                      <th className="px-3 py-2 text-right">Getiri</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedRecord.trades.map((t, i) => (
                      <tr key={i} className="border-t border-white/10">
                        <td className="tabular px-3 py-1.5 text-platinum">{t.entry ?? "—"}</td>
                        <td className="tabular px-3 py-1.5 text-platinum">{t.exit ?? "açık"}</td>
                        <td
                          className={`tabular px-3 py-1.5 text-right ${
                            t.return != null && t.return > 0 ? "text-teal" : "text-danger"
                          }`}
                        >
                          {t.return != null ? `${(t.return * 100).toFixed(2)}%` : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          )}
        </div>
      ) : null}
    </div>
  );
}
