"""
Wallet repository — queries for wallet tracking and smart money analysis.
"""

from datetime import datetime, timezone, timedelta
from typing import List, Optional, Sequence
from uuid import UUID

from sqlalchemy import and_, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.wallet import Wallet, WalletTrade, WalletHolding
from app.database.repositories.base_repository import BaseRepository


class WalletRepository(BaseRepository[Wallet]):
    model = Wallet

    async def get_by_address(self, address: str) -> Optional[Wallet]:
        stmt = select(Wallet).where(Wallet.address == address)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self, address: str, defaults: dict = None) -> tuple[Wallet, bool]:
        wallet = await self.get_by_address(address)
        if wallet:
            return wallet, False
        wallet = Wallet(address=address, **(defaults or {}))
        self.session.add(wallet)
        await self.session.flush()
        return wallet, True

    async def get_smart_money_wallets(self, limit: int = 100) -> Sequence[Wallet]:
        stmt = (
            select(Wallet)
            .where(and_(Wallet.is_smart_money == True, Wallet.is_tracked == True))
            .order_by(desc(Wallet.score))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_whale_wallets(self, limit: int = 50) -> Sequence[Wallet]:
        stmt = (
            select(Wallet)
            .where(and_(Wallet.is_whale == True, Wallet.is_tracked == True))
            .order_by(desc(Wallet.portfolio_value_usd))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_top_performers(self, limit: int = 50, min_trades: int = 10) -> Sequence[Wallet]:
        stmt = (
            select(Wallet)
            .where(Wallet.total_trades >= min_trades)
            .order_by(desc(Wallet.win_rate))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_wallets_holding_token(self, token_mint: str) -> Sequence[Wallet]:
        """Find tracked wallets currently holding a specific token."""
        stmt = (
            select(Wallet)
            .join(WalletHolding, WalletHolding.wallet_id == Wallet.id)
            .where(
                and_(
                    WalletHolding.token_mint == token_mint,
                    Wallet.is_smart_money == True,
                )
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_stale_wallets(self, hours: int = 6) -> Sequence[Wallet]:
        """Wallets that haven't been analyzed recently."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = (
            select(Wallet)
            .where(
                and_(
                    Wallet.is_tracked == True,
                    Wallet.last_analyzed_at < cutoff,
                )
            )
            .limit(200)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    # ─── Trades ───────────────────────────────────────────────────────────────

    async def add_trade(self, trade: WalletTrade) -> WalletTrade:
        self.session.add(trade)
        await self.session.flush()
        return trade

    async def get_wallet_trades(
        self,
        wallet_id: UUID,
        limit: int = 100,
        token_mint: Optional[str] = None,
    ) -> Sequence[WalletTrade]:
        stmt = (
            select(WalletTrade)
            .where(WalletTrade.wallet_id == wallet_id)
            .order_by(desc(WalletTrade.trade_timestamp))
            .limit(limit)
        )
        if token_mint:
            stmt = stmt.where(WalletTrade.token_mint == token_mint)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def trade_signature_exists(self, signature: str) -> bool:
        stmt = select(WalletTrade.id).where(WalletTrade.signature == signature).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar() is not None
