from abc import abstractmethod
from typing import Optional

from db.models.user import User
from db.repositories.base import AbstractRepository


class AbstractUserRepository(AbstractRepository[User]):
    @abstractmethod
    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]: ...

    @abstractmethod
    async def create(self, telegram_id: int, name: str, username: Optional[str]) -> User: ...

    @abstractmethod
    async def update_name(self, telegram_id: int, name: str) -> Optional[User]: ...
