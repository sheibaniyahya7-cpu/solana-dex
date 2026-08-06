"use client";

import useSWR from "swr";
import { Brain, Zap } from "lucide-react";
import { analysisApi } from "@/lib/api";
import { DecisionBadge, ScoreBadge } from "@/components/ui/Badge";
import { scoreColor, timeAgo } from "@/lib/utils";

const fetcher = (fn: () => Promise<unknown>) => fn().then((r: any) => r.data);

const SCORE_COMPONENTS = [
  { key: "security_score", label: "Security", color: "bg-blue-500" },
  { key: "smart_money_score", label: "Smart Money", color: "bg-purple-500" },
  { key: "volume_score", label: "Volume", color: "bg-amber-500" },
  { key: "liquidity_score", label: "Liquidity", color: "bg-cyan-500" },
  { key: "social_score", label: "Social", color: "bg-pink-500" },
] as const;

export default function AnalysisPage() {
  const { data: topPicks } = useSWR("ai-top-picks",
    () => fetcher(() => analysisApi.getTopPicks(30)), { refreshInterval: 120_000 });

  const picks = (topPicks as any[]) || [];

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="text-text-primary text-2xl font-bold flex items-center gap-2">
          <Brain className="w-6 h-6 text-primary" /> AI Analysis
        </h1>
        <p className="text-text-secondary text-sm mt-1">
          Multi-agent intelligence — Market, Security, Whale, Smart Money, Social → Trader Agent
        </p>
      </div>

      {/* Score weights legend */}
      <div className="card p-4 flex items-center gap-6 flex-wrap">
        <span className="text-text-secondary text-xs font-medium">Score Weights:</span>
        {SCORE_COMPONENTS.map(({ key, label, color }) => (
          <div key={key} className="flex items-center gap-1.5">
            <div className={`w-2 h-2 rounded-full ${color}`} />
            <span className="text-text-muted text-xs">{label}</span>
          </div>
        ))}
      </div>

      {/* Analysis cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {picks.map((pick: any) => (
          <div key={pick.token_mint} className="card p-5 space-y-4 hover:border-border-hover transition-colors">
            {/* Header */}
            <div className="flex items-center justify-between">
              <div>
                <div className="text-text-primary font-bold text-lg">
                  ${pick.token_symbol || pick.token_mint?.slice(0, 6)}
                </div>
                <div className="text-text-muted text-xs font-mono">
                  {pick.token_mint?.slice(0, 12)}...
                </div>
              </div>
              <DecisionBadge decision={pick.decision} />
            </div>

            {/* Final score */}
            <div className="flex items-center gap-4">
              <div>
                <div className="text-text-muted text-xs mb-1">AI Score</div>
                <div className={`text-2xl font-bold tabular ${scoreColor(pick.final_score)}`}>
                  {pick.final_score?.toFixed(0) ?? "—"}
                </div>
              </div>
              <div>
                <div className="text-text-muted text-xs mb-1">Confidence</div>
                <div className="text-text-primary font-semibold">
                  {pick.confidence ? `${(pick.confidence * 100).toFixed(0)}%` : "—"}
                </div>
              </div>
            </div>

            {/* Top signal + risk */}
            {pick.top_reason && (
              <div className="text-sm text-text-secondary flex items-start gap-1.5">
                <span className="text-green-400 shrink-0">✓</span> {pick.top_reason}
              </div>
            )}
            {pick.top_risk && (
              <div className="text-sm text-text-secondary flex items-start gap-1.5">
                <span className="text-amber-400 shrink-0">⚠</span> {pick.top_risk}
              </div>
            )}

            <div className="text-text-muted text-xs pt-1 border-t border-border">
              Analyzed {timeAgo(pick.analyzed_at)}
            </div>
          </div>
        ))}
        {picks.length === 0 && (
          <div className="col-span-3 card p-12 text-center text-text-muted">
            No AI analyses available yet. The system will analyze tokens automatically.
          </div>
        )}
      </div>
    </div>
  );
}
