from abc import ABC, abstractmethod
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


class AbstractRepository(ABC, Generic[T]):
    @abstractmethod
    async def get_by_id(self, id: int) -> Optional[T]: ...

    @abstractmethod
    async def create(self, **kwargs) -> T: ...

    @abstractmethod
    async def update(self, id: int, **kwargs) -> Optional[T]: ...

    @abstractmethod
    async def delete(self, id: int) -> bool: ...
