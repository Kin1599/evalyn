from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from bot.keyboards.main_menu import build_main_menu
from bot.states.registration import RegistrationStates
from core.config import settings
from db.models.user import User
from db.unit_of_work import UnitOfWork

router = Router()


async def _build_menu_for_user(user: User, uow: UnitOfWork) -> dict:
    if user.telegram_id in settings.admin_ids:
        is_whitelisted = True
    else:
        is_whitelisted = await uow.whitelist.is_whitelisted(
            user.telegram_id, user.username
        )
    teacher_courses = await uow.courses.get_courses_by_role(user.telegram_id, "owner")
    student_courses = await uow.courses.get_courses_by_role(user.telegram_id, "student")
    return dict(
        user=user,
        is_whitelisted=is_whitelisted,
        has_teacher_courses=len(teacher_courses) > 0,
        has_student_courses=len(student_courses) > 0,
    )


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    db_user: User | None,
    uow_factory,
) -> None:
    if db_user:
        async with uow_factory() as uow:
            menu_kwargs = await _build_menu_for_user(db_user, uow)

        await message.answer(
            f"С возвращением, {db_user.name}!",
            reply_markup=build_main_menu(**menu_kwargs),
        )
        return

    # New user — ask for display name
    tg_name = message.from_user.full_name or ""
    hint = f" (например: «{tg_name}»)" if tg_name else ""

    await state.set_state(RegistrationStates.waiting_for_name)
    await message.answer(
        f"Привет! Введите ваше имя{hint} — именно оно будет видно "
        "преподавателям и студентам:",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(RegistrationStates.waiting_for_name)
async def process_registration_name(
    message: Message,
    state: FSMContext,
    uow_factory,
) -> None:
    name = message.text.strip() if message.text else ""
    if not name or len(name) > 128:
        await message.answer("Имя не может быть пустым или длиннее 128 символов. Попробуйте ещё раз:")
        return

    async with uow_factory() as uow:
        user = await uow.users.create(
            telegram_id=message.from_user.id,
            name=name,
            username=message.from_user.username,
        )
        await uow.commit()
        is_whitelisted = await uow.whitelist.is_whitelisted(
            user.telegram_id, user.username
        )

    await state.clear()
    await message.answer(
        f"Отлично, {name}! Вы зарегистрированы.",
        reply_markup=build_main_menu(
            user=user,
            is_whitelisted=is_whitelisted,
            has_teacher_courses=False,
            has_student_courses=False,
        ),
    )
