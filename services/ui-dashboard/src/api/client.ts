import type {
  Asset,
  ForecastResult,
  JobEvent,
  ModelPerf,
  OHLCV,
  StrategyBacktest,
  StrategyCatalogItem,
} from "../types";

const json = async <T,>(url: string, init?: RequestInit): Promise<T> => {
  const ctrl = new AbortController();
  const timer = window.setTimeout(() => ctrl.abort(), 60000);
  try {
    const resp = await fetch(url, { ...init, signal: ctrl.signal });
    if (!resp.ok) {
      const err = new Error(`${resp.status}: ${(await resp.text().catch(() => "")).slice(0, 200)}`) as Error & {
        status?: number;
      };
      err.status = resp.status;
      throw err;
    }
    return resp.json() as Promise<T>;
  } finally {
    window.clearTimeout(timer);
  }
};

export const isNotFound = (e: unknown) =>
  e instanceof Error && (e as { status?: number }).status === 404;

export const api = {
  assets: () => json<Asset[]>("/api/assets"),

  history: (symbol: string, limit = 600, signal?: AbortSignal) =>
    json<{ symbol: string; interval: string; points: OHLCV[] }>(
      `/api/assets/history?symbol=${symbol}&limit=${limit}`,
      signal ? { signal } : undefined
    ),

  forecast: (symbol: string, horizon: number, force = true) =>
    json<{ job_id: string; cached: boolean; result?: ForecastResult }>("/api/forecast", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, horizon, interval: "1d", force }),
    }),

  forecastLatest: (symbol: string, horizon: number) =>
    json<ForecastResult>(`/api/forecast/latest?symbol=${symbol}&horizon=${horizon}`),

  modelPerformance: (symbol: string) =>
    json<{ symbol: string; models: ModelPerf[] }>(`/api/models/performance?symbol=${symbol}`),

  job: (jobId: string) =>
    json<{ job_id: string; state: string; stage?: string; progress?: string; result?: ForecastResult }>(
      `/api/assets/job/${jobId}`
    ),

  forecastHistory: (symbol: string) =>
    json<
      {
        job_id: string;
        symbol: string;
        horizon: number;
        created_at: string;
        up_probability: number;
        realized: { date: string; p50: number; actual: number | null }[];
      }[]
    >(`/api/forecast/history?symbol=${symbol}`),

  backfill: (symbol: string, days = 60) =>
    json<{ job_id: string }>("/api/forecast/backfill", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, interval: "1d", horizon: 30, days, skip_wf: true }),
    }),

  strategiesCatalog: () => json<StrategyCatalogItem[]>("/api/strategies"),

  strategyBacktest: (
    symbol: string,
    strategyId: string,
    params: Record<string, number | string>
  ) =>
    json<{ job_id: string; cached: boolean }>("/api/strategies/backtest", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, interval: "1d", strategy_id: strategyId, params }),
    }),

  strategyBacktests: (symbol: string) =>
    json<StrategyBacktest[]>(`/api/strategies/backtests?symbol=${symbol}`),
};

export const wsUrl = (jobId: string) => {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws/forecast/${jobId}`;
};

export const streamForecast = (
  jobId: string,
  onEvent: (ev: JobEvent) => void,
  onClose: () => void,
  onStatus?: (s: "connecting" | "open" | "closed") => void
): (() => void) => {
  const ws = new WebSocket(wsUrl(jobId));
  onStatus?.("connecting");
  ws.onopen = () => onStatus?.("open");
  ws.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data) as JobEvent);
    } catch {
      /* yoksay */
    }
  };
  ws.onclose = () => {
    onStatus?.("closed");
    onClose();
  };
  ws.onerror = () => {
    onStatus?.("closed");
    onClose();
  };
  return () => ws.close();
};
