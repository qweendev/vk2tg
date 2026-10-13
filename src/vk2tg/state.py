from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class RouteState(Base):
    __tablename__ = "routes"

    key: Mapped[str] = mapped_column(String(512), primary_key=True)
    last_post_id: Mapped[int] = mapped_column(BigInteger)


class State:
    """Remembers the newest VK post already handled for every route, so restarts never repost."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def last_post_id(self, key: str) -> int | None:
        async with self._sessions() as session:
            row = await session.get(RouteState, key)
            return row.last_post_id if row else None

    async def save(self, key: str, post_id: int) -> None:
        async with self._sessions.begin() as session:
            row = await session.get(RouteState, key)
            if row is None:
                session.add(RouteState(key=key, last_post_id=post_id))
            else:
                row.last_post_id = post_id
