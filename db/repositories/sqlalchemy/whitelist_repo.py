from typing import Optional

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.teacher_whitelist import TeacherWhitelist
from db.repositories.whitelist_repo import AbstractWhitelistRepository


class SQLAlchemyWhitelistRepository(AbstractWhitelistRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, id: int) -> Optional[TeacherWhitelist]:
        result = await self._session.execute(
            select(TeacherWhitelist).where(TeacherWhitelist.id == id)
        )
        return result.scalar_one_or_none()

    async def is_whitelisted(self, telegram_id: int, username: Optional[str]) -> bool:
        conditions = [TeacherWhitelist.telegram_id == telegram_id]
        if username:
            conditions.append(TeacherWhitelist.username == username.lstrip("@"))
        result = await self._session.execute(
            select(TeacherWhitelist).where(or_(*conditions))
        )
        return result.scalar_one_or_none() is not None

    async def add(
        self,
        added_by: int,
        telegram_id: Optional[int] = None,
        username: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> TeacherWhitelist:
        if username:
            username = username.lstrip("@")
        entry = TeacherWhitelist(
            telegram_id=telegram_id,
            username=username,
            added_by=added_by,
            notes=notes,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def remove(self, telegram_id: int) -> bool:
        result = await self._session.execute(
            delete(TeacherWhitelist).where(
                TeacherWhitelist.telegram_id == telegram_id
            )
        )
        return result.rowcount > 0

    async def get_all(self) -> list[TeacherWhitelist]:
        result = await self._session.execute(select(TeacherWhitelist))
        return list(result.scalars().all())

    async def create(self, **kwargs) -> TeacherWhitelist:
        return await self.add(**kwargs)

    async def update(self, id: int, **kwargs) -> Optional[TeacherWhitelist]:
        entry = await self.get_by_id(id)
        if not entry:
            return None
        for key, value in kwargs.items():
            setattr(entry, key, value)
        await self._session.flush()
        return entry

    async def delete(self, id: int) -> bool:
        entry = await self.get_by_id(id)
        if not entry:
            return False
        await self._session.delete(entry)
        return True
