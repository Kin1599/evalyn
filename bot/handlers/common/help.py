from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from core.config import settings
from db.models.user import User

router = Router()

_ADMIN_HELP = r"""
*Команды администратора:*
/admin\_add\_teacher @username \[заметка\] — добавить преподавателя по username
/admin\_add\_teacher 123456789 \[заметка\] — добавить по Telegram ID
/admin\_remove\_teacher @username — убрать из whitelist
/admin\_list\_teachers — список всех преподавателей

*Курсы и задания \(преподаватель\):*
/new\_course — создать новый курс
/my\_courses — список ваших курсов → задания → создать задание

*Курсы \(студент\):*
/join\_course — вступить в курс по коду
/student\_courses — список курсов, где вы учитесь

*Обычные команды:*
/start — главное меню
/help — эта справка
/profile — изменить отображаемое имя
"""

_TEACHER_HELP = r"""
*Курсы и задания:*
/new\_course — создать новый курс
/my\_courses — список ваших курсов → задания → создать задание
/join\_course — вступить в чужой курс как студент
/student\_courses — список курсов, где вы учитесь

*Обычные команды:*
/start — главное меню
/help — эта справка
/profile — изменить отображаемое имя

_Расширенный интерфейс \(агенты, аналитика\) — кнопка «Открыть панель»_
"""

_STUDENT_HELP = r"""
*Курсы:*
/join\_course — вступить в курс по invite\-коду
/student\_courses — мои курсы и задания

*Обычные команды:*
/start — главное меню
/help — эта справка
/profile — изменить отображаемое имя
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
