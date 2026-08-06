"""
Generic async repository base class.
Provides CRUD operations for any SQLAlchemy model.
All specific repositories extend this class.
"""

from typing import Any, Dict, Generic, List, Optional, Sequence, Type, TypeVar
from uuid import UUID

from sqlalchemy import func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """
    Generic repository providing standard CRUD + pagination.
    Usage: class TokenRepository(BaseRepository[Token]):
               model = Token
    """

    model: Type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, id: UUID) -> Optional[ModelT]:
        result = await self.session.get(self.model, id)
        return result

    async def get_all(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by=None,
    ) -> Sequence[ModelT]:
        stmt = select(self.model)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        stmt = stmt.limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count(self) -> int:
        stmt = select(func.count()).select_from(self.model)
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def create(self, obj: ModelT) -> ModelT:
        self.session.add(obj)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def create_many(self, objs: List[ModelT]) -> List[ModelT]:
        self.session.add_all(objs)
        await self.session.flush()
        return objs

    async def update(self, obj: ModelT, data: Dict[str, Any]) -> ModelT:
        for field, value in data.items():
            setattr(obj, field, value)
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
        await self.session.flush()

    async def exists(self, **kwargs) -> bool:
        stmt = select(self.model).filter_by(**kwargs).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar() is not None
