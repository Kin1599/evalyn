from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser

from db.base import async_session_factory
from db.repositories.sqlalchemy.user_repo import SQLAlchemyUserRepository
from db.unit_of_work import UnitOfWork


class AuthMiddleware(BaseMiddleware):
    """Attaches db_user and uow_factory to handler data if user is registered."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        if tg_user:
            async with UnitOfWork(async_session_factory) as uow:
                db_user = await uow.users.get_by_telegram_id(tg_user.id)
                data["db_user"] = db_user
                data["uow_factory"] = lambda: UnitOfWork(async_session_factory)

        return await handler(event, data)
