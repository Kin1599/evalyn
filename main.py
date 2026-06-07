import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from uvicorn import Config, Server

from bot.handlers.admin import router as admin_router
from bot.handlers.common.help import router as help_router
from bot.handlers.common.profile import router as profile_router
from bot.handlers.common.start import router as start_router
from bot.handlers.teacher.courses import router as teacher_courses_router
from bot.handlers.teacher.assignments import router as teacher_assignments_router
from bot.handlers.student.courses import router as student_courses_router
from bot.handlers.student.assignments import router as student_assignments_router
from bot.middlewares.auth import AuthMiddleware
from core.config import settings
from db.base import engine, Base
from db.base import async_session_factory
from db.unit_of_work import UnitOfWork
from api.app import app as fastapi_app
from services.review_scheduler import review_scheduler_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def create_tables() -> None:
    """Create database tables if they don't exist"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created/verified")


async def start_bot() -> None:
    """Start Telegram bot polling"""
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
    dp.include_router(teacher_courses_router)
    dp.include_router(teacher_assignments_router)
    dp.include_router(student_courses_router)
    dp.include_router(student_assignments_router)

    logger.info("🤖 Starting Telegram bot polling...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as exc:
        logger.error(f"Bot error: {exc}", exc_info=True)


async def start_api() -> None:
    """Start FastAPI server"""
    config = Config(
        app=fastapi_app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
    server = Server(config)
    logger.info("🚀 Starting FastAPI server on http://0.0.0.0:8000")
    try:
        await server.serve()
    except Exception as exc:
        logger.error(f"API error: {exc}", exc_info=True)


async def main() -> None:
    """Main entry point - create tables and start both bot and API"""
    logger.info("Initializing Evalyn...")
    
    # Create database tables
    await create_tables()
    
    logger.info("Starting bot, API, and review scheduler services...")
    stop_event = asyncio.Event()

    async def scheduler_runner() -> None:
        await review_scheduler_loop(lambda: UnitOfWork(async_session_factory), stop_event)

    try:
        await asyncio.gather(
            start_bot(),
            start_api(),
            scheduler_runner(),
            return_exceptions=True,
        )
    finally:
        stop_event.set()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested")
        sys.exit(0)
    except Exception as exc:
        logger.error(f"Fatal error: {exc}", exc_info=True)
        sys.exit(1)
