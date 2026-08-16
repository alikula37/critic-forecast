import React, { useEffect, useRef, useState } from "react";
import {
  ColorType,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type UTCTimestamp,
  createChart,
} from "lightweight-charts";
import type { ConePoint, OHLCV, RawModel, RegimePoint } from "../../types";
import { MODEL_COLORS, REGIME_COLORS } from "../../types";

const toTime = (iso: string): UTCTimestamp => Math.floor(Date.parse(iso) / 1000) as UTCTimestamp;

const fmt = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 4 });

type ViewMode = "konisi" | "model" | "tumu";

export function PriceChart({
  history,
  regimes,
  ensemble,
  rawModels,
  visibleModels,
  onToggleModel,
}: {
  history: OHLCV[];
  regimes: RegimePoint[];
  ensemble: ConePoint[];
  rawModels: RawModel[];
  visibleModels: Set<string>;
  onToggleModel?: (id: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const bgRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const futureBgRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const bandRef = useRef<{
    p90: ISeriesApi<"Area">;
    p10: ISeriesApi<"Area">;
    p50: ISeriesApi<"Line">;
  } | null>(null);
  const modelBandRef = useRef<{
    p90: ISeriesApi<"Area">;
    p10: ISeriesApi<"Area">;
    p50: ISeriesApi<"Line">;
  } | null>(null);
  const lineRef = useRef<Record<string, ISeriesApi<"Line">>>({});
  const priceLineRef = useRef<ReturnType<ISeriesApi<"Candlestick">["createPriceLine"]> | null>(null);
  const fittedRef = useRef(false);
  const coneFitKeyRef = useRef("");
  const lastHistoryKeyRef = useRef("");
  const [viewMode, setViewMode] = useState<ViewMode>("konisi");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [tip, setTip] = useState<string>("");
  const [tipX, setTipX] = useState(0);
  const [tipY, setTipY] = useState(0);
  const [todayX, setTodayX] = useState<number | null>(null);

  const ensembleRef = useRef(ensemble);
  ensembleRef.current = ensemble;
  const historyRef = useRef(history);
  historyRef.current = history;
  const rawModelsRef = useRef(rawModels);
  rawModelsRef.current = rawModels;
  const viewRef = useRef(viewMode);
  viewRef.current = viewMode;

  const updateTodayX = useRef<() => void>(() => {});
  updateTodayX.current = () => {
    const chart = chartRef.current;
    const h = historyRef.current;
    if (!chart || h.length === 0) return;
    const coord = chart.timeScale().timeToCoordinate(toTime(h[h.length - 1].t));
    setTodayX(coord);
  };

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
      rightPriceScale: {
        borderColor: "rgba(255,255,255,0.18)",
      },
      timeScale: {
        borderColor: "rgba(255,255,255,0.18)",
        timeVisible: true,
      },
      crosshair: {
        vertLine: { color: "rgba(233,252,251,0.35)", labelBackgroundColor: "#003734" },
        horzLine: { color: "rgba(233,252,251,0.35)", labelBackgroundColor: "#003734" },
      },
      autoSize: true,
    });
    chartRef.current = chart;

    const bgScale = chart.priceScale("background");
    bgScale.applyOptions({ scaleMargins: { top: 0.92, bottom: 0 }, visible: false });
    const bg = chart.addHistogramSeries({
      priceScaleId: "background",
      priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
      lastValueVisible: false,
      priceLineVisible: false,
    });
    bgRef.current = bg;

    const futureBg = chart.addHistogramSeries({
      priceScaleId: "background",
      priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
      lastValueVisible: false,
      priceLineVisible: false,
    });
    futureBgRef.current = futureBg;

    const candles = chart.addCandlestickSeries({
      upColor: "#2dd4bf",
      downColor: "#ff6b81",
      borderUpColor: "#2dd4bf",
      borderDownColor: "#ff6b81",
      wickUpColor: "#2dd4bf",
      wickDownColor: "#ff6b81",
      priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
    });
    candlesRef.current = candles;

    const onMove = (param: MouseEventParams) => {
      if (!param.time || !param.seriesData) return;
      const iso = new Date((param.time as number) * 1000).toISOString().slice(0, 10);
      const candle = param.seriesData.get(candles);
      const forecastDay = ensembleRef.current.find((e) => e.date.slice(0, 10) === iso);
      let html = `<b>${iso}</b>`;
      if (candle && "close" in candle) {
        const c = candle as { open: number; high: number; low: number; close: number };
        html += `<br>Açılış ${fmt.format(c.open)} · Kapanış <b>${fmt.format(c.close)}</b>`;
      }
      if (forecastDay) {
        html += `<br><span style="color:#fde9ff">P10 ${fmt.format(forecastDay.p10)}</span>`;
        html += `<br><span style="color:#fde9ff">P50 ${fmt.format(forecastDay.p50)}</span>`;
        html += `<br><span style="color:#fde9ff">P90 ${fmt.format(forecastDay.p90)}</span>`;
      }
      setTip(html);
      if (param.point) {
        setTipX(param.point.x + 14);
        setTipY(param.point.y - 10);
      }
    };
    const onLeave = () => setTip("");
    chart.subscribeCrosshairMove(onMove);
    chart.subscribeClick(onLeave);

    const ro = new ResizeObserver(() => updateTodayX.current());
    ro.observe(containerRef.current);
    chart.timeScale().subscribeVisibleLogicalRangeChange(() => updateTodayX.current());
    updateTodayX.current();

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candlesRef.current = null;
      bgRef.current = null;
      futureBgRef.current = null;
      bandRef.current = null;
      modelBandRef.current = null;
      lineRef.current = {};
      priceLineRef.current = null;
      fittedRef.current = false;
      coneFitKeyRef.current = "";
      setTip("");
      setTodayX(null);
    };
  }, []);

  useEffect(() => {
    const candles = candlesRef.current;
    if (!candles || history.length === 0) return;
    candles.setData(
      history.map((p) => ({
        time: toTime(p.t),
        open: p.o,
        high: p.h,
        low: p.l,
        close: p.c,
      }))
    );
    candles.setMarkers([
      {
        time: toTime(history[history.length - 1].t),
        position: "aboveBar",
        color: "#fde9ff",
        shape: "arrowDown",
        text: "BUGÜN",
      },
    ]);
    const lastClose = history[history.length - 1].c;
    if (priceLineRef.current) {
      candles.removePriceLine(priceLineRef.current);
      priceLineRef.current = null;
    }
    priceLineRef.current = candles.createPriceLine({
      price: lastClose,
      color: "rgba(201,220,218,0.55)",
      lineWidth: 1,
      lineStyle: 3,
      axisLabelVisible: true,
      title: "SON KAPANIŞ",
    });
    const historyKey = history[history.length - 1].t;
    const historyChanged = lastHistoryKeyRef.current !== historyKey;
    lastHistoryKeyRef.current = historyKey;
    if (historyChanged) {
      coneFitKeyRef.current = "";
      fittedRef.current = false;
    }
    if (!fittedRef.current) {
      fittedRef.current = true;
      chartRef.current?.timeScale().fitContent();
      const coneKey = `${historyKey}|${ensembleRef.current.length ? ensembleRef.current[ensembleRef.current.length - 1].date : ""}`;
      coneFitKeyRef.current = coneKey;
    }
    updateTodayX.current();
  }, [history]);

  useEffect(() => {
    const bg = bgRef.current;
    if (!bg) return;
    bg.setData(
      regimes.map((r) => ({
        time: toTime(r.date),
        value: 0,
        color: REGIME_COLORS[r.state] ?? "rgba(255,255,255,0.07)",
      }))
    );
  }, [regimes]);

  useEffect(() => {
    const futureBg = futureBgRef.current;
    if (!futureBg) return;
    const lastBar = historyRef.current.length
      ? toTime(historyRef.current[historyRef.current.length - 1].t)
      : null;
    if (!lastBar || ensemble.length === 0) {
      futureBg.setData([]);
      return;
    }
    futureBg.setData(
      ensemble.map((p) => ({
        time: toTime(p.date),
        value: 0,
        color: p.date.slice(0, 10) > new Date(lastBar * 1000).toISOString().slice(0, 10)
          ? "rgba(139,124,246,0.07)"
          : "rgba(139,124,246,0.02)",
      }))
    );
  }, [ensemble]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    let band = bandRef.current;
    if (ensemble.length === 0) {
      if (band) {
        band.p90.applyOptions({ visible: false });
        band.p10.applyOptions({ visible: false });
        band.p50.applyOptions({ visible: false });
      }
      return;
    }
    if (!band) {
      const p90 = chart.addAreaSeries({
        lineColor: "rgba(139,124,246,0.9)",
        lineWidth: 1,
        topColor: "rgba(139,124,246,0.30)",
        bottomColor: "rgba(139,124,246,0.03)",
        priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
      });
      const p10 = chart.addAreaSeries({
        lineColor: "rgba(1,38,36,0.0)",
        topColor: "rgba(1,38,36,0.88)",
        bottomColor: "rgba(1,38,36,0.95)",
        priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
      });
      const p50 = chart.addLineSeries({
        color: "#fde9ff",
        lineWidth: 3,
        lineStyle: 0,
        priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
      });
      band = { p90, p10, p50 };
      bandRef.current = band;
    }
    band.p90.applyOptions({ visible: viewRef.current === "konisi" || viewRef.current === "tumu" });
    band.p10.applyOptions({ visible: viewRef.current === "konisi" || viewRef.current === "tumu" });
    band.p50.applyOptions({ visible: viewRef.current === "konisi" || viewRef.current === "tumu" });
    band.p90.setData(ensemble.map((p) => ({ time: toTime(p.date), value: p.p90 })));
    band.p10.setData(ensemble.map((p) => ({ time: toTime(p.date), value: p.p10 })));
    band.p50.setData(ensemble.map((p) => ({ time: toTime(p.date), value: p.p50 })));
    const coneKey = `${historyRef.current.length ? historyRef.current[historyRef.current.length - 1].t : ""}|${ensemble[ensemble.length - 1]?.date ?? ""}`;
    if (!fittedRef.current || coneFitKeyRef.current !== coneKey) {
      coneFitKeyRef.current = coneKey;
      chart.timeScale().fitContent();
    }
  }, [ensemble, viewMode]);

  const selectedModelId = rawModels.some((m) => m.model_id === selectedModel)
    ? selectedModel
    : rawModels[0]?.model_id ?? "";

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || rawModels.length === 0) return;
    const model = rawModels.find((m) => m.model_id === selectedModelId);
    let mb = modelBandRef.current;
    if (model && viewMode === "model") {
      if (!mb) {
        const color = MODEL_COLORS[model.model_id] ?? "#7ee8fa";
        const p90 = chart.addAreaSeries({
          lineColor: color,
          lineWidth: 1,
          topColor: `${color}40`,
          bottomColor: `${color}08`,
          priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
        });
        const p10 = chart.addAreaSeries({
          lineColor: "rgba(1,38,36,0.0)",
          topColor: "rgba(1,38,36,0.88)",
          bottomColor: "rgba(1,38,36,0.95)",
          priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
        });
        const p50 = chart.addLineSeries({
          color,
          lineWidth: 3,
          lineStyle: 0,
          priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
        });
        mb = { p90, p10, p50 };
        modelBandRef.current = mb;
      }
      const color = MODEL_COLORS[model.model_id] ?? "#7ee8fa";
      mb.p90.applyOptions({ visible: true, lineColor: color, topColor: `${color}40` });
      mb.p10.applyOptions({ visible: true });
      mb.p50.applyOptions({ visible: true, color });
      mb.p90.setData(model.points.map((p) => ({ time: toTime(p.date), value: p.p90 })));
      mb.p10.setData(model.points.map((p) => ({ time: toTime(p.date), value: p.p10 })));
      mb.p50.setData(model.points.map((p) => ({ time: toTime(p.date), value: p.p50 })));
    } else if (mb) {
      mb.p90.applyOptions({ visible: false });
      mb.p10.applyOptions({ visible: false });
      mb.p50.applyOptions({ visible: false });
    }
  }, [rawModels, viewMode, selectedModelId]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    if (viewMode === "tumu") {
      for (const raw of rawModels) {
        let existing = lineRef.current[raw.model_id];
        if (!existing) {
          existing = chart.addLineSeries({
            color: MODEL_COLORS[raw.model_id] ?? "#ffffff",
            lineWidth: 2,
            lineStyle: 2,
            priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
          });
          lineRef.current[raw.model_id] = existing;
        }
        existing.setData(raw.points.map((p) => ({ time: toTime(p.date), value: p.p50 })));
        existing.applyOptions({ visible: true });
      }
      for (const id of Object.keys(lineRef.current)) {
        if (!rawModels.some((m) => m.model_id === id)) {
          chart.removeSeries(lineRef.current[id]);
          delete lineRef.current[id];
        }
      }
      return;
    }
    for (const raw of rawModels) {
      const existing = lineRef.current[raw.model_id];
      const want = viewMode === "konisi" && visibleModels.has(raw.model_id);
      if (!existing && want) {
        const s = chart.addLineSeries({
          color: MODEL_COLORS[raw.model_id] ?? "#ffffff",
          lineWidth: 2,
          lineStyle: 2,
          priceFormat: { type: "price", precision: 4, minMove: 0.0001 },
        });
        s.setData(raw.points.map((p) => ({ time: toTime(p.date), value: p.p50 })));
        lineRef.current[raw.model_id] = s;
      } else if (existing) {
        existing.applyOptions({ visible: want });
      }
    }
    for (const id of Object.keys(lineRef.current)) {
      if (!rawModels.some((m) => m.model_id === id)) {
        chart.removeSeries(lineRef.current[id]);
        delete lineRef.current[id];
      }
    }
  }, [rawModels, visibleModels, viewMode]);

  const zoomToHorizon = () => {
    const chart = chartRef.current;
    if (!chart) return;
    const lastBar = history.length ? toTime(history[history.length - 1].t) : 0;
    const total = ensemble.length ? 70 : 60;
    chart.timeScale().setVisibleRange({
      from: (lastBar - total * 86400) as UTCTimestamp,
      to: (lastBar + (ensemble.length ? 45 * 86400 : 0)) as UTCTimestamp,
    });
  };

  const zoomAll = () => {
    chartRef.current?.timeScale().fitContent();
  };

  const lastEnsemble = ensemble[ensemble.length - 1];
  const horizonDays = ensemble.length;
  const horizonEnd = lastEnsemble
    ? new Date(lastEnsemble.date).toLocaleDateString("tr-TR", { day: "2-digit", month: "short" })
    : null;

  return (
    <div className="glass flex h-full flex-col p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="eyebrow mb-1">
            {viewMode === "model" ? "Model Tahmini" : "Nihai Tahmin Konisi (Hakem Ağırlıklı)"}
            {horizonDays > 0 && (
              <span className="ml-2 rounded-full border border-white/15 px-2 py-0.5 text-[10px] text-silver">
                Ufuk: +{horizonDays} gün{horizonEnd ? ` · bitiş ${horizonEnd}` : ""}
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-baseline gap-3">
            <span className="text-2xl font-medium tabular text-platinum">
              {lastEnsemble ? fmt.format(lastEnsemble.p50) : "—"}
            </span>
            <span className="text-xs text-silver tabular">
              P10 {lastEnsemble ? fmt.format(lastEnsemble.p10) : "—"} / P90{" "}
              {lastEnsemble ? fmt.format(lastEnsemble.p90) : "—"}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-4 text-[11px] text-silver">
          <div className="flex gap-1 rounded-md border border-white/15 p-1">
            {(
              [
                ["konisi", "Hakem Konisi"],
                ["model", "Model"],
                ["tumu", "Tümü"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setViewMode(key)}
                className={`rounded px-2.5 py-1 transition-colors ${
                  viewMode === key ? "bg-teal/20 text-teal" : "hover:text-platinum"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {viewMode === "model" && rawModels.length > 0 && (
            <select
              value={selectedModelId}
              onChange={(e) => setSelectedModel(e.target.value)}
              className="rounded-md border border-white/20 bg-kelp px-2 py-1 text-[11px] text-platinum outline-none focus:border-teal"
            >
              {rawModels.map((m) => (
                <option key={m.model_id} value={m.model_id}>
                  {m.model_name}
                </option>
              ))}
            </select>
          )}
          <div className="flex flex-wrap items-center gap-3">
            {Object.entries(REGIME_COLORS).map(([k, v]) => (
              <span key={k} className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-sm" style={{ background: v }} />
                {k}
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <button className="btn-ghost !px-3 !py-1.5 text-[11px]" onClick={zoomToHorizon}>
              Ufuk
            </button>
            <button className="btn-ghost !px-3 !py-1.5 text-[11px]" onClick={zoomAll}>
              Tümü
            </button>
          </div>
        </div>
      </div>

      {rawModels.length > 0 && viewMode !== "tumu" && (
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="eyebrow">Modeller:</span>
          {rawModels.map((m) => (
            <button
              key={m.model_id}
              onClick={() => onToggleModel?.(m.model_id)}
              className={`rounded-full border px-2.5 py-0.5 text-[11px] transition-opacity ${
                visibleModels.has(m.model_id) ? "" : "opacity-30"
              }`}
              style={{
                borderColor: MODEL_COLORS[m.model_id],
                color: MODEL_COLORS[m.model_id],
                background: `${MODEL_COLORS[m.model_id]}14`,
              }}
              title="Satır görünürlüğünü aç/kapat"
            >
              {m.model_name}
            </button>
          ))}
        </div>
      )}

      <div className="relative min-h-[420px] flex-1">
        {history.length === 0 && (
          <div className="absolute inset-0 flex flex-col gap-3 p-2">
            <div className="skeleton h-1/3 w-full rounded-md" />
            <div className="skeleton h-1/3 w-2/3 rounded-md" />
            <div className="skeleton h-1/3 w-full rounded-md" />
            <span className="pulse-glow mt-1 text-xs text-mist">Grafik yükleniyor...</span>
          </div>
        )}
        <div ref={containerRef} className="absolute inset-0" />
        {todayX !== null && (
          <>
            <div
              className="pointer-events-none absolute top-0 bottom-0 w-px bg-gradient-to-b from-fuchsia/60 to-transparent"
              style={{ left: todayX }}
            />
            <div
              className="pointer-events-none absolute -top-1 -translate-x-1/2 rounded-sm bg-fuchsia/80 px-1.5 py-0.5 text-[10px] font-medium text-white"
              style={{ left: todayX }}
            >
              BUGÜN
            </div>
          </>
        )}
        {tip && (
          <div
            className="glass-deep pointer-events-none absolute z-10 px-3 py-2 text-xs leading-relaxed text-mist"
            style={{ left: tipX, top: tipY, transform: "translateY(-50%)" }}
            dangerouslySetInnerHTML={{ __html: tip }}
          />
        )}
      </div>
    </div>
  );
}
