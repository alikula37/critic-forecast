export interface OHLCV {
  t: string;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface Asset {
  symbol: string;
  name: string;
  type: "kripto" | "hisse" | "emtia";
  provider: "binance" | "yahoo";
}

export interface ConePoint {
  date: string;
  p10: number;
  p50: number;
  p90: number;
}

export interface ModelState {
  model_id: string;
  model_name: string;
  line: string;
  score: number;
  weight: number;
  confidence: number;
  divergence: number;
  regime_factor: number;
  up_probability: number;
  performance?: Record<string, unknown> | null;
}

export interface CriticState {
  models: ModelState[];
  ensemble: {
    points: ConePoint[];
    up_probability: number;
    confidence: number;
  };
  consensus: number;
  mean_divergence: number;
  current_regime: string;
  temperature: number;
  qra?: { used: boolean; n: number };
}

export interface RegimePoint {
  date: string;
  state: string;
  prob: number;
  state_id: number;
}

export interface RawModel {
  model_id: string;
  model_name: string;
  line: string;
  points: ConePoint[];
  up_probability: number;
  performance?: Record<string, unknown> | null;
  details?: Record<string, unknown>;
}

export interface ForecastResult {
  job_id: string;
  symbol: string;
  interval: string;
  horizon: number;
  created_at?: string;
  last_close: number;
  critic: CriticState;
  regimes: {
    states: RegimePoint[];
    current: { label: string; state_id: number };
    state_probs: Record<string, number>;
    state_means: Record<string, number>;
    state_stds: Record<string, number>;
  };
  garch: {
    sigma_daily: number[];
    params: Record<string, number>;
    annualized_vol: number;
  };
  seasonality: {
    components: { trend: number[]; seasonal: number[]; resid: number[] };
    cycles: { period: number; power: number }[];
  };
  mc: {
    distribution: { edges: number[]; counts: number[] };
    stats: {
      mean_final: number;
      median_final: number;
      std_final: number;
      var_1: number;
      var_5: number;
      cvar_5: number;
    };
    up_probability: number;
  };
  raw_models: RawModel[];
}

export interface ModelMetrics {
  f1: number;
  precision: number;
  recall: number;
  accuracy: number;
  rmse: number;
  mape: number;
  pinball_10: number;
  pinball_90: number;
  calibration: number;
  sharpe: number;
  samples: number;
}

export interface ModelPerf {
  model_id: string;
  metrics: ModelMetrics | null;
  series: { job_id: string; f1: number; hit_rate: number; rmse: number }[];
}

export interface JobEvent {
  job_id: string;
  stage: string;
  progress: number;
  message: string;
  payload?: ForecastResult;
}

export interface StrategyParamDef {
  label: string;
  default: number;
  min: number;
  max: number;
  step: number;
  type?: "number" | "select";
  options?: string[];
}

export interface StrategyCatalogItem {
  strategy_id: string;
  name: string;
  description: string;
  params: Record<string, StrategyParamDef>;
}

export interface StrategyBacktest {
  job_id: string;
  strategy_id: string;
  created_at: string;
  params: Record<string, number | string>;
  metrics: {
    total_return: number | null;
    benchmark_return: number | null;
    sharpe: number | null;
    sortino: number | null;
    calmar: number | null;
    max_drawdown: number | null;
    win_rate: number | null;
    profit_factor: number | null;
    expectancy: number | null;
    n_trades: number;
    coverage: number | null;
    fees: number;
    fee_mode?: string;
    slippage_bps?: number;
    max_position?: number;
    alpha?: number | null;
    beta?: number | null;
  } | null;
  equity: { date: string; value: number }[];
  benchmark: { date: string; value: number }[];
  trades: { entry: string | null; exit: string | null; return: number | null }[];
}

export const MODEL_COLORS: Record<string, string> = {
  bilstm_attention: "#2dd4bf",
  xgboost_quantile: "#8b7cf6",
  lightgbm_quantile: "#facc15",
  monte_carlo: "#fde9ff",
  ets_baseline: "#38bdf8",
  stl_seasonality: "#f5a97f",
};

export const MODEL_NAMES: Record<string, string> = {
  bilstm_attention: "Bi-LSTM + Attention",
  xgboost_quantile: "XGBoost (Yön + Quantile)",
  lightgbm_quantile: "LightGBM (Yön + Quantile)",
  monte_carlo: "Monte Carlo + HMM/GARCH",
  ets_baseline: "ETS Trend (Baseline)",
  stl_seasonality: "STL Döngüsellik",
};

export const REGIME_COLORS: Record<string, string> = {
  boğa: "rgba(45, 212, 191, 0.18)",
  ayı: "rgba(255, 107, 129, 0.18)",
  yatay: "rgba(255, 255, 255, 0.07)",
};

export const LINE_NAMES: Record<string, string> = {
  derin_ogrenme: "Derin Öğrenme",
  gradient_boosting: "Karar Ağacı",
  istatistik: "İstatistiksel",
  döngüsellik: "Döngüsellik",
};
