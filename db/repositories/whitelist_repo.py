from abc import abstractmethod
from typing import Optional

from db.models.teacher_whitelist import TeacherWhitelist
from db.repositories.base import AbstractRepository


class AbstractWhitelistRepository(AbstractRepository[TeacherWhitelist]):
    @abstractmethod
    async def is_whitelisted(self, telegram_id: int, username: Optional[str]) -> bool: ...

    @abstractmethod
    async def add(
        self,
        added_by: int,
        telegram_id: Optional[int] = None,
        username: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> TeacherWhitelist: ...

    @abstractmethod
    async def remove(self, telegram_id: int) -> bool: ...

    @abstractmethod
    async def get_all(self) -> list[TeacherWhitelist]: ...
