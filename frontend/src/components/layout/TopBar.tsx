"use client";

import { useState, useCallback } from "react";
import { Search, Wifi, WifiOff } from "lucide-react";
import { useWebSocket } from "@/hooks/useWebSocket";
import type { WSMessage } from "@/hooks/useWebSocket";

export function TopBar() {
  const [liveEventCount, setLiveEventCount] = useState(0);

  const handleMessage = useCallback((msg: WSMessage) => {
    if (msg.type === "market_event") {
      setLiveEventCount((c) => c + 1);
    }
  }, []);

  const { connected } = useWebSocket("events", handleMessage);

  return (
    <header className="h-14 bg-surface border-b border-border px-6 flex items-center justify-between shrink-0">
      {/* Search */}
      <div className="relative w-72">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted" />
        <input
          type="text"
          placeholder="Search tokens, wallets..."
          className="w-full bg-surface-2 border border-border rounded-lg pl-9 pr-4 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-primary/50 transition-colors"
        />
      </div>

      {/* Status indicators */}
      <div className="flex items-center gap-4">
        {liveEventCount > 0 && (
          <span className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2.5 py-1 rounded-full">
            {liveEventCount} new events
          </span>
        )}

        <div className={`flex items-center gap-1.5 text-xs ${connected ? "text-green-400" : "text-red-400"}`}>
          {connected ? <Wifi className="w-3.5 h-3.5" /> : <WifiOff className="w-3.5 h-3.5" />}
          {connected ? "Live" : "Offline"}
        </div>
      </div>
    </header>
  );
}
