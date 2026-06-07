from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)

from bot.states.course import CourseCreateStates
from core.config import settings
from db.models.user import User

router = Router()


class CourseCD(CallbackData, prefix="course"):
    action: str
    course_id: int


def _course_menu_kb(course_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Задания", callback_data=CourseCD(action="assignments", course_id=course_id).pack()),
            InlineKeyboardButton(text="👥 Студенты", callback_data=CourseCD(action="students", course_id=course_id).pack()),
        ],
        [
            InlineKeyboardButton(text="🔑 Код приглашения", callback_data=CourseCD(action="code", course_id=course_id).pack()),
        ],
    ])


async def _check_is_teacher(message: Message, db_user: User | None, uow_factory) -> bool:
    if not db_user:
        await message.answer("Сначала зарегистрируйтесь через /start.")
        return False
    if message.from_user.id in settings.admin_ids:
        return True
    async with uow_factory() as uow:
        ok = await uow.whitelist.is_whitelisted(db_user.telegram_id, db_user.username)
    if not ok:
        await message.answer("Создавать курсы могут только преподаватели из whitelist.")
    return ok


@router.message(StateFilter("*"), F.text == "➕ Создать курс")
@router.message(Command("new_course"))
async def btn_create_course(message: Message, state: FSMContext, db_user: User | None, uow_factory) -> None:
    if not await _check_is_teacher(message, db_user, uow_factory):
        return
    await state.set_state(CourseCreateStates.waiting_for_name)
    await message.answer("Введите название курса:", reply_markup=ReplyKeyboardRemove())


@router.message(CourseCreateStates.waiting_for_name)
async def process_course_name(message: Message, state: FSMContext, db_user: User, uow_factory) -> None:
    name = message.text.strip() if message.text else ""
    if not name or len(name) > 256:
        await message.answer("Название не может быть пустым или длиннее 256 символов. Попробуйте ещё раз:")
        return

    async with uow_factory() as uow:
        course = await uow.courses.create(creator_id=db_user.telegram_id, name=name)
        await uow.courses.add_member(db_user.telegram_id, course.id, "owner")
        await uow.commit()

    await state.clear()
    from bot.keyboards.main_menu import build_main_menu
    from db.unit_of_work import UnitOfWork
    from db.base import async_session_factory
    async with UnitOfWork(async_session_factory) as uow:
        is_whitelisted = message.from_user.id in settings.admin_ids or await uow.whitelist.is_whitelisted(db_user.telegram_id, db_user.username)
        teacher_courses = await uow.courses.get_courses_by_role(db_user.telegram_id, "owner")
        student_courses = await uow.courses.get_courses_by_role(db_user.telegram_id, "student")

    await message.answer(
        f"✅ Курс создан!\n\n"
        f"📚 <b>{course.name}</b>\n"
        f"🔑 Код для вступления: <code>{course.invite_code}</code>\n\n"
        f"Поделитесь кодом со студентами.",
        reply_markup=build_main_menu(
            user=db_user,
            is_whitelisted=is_whitelisted,
            has_teacher_courses=len(teacher_courses) > 0,
            has_student_courses=len(student_courses) > 0,
        ),
    )


@router.message(StateFilter("*"), F.text == "🎓 Мои курсы (преподаватель)")
@router.message(Command("my_courses"))
async def btn_teacher_courses(message: Message, db_user: User | None, uow_factory) -> None:
    if not db_user:
        return

    async with uow_factory() as uow:
        courses = await uow.courses.get_courses_by_role(db_user.telegram_id, "owner")

    if not courses:
        await message.answer("У вас пока нет курсов. Создайте первый курс кнопкой «➕ Создать курс».")
        return

    buttons = [
        [InlineKeyboardButton(text=f"📚 {c.name}", callback_data=CourseCD(action="view", course_id=c.id).pack())]
        for c in courses
    ]
    await message.answer(
        f"Ваши курсы ({len(courses)}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(CourseCD.filter(F.action == "view"))
async def cb_course_view(query: CallbackQuery, callback_data: CourseCD, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        course = await uow.courses.get_by_id(callback_data.course_id)
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)

    if not course or not role or role.role != "owner":
        await query.answer("Нет доступа.", show_alert=True)
        return

    await query.message.edit_text(
        f"📚 <b>{course.name}</b>\n🔑 Код: <code>{course.invite_code}</code>",
        reply_markup=_course_menu_kb(course.id),
    )
    await query.answer()


@router.callback_query(CourseCD.filter(F.action == "students"))
async def cb_course_students(query: CallbackQuery, callback_data: CourseCD, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        course = await uow.courses.get_by_id(callback_data.course_id)
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)
        students = await uow.courses.get_members(callback_data.course_id, "student")

    if not course or not role or role.role != "owner":
        await query.answer("Нет доступа.", show_alert=True)
        return

    back_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="← Назад", callback_data=CourseCD(action="view", course_id=course.id).pack()),
    ]])

    if not students:
        await query.message.edit_text(
            f"📚 <b>{course.name}</b>\n\n👥 Студентов пока нет.",
            reply_markup=back_kb,
        )
        await query.answer()
        return

    lines = []
    for i, u in enumerate(students, 1):
        username_part = f" (@{u.username})" if u.username else ""
        lines.append(f"{i}. {u.name}{username_part}")

    await query.message.edit_text(
        f"📚 <b>{course.name}</b>\n👥 Студенты ({len(students)}):\n\n" + "\n".join(lines),
        reply_markup=back_kb,
    )
    await query.answer()


@router.callback_query(CourseCD.filter(F.action == "code"))
async def cb_course_code(query: CallbackQuery, callback_data: CourseCD, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        course = await uow.courses.get_by_id(callback_data.course_id)
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)

    if not course or not role or role.role != "owner":
        await query.answer("Нет доступа.", show_alert=True)
        return

    await query.answer(f"Код курса: {course.invite_code}", show_alert=True)
