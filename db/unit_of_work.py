from types import TracebackType
from typing import Optional, Type

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.repositories.sqlalchemy.user_repo import SQLAlchemyUserRepository
from db.repositories.sqlalchemy.whitelist_repo import SQLAlchemyWhitelistRepository


class UnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __aenter__(self) -> "UnitOfWork":
        self._session: AsyncSession = self._session_factory()
        self.users = SQLAlchemyUserRepository(self._session)
        self.whitelist = SQLAlchemyWhitelistRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        if exc_type:
            await self._session.rollback()
        await self._session.close()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
