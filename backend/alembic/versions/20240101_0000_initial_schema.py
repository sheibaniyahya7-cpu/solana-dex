"""Initial schema — creates dex schema and all core tables.

Revision ID: 0001_initial
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─── Schema ───────────────────────────────────────────────────────────────
    op.execute("CREATE SCHEMA IF NOT EXISTS dex")

    # ─── tokens ───────────────────────────────────────────────────────────────
    op.create_table(
        "tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("mint_address", sa.String(44), nullable=False),
        sa.Column("symbol", sa.String(32), nullable=True),
        sa.Column("name", sa.String(128), nullable=True),
        sa.Column("decimals", sa.Integer(), default=9, nullable=False),
        sa.Column("logo_uri", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        # Market
        sa.Column("price_usd", sa.Numeric(30, 12), nullable=True),
        sa.Column("price_sol", sa.Numeric(30, 12), nullable=True),
        sa.Column("market_cap_usd", sa.Numeric(30, 2), nullable=True),
        sa.Column("fully_diluted_value", sa.Numeric(30, 2), nullable=True),
        sa.Column("total_supply", sa.Numeric(38, 0), nullable=True),
        sa.Column("circulating_supply", sa.Numeric(38, 0), nullable=True),
        # Volume
        sa.Column("volume_24h_usd", sa.Numeric(30, 2), nullable=True),
        sa.Column("volume_1h_usd", sa.Numeric(30, 2), nullable=True),
        sa.Column("volume_5m_usd", sa.Numeric(30, 2), nullable=True),
        sa.Column("liquidity_usd", sa.Numeric(30, 2), nullable=True),
        # Price changes
        sa.Column("price_change_5m", sa.Float(), nullable=True),
        sa.Column("price_change_1h", sa.Float(), nullable=True),
        sa.Column("price_change_6h", sa.Float(), nullable=True),
        sa.Column("price_change_24h", sa.Float(), nullable=True),
        # TX counts
        sa.Column("tx_count_5m", sa.Integer(), nullable=True),
        sa.Column("tx_count_1h", sa.Integer(), nullable=True),
        sa.Column("tx_count_24h", sa.Integer(), nullable=True),
        sa.Column("buys_5m", sa.Integer(), nullable=True),
        sa.Column("sells_5m", sa.Integer(), nullable=True),
        sa.Column("buys_1h", sa.Integer(), nullable=True),
        sa.Column("sells_1h", sa.Integer(), nullable=True),
        # Holders
        sa.Column("holder_count", sa.Integer(), nullable=True),
        sa.Column("top_10_holder_pct", sa.Float(), nullable=True),
        sa.Column("dev_wallet_pct", sa.Float(), nullable=True),
        # Security
        sa.Column("has_mint_authority", sa.Boolean(), default=True, nullable=False),
        sa.Column("has_freeze_authority", sa.Boolean(), default=True, nullable=False),
        sa.Column("is_mutable", sa.Boolean(), default=True, nullable=False),
        sa.Column("security_score", sa.Float(), nullable=True),
        sa.Column("rug_probability", sa.Float(), nullable=True),
        # AI scores
        sa.Column("ai_score", sa.Float(), nullable=True),
        sa.Column("smart_money_score", sa.Float(), nullable=True),
        sa.Column("volume_score", sa.Float(), nullable=True),
        sa.Column("liquidity_score", sa.Float(), nullable=True),
        sa.Column("social_score", sa.Float(), nullable=True),
        sa.Column("ai_decision", sa.String(20), nullable=True),
        sa.Column("ai_analysis_text", sa.Text(), nullable=True),
        sa.Column("ai_analyzed_at", sa.DateTime(timezone=True), nullable=True),
        # DEX info
        sa.Column("dex_id", sa.String(64), nullable=True),
        sa.Column("pair_address", sa.String(44), nullable=True),
        sa.Column("base_token_address", sa.String(44), nullable=True),
        sa.Column("quote_token_address", sa.String(44), nullable=True),
        # Social
        sa.Column("website", sa.Text(), nullable=True),
        sa.Column("twitter", sa.Text(), nullable=True),
        sa.Column("telegram", sa.Text(), nullable=True),
        sa.Column("discord", sa.Text(), nullable=True),
        # Status
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("is_verified", sa.Boolean(), default=False, nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_tokens"),
        sa.UniqueConstraint("mint_address", name="uq_tokens_mint_address"),
        schema="dex",
    )
    op.create_index("ix_tokens_symbol", "tokens", ["symbol"], schema="dex")
    op.create_index("ix_tokens_created_at", "tokens", ["created_at"], schema="dex")
    op.create_index("ix_tokens_ai_score", "tokens", ["ai_score"], schema="dex")
    op.create_index("ix_tokens_is_active", "tokens", ["is_active"], schema="dex")

    # ─── token_price_history ──────────────────────────────────────────────────
    op.create_table(
        "token_price_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("token_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval", sa.String(8), nullable=False),
        sa.Column("open", sa.Numeric(30, 12), nullable=True),
        sa.Column("high", sa.Numeric(30, 12), nullable=True),
        sa.Column("low", sa.Numeric(30, 12), nullable=True),
        sa.Column("close", sa.Numeric(30, 12), nullable=True),
        sa.Column("volume_usd", sa.Numeric(30, 2), nullable=True),
        sa.Column("tx_count", sa.Integer(), nullable=True),
        sa.Column("buys", sa.Integer(), nullable=True),
        sa.Column("sells", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["token_id"], ["dex.tokens.id"], name="fk_price_history_token", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_token_price_history"),
        schema="dex",
    )
    op.create_index("ix_price_history_token_ts", "token_price_history", ["token_id", "timestamp"], schema="dex")
    op.create_index("ix_price_history_timestamp", "token_price_history", ["timestamp"], schema="dex")

    # ─── wallets ──────────────────────────────────────────────────────────────
    op.create_table(
        "wallets",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("address", sa.String(44), nullable=False),
        sa.Column("label", sa.String(128), nullable=True),
        sa.Column("wallet_type", sa.String(20), default="unknown", nullable=False),
        sa.Column("is_smart_money", sa.Boolean(), default=False, nullable=False),
        sa.Column("is_whale", sa.Boolean(), default=False, nullable=False),
        sa.Column("is_insider", sa.Boolean(), default=False, nullable=False),
        sa.Column("is_bot", sa.Boolean(), default=False, nullable=False),
        sa.Column("is_tracked", sa.Boolean(), default=True, nullable=False),
        sa.Column("total_trades", sa.Integer(), default=0, nullable=False),
        sa.Column("winning_trades", sa.Integer(), default=0, nullable=False),
        sa.Column("losing_trades", sa.Integer(), default=0, nullable=False),
        sa.Column("win_rate", sa.Float(), nullable=True),
        sa.Column("total_pnl_usd", sa.Numeric(30, 2), nullable=True),
        sa.Column("total_pnl_sol", sa.Numeric(20, 6), nullable=True),
        sa.Column("realized_pnl_usd", sa.Numeric(30, 2), nullable=True),
        sa.Column("unrealized_pnl_usd", sa.Numeric(30, 2), nullable=True),
        sa.Column("roi_pct", sa.Float(), nullable=True),
        sa.Column("avg_profit_per_trade_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("avg_loss_per_trade_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("best_trade_pnl_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("worst_trade_pnl_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("avg_holding_time_hours", sa.Float(), nullable=True),
        sa.Column("avg_entry_timing_score", sa.Float(), nullable=True),
        sa.Column("avg_exit_timing_score", sa.Float(), nullable=True),
        sa.Column("preferred_trade_size_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("sol_balance", sa.Numeric(20, 6), nullable=True),
        sa.Column("portfolio_value_usd", sa.Numeric(30, 2), nullable=True),
        sa.Column("token_count", sa.Integer(), default=0, nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("score_breakdown", postgresql.JSONB(), nullable=True),
        sa.Column("first_trade_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_trade_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_analyzed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_wallets"),
        sa.UniqueConstraint("address", name="uq_wallets_address"),
        schema="dex",
    )
    op.create_index("ix_wallets_address", "wallets", ["address"], unique=True, schema="dex")
    op.create_index("ix_wallets_wallet_type", "wallets", ["wallet_type"], schema="dex")
    op.create_index("ix_wallets_score", "wallets", ["score"], schema="dex")
    op.create_index("ix_wallets_win_rate", "wallets", ["win_rate"], schema="dex")

    # ─── wallet_trades ────────────────────────────────────────────────────────
    op.create_table(
        "wallet_trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("wallet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_mint", sa.String(44), nullable=False),
        sa.Column("token_symbol", sa.String(32), nullable=True),
        sa.Column("trade_type", sa.String(10), nullable=False),
        sa.Column("trade_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signature", sa.String(88), nullable=False),
        sa.Column("amount_token", sa.Numeric(38, 9), nullable=True),
        sa.Column("amount_sol", sa.Numeric(20, 9), nullable=True),
        sa.Column("amount_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("price_per_token_usd", sa.Numeric(30, 12), nullable=True),
        sa.Column("pnl_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("holding_time_hours", sa.Float(), nullable=True),
        sa.Column("is_profitable", sa.Boolean(), nullable=True),
        sa.Column("dex_program", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["wallet_id"], ["dex.wallets.id"], name="fk_wallet_trades_wallet", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_wallet_trades"),
        schema="dex",
    )
    op.create_index("ix_wallet_trades_wallet_id", "wallet_trades", ["wallet_id"], schema="dex")
    op.create_index("ix_wallet_trades_token_mint", "wallet_trades", ["token_mint"], schema="dex")
    op.create_index("ix_wallet_trades_timestamp", "wallet_trades", ["trade_timestamp"], schema="dex")

    # ─── wallet_holdings ──────────────────────────────────────────────────────
    op.create_table(
        "wallet_holdings",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("wallet_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_mint", sa.String(44), nullable=False),
        sa.Column("token_symbol", sa.String(32), nullable=True),
        sa.Column("balance", sa.Numeric(38, 9), nullable=False),
        sa.Column("value_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("avg_buy_price_usd", sa.Numeric(30, 12), nullable=True),
        sa.Column("unrealized_pnl_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("unrealized_pnl_pct", sa.Float(), nullable=True),
        sa.Column("first_buy_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["wallet_id"], ["dex.wallets.id"], name="fk_wallet_holdings_wallet", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_wallet_holdings"),
        schema="dex",
    )
    op.create_index("ix_wallet_holdings_wallet_id", "wallet_holdings", ["wallet_id"], schema="dex")
    op.create_index("ix_wallet_holdings_token_mint", "wallet_holdings", ["token_mint"], schema="dex")

    # ─── market_events ────────────────────────────────────────────────────────
    op.create_table(
        "market_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("token_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_mint", sa.String(44), nullable=False),
        sa.Column("token_symbol", sa.String(32), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(10), default="medium", nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("price_usd_at_event", sa.Numeric(30, 12), nullable=True),
        sa.Column("volume_usd_at_event", sa.Numeric(30, 2), nullable=True),
        sa.Column("liquidity_usd_at_event", sa.Numeric(30, 2), nullable=True),
        sa.Column("volume_change_pct", sa.Float(), nullable=True),
        sa.Column("price_change_pct", sa.Float(), nullable=True),
        sa.Column("liquidity_change_pct", sa.Float(), nullable=True),
        sa.Column("smart_wallets_count", sa.Integer(), default=0, nullable=False),
        sa.Column("smart_wallets_addresses", postgresql.JSONB(), nullable=True),
        sa.Column("whale_wallet_address", sa.String(44), nullable=True),
        sa.Column("whale_amount_usd", sa.Numeric(20, 2), nullable=True),
        sa.Column("ai_score", sa.Float(), nullable=True),
        sa.Column("ai_decision", sa.String(20), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("ai_confidence", sa.Float(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_processed", sa.Boolean(), default=False, nullable=False),
        sa.Column("is_alerted", sa.Boolean(), default=False, nullable=False),
        sa.Column("alerted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["token_id"], ["dex.tokens.id"], name="fk_market_events_token", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_market_events"),
        schema="dex",
    )
    op.create_index("ix_market_events_token_id", "market_events", ["token_id"], schema="dex")
    op.create_index("ix_market_events_event_type", "market_events", ["event_type"], schema="dex")
    op.create_index("ix_market_events_severity", "market_events", ["severity"], schema="dex")
    op.create_index("ix_market_events_detected_at", "market_events", ["detected_at"], schema="dex")
    op.create_index("ix_market_events_is_processed", "market_events", ["is_processed"], schema="dex")

    # ─── alerts ───────────────────────────────────────────────────────────────
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("token_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(10), default="medium", nullable=False),
        sa.Column("title", sa.String(256), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("ai_score", sa.Float(), nullable=True),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("channel_id", sa.String(128), nullable=True),
        sa.Column("is_sent", sa.Boolean(), default=False, nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), default=0, nullable=False),
        sa.Column("extra_data", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["token_id"], ["dex.tokens.id"], name="fk_alerts_token", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["event_id"], ["dex.market_events.id"], name="fk_alerts_event", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name="pk_alerts"),
        schema="dex",
    )
    op.create_index("ix_alerts_token_id", "alerts", ["token_id"], schema="dex")
    op.create_index("ix_alerts_event_id", "alerts", ["event_id"], schema="dex")
    op.create_index("ix_alerts_alert_type", "alerts", ["alert_type"], schema="dex")
    op.create_index("ix_alerts_sent_at", "alerts", ["sent_at"], schema="dex")

    # ─── ai_analyses ──────────────────────────────────────────────────────────
    op.create_table(
        "ai_analyses",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("token_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_mint", sa.String(44), nullable=False),
        sa.Column("token_symbol", sa.String(32), nullable=True),
        sa.Column("market_agent_output", postgresql.JSONB(), nullable=True),
        sa.Column("security_agent_output", postgresql.JSONB(), nullable=True),
        sa.Column("whale_agent_output", postgresql.JSONB(), nullable=True),
        sa.Column("wallet_agent_output", postgresql.JSONB(), nullable=True),
        sa.Column("social_agent_output", postgresql.JSONB(), nullable=True),
        sa.Column("security_score", sa.Float(), nullable=True),
        sa.Column("smart_money_score", sa.Float(), nullable=True),
        sa.Column("volume_score", sa.Float(), nullable=True),
        sa.Column("liquidity_score", sa.Float(), nullable=True),
        sa.Column("social_score", sa.Float(), nullable=True),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("decision", sa.String(20), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("reasons", postgresql.JSONB(), nullable=True),
        sa.Column("risks", postgresql.JSONB(), nullable=True),
        sa.Column("catalysts", postgresql.JSONB(), nullable=True),
        sa.Column("raw_trader_output", sa.Text(), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_used", sa.String(64), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("analysis_duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["token_id"], ["dex.tokens.id"], name="fk_ai_analyses_token", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_ai_analyses"),
        schema="dex",
    )
    op.create_index("ix_ai_analyses_token_id", "ai_analyses", ["token_id"], schema="dex")
    op.create_index("ix_ai_analyses_analyzed_at", "ai_analyses", ["analyzed_at"], schema="dex")
    op.create_index("ix_ai_analyses_final_score", "ai_analyses", ["final_score"], schema="dex")
    op.create_index("ix_ai_analyses_decision", "ai_analyses", ["decision"], schema="dex")


def downgrade() -> None:
    op.drop_table("ai_analyses", schema="dex")
    op.drop_table("alerts", schema="dex")
    op.drop_table("market_events", schema="dex")
    op.drop_table("wallet_holdings", schema="dex")
    op.drop_table("wallet_trades", schema="dex")
    op.drop_table("wallets", schema="dex")
    op.drop_table("token_price_history", schema="dex")
    op.drop_table("tokens", schema="dex")
    op.execute("DROP SCHEMA IF EXISTS dex CASCADE")
