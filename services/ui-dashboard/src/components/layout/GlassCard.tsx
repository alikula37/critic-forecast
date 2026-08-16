import React from "react";

export function GlassCard({
  title,
  eyebrow,
  children,
  className = "",
  right,
}: {
  title?: string;
  eyebrow?: string;
  children: React.ReactNode;
  className?: string;
  right?: React.ReactNode;
}) {
  return (
    <section className={`glass p-6 ${className}`}>
      {(title || eyebrow || right) && (
        <div className="mb-5 flex items-start justify-between gap-4">
          <div>
            {eyebrow && <div className="eyebrow mb-1">{eyebrow}</div>}
            {title && <h2 className="text-xl font-medium tracking-tight text-platinum">{title}</h2>}
          </div>
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function StatBlock({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div>
      <div className="eyebrow mb-2">{label}</div>
      <div className={`stat-number text-3xl ${accent ? "" : ""}`} style={accent ? { color: "var(--color-phosphor)" } : {}}>
        {value}
      </div>
      {sub && <div className="mt-1 text-xs text-silver">{sub}</div>}
    </div>
  );
}

export function ProgressBar({ value, color = "#00c2b8" }: { value: number; color?: string }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
      <div
        className="h-full rounded-full transition-all duration-500"
        style={{ width: `${Math.min(100, Math.max(0, value))}%`, background: color }}
      />
    </div>
  );
}

export function Chip({
  children,
  color = "rgba(0,194,184,0.15)",
  textColor = "#edfffe",
}: {
  children: React.ReactNode;
  color?: string;
  textColor?: string;
}) {
  return (
    <span
      className="inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-medium"
      style={{ background: color, color: textColor }}
    >
      {children}
    </span>
  );
}
