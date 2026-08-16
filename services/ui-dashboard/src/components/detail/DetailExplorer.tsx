import React, { useState } from "react";
import type { ForecastResult, ModelPerf } from "../../types";
import { LINE_NAMES, MODEL_COLORS } from "../../types";

const TABS = [
  ["models", "Model Detayları"],
  ["backtest", "Backtest Metrikleri"],
  ["regime", "Rejim Analizi"],
  ["glossary", "Terimler Sözlüğü"],
] as const;

type TabId = (typeof TABS)[number][0];

const fmt = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 4 });
const pct = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 1 });

function MiniBars({ data, color }: { data: { label: string; value: number }[]; color: string }) {
  const max = Math.max(...data.map((d) => d.value), 1e-9);
  return (
    <div className="space-y-2">
      {data.map((d) => (
        <div key={d.label} className="flex items-center gap-3">
          <span className="w-24 truncate text-xs text-silver">{d.label}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-sm bg-white/10">
            <div
              className="h-full rounded-sm"
              style={{ width: `${(d.value / max) * 100}%`, background: color }}
            />
          </div>
          <span className="tabular w-10 text-right text-xs text-slate-deep">
            {d.value.toFixed(3)}
          </span>
        </div>
      ))}
    </div>
  );
}

function RegimeStrip({ result }: { result: ForecastResult }) {
  const states = result.regimes.states;
  const counts: Record<string, number> = {};
  for (const s of states) counts[s.state] = (counts[s.state] ?? 0) + 1;
  const total = states.length || 1;
  const colors: Record<string, string> = {
    boğa: "#2dd4bf",
    ayı: "#ff6b81",
    yatay: "#94a3b8",
  };
  return (
    <div>
      <div className="flex h-6 w-full overflow-hidden rounded-md">
        {states.map((s, i) => (
          <div
            key={i}
            style={{ background: colors[s.state] ?? "#94a3b8", opacity: 0.35 + 0.65 * s.prob }}
            title={`${s.date} — ${s.state} (%${pct.format(s.prob * 100)})`}
          />
        ))}
      </div>
      <div className="mt-3 grid gap-4 md:grid-cols-3">
        {Object.entries(counts).map(([k, v]) => (
          <div key={k} className="rounded-md border border-white/10 p-4">
            <div className="eyebrow mb-1">{k}</div>
            <div className="tabular text-xl font-medium" style={{ color: colors[k] }}>
              %{pct.format((v / total) * 100)}
            </div>
            <div className="mt-1 text-[11px] text-slate-deep">
              ort. getiri {pct.format(((result.regimes.state_means[k] ?? 0) * 100))}% · σ{" "}
              {pct.format(((result.regimes.state_stds[k] ?? 0) * 100))}%
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ModelsTab({ result }: { result: ForecastResult }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="space-y-3">
      {result.raw_models.map((m) => {
        const color = MODEL_COLORS[m.model_id] ?? "#fff";
        const d = m.details ?? {};
        const top = (d.top_features as { feature: string; importance: number }[]) ?? [];
        const isOpen = open === m.model_id;
        return (
          <div key={m.model_id} className="overflow-hidden rounded-xl border border-white/12">
            <button
              className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left hover:bg-white/[0.04]"
              onClick={() => setOpen(isOpen ? null : m.model_id)}
            >
              <div className="flex items-center gap-3">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
                <div>
                  <div className="font-medium text-platinum">{m.model_name}</div>
                  <div className="text-[11px] text-slate-deep">{LINE_NAMES[m.line] ?? m.line}</div>
                </div>
              </div>
              <span className="text-sm text-silver">{isOpen ? "−" : "+"}</span>
            </button>
            {isOpen && (
              <div className="border-t border-white/10 px-5 py-4">
                <div className="grid gap-6 lg:grid-cols-2">
                  <div>
                    <div className="eyebrow mb-3">Hiperparametreler / Yapılandırma</div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      {Object.entries(d)
                        .filter(([k]) => k !== "top_features")
                        .map(([k, v]) => (
                          <div key={k} className="rounded-md bg-white/[0.05] px-3 py-2">
                            <div className="text-slate-deep">{k}</div>
                            <div className="tabular truncate text-mist">{String(v)}</div>
                          </div>
                        ))}
                      {Object.keys(d).filter((k) => k !== "top_features").length === 0 && (
                        <div className="text-slate-deep">—</div>
                      )}
                    </div>
                  </div>
                  <div>
                    <div className="eyebrow mb-3">En Etkili Özellikler</div>
                    {top.length ? (
                      <MiniBars
                        data={top.map((t) => ({ label: t.feature, value: t.importance }))}
                        color={color}
                      />
                    ) : (
                      <div className="text-xs text-slate-deep">
                        Bu model için özellik önemi raporlanmıyor (sinir ağı / simülasyon hattı).
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function BacktestTab({ result, perf }: { result: ForecastResult; perf: ModelPerf[] }) {
  const rows = result.critic.models.map((m) => {
    const p = perf.find((x) => x.model_id === m.model_id);
    return { model: m, p };
  });
  return (
    <div className="space-y-4">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[860px] text-sm">
          <thead>
            <tr className="eyebrow border-b border-white/15 text-left">
              <th className="py-3 pr-4 font-medium">Model</th>
              <th className="py-3 pr-4 text-right font-medium">F1</th>
              <th className="py-3 pr-4 text-right font-medium">Precision</th>
              <th className="py-3 pr-4 text-right font-medium">Recall</th>
              <th className="py-3 pr-4 text-right font-medium">Doğruluk</th>
              <th className="py-3 pr-4 text-right font-medium">RMSE</th>
              <th className="py-3 pr-4 text-right font-medium">Kalibrasyon</th>
              <th className="py-3 pr-4 text-right font-medium">Sharpe</th>
              <th className="py-3 text-right font-medium">Walk-fwd RMSE</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ model, p }) => {
              const mx = p?.metrics;
              const wf = model.performance as Record<string, number> | null | undefined;
              return (
                <tr key={model.model_id} className="border-t border-white/10">
                  <td className="py-3 pr-4 font-medium text-platinum">{model.model_name}</td>
                  <td className="py-3 pr-4 text-right tabular">
                    {mx ? (
                      <span style={{ color: mx.f1 >= 0.5 ? "#2dd4bf" : "#ff6b81" }}>{mx.f1.toFixed(3)}</span>
                    ) : (
                      <span className="text-slate-deep">—</span>
                    )}
                  </td>
                  <td className="py-3 pr-4 text-right tabular">{mx ? mx.precision.toFixed(3) : "—"}</td>
                  <td className="py-3 pr-4 text-right tabular">{mx ? mx.recall.toFixed(3) : "—"}</td>
                  <td className="py-3 pr-4 text-right tabular">{mx ? mx.accuracy.toFixed(3) : "—"}</td>
                  <td className="py-3 pr-4 text-right tabular">{mx ? fmt.format(mx.rmse) : "—"}</td>
                  <td className="py-3 pr-4 text-right tabular">
                    {mx ? `%${pct.format(mx.calibration * 100)}` : "—"}
                  </td>
                  <td className="py-3 pr-4 text-right tabular">{mx ? mx.sharpe.toFixed(2) : "—"}</td>
                  <td className="py-3 text-right tabular">
                    {wf?.rmse != null ? fmt.format(wf.rmse) : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-slate-deep">
        Canlı sütunlar: hedef tarihi geçmiş tahminlerin gerçekleşen fiyatla karşılaştırılmasından
        hesaplanır. Walk-forward RMSE: modelin iç doğrulama (yalnızca geçmiş veriyle) sonucudur.
        Kalibrasyon = gerçekleşmenin P10–P90 bandına düşme oranı (hedef ≈ %80).
      </p>
    </div>
  );
}

const GLOSSARY = [
  ["P10 / P50 / P90", "Tahmin konisinin dilimleri: %10, %50 ve %90 olasılıkla geçilmesi beklenen fiyat seviyeleri. P50 = medyan (en olası) yol."],
  ["HMM (Rejim)", "Gizli Markov Modeli; piyasayı Boğa / Ayı / Yatay rejimlerine böler ve her gün için rejim olasılığı verir."],
  ["GARCH", "Volatilite kümelenmesini modelleyen istatistiksel model; gelecek günlerin oynaklığını tahmin eder (Monte Carlo'nun sigma'sını besler)."],
  ["STL", "Zaman serisini Trend + Sezonluk + Kalıntı bileşenlerine ayırır; FFT ile tekrar eden döngüleri tespit eder."],
  ["Monte Carlo", "Binlerce (10.000) rastgele fiyat senaryosu üretir; sonuç dağılımından yükseliş olasılığı ve risk ölçütleri (VaR/CVaR) çıkar."],
  ["Walk-forward", "Modelin yalnızca geçmişle eğitilip gelecekte test edildiği dürüst backtest yöntemi; geleceğe sızıntı yapmaz."],
  ["Pinball Loss", "Quantile tahminlerinin (P10/P90) kalibrasyonunu ölçen kayıp fonksiyonu; düşük değer = koni dürüst."],
  ["Kalibrasyon", "Gerçekleşen değerlerin P10–P90 bandına düşme oranı; ideal değer %80'e yakındır."],
  ["F1 Skoru", "Precision ve recall'un harmonik ortalaması; modelin 'yükseliş' yönündeki tahmin kalitesini tek sayıyla özetler."],
  ["Güven Skoru", "Hakem sisteminin modele verdiği 0–1 arası puan; tarihsel isabet, rejim uyumu ve modeller arası uzlaşmadan türetilir."],
  ["Diverjans (Çelişki)", "Modellerin tahminleri arasındaki ortalama uzaklık; yüksek çelişki belirsizliği artırır, güveni düşürür."],
  ["Sharpe", "Risk birimi başına getiri; model sinyaliyle yapılan hayali işlemlerin yıllıklaştırılmış ödül/risk oranı."],
];

function GlossaryTab() {
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {GLOSSARY.map(([term, def]) => (
        <div key={term} className="rounded-xl border border-white/10 p-4">
          <div className="mb-1 text-sm font-medium text-teal">{term}</div>
          <div className="text-xs leading-relaxed text-silver">{def}</div>
        </div>
      ))}
    </div>
  );
}

export function DetailExplorer({ result, perf }: { result: ForecastResult; perf: ModelPerf[] }) {
  const [tab, setTab] = useState<TabId>("models");
  return (
    <section className="glass overflow-hidden">
      <div className="border-b border-white/15 px-6 pt-4">
        <div className="eyebrow mb-3">Detay Gezgini</div>
        <div className="flex flex-wrap gap-1">
          {TABS.map(([id, label]) => (
            <button
              key={id}
              onClick={() => setTab(id)}
              className={`rounded-t-md px-4 py-2 text-sm transition-colors ${
                tab === id
                  ? "border-b-2 border-teal bg-white/[0.06] font-medium text-platinum"
                  : "text-silver hover:text-platinum"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>
      <div className="p-6">
        {tab === "models" && <ModelsTab result={result} />}
        {tab === "backtest" && <BacktestTab result={result} perf={perf} />}
        {tab === "regime" && <RegimeStrip result={result} />}
        {tab === "glossary" && <GlossaryTab />}
      </div>
    </section>
  );
}
