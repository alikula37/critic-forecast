import React, { useState } from "react";
import type { ModelPerf, ModelState, RawModel } from "../../types";
import { LINE_NAMES, MODEL_COLORS } from "../../types";
import { Chip, ProgressBar } from "../layout/GlassCard";

const fmt = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 4 });
const pct = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 1 });

function scoreColor(score: number) {
  if (score >= 0.7) return "#2dd4bf";
  if (score >= 0.45) return "#f5a97f";
  return "#ff6b81";
}

function MetricCell({ label, value, good }: { label: string; value: string; good?: boolean }) {
  return (
    <div>
      <div className="eyebrow mb-1">{label}</div>
      <div className={`tabular text-lg font-medium ${good ? "text-teal" : "text-platinum"}`}>{value}</div>
    </div>
  );
}

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (!data.length) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const w = 260;
  const h = 40;
  const pts = data
    .map(
      (v, i) =>
        `${((i / (data.length - 1)) * w).toFixed(1)},${(h - ((v - min) / span) * (h - 4) - 2).toFixed(1)}`
    )
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full max-w-64">
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" />
    </svg>
  );
}

export function ModelRaceTable({
  models,
  rawModels,
  perf,
  visible,
  onToggle,
}: {
  models: ModelState[];
  rawModels: RawModel[];
  perf: ModelPerf[];
  visible: Set<string>;
  onToggle: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const sorted = [...models].sort((a, b) => b.weight - a.weight);
  const maxWeight = Math.max(...sorted.map((m) => m.weight), 0.0001);
  const p50At = (id: string) => {
    const raw = rawModels.find((r) => r.model_id === id);
    return raw && raw.points.length ? raw.points[raw.points.length - 1].p50 : null;
  };
  const perfOf = (id: string) => perf.find((p) => p.model_id === id);

  return (
    <div className="glass overflow-hidden">
      <div className="border-b border-white/15 px-6 py-4">
        <div className="eyebrow mb-1">Katman 2 — Hakem Çıktısı</div>
        <h2 className="text-xl font-medium tracking-tight text-platinum">
          Model Yarışı ve Puanlama
        </h2>
        <p className="mt-1 text-xs text-slate-deep">
          F1 ve RMSE, gerçekleşmiş tahminlerden hesaplanır (canlı geri bildirim). Satıra tıklayarak
          detayları açın.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[1020px] text-sm">
          <thead>
            <tr className="eyebrow border-b border-white/15 text-left">
              <th className="px-6 py-3 font-medium">Model</th>
              <th className="px-3 py-3 font-medium">Hat</th>
              <th className="px-3 py-3 text-right font-medium">P50 (Ufuk)</th>
              <th className="px-3 py-3 font-medium">Yön</th>
              <th className="px-3 py-3 font-medium">Güven Skoru</th>
              <th className="px-3 py-3 font-medium">Hakem Ağırlığı</th>
              <th className="px-3 py-3 font-medium">F1 (canlı)</th>
              <th className="px-3 py-3 text-right font-medium">Kayıt</th>
              <th className="px-3 py-3 text-right font-medium">Grafik</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((m) => {
              const color = MODEL_COLORS[m.model_id] ?? "#ffffff";
              const up = m.up_probability >= 0.5;
              const p = perfOf(m.model_id);
              const f1 = p?.metrics?.f1;
              const samples = p?.metrics?.samples;
              const isOpen = expanded === m.model_id;
              return (
                <React.Fragment key={m.model_id}>
                  <tr
                    className="cursor-pointer border-b border-white/10 last:border-0 hover:bg-white/[0.04]"
                    onClick={() => setExpanded(isOpen ? null : m.model_id)}
                  >
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
                        <div>
                          <div className="font-medium text-platinum">{m.model_name}</div>
                          <div className="text-xs text-slate-deep">
                            {m.performance?.samples
                              ? `${m.performance.samples} walk-forward örnek`
                              : "doğrulama bekleniyor"}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-4">
                      <Chip color="rgba(255,255,255,0.09)">{LINE_NAMES[m.line] ?? m.line}</Chip>
                    </td>
                    <td className="px-3 py-4 text-right tabular text-silver">
                      {p50At(m.model_id) !== null ? fmt.format(p50At(m.model_id)!) : "—"}
                    </td>
                    <td className="px-3 py-4">
                      <span className="tabular font-medium" style={{ color: up ? "#2dd4bf" : "#ff6b81" }}>
                        {up ? "▲" : "▼"} %{pct.format(m.up_probability * 100)}
                      </span>
                    </td>
                    <td className="px-3 py-4">
                      <div className="flex items-center gap-2">
                        <span className="tabular font-semibold" style={{ color: scoreColor(m.score) }}>
                          {m.score.toFixed(2)}
                        </span>
                        <div className="w-16">
                          <ProgressBar value={m.score * 100} color={scoreColor(m.score)} />
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-4">
                      <div className="flex items-center gap-2">
                        <div className="relative h-3 w-full max-w-24 overflow-hidden rounded-sm bg-white/10">
                          <div
                            className="h-full rounded-sm transition-all duration-700"
                            style={{
                              width: `${(m.weight / maxWeight) * 100}%`,
                              background: `linear-gradient(90deg, ${color}, ${color}66)`,
                            }}
                          />
                        </div>
                        <span className="tabular w-12 text-xs text-silver">%{pct.format(m.weight * 100)}</span>
                      </div>
                    </td>
                    <td className="px-3 py-4">
                      {f1 !== undefined && f1 !== null ? (
                        <span className="tabular font-semibold" style={{ color: scoreColor(f1) }}>
                          {f1.toFixed(3)}
                        </span>
                      ) : (
                        <span className="text-xs text-slate-deep">henüz yok</span>
                      )}
                    </td>
                    <td className="px-3 py-4 text-right tabular text-silver">
                      {samples ?? "—"}
                    </td>
                    <td className="px-3 py-4 text-right" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={visible.has(m.model_id)}
                        onChange={() => onToggle(m.model_id)}
                        className="h-4 w-4 accent-teal"
                      />
                    </td>
                  </tr>
                  {isOpen && (
                    <tr className="border-b border-white/10 bg-black/20">
                      <td colSpan={9} className="px-6 py-5">
                        <div className="grid gap-6 lg:grid-cols-2">
                          <div>
                            <div className="eyebrow mb-3">Backtest Metrikleri (walk-forward)</div>
                            {m.performance ? (
                              <div className="grid grid-cols-3 gap-4">
                                <MetricCell
                                  label="RMSE"
                                  value={m.performance.rmse != null ? fmt.format(Number(m.performance.rmse)) : "—"}
                                />
                                <MetricCell
                                  label="İsabet"
                                  value={m.performance.hit_rate != null ? `%${pct.format(Number(m.performance.hit_rate) * 100)}` : "—"}
                                  good={m.performance.hit_rate != null && Number(m.performance.hit_rate) >= 0.5}
                                />
                                <MetricCell
                                  label="Sharpe"
                                  value={m.performance.sharpe != null ? Number(m.performance.sharpe).toFixed(2) : "—"}
                                />
                                <MetricCell
                                  label="Pinball P10"
                                  value={m.performance.pinball_10 != null ? fmt.format(Number(m.performance.pinball_10)) : "—"}
                                />
                                <MetricCell
                                  label="Pinball P90"
                                  value={m.performance.pinball_90 != null ? fmt.format(Number(m.performance.pinball_90)) : "—"}
                                />
                                <MetricCell
                                  label="MaxDD"
                                  value={m.performance.max_drawdown != null ? `%${pct.format(Number(m.performance.max_drawdown) * 100)}` : "—"}
                                />
                              </div>
                            ) : (
                              <p className="text-xs text-slate-deep">
                                Bu model için henüz walk-forward metriği yok — tahmin geçmişi biriktikçe
                                otomatik hesaplanır.
                              </p>
                            )}
                            {((m.performance?.regime_errors as Record<string, { rmse: number }> | undefined)) && (
                              <div className="mt-4 text-xs text-slate-deep">
                                Rejim hataları:{" "}
                                {Object.entries(
                                  m.performance!.regime_errors as Record<string, { rmse: number }>
                                )
                                  .map(([k, v]) => `${k} ${fmt.format(v.rmse)}`)
                                  .join(" · ")}
                              </div>
                            )}
                          </div>
                          <div>
                            <div className="eyebrow mb-3">Canlı Geri Bildirim (gerçekleşen tahminler)</div>
                            {p && p.series.length > 0 ? (
                              <div className="flex flex-wrap items-center gap-6">
                                <div>
                                  <div className="eyebrow mb-1">F1 zaman serisi</div>
                                  <Sparkline data={p.series.map((s) => s.f1)} color="#fde9ff" />
                                </div>
                                <div>
                                  <div className="eyebrow mb-1">İsabet zaman serisi</div>
                                  <Sparkline data={p.series.map((s) => s.hit_rate)} color="#2dd4bf" />
                                </div>
                              </div>
                            ) : (
                              <div className="text-xs text-slate-deep">
                                Henüz gerçekleşmiş tahmin yok; tahminlerin hedef tarihleri geçtikçe
                                F1 / precision / recall otomatik hesaplanır.
                              </div>
                            )}
                            {p?.metrics && (
                              <div className="mt-4 grid grid-cols-3 gap-4">
                                <MetricCell label="Precision" value={`%${pct.format(p.metrics.precision * 100)}`} />
                                <MetricCell label="Recall" value={`%${pct.format(p.metrics.recall * 100)}`} />
                                <MetricCell label="Kalibrasyon" value={`%${pct.format(p.metrics.calibration * 100)}`} />
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
