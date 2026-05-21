from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from core.config import settings
from db.models.user import User

router = Router()

_ADMIN_HELP = """
*Команды администратора:*
/admin\_add\_teacher @username \[заметка\] — добавить преподавателя по username
/admin\_add\_teacher 123456789 \[заметка\] — добавить по Telegram ID
/admin\_remove\_teacher @username — убрать из whitelist
/admin\_list\_teachers — список всех преподавателей

*Как преподаватель, вы также можете:*
• Создавать курсы и задания
• Настраивать AI\-агентов для проверки
• Запускать анализ работ и просматривать результаты
• Отправлять фидбек студентам
• Смотреть аналитику по студентам

*Как студент, вы можете:*
• Вступить в курс по invite\-коду
• Сдавать работы и получать фидбек

*Обычные команды:*
/start — главное меню
/help — эта справка
/profile — изменить отображаемое имя
"""

_TEACHER_HELP = """
*Доступные команды:*
/start — главное меню
/help — эта справка
/profile — изменить отображаемое имя

*Что вы можете делать:*
• Создавать курсы и управлять ими
• Создавать задания
• Настраивать AI\-агентов для проверки
• Запускать анализ работ и просматривать результаты
• Отправлять фидбек студентам

*Кнопка «Открыть панель»* — расширенный интерфейс для работы с агентами и аналитикой\.
"""

_STUDENT_HELP = """
*Доступные команды:*
/start — главное меню
/help — эта справка
/profile — изменить отображаемое имя

*Что вы можете делать:*
• Вступить в курс по invite\-коду
• Просматривать задания
• Сдавать работы \(текст, файлы, код\)
• Получать фидбек от преподавателя
"""


@router.message(Command("help"))
async def cmd_help(message: Message, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await message.answer(
            "Вы ещё не зарегистрированы. Нажмите /start, чтобы начать."
        )
        return

    if message.from_user.id in settings.admin_ids:
        await message.answer(_ADMIN_HELP, parse_mode="MarkdownV2")
        return

    async with uow_factory() as uow:
        is_whitelisted = await uow.whitelist.is_whitelisted(
            db_user.telegram_id, db_user.username
        )

    text = _TEACHER_HELP if is_whitelisted else _STUDENT_HELP
    await message.answer(text, parse_mode="MarkdownV2")
