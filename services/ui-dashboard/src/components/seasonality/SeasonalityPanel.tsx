import React from "react";
import type { ForecastResult } from "../../types";
import { GlassCard } from "../layout/GlassCard";

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (!data.length) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const w = 240;
  const h = 44;
  const pts = data
    .map(
      (v, i) =>
        `${((i / (data.length - 1)) * w).toFixed(1)},${(
          h -
          ((v - min) / span) * (h - 4) -
          2
        ).toFixed(1)}`
    )
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}

export function SeasonalityPanel({ result }: { result: ForecastResult }) {
  const { components, cycles } = result.seasonality;
  return (
    <GlassCard eyebrow="Katman 1 — Döngüsellik Hattı" title="STL Ayrıştırması ve Döngü Tespiti">
      <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
        <div>
          <div className="eyebrow mb-2">Trend (fiyat ölçeği)</div>
          <Sparkline data={components.trend.slice(-120)} color="#00c2b8" />
        </div>
        <div>
          <div className="eyebrow mb-2">Sezonluk (fiyat ölçeği)</div>
          <Sparkline data={components.seasonal.slice(-120)} color="#7c6cf0" />
        </div>
        <div>
          <div className="eyebrow mb-2">Kalıntı (gürültü)</div>
          <Sparkline data={components.resid.slice(-120)} color="#f5a97f" />
        </div>
      </div>
      <div className="mt-6">
        <div className="eyebrow mb-3">FFT ile Tespit Edilen Döngüler</div>
        {cycles.length === 0 && <div className="text-xs text-slate-deep">Belirgin döngü tespit edilemedi.</div>}
        <div className="flex flex-wrap gap-3">
          {cycles.map((c, i) => (
            <div key={i} className="rounded-md border border-white/10 px-4 py-3">
              <div className="stat-number text-xl tabular">{c.period} gün</div>
              <div className="text-[11px] text-slate-deep">güç %{(c.power * 100).toFixed(1)}</div>
            </div>
          ))}
        </div>
      </div>
    </GlassCard>
  );
}
