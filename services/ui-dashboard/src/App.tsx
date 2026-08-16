import React, { useState } from "react";
import { Header } from "./components/layout/Header";
import { DashboardPage } from "./pages/DashboardPage";
import { HistoryPage } from "./pages/HistoryPage";
import { SimulationPage } from "./pages/SimulationPage";

export default function App() {
  const [page, setPage] = useState<"dashboard" | "history" | "simulation">("dashboard");
  return (
    <div className="min-h-full">
      <Header onNavigate={setPage} current={page} />
      {page === "dashboard" ? (
        <DashboardPage />
      ) : page === "simulation" ? (
        <SimulationPage />
      ) : (
        <HistoryPage />
      )}
    </div>
  );
}
