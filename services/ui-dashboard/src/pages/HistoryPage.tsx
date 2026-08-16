import React, { useEffect, useState } from "react";
import { api, isNotFound } from "../api/client";
import { GlassCard } from "../components/layout/GlassCard";
import type { Asset } from "../types";

type HistoryRow = {
  job_id: string;
  symbol: string;
  horizon: number;
  created_at: string;
  up_probability: number;
  realized: { date: string; p50: number; actual: number | null }[];
};

const fmt = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 4 });

export function HistoryPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [symbol, setSymbol] = useState("BTC");
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [assetsWarn, setAssetsWarn] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .assets()
      .then((a) => {
        if (!cancelled) setAssets(a);
      })
      .catch(() => {
        if (!cancelled) setAssetsWarn("Varlık listesi yüklenemedi — sunucuya erişilemiyor.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    setLoading(true);
    setError("");
    let cancelled = false;
    api
      .forecastHistory(symbol)
      .then((r) => {
        if (cancelled) return;
        const withActual = r.filter(
          (row) => row.realized.length && row.realized.some((p) => p.actual !== null)
        );
        setRows(withActual.length ? withActual : r);
      })
      .catch((e) => {
        if (cancelled) return;
        setRows([]);
        setError(
          isNotFound(e)
            ? "Bu varlık için kayıtlı tahmin yok."
            : "Sunucuya ulaşılamadı — geçmiş tahminler yüklenemedi."
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [symbol]);

  return (
    <div className="mx-auto max-w-[1440px] space-y-6 px-6 py-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="eyebrow mb-1">Canlı Geri Bildirim</div>
          <h1 className="text-3xl font-medium tracking-tight text-platinum">Geçmiş Tahminler ve Gerçekleşmeler</h1>
        </div>
        <select
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="rounded-md border border-white/15 bg-kelp px-4 py-2.5 text-sm text-platinum outline-none focus:border-teal"
        >
          {assets.map((a) => (
            <option key={a.symbol} value={a.symbol}>
              {a.symbol} — {a.name}
            </option>
          ))}
        </select>
      </div>

      {error && <div className="text-sm text-silver">{error}</div>}
      {assetsWarn && <div className="text-xs text-silver">{assetsWarn}</div>}
      {loading && <div className="text-sm text-silver">Yükleniyor...</div>}

      <div className="grid gap-6">
        {rows.map((row) => {
          const hits = row.realized.filter((p) => p.actual !== null);
          const hitRate =
            hits.length > 1
              ? hits.filter((p, i) => i === 0 || (p.actual! > hits[i - 1].actual!) === (p.p50 > hits[i - 1].p50)).length / (hits.length - 1)
              : null;
          return (
            <GlassCard key={row.job_id} eyebrow={`${new Date(row.created_at).toLocaleString("tr-TR")}`} title={`${row.symbol} · ${row.horizon} gün ufku`} right={
              <span className="tabular text-sm text-silver">
                Yükseliş olas.: <b className="text-phosphor">%{(row.up_probability * 100).toFixed(1)}</b>
              </span>
            }>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-sm">
                  <thead>
                    <tr className="eyebrow text-left">
                      <th className="py-2 pr-4 font-medium">Tarih</th>
                      <th className="py-2 pr-4 text-right font-medium">P50 Tahmin</th>
                      <th className="py-2 pr-4 text-right font-medium">Gerçekleşen</th>
                      <th className="py-2 font-medium">Durum</th>
                    </tr>
                  </thead>
                  <tbody>
                    {row.realized.map((p, i) => {
                      const hit = p.actual !== null && i > 0
                        ? (p.actual! > row.realized[i - 1].actual!) === (p.p50 > row.realized[i - 1].p50)
                        : null;
                      return (
                        <tr key={p.date} className="border-t border-white/5">
                          <td className="py-2 pr-4 tabular text-silver">{p.date.slice(0, 10)}</td>
                          <td className="py-2 pr-4 text-right tabular">{fmt.format(p.p50)}</td>
                          <td className="py-2 pr-4 text-right tabular">
                            {p.actual !== null ? fmt.format(p.actual) : "—"}
                          </td>
                          <td className="py-2">
                            {hit === null ? (
                              <span className="text-slate-deep">—</span>
                            ) : hit ? (
                              <span className="text-teal">yön isabet</span>
                            ) : (
                              <span className="text-danger">sapma</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {hitRate !== null && (
                <div className="mt-4 text-xs text-slate-deep">
                  Dönem yön isabet oranı: <b className="tabular text-silver">%{(hitRate * 100).toFixed(1)}</b>
                </div>
              )}
            </GlassCard>
          );
        })}
        {!loading && rows.length === 0 && (
          <div className="glass p-10 text-center text-sm text-silver">
            Henüz bu varlık için tamamlanmış tahmin yok.
          </div>
        )}
      </div>
    </div>
  );
}
