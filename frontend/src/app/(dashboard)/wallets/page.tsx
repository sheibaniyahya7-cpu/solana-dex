"use client";

import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { Brain, TrendingUp, Fish } from "lucide-react";
import { walletApi } from "@/lib/api";
import { formatUSD, formatPct, scoreColor, timeAgo, truncateAddress } from "@/lib/utils";
import type { WalletListItem } from "@/types";

const fetcher = (fn: () => Promise<unknown>) => fn().then((r: any) => r.data);
type Tab = "smart" | "whales" | "top";

const WALLET_TYPE_BADGE: Record<string, string> = {
  smart_money: "bg-purple-500/10 text-purple-400 border-purple-500/20",
  whale: "bg-blue-500/10 text-blue-400 border-blue-500/20",
  insider: "bg-red-500/10 text-red-400 border-red-500/20",
  retail: "bg-slate-500/10 text-slate-400 border-slate-500/20",
  unknown: "bg-slate-500/10 text-slate-500 border-slate-500/20",
};

export default function WalletsPage() {
  const [tab, setTab] = useState<Tab>("smart");

  const { data: smartWallets } = useSWR(tab === "smart" ? "smart-money" : null,
    () => fetcher(() => walletApi.getSmartMoney(100)), { refreshInterval: 120_000 });
  const { data: whaleWallets } = useSWR(tab === "whales" ? "whale-wallets" : null,
    () => fetcher(() => walletApi.getWhales(100)), { refreshInterval: 120_000 });
  const { data: topPerformers } = useSWR(tab === "top" ? "top-performers" : null,
    () => fetcher(() => walletApi.getTopPerformers(100)), { refreshInterval: 120_000 });

  const wallets: WalletListItem[] =
    tab === "smart" ? (smartWallets as WalletListItem[] || []) :
    tab === "whales" ? (whaleWallets as WalletListItem[] || []) :
    (topPerformers as WalletListItem[] || []);

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="text-text-primary text-2xl font-bold">Wallet Intelligence</h1>
        <p className="text-text-secondary text-sm mt-1">Track smart money, whales, and top performers</p>
      </div>

      <div className="flex bg-surface-2 border border-border rounded-lg p-1 gap-1 w-fit">
        {([
          { id: "smart", label: "Smart Money", icon: Brain },
          { id: "whales", label: "Whales", icon: Fish },
          { id: "top", label: "Top Performers", icon: TrendingUp },
        ] as const).map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              tab === id ? "bg-primary text-white" : "text-text-secondary hover:text-text-primary"
            }`}
          >
            <Icon className="w-3 h-3" /> {label}
          </button>
        ))}
      </div>

      <div className="card overflow-hidden">
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Wallet</th>
              <th>Type</th>
              <th>Win Rate</th>
              <th>Total PnL</th>
              <th>ROI</th>
              <th>Trades</th>
              <th>Score</th>
              <th>Last Trade</th>
            </tr>
          </thead>
          <tbody>
            {wallets.map((w, i) => (
              <tr key={w.id}>
                <td className="text-text-muted text-xs">{i + 1}</td>
                <td>
                  <Link href={`/wallets/${w.address}`} className="hover:text-primary transition-colors">
                    <div className="font-mono text-sm text-text-primary">
                      {w.label || truncateAddress(w.address)}
                    </div>
                    {w.label && (
                      <div className="text-text-muted text-xs font-mono">{truncateAddress(w.address)}</div>
                    )}
                  </Link>
                </td>
                <td>
                  <span className={`text-xs px-2 py-0.5 rounded border font-medium capitalize ${WALLET_TYPE_BADGE[w.wallet_type] || WALLET_TYPE_BADGE.unknown}`}>
                    {w.wallet_type.replace("_", " ")}
                  </span>
                </td>
                <td className={w.win_rate && w.win_rate >= 0.65 ? "text-green-400 tabular" : "text-text-secondary tabular"}>
                  {w.win_rate ? `${(w.win_rate * 100).toFixed(1)}%` : "—"}
                </td>
                <td className={`tabular ${w.total_pnl_usd && parseFloat(w.total_pnl_usd) > 0 ? "text-green-400" : "text-red-400"}`}>
                  {formatUSD(w.total_pnl_usd, true)}
                </td>
                <td className={`tabular ${w.roi_pct && w.roi_pct > 0 ? "text-green-400" : "text-red-400"}`}>
                  {w.roi_pct ? `${w.roi_pct > 0 ? "+" : ""}${w.roi_pct.toFixed(0)}%` : "—"}
                </td>
                <td className="text-text-secondary tabular">{w.total_trades}</td>
                <td className={`font-bold tabular ${scoreColor(w.score)}`}>
                  {w.score?.toFixed(0) ?? "—"}
                </td>
                <td className="text-text-muted text-xs">{timeAgo(w.last_trade_at)}</td>
              </tr>
            ))}
            {wallets.length === 0 && (
              <tr><td colSpan={9} className="text-center text-text-muted py-12">Loading wallets...</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
