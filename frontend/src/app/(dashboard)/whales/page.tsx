"use client";

import useSWR from "swr";
import { Fish, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { whaleApi } from "@/lib/api";
import { SeverityBadge } from "@/components/ui/Badge";
import { formatUSD, timeAgo, truncateAddress } from "@/lib/utils";
import type { MarketEvent, WalletTrade } from "@/types";

const fetcher = (fn: () => Promise<unknown>) => fn().then((r: any) => r.data);

export default function WhalesPage() {
  const { data: activity } = useSWR("whale-activity",
    () => fetcher(() => whaleApi.getActivity(48, 100)), { refreshInterval: 30_000 });
  const { data: trades } = useSWR("whale-trades",
    () => fetcher(() => whaleApi.getRecentTrades(24, 50)), { refreshInterval: 30_000 });

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="text-text-primary text-2xl font-bold flex items-center gap-2">
          <Fish className="w-6 h-6 text-blue-400" /> Whale Activity
        </h1>
        <p className="text-text-secondary text-sm mt-1">
          Large wallet movements on Solana DEXes — last 48 hours
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Whale Events */}
        <div className="card p-0 overflow-hidden">
          <div className="px-5 py-4 border-b border-border">
            <h2 className="font-semibold text-text-primary text-sm">Detected Events</h2>
          </div>
          <div className="divide-y divide-border/50 max-h-[500px] overflow-y-auto">
            {(activity as MarketEvent[] | undefined)?.map((evt) => (
              <div key={evt.id} className="px-5 py-4 hover:bg-surface-2/50 transition-colors">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2 mb-1.5">
                      {evt.event_type === "WHALE_BUY"
                        ? <ArrowUpRight className="w-4 h-4 text-green-400" />
                        : <ArrowDownRight className="w-4 h-4 text-red-400" />}
                      <span className="text-text-primary font-semibold text-sm">${evt.token_symbol}</span>
                      <SeverityBadge severity={evt.severity} />
                    </div>
                    <p className="text-text-secondary text-sm">{evt.description}</p>
                    {evt.whale_amount_usd && (
                      <div className="mt-1.5 text-sm font-semibold text-text-primary">
                        {formatUSD(evt.whale_amount_usd, true)}
                      </div>
                    )}
                  </div>
                  <span className="text-text-muted text-xs shrink-0">{timeAgo(evt.detected_at)}</span>
                </div>
              </div>
            ))}
            {!activity && (
              <div className="px-5 py-12 text-center text-text-muted text-sm">Loading...</div>
            )}
          </div>
        </div>

        {/* Whale Trades */}
        <div className="card p-0 overflow-hidden">
          <div className="px-5 py-4 border-b border-border">
            <h2 className="font-semibold text-text-primary text-sm">Recent Whale Trades</h2>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Token</th>
                <th>Action</th>
                <th>Amount</th>
                <th>Wallet</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {(trades as WalletTrade[] | undefined)?.map((t) => (
                <tr key={t.id}>
                  <td className="font-medium text-text-primary">
                    ${t.token_symbol || t.token_mint.slice(0, 6)}
                  </td>
                  <td>
                    <span className={`text-xs font-semibold px-2 py-0.5 rounded ${
                      t.trade_type === "buy"
                        ? "bg-green-500/10 text-green-400"
                        : "bg-red-500/10 text-red-400"
                    }`}>
                      {t.trade_type.toUpperCase()}
                    </span>
                  </td>
                  <td className="text-text-primary tabular">{formatUSD(t.amount_usd, true)}</td>
                  <td className="text-text-muted font-mono text-xs">—</td>
                  <td className="text-text-muted text-xs">{timeAgo(t.trade_timestamp)}</td>
                </tr>
              ))}
              {!trades && (
                <tr><td colSpan={5} className="text-center text-text-muted py-8">Loading...</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
