"use client";

import { useEffect, useRef, useCallback, useState } from "react";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export type WSMessage = { type: string; [key: string]: unknown };

export function useWebSocket(channel: string, onMessage: (msg: WSMessage) => void) {
  const ws = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const reconnectTimer = useRef<NodeJS.Timeout>();

  const connect = useCallback(() => {
    ws.current = new WebSocket(`${WS_URL}/ws/${channel}`);

    ws.current.onopen = () => setConnected(true);

    ws.current.onmessage = (evt) => {
      try {
        const data: WSMessage = JSON.parse(evt.data);
        if (data.type !== "ping") onMessage(data);
      } catch {/* ignore parse errors */}
    };

    ws.current.onclose = () => {
      setConnected(false);
      reconnectTimer.current = setTimeout(connect, 3000);
    };

    ws.current.onerror = () => ws.current?.close();
  }, [channel, onMessage]);

  useEffect(() => {
    connect();
    return () => {
      clearTimeout(reconnectTimer.current);
      ws.current?.close();
    };
  }, [connect]);

  return { connected };
}
