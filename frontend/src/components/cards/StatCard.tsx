import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

interface StatCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: ReactNode;
  trend?: number | null;
  className?: string;
}

export function StatCard({ title, value, subtitle, icon, trend, className }: StatCardProps) {
  return (
    <div className={cn(
      "bg-surface border border-border rounded-xl p-5 flex flex-col gap-3 hover:border-border-hover transition-colors",
      className,
    )}>
      <div className="flex items-center justify-between">
        <span className="text-text-secondary text-sm font-medium">{title}</span>
        {icon && <span className="text-text-muted">{icon}</span>}
      </div>
      <div className="flex items-end justify-between">
        <span className="text-text-primary text-2xl font-bold tabular-nums">{value}</span>
        {trend !== null && trend !== undefined && (
          <span className={cn(
            "text-sm font-medium",
            trend > 0 ? "text-green-400" : trend < 0 ? "text-red-400" : "text-slate-400",
          )}>
            {trend > 0 ? "+" : ""}{trend.toFixed(1)}%
          </span>
        )}
      </div>
      {subtitle && <span className="text-text-muted text-xs">{subtitle}</span>}
    </div>
  );
}
