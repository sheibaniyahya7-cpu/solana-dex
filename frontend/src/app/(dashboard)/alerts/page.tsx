"use client";

import { useState, useCallback } from "react";
import useSWR from "swr";
import { Bell, CheckCircle, XCircle } from "lucide-react";
import { alertApi } from "@/lib/api";
import { SeverityBadge } from "@/components/ui/Badge";
import { scoreColor, timeAgo } from "@/lib/utils";
import { useWebSocket } from "@/hooks/useWebSocket";
import type { Alert } from "@/types";
import type { WSMessage } from "@/hooks/useWebSocket";

const fetcher = (fn: () => Promise<unknown>) => fn().then((r: any) => r.data);

const ALERT_TYPE_EMOJI: Record<string, string> = {
  SMART_MONEY_ENTRY: "🧠",
  WHALE_BUY: "🐋",
  WHALE_SELL: "⚠️",
  VOLUME_SPIKE: "🔥",
  NEW_TOKEN: "🆕",
  MOMENTUM: "⚡",
  RUG_RISK: "🚨",
  AI_ANALYSIS: "🤖",
  DEFAULT: "📢",
};

export default function AlertsPage() {
  const [liveAlerts, setLiveAlerts] = useState<any[]>([]);

  const handleWsMessage = useCallback((msg: WSMessage) => {
    if (msg.type === "alert") {
      setLiveAlerts((prev) => [msg, ...prev].slice(0, 5));
    }
  }, []);

  useWebSocket("alerts", handleWsMessage);

  const { data } = useSWR("alerts-list",
    () => fetcher(() => alertApi.list({ page_size: 50, hours: 48 })),
    { refreshInterval: 30_000 },
  );

  const alerts: Alert[] = (data as any)?.alerts || [];

  return (
    <div className="space-y-5 animate-fade-in">
      <div>
        <h1 className="text-text-primary text-2xl font-bold flex items-center gap-2">
          <Bell className="w-6 h-6 text-amber-400" /> Alerts
        </h1>
        <p className="text-text-secondary text-sm mt-1">
          Notification history — last 48 hours
        </p>
      </div>

      {/* Live alerts banner */}
      {liveAlerts.length > 0 && (
        <div className="space-y-2">
          <div className="text-text-muted text-xs font-medium uppercase tracking-wider">Live</div>
          {liveAlerts.map((a, i) => (
            <div key={i} className="border border-amber-500/30 bg-amber-500/5 rounded-lg px-4 py-3 flex items-center gap-3 animate-slide-up">
              <span>{ALERT_TYPE_EMOJI[a.event_type as string] || "📢"}</span>
              <div>
                <div className="text-text-primary text-sm font-medium">{a.title as string}</div>
                <div className="text-text-muted text-xs">${(a.token_symbol || a.token_mint || "").toString().slice(0, 10)}</div>
              </div>
              <div className="ml-auto text-xs text-amber-400">Live</div>
            </div>
          ))}
        </div>
      )}

      {/* Alert history */}
      <div className="card overflow-hidden">
        <div className="px-5 py-4 border-b border-border flex items-center justify-between">
          <h2 className="font-semibold text-text-primary text-sm">Alert History</h2>
          <span className="text-text-muted text-xs">{alerts.length} alerts</span>
        </div>
        <div className="divide-y divide-border/50">
          {alerts.map((alert) => (
            <div key={alert.id} className="px-5 py-4 hover:bg-surface-2/30 transition-colors">
              <div className="flex items-start gap-3">
                <div className="text-lg shrink-0">
                  {ALERT_TYPE_EMOJI[alert.alert_type] || ALERT_TYPE_EMOJI.DEFAULT}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-1">
                    <span className="text-text-primary font-medium text-sm">{alert.title}</span>
                    <SeverityBadge severity={alert.severity} />
                    {alert.ai_score && (
                      <span className={`text-xs font-bold tabular ${scoreColor(alert.ai_score)}`}>
                        {alert.ai_score.toFixed(0)}/100
                      </span>
                    )}
                  </div>
                  <p className="text-text-secondary text-sm line-clamp-2">{alert.message}</p>
                </div>
                <div className="flex flex-col items-end gap-1 shrink-0">
                  <span className="text-text-muted text-xs">{timeAgo(alert.created_at)}</span>
                  {alert.is_sent
                    ? <CheckCircle className="w-3.5 h-3.5 text-green-400" />
                    : <XCircle className="w-3.5 h-3.5 text-red-400" />
                  }
                </div>
              </div>
            </div>
          ))}
          {alerts.length === 0 && (
            <div className="px-5 py-12 text-center text-text-muted text-sm">
              No alerts in the last 48 hours.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
