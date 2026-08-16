import React from "react";
import type { ForecastResult } from "../../types";
import { GlassCard, StatBlock } from "../layout/GlassCard";

const fmt = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 4 });

function Histogram({
  edges,
  counts,
  current,
}: {
  edges: number[];
  counts: number[];
  current: number;
}) {
  const max = Math.max(...counts, 1);
  const min = edges[0];
  const maxE = edges[edges.length - 1];
  return (
    <div className="flex h-40 items-end gap-[2px]">
      {counts.map((c, i) => {
        const inRange = edges[i] <= current && current <= edges[i + 1];
        return (
          <div
            key={i}
            className="flex-1 rounded-t-[2px] transition-all"
            style={{
              height: `${(c / max) * 100}%`,
              background: inRange
                ? "linear-gradient(180deg, #fde9ff, #7c6cf0)"
                : "rgba(0,194,184,0.35)",
            }}
            title={`${fmt.format(edges[i])} – ${fmt.format(edges[i + 1])}: ${c} yol`}
          />
        );
      })}
    </div>
  );
}

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (!data.length) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const w = 300;
  const h = 56;
  const pts = data
    .map((v, i) => `${((i / (data.length - 1)) * w).toFixed(1)},${(h - ((v - min) / span) * (h - 4) - 2).toFixed(1)}`)
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}

export function MonteCarloPanel({ result }: { result: ForecastResult }) {
  const { mc, garch } = result;
  return (
    <GlassCard eyebrow="Katman 1 — İstatistiksel Hat" title="Monte Carlo (10.000 Senaryo)">
      <div className="grid grid-cols-2 gap-6 md:grid-cols-3">
        <StatBlock label="GARCH Yıllık Vol." value={`%${(garch.annualized_vol * 100).toFixed(1)}`} accent />
        <StatBlock label="MC Yükseliş Olas." value={`%${(mc.up_probability * 100).toFixed(1)}`} />
        <StatBlock label="Ufuk Sonu Medyan" value={fmt.format(mc.stats.median_final)} />
        <StatBlock label="VaR %1" value={fmt.format(mc.stats.var_1)} />
        <StatBlock label="VaR %5" value={fmt.format(mc.stats.var_5)} />
        <StatBlock label="CVaR %5" value={fmt.format(mc.stats.cvar_5)} />
      </div>
      <div className="mt-6">
        <div className="eyebrow mb-2">Ufuk Sonu Dağılımı (GARCH sigma + rejim drifti)</div>
        <Histogram
          edges={mc.distribution.edges}
          counts={mc.distribution.counts}
          current={result.last_close}
        />
      </div>
      <div className="mt-6 grid grid-cols-2 gap-6">
        <div>
          <div className="eyebrow mb-2">GARCH Koşullu Vol Öngörüsü (σ)</div>
          <Sparkline data={garch.sigma_daily} color="#f5a97f" />
        </div>
        <div className="text-xs text-slate-deep">
          <div className="eyebrow mb-2">GARCH Parametreleri</div>
          <div className="tabular space-y-1">
            <div>ω (sabit) — {typeof garch.params.omega === "number" ? garch.params.omega.toExponential(2) : "—"}</div>
            <div>α (şok) — {garch.params.alpha.toFixed(4)}</div>
            <div>β (kalıcılık) — {garch.params.beta.toFixed(4)}</div>
          </div>
        </div>
      </div>
    </GlassCard>
  );
}
