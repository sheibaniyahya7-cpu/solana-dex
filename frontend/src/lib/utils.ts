import clsx, { type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { AIDecision, Severity } from "@/types";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

type Numeric = string | number | null | undefined;

function toNumber(value: Numeric): number | null {
  if (value === null || value === undefined || value === "") return null;
  const n = typeof value === "string" ? parseFloat(value) : value;
  return Number.isFinite(n) ? n : null;
}

const EM_DASH = "—";

function compactSuffix(abs: number): [number, string] {
  if (abs >= 1_000_000_000) return [1_000_000_000, "B"];
  if (abs >= 1_000_000) return [1_000_000, "M"];
  if (abs >= 1_000) return [1_000, "K"];
  return [1, ""];
}

/**
 * Prices on Solana routinely run to eight decimals, so small values keep more
 * precision than a fixed-2 currency format would allow.
 */
export function formatUSD(value: Numeric, compact = false): string {
  const n = toNumber(value);
  if (n === null) return EM_DASH;

  if (compact) {
    const [divisor, suffix] = compactSuffix(Math.abs(n));
    const scaled = n / divisor;
    return `$${scaled.toFixed(scaled >= 100 || suffix === "" ? 0 : 2)}${suffix}`;
  }

  const abs = Math.abs(n);
  if (abs === 0) return "$0";
  if (abs < 0.000001) return `$${n.toExponential(2)}`;
  if (abs < 0.01) return `$${n.toFixed(8)}`;
  if (abs < 1) return `$${n.toFixed(4)}`;
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatNumber(value: Numeric, compact = true): string {
  const n = toNumber(value);
  if (n === null) return EM_DASH;

  if (compact) {
    const [divisor, suffix] = compactSuffix(Math.abs(n));
    if (suffix) return `${(n / divisor).toFixed(1)}${suffix}`;
  }
  return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

export function formatPct(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return EM_DASH;
  return `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
}

export function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "text-text-muted";
  if (score >= 85) return "text-emerald-400";
  if (score >= 70) return "text-green-400";
  if (score >= 50) return "text-amber-400";
  if (score >= 30) return "text-orange-400";
  return "text-red-400";
}

export function priceChangeColor(change: number | null | undefined): string {
  if (change === null || change === undefined || change === 0) return "text-text-secondary";
  return change > 0 ? "text-green-400" : "text-red-400";
}

export function timeAgo(timestamp: string | Date | null | undefined): string {
  if (!timestamp) return EM_DASH;
  const then = timestamp instanceof Date ? timestamp : new Date(timestamp);
  const ms = then.getTime();
  if (!Number.isFinite(ms)) return EM_DASH;

  const seconds = Math.floor((Date.now() - ms) / 1000);
  if (seconds < 0) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
}

export function truncateAddress(address: string | null | undefined, lead = 4, tail = 4): string {
  if (!address) return EM_DASH;
  if (address.length <= lead + tail + 3) return address;
  return `${address.slice(0, lead)}...${address.slice(-tail)}`;
}

export const decisionConfig: Record<
  AIDecision,
  { label: string; color: string; bg: string; border: string }
> = {
  STRONG_BUY: {
    label: "STRONG BUY",
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/20",
  },
  BUY: {
    label: "BUY",
    color: "text-green-400",
    bg: "bg-green-500/10",
    border: "border-green-500/20",
  },
  WATCH: {
    label: "WATCH",
    color: "text-amber-400",
    bg: "bg-amber-500/10",
    border: "border-amber-500/20",
  },
  AVOID: {
    label: "AVOID",
    color: "text-orange-400",
    bg: "bg-orange-500/10",
    border: "border-orange-500/20",
  },
  DANGER: {
    label: "DANGER",
    color: "text-red-400",
    bg: "bg-red-500/10",
    border: "border-red-500/20",
  },
};

export const severityConfig: Record<
  Severity,
  { color: string; bg: string; dot: string }
> = {
  low: { color: "text-slate-400", bg: "bg-slate-500/10", dot: "bg-slate-400" },
  medium: { color: "text-blue-400", bg: "bg-blue-500/10", dot: "bg-blue-400" },
  high: { color: "text-amber-400", bg: "bg-amber-500/10", dot: "bg-amber-400" },
  critical: { color: "text-red-400", bg: "bg-red-500/10", dot: "bg-red-400" },
};
