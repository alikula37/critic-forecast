import React from "react";
import type { CriticState } from "../../types";
import { MODEL_COLORS } from "../../types";
import { Chip, GlassCard, StatBlock } from "../layout/GlassCard";

const pct = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 1 });

function regimeColor(regime: string) {
  if (regime === "boğa") return "rgba(0,194,184,0.15)";
  if (regime === "ayı") return "rgba(255,93,115,0.15)";
  return "rgba(255,255,255,0.07)";
}

function Gauge({ value, label }: { value: number; label: string }) {
  const safe = Number.isFinite(value) ? value : 0;
  const pctVal = Math.min(100, Math.max(0, safe * 100));
  return (
    <div className="flex flex-col items-center gap-2">
      <div
        className="flex h-28 w-28 items-center justify-center rounded-full"
        style={{
          background: `conic-gradient(#00c2b8 ${pctVal}%, rgba(255,255,255,0.08) ${pctVal}%)`,
        }}
      >
        <div className="flex h-[88px] w-[88px] flex-col items-center justify-center rounded-full bg-deep">
          <span className="stat-number text-2xl tabular">%{pct.format(pctVal)}</span>
        </div>
      </div>
      <span className="eyebrow">{label}</span>
    </div>
  );
}

export function CriticPanel({ critic }: { critic: CriticState }) {
  const models = [...critic.models].sort((a, b) => b.weight - a.weight);
  return (
    <GlassCard eyebrow="Katman 2 — Hakem Motoru" title="Güven, Rejim ve Ağırlık Dağılımı">
      <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
        <Gauge value={critic.ensemble.up_probability} label="Yükseliş Olasılığı" />
        <Gauge value={critic.ensemble.confidence} label="Ensemble Güveni" />
        <StatBlock
          label="Rejim (HMM)"
          value={critic.current_regime}
          accent
        />
        <StatBlock
          label="Konsensüs"
          value={`%${pct.format(critic.consensus * 100)}`}
          sub={`Ort. çelişki %${pct.format(critic.mean_divergence * 100)}`}
        />
      </div>

      <div className="mt-8">
        <div className="eyebrow mb-3">Hakem Ağırlıkları (softmax + rejim uyumu)</div>
        <div className="space-y-3">
          {models.map((m) => {
            const color = MODEL_COLORS[m.model_id] ?? "#fff";
            return (
              <div key={m.model_id} className="flex items-center gap-3">
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: color }} />
                <div className="w-44 truncate text-sm text-silver">{m.model_name}</div>
                <div className="h-2.5 flex-1 overflow-hidden rounded-sm bg-white/10">
                  <div
                    className="h-full rounded-sm transition-all duration-700"
                    style={{
                      width: `${m.weight * 100}%`,
                      background: `linear-gradient(90deg, ${color}, ${color}55)`,
                    }}
                  />
                </div>
                <span className="tabular w-14 text-right text-sm text-platinum">
                  %{pct.format(m.weight * 100)}
                </span>
                <Chip color={regimeColor(critic.current_regime)}>
                  {m.regime_factor > 1 ? "rejim +" : m.regime_factor < 1 ? "rejim −" : "rejim ="}
                </Chip>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mt-8 grid grid-cols-2 gap-4 text-xs text-slate-deep md:grid-cols-4">
        <div>Canlı geri bildirim ağırlığı: %60</div>
        <div>Backtest ağırlığı: %40</div>
        <div>Sıcaklık: {critic.temperature}</div>
        <div>Meta düzeltme: Ridge shrinkaj</div>
      </div>
    </GlassCard>
  );
}
