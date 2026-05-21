import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.admin import router as admin_router
from bot.handlers.common.help import router as help_router
from bot.handlers.common.profile import router as profile_router
from bot.handlers.common.start import router as start_router
from bot.middlewares.auth import AuthMiddleware
from core.config import settings
from db.base import engine
from db.base import Base

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def start_bot() -> None:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(AuthMiddleware())

    dp.include_router(start_router)
    dp.include_router(help_router)
    dp.include_router(profile_router)
    dp.include_router(admin_router)

    logger.info("Starting bot...")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


async def main() -> None:
    await create_tables()
    await start_bot()


if __name__ == "__main__":
    asyncio.run(main())
