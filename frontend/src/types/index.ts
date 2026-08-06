// ─── Token ────────────────────────────────────────────────────────────────────

export type AIDecision = "STRONG_BUY" | "BUY" | "WATCH" | "AVOID" | "DANGER";

export interface Token {
  id: string;
  mint_address: string;
  symbol: string | null;
  name: string | null;
  logo_uri: string | null;
  decimals: number;
  // Market
  price_usd: string | null;
  price_sol: string | null;
  market_cap_usd: string | null;
  volume_24h_usd: string | null;
  volume_1h_usd: string | null;
  volume_5m_usd: string | null;
  liquidity_usd: string | null;
  // Price changes
  price_change_5m: number | null;
  price_change_1h: number | null;
  price_change_6h: number | null;
  price_change_24h: number | null;
  // Transactions
  buys_1h: number | null;
  sells_1h: number | null;
  buys_5m: number | null;
  sells_5m: number | null;
  tx_count_24h: number | null;
  // Security
  has_mint_authority: boolean;
  has_freeze_authority: boolean;
  is_mutable: boolean;
  holder_count: number | null;
  top_10_holder_pct: number | null;
  dev_wallet_pct: number | null;
  security_score: number | null;
  rug_probability: number | null;
  // AI
  ai_score: number | null;
  ai_decision: AIDecision | null;
  ai_analysis_text: string | null;
  ai_analyzed_at: string | null;
  smart_money_score: number | null;
  // DEX
  pair_address: string | null;
  dex_id: string | null;
  // Social
  website: string | null;
  twitter: string | null;
  telegram: string | null;
  // Status
  is_active: boolean;
  is_verified: boolean;
  first_seen_at: string | null;
  last_updated_at: string | null;
  created_at: string;
}

export interface TokenListItem {
  id: string;
  mint_address: string;
  symbol: string | null;
  name: string | null;
  logo_uri: string | null;
  price_usd: string | null;
  price_change_1h: number | null;
  price_change_24h: number | null;
  volume_24h_usd: string | null;
  liquidity_usd: string | null;
  ai_score: number | null;
  ai_decision: AIDecision | null;
  security_score: number | null;
  first_seen_at: string | null;
  is_verified: boolean;
}

export interface PriceCandle {
  timestamp: string;
  interval: string;
  open: string | null;
  high: string | null;
  low: string | null;
  close: string | null;
  volume_usd: string | null;
  buys: number | null;
  sells: number | null;
}

export interface TokenStats {
  total_tokens: number;
  active_tokens: number;
  new_tokens_24h: number;
  total_volume_24h_usd: string | null;
  total_liquidity_usd: string | null;
  avg_ai_score: number | null;
  top_movers: TokenListItem[];
  top_by_volume: TokenListItem[];
  top_by_score: TokenListItem[];
}

// ─── Wallet ───────────────────────────────────────────────────────────────────

export type WalletType = "smart_money" | "whale" | "insider" | "retail" | "unknown";

export interface WalletListItem {
  id: string;
  address: string;
  label: string | null;
  wallet_type: WalletType;
  is_smart_money: boolean;
  is_whale: boolean;
  win_rate: number | null;
  total_pnl_usd: string | null;
  roi_pct: number | null;
  total_trades: number;
  score: number | null;
  last_trade_at: string | null;
}

export interface Wallet extends WalletListItem {
  winning_trades: number;
  is_insider: boolean;
  avg_profit_per_trade_usd: string | null;
  avg_holding_time_hours: number | null;
  avg_entry_timing_score: number | null;
  avg_exit_timing_score: number | null;
  sol_balance: string | null;
  portfolio_value_usd: string | null;
  token_count: number;
  score_breakdown: Record<string, number> | null;
  last_analyzed_at: string | null;
  tags: string[] | null;
}

export interface WalletTrade {
  id: string;
  token_mint: string;
  token_symbol: string | null;
  trade_type: "buy" | "sell";
  trade_timestamp: string;
  signature: string;
  amount_usd: string | null;
  price_per_token_usd: string | null;
  pnl_usd: string | null;
  pnl_pct: number | null;
  holding_time_hours: number | null;
  is_profitable: boolean | null;
  dex_program: string | null;
}

// ─── Market Event ─────────────────────────────────────────────────────────────

export type EventType =
  | "VOLUME_SPIKE" | "PRICE_SPIKE" | "PRICE_DROP"
  | "WHALE_BUY" | "WHALE_SELL"
  | "SMART_MONEY_ENTRY" | "SMART_MONEY_EXIT"
  | "NEW_TOKEN" | "MOMENTUM" | "RUG_RISK"
  | "LIQUIDITY_ADD" | "LIQUIDITY_REMOVE";

export type Severity = "low" | "medium" | "high" | "critical";

export interface MarketEvent {
  id: string;
  token_id: string;
  token_mint: string;
  token_symbol: string | null;
  event_type: EventType;
  severity: Severity;
  title: string;
  description: string;
  price_usd_at_event: string | null;
  volume_usd_at_event: string | null;
  volume_change_pct: number | null;
  price_change_pct: number | null;
  smart_wallets_count: number;
  whale_wallet_address: string | null;
  whale_amount_usd: string | null;
  ai_score: number | null;
  ai_decision: AIDecision | null;
  ai_summary: string | null;
  detected_at: string;
  is_processed: boolean;
  is_alerted: boolean;
}

// ─── AI Analysis ──────────────────────────────────────────────────────────────

export interface AIAnalysis {
  id: string;
  token_id: string;
  token_mint: string;
  token_symbol: string | null;
  security_score: number | null;
  smart_money_score: number | null;
  volume_score: number | null;
  liquidity_score: number | null;
  social_score: number | null;
  final_score: number | null;
  decision: AIDecision | null;
  confidence: number | null;
  summary: string | null;
  reasons: string[] | null;
  risks: string[] | null;
  catalysts: string[] | null;
  analyzed_at: string;
  model_used: string | null;
  analysis_duration_ms: number | null;
}

// ─── Alert ────────────────────────────────────────────────────────────────────

export interface Alert {
  id: string;
  token_id: string | null;
  event_id: string | null;
  alert_type: string;
  severity: Severity;
  title: string;
  message: string;
  ai_score: number | null;
  channel: string;
  is_sent: boolean;
  sent_at: string | null;
  created_at: string;
}

// ─── API Pagination ───────────────────────────────────────────────────────────

export interface PaginatedResponse<T> {
  items?: T[];
  tokens?: T[];
  wallets?: T[];
  events?: T[];
  alerts?: T[];
  total: number;
  page: number;
  page_size: number;
}
