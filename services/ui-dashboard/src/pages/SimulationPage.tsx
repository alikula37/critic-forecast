import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  ColorType,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
  createChart,
} from "lightweight-charts";
import { api, isNotFound } from "../api/client";
import { GlassCard, StatBlock } from "../components/layout/GlassCard";
import type { Asset, ConePoint, ForecastResult } from "../types";

const fmt = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 4 });
const toTime = (iso: string): UTCTimestamp => Math.floor(Date.parse(iso) / 1000) as UTCTimestamp;

function pctAbove(edges: number[], counts: number[], x: number): number {
  if (!edges.length || !counts.length) return 0;
  const total = counts.reduce((a, b) => a + b, 0);
  if (total <= 0) return 0;
  if (x <= edges[0]) return 1;
  if (x >= edges[edges.length - 1]) return 0;
  let cum = 0;
  for (let i = 0; i < counts.length; i++) {
    const lo = edges[i];
    const hi = edges[i + 1];
    if (x <= hi) {
      const f = (x - lo) / Math.max(hi - lo, 1e-12);
      return 1 - (cum + counts[i] * f) / total;
    }
    cum += counts[i];
  }
  return 0;
}

const FAN_Q = { p05: -1.645, p95: 1.645 };

export function SimulationPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [symbol, setSymbol] = useState("BTC");
  const [horizon, setHorizon] = useState(30);
  const [result, setResult] = useState<ForecastResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sourceId, setSourceId] = useState("ensemble");
  const [targetPrice, setTargetPrice] = useState("");
  const [scenarioDays, setScenarioDays] = useState("10");
  const [selectedEnd, setSelectedEnd] = useState(30);
  const [assetsLoading, setAssetsLoading] = useState(true);
  const [assetsError, setAssetsError] = useState("");

  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const bandRef = useRef<{
    outer: ISeriesApi<"Area">;
    inner: ISeriesApi<"Area">;
    p05: ISeriesApi<"Line">;
    p95: ISeriesApi<"Line">;
    p50: ISeriesApi<"Line">;
  } | null>(null);
  const fittedRef = useRef(false);

  useEffect(() => {
    let cancelled = false;
    setAssetsLoading(true);
    api
      .assets()
      .then((a) => {
        if (!cancelled) setAssets(a);
      })
      .catch(() => {
        if (!cancelled) setAssetsError("Varlık listesi yüklenemedi — sunucuya erişilemiyor.");
      })
      .finally(() => {
        if (!cancelled) setAssetsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    setResult(null);
    api
      .forecastLatest(symbol, horizon)
      .then((r) => {
        if (cancelled) return;
        fittedRef.current = false;
        setResult(r);
        setSourceId("ensemble");
        setTargetPrice(String(r.last_close));
        setSelectedEnd(Math.min(30, r.horizon));
      })
      .catch((e) => {
        if (cancelled) return;
        setResult(null);
        setError(
          isNotFound(e)
            ? "Bu sembol için kayıtlı tahmin yok — önce Panel'den tahmin çalıştırın."
            : "Sunucuya ulaşılamadı — simülasyon verisi yüklenemedi."
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol, horizon]);

  const sourcePoints = useCallback((): ConePoint[] => {
    if (!result) return [];
    if (sourceId === "ensemble") return result.critic.ensemble.points;
    return result.raw_models.find((m) => m.model_id === sourceId)?.points ?? [];
  }, [result, sourceId]);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#c9dcda",
        fontFamily: "'Inter Tight Variable', sans-serif",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.07)" },
        horzLines: { color: "rgba(255,255,255,0.07)" },
      },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.18)" },
      timeScale: { borderColor: "rgba(255,255,255,0.18)", timeVisible: true },
      crosshair: {
        vertLine: { color: "rgba(233,252,251,0.35)", labelBackgroundColor: "#003734" },
        horzLine: { color: "rgba(233,252,251,0.35)", labelBackgroundColor: "#003734" },
      },
      autoSize: true,
    });
    chartRef.current = chart;
    const outer = chart.addAreaSeries({
      lineColor: "rgba(139,124,246,0.0)",
      topColor: "rgba(139,124,246,0.28)",
      bottomColor: "rgba(139,124,246,0.02)",
      priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
    });
    const inner = chart.addAreaSeries({
      lineColor: "rgba(1,38,36,0.0)",
      topColor: "rgba(1,38,36,0.85)",
      bottomColor: "rgba(1,38,36,0.95)",
      priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
    });
    const p05 = chart.addLineSeries({
      color: "rgba(139,124,246,0.55)",
      lineWidth: 1,
      lineStyle: 2,
      priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
    });
    const p95 = chart.addLineSeries({
      color: "rgba(139,124,246,0.55)",
      lineWidth: 1,
      lineStyle: 2,
      priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
    });
    const p50 = chart.addLineSeries({
      color: "#fde9ff",
      lineWidth: 3,
      priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
    });
    bandRef.current = { outer, inner, p05, p95, p50 };
    return () => {
      chart.remove();
      chartRef.current = null;
      bandRef.current = null;
      fittedRef.current = false;
    };
  }, []);

  useEffect(() => {
    const band = bandRef.current;
    const chart = chartRef.current;
    const pts = sourcePoints();
    if (!band || !chart) return;
    if (pts.length === 0) {
      band.outer.setData([]);
      band.inner.setData([]);
      band.p05.setData([]);
      band.p95.setData([]);
      band.p50.setData([]);
      return;
    }
    const data = pts.map((p) => {
      const sigma = Math.max((p.p90 - p.p10) / 2.56, 1e-12);
      return {
        time: toTime(p.date),
        p05: p.p50 + FAN_Q.p05 * sigma,
        p95: p.p50 + FAN_Q.p95 * sigma,
        p10: p.p10,
        p90: p.p90,
        p50: p.p50,
      };
    });
    band.outer.setData(data.map((d) => ({ time: d.time, value: d.p90 })));
    band.inner.setData(data.map((d) => ({ time: d.time, value: d.p10 })));
    band.p05.setData(data.map((d) => ({ time: d.time, value: d.p05 })));
    band.p95.setData(data.map((d) => ({ time: d.time, value: d.p95 })));
    band.p50.setData(data.map((d) => ({ time: d.time, value: d.p50 })));
    if (!fittedRef.current) {
      fittedRef.current = true;
      chart.timeScale().fitContent();
    }
  }, [sourcePoints]);

  const last = result?.last_close;
  const target = Number(targetPrice);
  const dist = result?.mc.distribution;
  const probAbove = last && dist && Number.isFinite(target)
    ? pctAbove(dist.edges, dist.counts, target)
    : null;
  const scenarioStep = Number(scenarioDays) || 10;
  const scenarioPoints: { date: string; p10: number; p50: number; p90: number; chg: number }[] = [];
  const pts = sourcePoints();
  if (last) {
    for (let i = scenarioStep - 1; i < pts.length; i += scenarioStep) {
      const p = pts[i];
      scenarioPoints.push({
        date: p.date,
        p10: p.p10,
        p50: p.p50,
        p90: p.p90,
        chg: ((p.p50 - last) / last) * 100,
      });
    }
    const endIdx = Math.min(selectedEnd, pts.length) - 1;
    if (endIdx >= 0) {
      const p = pts[endIdx];
      scenarioPoints.push({
        date: p.date,
        p10: p.p10,
        p50: p.p50,
        p90: p.p90,
        chg: ((p.p50 - last) / last) * 100,
      });
    }
    const seen = new Set<string>();
    scenarioPoints.sort((a, b) => a.date.localeCompare(b.date));
    const uniq = [];
    for (const s of scenarioPoints) {
      if (!seen.has(s.date)) {
        seen.add(s.date);
        uniq.push(s);
      }
    }
    scenarioPoints.length = 0;
    scenarioPoints.push(...uniq);
  }

  const groups: Record<string, Asset[]> = { kripto: [], hisse: [], emtia: [] };
  for (const a of assets) groups[a.type]?.push(a);

  return (
    <div className="mx-auto max-w-[1440px] space-y-6 px-6 py-8">
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <div className="eyebrow mb-1">Gelecek Simülasyonu</div>
          <h1 className="text-3xl font-medium tracking-tight text-platinum">Simülasyon Merkezi</h1>
        </div>
        <div className="flex flex-wrap items-center gap-4">
          <label className="text-xs text-silver">
            <div className="eyebrow mb-1">
              Varlık {assetsLoading && <span className="pulse-glow ml-2">yükleniyor...</span>}
            </div>
            <select
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              className="rounded-md border border-white/20 bg-kelp px-4 py-2.5 text-sm text-platinum outline-none focus:border-teal"
            >
              {(["kripto", "hisse", "emtia"] as const).map((g) => (
                <optgroup
                  key={g}
                  label={{ kripto: "Kripto", hisse: "Hisse Senedi", emtia: "Emtia ETF" }[g]}
                >
                  {groups[g]?.map((a) => (
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
              className="rounded-md border border-white/20 bg-kelp px-4 py-2.5 text-sm text-platinum outline-none focus:border-teal"
            >
              {[7, 14, 30, 60, 90].map((h) => (
                <option key={h} value={h}>
                  {h} gün
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      {loading && (
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
      )}

      {!loading && error && (
        <div className="glass-deep border-danger/40 p-5 text-sm text-danger">{error}</div>
      )}

      {!loading && !error && !result && (
        <div className="glass-deep p-6 text-center">
          <div className="eyebrow mb-2">Simülasyon Verisi Yok</div>
          <p className="mx-auto max-w-xl text-sm text-slate-deep">
            Bu sembol için kayıtlı tahmin bulunamadı. Panel sekmesinden tahmin çalıştırdıktan sonra
            senaryo ve olasılık analizleri burada görünür.
          </p>
        </div>
      )}

      {!loading && assetsError && !result && (
        <div className="glass-deep p-3 text-xs text-silver">
          {assetsError} — seçim için varsayılan sembol kullanılıyor.
        </div>
      )}

      <GlassCard title="Fan Chart — Olasılık Koridoru (P5–P95)" className="p-4">
        {result && (
          <div className="mb-3 flex flex-wrap items-center gap-3 text-xs text-silver">
            <label className="flex items-center gap-2">
              Kaynak
              <select
                value={sourceId}
                onChange={(e) => setSourceId(e.target.value)}
                className="rounded-md border border-white/20 bg-kelp px-2 py-1 text-[11px] text-platinum outline-none focus:border-teal"
              >
                <option value="ensemble">Hakem Konisi (ensamble)</option>
                {result.raw_models.map((m) => (
                  <option key={m.model_id} value={m.model_id}>
                    {m.model_name}
                  </option>
                ))}
              </select>
            </label>
            <span className="ml-auto">
              {result.critic.qra?.used ? (
                <span className="text-teal">
                  ● QRA ağırlıkları ({result.critic.qra.n} gerçekleşme)
                </span>
              ) : (
                <span>● Ağırlıklandırma: softmax + meta ayar</span>
              )}
            </span>
          </div>
        )}
        <div className="relative h-[300px]">
          <div ref={containerRef} className="absolute inset-0" />
          {!result && (
            <div className="absolute inset-0 flex items-center justify-center text-xs text-slate-deep">
              {loading ? (
                <span className="pulse-glow">Grafik yükleniyor...</span>
              ) : (
                "Tahmin yok — fan chart için önce Panel'den tahmin çalıştırın"
              )}
            </div>
          )}
        </div>
      </GlassCard>

      {!loading && !error && result && (
        <>
          <div className="flex flex-wrap gap-8">
            <StatBlock label="Son Kapanış" value={fmt.format(result.last_close)} accent />
            <StatBlock
              label="Ensemble Yükseliş Olasılığı"
              value={`%${(result.critic.ensemble.up_probability * 100).toFixed(1)}`}
              sub="hakem ağırlıklı"
            />
            <StatBlock
              label="MC Yükseliş Olasılığı"
              value={`%${(result.mc.up_probability * 100).toFixed(1)}`}
              sub="monte carlo"
            />
            <StatBlock
              label="Ensemble Güveni"
              value={`%${(result.critic.ensemble.confidence * 100).toFixed(1)}`}
              sub={`${result.critic.current_regime} rejimi`}
            />
            <StatBlock
              label="Ufuk Sonu (P50)"
              value={fmt.format(
                result.critic.ensemble.points[result.critic.ensemble.points.length - 1]?.p50
              )}
              sub={`${result.horizon} gün`}
            />
          </div>

          <div className="grid gap-6 xl:grid-cols-2">
            <GlassCard title="Olasılık Hesap Makinesi" className="p-4">
              <div className="flex flex-wrap items-end gap-3">
                <label className="flex-1 text-xs text-silver">
                  <div className="eyebrow mb-1">
                    Ufuk sonunda (T={result.horizon} gün) fiyatın üzerinde kalma olasılığı
                  </div>
                  <input
                    type="number"
                    value={targetPrice}
                    onChange={(e) => setTargetPrice(e.target.value)}
                    className="w-full rounded-md border border-white/20 bg-kelp px-4 py-2.5 text-sm tabular text-platinum outline-none focus:border-teal"
                  />
                </label>
                <button
                  className="btn-ghost"
                  onClick={() => setTargetPrice(String(result.last_close))}
                >
                  Son Kapanış
                </button>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-4">
                <div className="glass-deep p-4 text-center">
                  <div className="eyebrow mb-1">Üstünde Kalma</div>
                  <div className="text-3xl font-medium tabular text-teal">
                    {probAbove !== null ? `%${(probAbove * 100).toFixed(1)}` : "—"}
                  </div>
                </div>
                <div className="glass-deep p-4 text-center">
                  <div className="eyebrow mb-1">Altında Kalma</div>
                  <div className="text-3xl font-medium tabular text-danger">
                    {probAbove !== null ? `%${((1 - probAbove) * 100).toFixed(1)}` : "—"}
                  </div>
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[11px] text-silver">
                <span>Ort. final: <b className="tabular text-platinum">{fmt.format(result.mc.stats.mean_final)}</b></span>
                <span>Std: <b className="tabular text-platinum">{fmt.format(result.mc.stats.std_final)}</b></span>
                <span>VaR%1: <b className="tabular text-platinum">{fmt.format(result.mc.stats.var_1)}</b></span>
                <span>CVaR%5: <b className="tabular text-platinum">{fmt.format(result.mc.stats.cvar_5)}</b></span>
              </div>
            </GlassCard>

            <GlassCard title="Senaryo Tablosu" className="p-4">
              <div className="mb-3 flex flex-wrap items-center gap-3 text-xs text-silver">
                <label className="flex items-center gap-2">
                  Adım (gün)
                  <select
                    value={scenarioDays}
                    onChange={(e) => setScenarioDays(e.target.value)}
                    className="rounded-md border border-white/20 bg-kelp px-2 py-1 text-[11px] text-platinum outline-none focus:border-teal"
                  >
                    {["5", "10", "15", "30"].map((s) => (
                      <option key={s} value={s}>
                        her {s} gün
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex items-center gap-2">
                  Ufuk sonu gün
                  <select
                    value={selectedEnd}
                    onChange={(e) => setSelectedEnd(Number(e.target.value))}
                    className="rounded-md border border-white/20 bg-kelp px-2 py-1 text-[11px] text-platinum outline-none focus:border-teal"
                  >
                    {[10, 20, 30, 60, 90]
                      .filter((d) => d <= result.horizon)
                      .map((d) => (
                        <option key={d} value={d}>
                          {d}
                        </option>
                      ))}
                  </select>
                </label>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b border-white/10 text-left text-silver">
                      <th className="py-2 pr-3 font-medium">Tarih</th>
                      <th className="py-2 pr-3 font-medium">P10</th>
                      <th className="py-2 pr-3 font-medium">P50</th>
                      <th className="py-2 pr-3 font-medium">P90</th>
                      <th className="py-2 font-medium">P50 Değişim</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scenarioPoints.map((s) => (
                      <tr key={s.date} className="border-b border-white/5">
                        <td className="py-2 pr-3 text-platinum">
                          {new Date(s.date).toLocaleDateString("tr-TR", {
                            day: "2-digit",
                            month: "short",
                            year: "numeric",
                          })}
                        </td>
                        <td className="py-2 pr-3 tabular">{fmt.format(s.p10)}</td>
                        <td className="py-2 pr-3 tabular text-platinum">{fmt.format(s.p50)}</td>
                        <td className="py-2 pr-3 tabular">{fmt.format(s.p90)}</td>
                        <td
                          className={`py-2 tabular font-medium ${
                            s.chg >= 0 ? "text-teal" : "text-danger"
                          }`}
                        >
                          %{s.chg >= 0 ? "+" : ""}
                          {s.chg.toFixed(2)}
                        </td>
                      </tr>
                    ))}
                    {scenarioPoints.length === 0 && (
                      <tr>
                        <td colSpan={5} className="py-4 text-center text-slate-deep">
                          Senaryo noktası yok — kaynak seçimini değiştirin.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </GlassCard>
          </div>
        </>
      )}
    </div>
  );
}
