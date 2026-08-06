import { cn } from "@/lib/utils";
import type { AIDecision, Severity } from "@/types";
import { decisionConfig, severityConfig } from "@/lib/utils";

interface DecisionBadgeProps {
  decision: AIDecision | null | undefined;
  size?: "sm" | "md";
}

export function DecisionBadge({ decision, size = "md" }: DecisionBadgeProps) {
  if (!decision) return <span className="text-slate-500 text-xs">—</span>;
  const cfg = decisionConfig[decision];
  return (
    <span className={cn(
      "inline-flex items-center font-semibold rounded border tracking-wide",
      cfg.color, cfg.bg, cfg.border,
      size === "sm" ? "px-1.5 py-0.5 text-xs" : "px-2 py-1 text-xs",
    )}>
      {cfg.label}
    </span>
  );
}

interface SeverityBadgeProps {
  severity: Severity;
}

export function SeverityBadge({ severity }: SeverityBadgeProps) {
  const cfg = severityConfig[severity];
  return (
    <span className={cn("inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium", cfg.color, cfg.bg)}>
      <span className={cn("w-1.5 h-1.5 rounded-full", cfg.dot)} />
      {severity.charAt(0).toUpperCase() + severity.slice(1)}
    </span>
  );
}

interface ScoreBadgeProps {
  score: number | null | undefined;
  label?: string;
}

export function ScoreBadge({ score, label }: ScoreBadgeProps) {
  if (score === null || score === undefined) return <span className="text-slate-500">—</span>;
  const color = score >= 75 ? "text-emerald-400" : score >= 55 ? "text-amber-400" : "text-red-400";
  return (
    <span className={cn("font-bold tabular-nums", color)}>
      {score.toFixed(0)}{label ? `/${label}` : ""}
    </span>
  );
}
