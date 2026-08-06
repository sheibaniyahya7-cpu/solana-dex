"use client";

import {
  Chart as ChartJS, CategoryScale, LinearScale,
  PointElement, LineElement, Title, Tooltip, Legend,
  Filler,
} from "chart.js";
import { Line } from "react-chartjs-2";
import type { PriceCandle } from "@/types";
import { format } from "date-fns";

ChartJS.register(
  CategoryScale, LinearScale, PointElement,
  LineElement, Title, Tooltip, Legend, Filler,
);

interface PriceChartProps {
  candles: PriceCandle[];
  height?: number;
}

export function PriceChart({ candles, height = 200 }: PriceChartProps) {
  if (!candles.length) {
    return (
      <div className="flex items-center justify-center h-32 text-text-muted text-sm">
        No price history available
      </div>
    );
  }

  const labels = candles.map((c) =>
    format(new Date(c.timestamp), "HH:mm")
  );
  const closes = candles.map((c) => parseFloat(c.close || "0"));
  const firstPrice = closes[0] || 0;
  const lastPrice = closes[closes.length - 1] || 0;
  const isPositive = lastPrice >= firstPrice;

  const data = {
    labels,
    datasets: [
      {
        label: "Price",
        data: closes,
        borderColor: isPositive ? "#10b981" : "#ef4444",
        backgroundColor: isPositive
          ? "rgba(16, 185, 129, 0.08)"
          : "rgba(239, 68, 68, 0.08)",
        borderWidth: 1.5,
        pointRadius: 0,
        pointHoverRadius: 4,
        fill: true,
        tension: 0.3,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: "#1a1a24",
        borderColor: "#2a2a38",
        borderWidth: 1,
        titleColor: "#94a3b8",
        bodyColor: "#f1f5f9",
        callbacks: {
          label: (ctx: { parsed: { y: number } }) => {
            const v = ctx.parsed.y;
            return ` $${v < 0.01 ? v.toFixed(8) : v.toFixed(4)}`;
          },
        },
      },
    },
    scales: {
      x: {
        grid: { color: "rgba(255,255,255,0.04)" },
        ticks: { color: "#475569", maxTicksLimit: 6, font: { size: 11 } },
        border: { color: "#2a2a38" },
      },
      y: {
        grid: { color: "rgba(255,255,255,0.04)" },
        ticks: {
          color: "#475569",
          font: { size: 11 },
          callback: (v: string | number) => {
            const n = typeof v === "string" ? parseFloat(v) : v;
            return n < 0.01 ? `$${n.toFixed(6)}` : `$${n.toFixed(4)}`;
          },
        },
        border: { color: "#2a2a38" },
      },
    },
    interaction: { mode: "index" as const, intersect: false },
  };

  return (
    <div style={{ height }}>
      <Line data={data} options={options} />
    </div>
  );
}
