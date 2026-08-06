"use client";

import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { Search, Filter, Zap } from "lucide-react";
import { tokenApi } from "@/lib/api";
import { DecisionBadge, SeverityBadge } from "@/components/ui/Badge";
import {
  formatUSD, formatNumber, formatPct, scoreColor,
  priceChangeColor, timeAgo,
} from "@/lib/utils";
import type { TokenListItem } from "@/types";

const fetcher = (fn: () => Promise<unknown>) => fn().then((r: any) => r.data);

type Tab = "all" | "new" | "top";

export default function TokensPage() {
  const [tab, setTab] = useState<Tab>("top");
  const [search, setSearch] = useState("");

  const { data: topTokens } = useSWR(
    tab === "top" ? "top-tokens-list" : null,
    () => fetcher(() => tokenApi.getTop(100)),
    { refreshInterval: 30_000 },
  );

  const { data: newTokens } = useSWR(
    tab === "new" ? "new-tokens" : null,
    () => fetcher(() => tokenApi.getNew(24, 100)),
    { refreshInterval: 30_000 },
  );

  const { data: searchResults } = useSWR(
    search.length >= 2 ? `search-${search}` : null,
    () => fetcher(() => tokenApi.search(search, 30)),
    { revalidateOnFocus: false },
  );

  const tokens: TokenListItem[] = search.length >= 2
    ? (searchResults as TokenListItem[] || [])
    : tab === "top"
    ? (topTokens as TokenListItem[] || [])
    : (newTokens as TokenListItem[] || []);

  return (
    <div className="space-y-5 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-text-primary text-2xl font-bold">Tokens</h1>
          <p className="text-text-secondary text-sm mt-1">
            {formatNumber(tokens.length, false)} tokens tracked
          </p>
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex bg-surface-2 border border-border rounded-lg p-1 gap-1">
          {(["top", "new", "all"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1.5 rounded text-xs font-medium capitalize transition-colors ${
                tab === t
                  ? "bg-primary text-white"
                  : "text-text-secondary hover:text-text-primary"
              }`}
            >
              {t === "top" ? "Top AI Picks" : t === "new" ? "New Launches" : "All Tokens"}
            </button>
          ))}
        </div>

        <div className="relative flex-1 max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-text-muted" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter by symbol or mint..."
            className="w-full bg-surface-2 border border-border rounded-lg pl-8 pr-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-primary/50"
          />
        </div>
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Token</th>
              <th>Price</th>
              <th>5m</th>
              <th>1h</th>
              <th>Volume 24h</th>
              <th>Liquidity</th>
              <th>AI Score</th>
              <th>Signal</th>
              <th>Age</th>
            </tr>
          </thead>
          <tbody>
            {tokens.map((token, i) => (
              <tr key={token.id}>
                <td className="text-text-muted text-xs w-10">{i + 1}</td>
                <td>
                  <Link href={`/tokens/${token.mint_address}`} className="flex items-center gap-2 hover:text-primary transition-colors">
                    {token.logo_uri ? (
                      <img src={token.logo_uri} alt="" className="w-6 h-6 rounded-full" onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
                    ) : (
                      <div className="w-6 h-6 rounded-full bg-surface-3 text-xs flex items-center justify-center text-text-muted">
                        {(token.symbol || "?")[0]}
                      </div>
                    )}
                    <div>
                      <div className="font-medium text-text-primary text-sm">
                        {token.symbol || "Unknown"}
                      </div>
                      <div className="text-text-muted text-xs font-mono">
                        {token.mint_address.slice(0, 8)}...
                      </div>
                    </div>
                  </Link>
                </td>
                <td className="text-text-primary tabular text-sm">
                  {formatUSD(token.price_usd)}
                </td>
                <td className={`text-sm tabular ${priceChangeColor(token.price_change_1h)}`}>
                  {formatPct(token.price_change_1h)}
                </td>
                <td className={`text-sm tabular ${priceChangeColor(token.price_change_24h)}`}>
                  {formatPct(token.price_change_24h)}
                </td>
                <td className="text-text-secondary text-sm tabular">
                  {formatUSD(token.volume_24h_usd, true)}
                </td>
                <td className="text-text-secondary text-sm tabular">
                  {formatUSD(token.liquidity_usd, true)}
                </td>
                <td className={`font-bold tabular ${scoreColor(token.ai_score)}`}>
                  {token.ai_score?.toFixed(0) ?? "—"}
                </td>
                <td>
                  <DecisionBadge decision={token.ai_decision} size="sm" />
                </td>
                <td className="text-text-muted text-xs">
                  {timeAgo(token.first_seen_at)}
                </td>
              </tr>
            ))}
            {tokens.length === 0 && (
              <tr>
                <td colSpan={10} className="text-center text-text-muted py-12">
                  {search.length >= 2 ? "No tokens match your search." : "Loading tokens..."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
