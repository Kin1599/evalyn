from aiogram import F, Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)

from bot.keyboards.main_menu import build_main_menu
from bot.states.registration import ProfileStates
from core.config import settings
from db.models.user import User

router = Router()


class ProfileCD(CallbackData, prefix="profile"):
    action: str


def _profile_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✏️ Изменить имя", callback_data=ProfileCD(action="rename").pack()),
    ]])


async def _build_profile_text(db_user: User, uow_factory) -> str:
    async with uow_factory() as uow:
        is_admin = db_user.telegram_id in settings.admin_ids
        is_whitelisted = is_admin or await uow.whitelist.is_whitelisted(
            db_user.telegram_id, db_user.username
        )
        teacher_courses = await uow.courses.get_courses_by_role(db_user.telegram_id, "owner") if is_whitelisted else []
        student_courses = await uow.courses.get_courses_by_role(db_user.telegram_id, "student")

    username_part = f" (@{db_user.username})" if db_user.username else ""
    role_label = "Администратор" if db_user.telegram_id in settings.admin_ids else ("Преподаватель" if is_whitelisted else "Студент")

    lines = [
        f"👤 <b>{db_user.name}</b>{username_part}",
        f"🏷 Роль: {role_label}",
    ]

    if is_whitelisted:
        lines.append("")
        if teacher_courses:
            lines.append("🎓 <b>Мои курсы (преподаватель):</b>")
            for c in teacher_courses:
                lines.append(f"  • {c.name}")
        else:
            lines.append("🎓 Курсов как преподаватель: нет")

    if student_courses:
        lines.append("")
        lines.append("📚 <b>Мои курсы (студент):</b>")
        for c in student_courses:
            lines.append(f"  • {c.name}")
    elif not is_whitelisted:
        lines.append("")
        lines.append("📚 Курсов как студент: нет")

    return "\n".join(lines)


@router.message(Command("profile"))
async def cmd_profile(message: Message, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await message.answer("Сначала зарегистрируйтесь через /start.")
        return

    text = await _build_profile_text(db_user, uow_factory)
    await message.answer(text, reply_markup=_profile_kb())


@router.callback_query(ProfileCD.filter(F.action == "rename"))
async def cb_profile_rename(query: CallbackQuery, state: FSMContext, db_user: User | None) -> None:
    if not db_user:
        await query.answer()
        return

    await state.set_state(ProfileStates.waiting_for_new_name)
    await query.message.answer(
        f"Текущее имя: <b>{db_user.name}</b>\n\nВведите новое имя:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await query.answer()


@router.message(ProfileStates.waiting_for_new_name)
async def process_new_name(
    message: Message,
    state: FSMContext,
    db_user: User | None,
    uow_factory,
) -> None:
    if not db_user:
        await state.clear()
        return

    name = message.text.strip() if message.text else ""
    if not name or len(name) > 128:
        await message.answer("Имя не может быть пустым или длиннее 128 символов. Попробуйте ещё раз:")
        return

    async with uow_factory() as uow:
        updated = await uow.users.update_name(db_user.telegram_id, name)
        await uow.commit()
        is_whitelisted = db_user.telegram_id in settings.admin_ids or await uow.whitelist.is_whitelisted(
            db_user.telegram_id, db_user.username
        )
        teacher_courses = await uow.courses.get_courses_by_role(db_user.telegram_id, "owner")
        student_courses = await uow.courses.get_courses_by_role(db_user.telegram_id, "student")

    await state.clear()
    await message.answer(
        f"✅ Имя изменено на <b>{name}</b>.",
        reply_markup=build_main_menu(
            user=updated,
            is_whitelisted=is_whitelisted,
            has_teacher_courses=len(teacher_courses) > 0,
            has_student_courses=len(student_courses) > 0,
        ),
    )
