from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from db.models.user import User
from db.models.teacher_whitelist import TeacherWhitelist


def build_main_menu(
    user: User,
    is_whitelisted: bool,
    has_teacher_courses: bool,
    has_student_courses: bool,
) -> ReplyKeyboardMarkup:
    buttons: list[list[KeyboardButton]] = []

    if is_whitelisted:
        buttons.append([KeyboardButton(text="➕ Создать курс")])
        buttons.append([KeyboardButton(text="🎓 Открыть панель")])

    if has_teacher_courses:
        buttons.append([KeyboardButton(text="🎓 Мои курсы (преподаватель)")])

    if has_student_courses:
        buttons.append([KeyboardButton(text="📚 Мои курсы (студент)")])

    buttons.append([KeyboardButton(text="🔑 Вступить в курс по коду")])
    buttons.append([KeyboardButton(text="👤 Мой профиль")])

    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
