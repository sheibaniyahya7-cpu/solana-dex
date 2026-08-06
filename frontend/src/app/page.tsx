"use client";

import useSWR from "swr";
import { Activity, Coins, TrendingUp, Zap, Shield, Brain } from "lucide-react";
import { tokenApi, eventApi } from "@/lib/api";
import { StatCard } from "@/components/cards/StatCard";
import { DecisionBadge, SeverityBadge } from "@/components/ui/Badge";
import {
  formatUSD, formatNumber, formatPct, scoreColor,
  priceChangeColor, timeAgo,
} from "@/lib/utils";
import type { TokenListItem, MarketEvent } from "@/types";

const fetcher = (fn: () => Promise<unknown>) => fn().then((r: any) => r.data);

export default function OverviewPage() {
  const { data: stats } = useSWR("stats", () => fetcher(tokenApi.getStats), {
    refreshInterval: 30_000,
  });
  const { data: topTokens } = useSWR("top-tokens", () =>
    fetcher(() => tokenApi.getTop(10)), { refreshInterval: 30_000 }
  );
  const { data: recentEvents } = useSWR("recent-events", () =>
    fetcher(() => eventApi.list({ hours: 2, page_size: 8 })), { refreshInterval: 20_000 }
  );

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-text-primary text-2xl font-bold">Market Overview</h1>
        <p className="text-text-secondary text-sm mt-1">
          Real-time Solana DEX intelligence — updated every 30 seconds
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="Tracked Tokens"
          value={formatNumber(stats?.active_tokens, false)}
          subtitle={`${stats?.new_tokens_24h ?? 0} new in 24h`}
          icon={<Coins className="w-4 h-4" />}
        />
        <StatCard
          title="Total Volume 24h"
          value={formatUSD(stats?.total_volume_24h_usd, true)}
          icon={<TrendingUp className="w-4 h-4" />}
        />
        <StatCard
          title="Total Liquidity"
          value={formatUSD(stats?.total_liquidity_usd, true)}
          icon={<Activity className="w-4 h-4" />}
        />
        <StatCard
          title="Avg AI Score"
          value={stats?.avg_ai_score ? `${stats.avg_ai_score.toFixed(0)}/100` : "—"}
          icon={<Brain className="w-4 h-4" />}
        />
      </div>

      {/* Two columns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top AI Picks */}
        <div className="card p-0 overflow-hidden">
          <div className="px-5 py-4 border-b border-border flex items-center gap-2">
            <Brain className="w-4 h-4 text-primary" />
            <h2 className="text-text-primary font-semibold text-sm">Top AI Picks</h2>
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Token</th>
                <th>Price</th>
                <th>1h</th>
                <th>Score</th>
                <th>Signal</th>
              </tr>
            </thead>
            <tbody>
              {(topTokens as TokenListItem[] | undefined)?.map((token) => (
                <tr key={token.id} className="cursor-pointer">
                  <td>
                    <div className="flex items-center gap-2">
                      {token.logo_uri ? (
                        <img src={token.logo_uri} alt="" className="w-6 h-6 rounded-full" onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
                      ) : (
                        <div className="w-6 h-6 rounded-full bg-surface-3 flex items-center justify-center text-xs text-text-muted">
                          {(token.symbol || "?")[0]}
                        </div>
                      )}
                      <span className="text-text-primary font-medium">
                        {token.symbol || token.mint_address.slice(0, 6)}
                      </span>
                    </div>
                  </td>
                  <td className="text-text-primary tabular">
                    {formatUSD(token.price_usd)}
                  </td>
                  <td className={priceChangeColor(token.price_change_1h)}>
                    {formatPct(token.price_change_1h)}
                  </td>
                  <td className={scoreColor(token.ai_score)}>
                    {token.ai_score?.toFixed(0) ?? "—"}
                  </td>
                  <td>
                    <DecisionBadge decision={token.ai_decision} size="sm" />
                  </td>
                </tr>
              ))}
              {!topTokens && (
                <tr><td colSpan={5} className="text-center text-text-muted py-8">Loading...</td></tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Recent Events */}
        <div className="card p-0 overflow-hidden">
          <div className="px-5 py-4 border-b border-border flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-400" />
            <h2 className="text-text-primary font-semibold text-sm">Recent Events</h2>
          </div>
          <div className="divide-y divide-border/50">
            {(recentEvents as { events: MarketEvent[] } | undefined)?.events?.map((evt) => (
              <div key={evt.id} className="px-5 py-3.5 hover:bg-surface-2/50 transition-colors">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <SeverityBadge severity={evt.severity} />
                      <span className="text-text-secondary text-xs font-mono">
                        ${evt.token_symbol || evt.token_mint.slice(0, 6)}
                      </span>
                    </div>
                    <p className="text-text-primary text-sm leading-snug line-clamp-2">
                      {evt.title}
                    </p>
                  </div>
                  <span className="text-text-muted text-xs shrink-0">
                    {timeAgo(evt.detected_at)}
                  </span>
                </div>
              </div>
            ))}
            {!recentEvents && (
              <div className="px-5 py-8 text-center text-text-muted text-sm">Loading events...</div>
            )}
            {recentEvents && (recentEvents as any).events?.length === 0 && (
              <div className="px-5 py-8 text-center text-text-muted text-sm">No recent events</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
