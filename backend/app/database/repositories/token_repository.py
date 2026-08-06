"""
Token repository — all database queries related to tokens.
"""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import List, Optional, Sequence
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.token import Token, TokenPriceHistory
from app.database.repositories.base_repository import BaseRepository


class TokenRepository(BaseRepository[Token]):
    model = Token

    async def get_by_mint(self, mint_address: str) -> Optional[Token]:
        stmt = select(Token).where(Token.mint_address == mint_address)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self, mint_address: str, defaults: dict
    ) -> tuple[Token, bool]:
        """Return (token, created). Upsert by mint address."""
        token = await self.get_by_mint(mint_address)
        if token:
            return token, False
        token = Token(mint_address=mint_address, **defaults)
        self.session.add(token)
        await self.session.flush()
        return token, True

    async def get_active_tokens(
        self,
        limit: int = 100,
        offset: int = 0,
        min_liquidity: float = 0,
        min_score: float = 0,
    ) -> Sequence[Token]:
        stmt = (
            select(Token)
            .where(
                and_(
                    Token.is_active == True,
                    Token.liquidity_usd >= min_liquidity,
                )
            )
            .order_by(desc(Token.ai_score))
            .limit(limit)
            .offset(offset)
        )
        if min_score > 0:
            stmt = stmt.where(Token.ai_score >= min_score)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_new_tokens(self, hours: int = 24, limit: int = 50) -> Sequence[Token]:
        """Tokens discovered in the last N hours."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        stmt = (
            select(Token)
            .where(Token.first_seen_at >= cutoff)
            .order_by(desc(Token.first_seen_at))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_top_by_score(self, limit: int = 20) -> Sequence[Token]:
        stmt = (
            select(Token)
            .where(and_(Token.is_active == True, Token.ai_score.isnot(None)))
            .order_by(desc(Token.ai_score))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def search(self, query: str, limit: int = 20) -> Sequence[Token]:
        stmt = (
            select(Token)
            .where(
                or_(
                    Token.symbol.ilike(f"%{query}%"),
                    Token.name.ilike(f"%{query}%"),
                    Token.mint_address.ilike(f"{query}%"),
                )
            )
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def update_market_data(self, mint: str, data: dict) -> Optional[Token]:
        stmt = (
            update(Token)
            .where(Token.mint_address == mint)
            .values(**data, last_updated_at=datetime.now(timezone.utc))
            .returning(Token)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def bulk_update_prices(self, updates: list[dict]) -> None:
        """Efficiently update prices for many tokens at once."""
        for upd in updates:
            mint = upd.pop("mint_address")
            await self.session.execute(
                update(Token)
                .where(Token.mint_address == mint)
                .values(**upd)
            )

    # ─── Price History ────────────────────────────────────────────────────────

    async def add_price_candle(self, candle: TokenPriceHistory) -> TokenPriceHistory:
        self.session.add(candle)
        await self.session.flush()
        return candle

    async def get_price_history(
        self,
        token_id: UUID,
        interval: str = "5m",
        limit: int = 200,
    ) -> Sequence[TokenPriceHistory]:
        stmt = (
            select(TokenPriceHistory)
            .where(
                and_(
                    TokenPriceHistory.token_id == token_id,
                    TokenPriceHistory.interval == interval,
                )
            )
            .order_by(desc(TokenPriceHistory.timestamp))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
