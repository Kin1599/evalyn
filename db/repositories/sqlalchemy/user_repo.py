from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.user import User
from db.repositories.user_repo import AbstractUserRepository


class SQLAlchemyUserRepository(AbstractUserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, id: int) -> Optional[User]:
        return await self.get_by_telegram_id(id)

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def create(self, telegram_id: int, name: str, username: Optional[str]) -> User:
        user = User(telegram_id=telegram_id, name=name, username=username)
        self._session.add(user)
        await self._session.flush()
        return user

    async def update(self, id: int, **kwargs) -> Optional[User]:
        await self._session.execute(
            update(User).where(User.telegram_id == id).values(**kwargs)
        )
        return await self.get_by_telegram_id(id)

    async def update_name(self, telegram_id: int, name: str) -> Optional[User]:
        return await self.update(telegram_id, name=name)

    async def delete(self, id: int) -> bool:
        user = await self.get_by_telegram_id(id)
        if not user:
            return False
        await self._session.delete(user)
        return True
