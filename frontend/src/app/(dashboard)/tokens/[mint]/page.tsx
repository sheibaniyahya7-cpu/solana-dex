"use client";

import { useState } from "react";
import useSWR from "swr";
import { ArrowLeft, Shield, Brain, TrendingUp, ExternalLink } from "lucide-react";
import Link from "next/link";
import { tokenApi, analysisApi } from "@/lib/api";
import { PriceChart } from "@/components/charts/PriceChart";
import { DecisionBadge } from "@/components/ui/Badge";
import { ScoreBadge } from "@/components/ui/Badge";
import {
  formatUSD, formatNumber, formatPct, scoreColor,
  priceChangeColor, timeAgo, truncateAddress, cn,
} from "@/lib/utils";
import type { Token, AIAnalysis, PriceCandle } from "@/types";

const fetcher = (fn: () => Promise<unknown>) => fn().then((r: any) => r.data);

export default function TokenDetailPage({ params }: { params: { mint: string } }) {
  const { mint } = params;
  const [chartInterval, setChartInterval] = useState<"1m" | "5m" | "1h">("5m");

  const { data: token } = useSWR(`token-${mint}`, () => fetcher(() => tokenApi.getByMint(mint)), {
    refreshInterval: 15_000,
  });
  const { data: candles } = useSWR(
    `candles-${mint}-${chartInterval}`,
    () => fetcher(() => tokenApi.getPriceHistory(mint, chartInterval, 200)),
    { refreshInterval: 30_000 },
  );
  const { data: analysis } = useSWR(`analysis-${mint}`, () =>
    fetcher(() => analysisApi.getLatest(mint)).catch(() => null),
  );

  const t = token as Token | undefined;
  const a = analysis as AIAnalysis | null | undefined;

  return (
    <div className="space-y-6 animate-fade-in max-w-6xl">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Link href="/tokens" className="text-text-muted hover:text-text-primary transition-colors">
          <ArrowLeft className="w-5 h-5" />
        </Link>
        {t ? (
          <div className="flex items-center gap-3">
            {t.logo_uri && (
              <img src={t.logo_uri} alt="" className="w-10 h-10 rounded-full" />
            )}
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold text-text-primary">{t.symbol}</h1>
                <DecisionBadge decision={t.ai_decision} />
              </div>
              <div className="text-text-muted text-sm font-mono">{truncateAddress(t.mint_address)}</div>
            </div>
          </div>
        ) : (
          <div className="h-8 w-48 bg-surface-2 animate-pulse rounded" />
        )}
      </div>

      {/* Price + Chart */}
      <div className="card p-5 space-y-4">
        <div className="flex items-baseline justify-between flex-wrap gap-4">
          <div>
            <div className="text-3xl font-bold text-text-primary tabular">
              {t ? formatUSD(t.price_usd) : "—"}
            </div>
            <div className="flex items-center gap-3 mt-1">
              {[
                { label: "5m", val: t?.price_change_5m },
                { label: "1h", val: t?.price_change_1h },
                { label: "24h", val: t?.price_change_24h },
              ].map(({ label, val }) => (
                <span key={label} className={`text-sm tabular ${priceChangeColor(val ?? null)}`}>
                  {label}: {formatPct(val ?? null)}
                </span>
              ))}
            </div>
          </div>
          <div className="flex gap-1">
            {(["1m", "5m", "1h"] as const).map((iv) => (
              <button
                key={iv}
                onClick={() => setChartInterval(iv)}
                className={cn(
                  "px-2.5 py-1 rounded text-xs font-medium transition-colors",
                  chartInterval === iv
                    ? "bg-primary text-white"
                    : "bg-surface-2 text-text-secondary hover:text-text-primary",
                )}
              >
                {iv}
              </button>
            ))}
          </div>
        </div>
        <PriceChart candles={(candles as PriceCandle[] | undefined) || []} height={220} />
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Volume 24h", value: formatUSD(t?.volume_24h_usd, true) },
          { label: "Liquidity", value: formatUSD(t?.liquidity_usd, true) },
          { label: "Market Cap", value: formatUSD(t?.market_cap_usd, true) },
          { label: "Holders", value: formatNumber(t?.holder_count) },
        ].map(({ label, value }) => (
          <div key={label} className="card px-4 py-3">
            <div className="text-text-muted text-xs mb-1">{label}</div>
            <div className="text-text-primary font-semibold">{value}</div>
          </div>
        ))}
      </div>

      {/* AI Analysis + Security */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* AI */}
        <div className="card p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Brain className="w-4 h-4 text-primary" />
            <h2 className="font-semibold text-text-primary">AI Analysis</h2>
          </div>
          {a ? (
            <>
              <div className="flex items-center gap-4">
                <div>
                  <div className="text-text-muted text-xs mb-1">Final Score</div>
                  <div className={`text-3xl font-bold tabular ${scoreColor(a.final_score)}`}>
                    {a.final_score?.toFixed(0) ?? "—"}
                  </div>
                </div>
                <DecisionBadge decision={a.decision} />
              </div>
              {a.summary && (
                <p className="text-text-secondary text-sm leading-relaxed">{a.summary}</p>
              )}
              {a.reasons && a.reasons.length > 0 && (
                <div>
                  <div className="text-text-muted text-xs mb-2">Reasons</div>
                  <ul className="space-y-1">
                    {a.reasons.map((r, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                        <span className="text-green-400 mt-0.5">✓</span> {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {a.risks && a.risks.length > 0 && (
                <div>
                  <div className="text-text-muted text-xs mb-2">Risks</div>
                  <ul className="space-y-1">
                    {a.risks.map((r, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                        <span className="text-amber-400 mt-0.5">⚠</span> {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="text-text-muted text-xs">
                Analyzed {timeAgo(a.analyzed_at)} · {a.model_used}
              </div>
            </>
          ) : (
            <div className="text-text-muted text-sm">
              {t ? "No analysis yet. " : "Loading..."}
              {t && (
                <button
                  onClick={() => analysisApi.trigger(mint)}
                  className="text-primary hover:underline"
                >
                  Trigger analysis →
                </button>
              )}
            </div>
          )}
        </div>

        {/* Security */}
        <div className="card p-5 space-y-4">
          <div className="flex items-center gap-2">
            <Shield className="w-4 h-4 text-blue-400" />
            <h2 className="font-semibold text-text-primary">Security</h2>
          </div>
          <div className="flex items-center gap-4">
            <ScoreBadge score={t?.security_score} label="100" />
            <div className="text-sm text-text-secondary">
              Rug probability:{" "}
              <span className={t?.rug_probability && t.rug_probability > 0.5 ? "text-red-400 font-semibold" : "text-text-primary"}>
                {t?.rug_probability ? `${(t.rug_probability * 100).toFixed(0)}%` : "N/A"}
              </span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {[
              { label: "Mint Authority", value: t?.has_mint_authority, risky: true },
              { label: "Freeze Authority", value: t?.has_freeze_authority, risky: true },
              { label: "Mutable Metadata", value: t?.is_mutable, risky: true },
            ].map(({ label, value, risky }) => (
              <div key={label} className="bg-surface-2 rounded-lg px-3 py-2.5">
                <div className="text-text-muted text-xs mb-1">{label}</div>
                <div className={cn("text-sm font-medium",
                  value === null || value === undefined ? "text-text-muted" :
                  risky && value ? "text-red-400" : "text-green-400"
                )}>
                  {value === null || value === undefined ? "Unknown" : value ? "Active ⚠" : "Revoked ✓"}
                </div>
              </div>
            ))}
            <div className="bg-surface-2 rounded-lg px-3 py-2.5">
              <div className="text-text-muted text-xs mb-1">Top 10 Holders</div>
              <div className={cn("text-sm font-medium",
                !t?.top_10_holder_pct ? "text-text-muted" :
                t.top_10_holder_pct > 60 ? "text-red-400" :
                t.top_10_holder_pct > 40 ? "text-amber-400" : "text-green-400"
              )}>
                {t?.top_10_holder_pct ? `${t.top_10_holder_pct.toFixed(1)}%` : "N/A"}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
