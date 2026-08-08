import axios from "axios";
import type {
  AIAnalysis,
  Alert,
  MarketEvent,
  PriceCandle,
  Token,
  TokenListItem,
  TokenStats,
  WalletListItem,
  WalletTrade,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const apiClient = axios.create({
  baseURL: `${API_BASE}/api/v1`,
  timeout: 20_000,
  headers: { "Content-Type": "application/json" },
});

export interface EventListResponse {
  events: MarketEvent[];
  total: number;
  page: number;
  page_size: number;
}

export interface AlertListResponse {
  alerts: Alert[];
  total: number;
  page: number;
  page_size: number;
}

export interface AnalysisSummary {
  token_mint: string;
  token_symbol: string | null;
  final_score: number | null;
  decision: AIAnalysis["decision"];
  confidence: number | null;
  top_reason: string | null;
  top_risk: string | null;
  analyzed_at: string | null;
}

export const tokenApi = {
  getStats: () => apiClient.get<TokenStats>("/tokens/stats"),
  getTop: (limit = 20) => apiClient.get<TokenListItem[]>("/tokens/top", { params: { limit } }),
  getNew: (hours = 24, limit = 50) =>
    apiClient.get<TokenListItem[]>("/tokens/new", { params: { hours, limit } }),
  search: (q: string, limit = 20) =>
    apiClient.get<TokenListItem[]>("/tokens/search", { params: { q, limit } }),
  getByMint: (mint: string) => apiClient.get<Token>(`/tokens/${mint}`),
  getPriceHistory: (mint: string, interval = "5m", limit = 200) =>
    apiClient.get<PriceCandle[]>(`/tokens/${mint}/price-history`, {
      params: { interval, limit },
    }),
};

export const eventApi = {
  list: (params: { hours?: number; page?: number; page_size?: number; event_type?: string; severity?: string } = {}) =>
    apiClient.get<EventListResponse>("/events", { params }),
  getUnprocessed: (limit = 50) =>
    apiClient.get<MarketEvent[]>("/events/unprocessed", { params: { limit } }),
};

export const walletApi = {
  getSmartMoney: (limit = 50) =>
    apiClient.get<WalletListItem[]>("/wallets/smart-money", { params: { limit } }),
  getWhales: (limit = 50) =>
    apiClient.get<WalletListItem[]>("/wallets/whales", { params: { limit } }),
  getTopPerformers: (limit = 50) =>
    apiClient.get<WalletListItem[]>("/wallets/top-performers", { params: { limit } }),
  getByAddress: (address: string) => apiClient.get(`/wallets/${address}`),
  getTrades: (address: string, limit = 100) =>
    apiClient.get<WalletTrade[]>(`/wallets/${address}/trades`, { params: { limit } }),
};

export const whaleApi = {
  getActivity: (hours = 24, limit = 50) =>
    apiClient.get<MarketEvent[]>("/whales/activity", { params: { hours, limit } }),
  getRecentTrades: (hours = 24, limit = 50) =>
    apiClient.get<WalletTrade[]>("/whales/recent-trades", { params: { hours, limit } }),
  getWallets: (limit = 50) =>
    apiClient.get<WalletListItem[]>("/whales/wallets", { params: { limit } }),
};

export const analysisApi = {
  getLatest: (mint: string) => apiClient.get<AIAnalysis>(`/analysis/${mint}/latest`),
  getHistory: (mint: string, limit = 10) =>
    apiClient.get<AIAnalysis[]>(`/analysis/${mint}/history`, { params: { limit } }),
  getTopPicks: (limit = 20, decision?: string) =>
    apiClient.get<AnalysisSummary[]>("/analysis/summaries/top", {
      params: { limit, ...(decision ? { decision } : {}) },
    }),
  trigger: (mint: string, forceRefresh = false) =>
    apiClient.post("/analysis/trigger", {
      mint_address: mint,
      force_refresh: forceRefresh,
    }),
};

export const alertApi = {
  list: (params: { hours?: number; page?: number; page_size?: number; alert_type?: string } = {}) =>
    apiClient.get<AlertListResponse>("/alerts", { params }),
  getUnsent: () => apiClient.get<Alert[]>("/alerts/unsent"),
};
