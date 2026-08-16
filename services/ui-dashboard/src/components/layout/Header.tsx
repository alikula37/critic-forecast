import React from "react";

export function Header({
  onNavigate,
  current,
}: {
  onNavigate: (page: "dashboard" | "history" | "simulation") => void;
  current: "dashboard" | "history" | "simulation";
}) {
  return (
    <header className="sticky top-0 z-40 border-b border-white/10 bg-abyss/70 backdrop-blur-xl">
      <div className="mx-auto flex max-w-[1440px] items-center justify-between px-6 py-4">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-md bg-gradient-to-br from-teal to-phosphor" />
          <div>
            <div className="text-lg font-medium leading-none tracking-tight text-platinum">
              Critic<span className="text-teal">Forecast</span>
            </div>
            <div className="eyebrow mt-1">Çok Modelli Hakem Sistemi</div>
          </div>
        </div>
        <nav className="flex items-center gap-2">
          {(
            [
              ["dashboard", "Panel"],
              ["simulation", "Simülasyon"],
              ["history", "Geçmiş Tahminler"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => onNavigate(key)}
              className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
                current === key
                  ? "bg-white/10 text-platinum"
                  : "text-silver hover:text-platinum"
              }`}
            >
              {label}
            </button>
          ))}
        </nav>
      </div>
    </header>
  );
}
