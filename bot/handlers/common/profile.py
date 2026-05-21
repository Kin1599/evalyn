from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from bot.keyboards.main_menu import build_main_menu
from bot.states.registration import ProfileStates
from db.models.user import User

router = Router()


@router.message(Command("profile"))
async def cmd_profile(message: Message, db_user: User | None, state: FSMContext) -> None:
    if not db_user:
        await message.answer("Сначала зарегистрируйтесь через /start.")
        return

    await state.set_state(ProfileStates.waiting_for_new_name)
    await message.answer(
        f"Ваше текущее имя: *{db_user.name}*\n\nВведите новое имя:",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )


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
        is_whitelisted = await uow.whitelist.is_whitelisted(
            db_user.telegram_id, db_user.username
        )

    await state.clear()
    await message.answer(
        f"Имя изменено на *{name}*.",
        parse_mode="Markdown",
        reply_markup=build_main_menu(
            user=updated,
            is_whitelisted=is_whitelisted,
            has_teacher_courses=False,
            has_student_courses=False,
        ),
    )
