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

from bot.states.course import JoinCourseStates
from db.models.user import User

router = Router()


class StudentCourseCD(CallbackData, prefix="student_course"):
    action: str
    course_id: int


@router.message(F.text == "🔑 Вступить в курс по коду")
@router.message(Command("join_course"))
async def btn_join_course(message: Message, state: FSMContext, db_user: User | None) -> None:
    if not db_user:
        await message.answer("Сначала зарегистрируйтесь через /start.")
        return
    await state.set_state(JoinCourseStates.waiting_for_code)
    await message.answer("Введите код курса:", reply_markup=ReplyKeyboardRemove())


@router.message(JoinCourseStates.waiting_for_code)
async def process_join_code(message: Message, state: FSMContext, db_user: User, uow_factory) -> None:
    code = message.text.strip() if message.text else ""
    if not code:
        await message.answer("Код не может быть пустым. Введите код курса:")
        return

    async with uow_factory() as uow:
        course = await uow.courses.get_by_invite_code(code)
        if not course:
            await message.answer("Курс с таким кодом не найден. Проверьте код и попробуйте ещё раз:")
            return

        existing_role = await uow.courses.get_role(db_user.telegram_id, course.id)
        if existing_role:
            await state.clear()
            role_label = "преподаватель" if existing_role.role == "owner" else "студент"
            await message.answer(
                f"Вы уже состоите в курсе <b>{course.name}</b> ({role_label}).",
                reply_markup=_restore_menu(db_user),
            )
            return

        await uow.courses.add_member(db_user.telegram_id, course.id, "student")
        await uow.commit()

    await state.clear()
    from bot.keyboards.main_menu import build_main_menu
    from core.config import settings
    from db.unit_of_work import UnitOfWork
    from db.base import async_session_factory
    async with UnitOfWork(async_session_factory) as uow:
        is_whitelisted = db_user.telegram_id in settings.admin_ids or await uow.whitelist.is_whitelisted(db_user.telegram_id, db_user.username)
        teacher_courses = await uow.courses.get_courses_by_role(db_user.telegram_id, "owner")
        student_courses = await uow.courses.get_courses_by_role(db_user.telegram_id, "student")

    await message.answer(
        f"✅ Вы вступили в курс <b>{course.name}</b>!",
        reply_markup=build_main_menu(
            user=db_user,
            is_whitelisted=is_whitelisted,
            has_teacher_courses=len(teacher_courses) > 0,
            has_student_courses=len(student_courses) > 0,
        ),
    )


def _restore_menu(db_user):
    from bot.keyboards.main_menu import build_main_menu
    return build_main_menu(
        user=db_user,
        is_whitelisted=False,
        has_teacher_courses=False,
        has_student_courses=False,
    )


@router.message(F.text == "📚 Мои курсы (студент)")
@router.message(Command("student_courses"))
async def btn_student_courses(message: Message, db_user: User | None, uow_factory) -> None:
    if not db_user:
        return

    async with uow_factory() as uow:
        courses = await uow.courses.get_courses_by_role(db_user.telegram_id, "student")

    if not courses:
        await message.answer("Вы ещё не вступили ни в один курс. Нажмите «🔑 Вступить в курс по коду».")
        return

    buttons = [
        [InlineKeyboardButton(
            text=f"📚 {c.name}",
            callback_data=StudentCourseCD(action="view", course_id=c.id).pack(),
        )]
        for c in courses
    ]
    await message.answer(
        f"Курсы, в которых вы учитесь ({len(courses)}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


async def _render_course_assignments(query: CallbackQuery, course_id: int, db_user: User, uow_factory) -> None:
    from bot.handlers.student.assignments import StudentAssignmentCD

    async with uow_factory() as uow:
        course = await uow.courses.get_by_id(course_id)
        role = await uow.courses.get_role(db_user.telegram_id, course_id)
        assignments = [
            a for a in await uow.assignments.get_by_course(course_id)
            if not getattr(a, "is_private", False)
        ]
        submissions = {
            s.assignment_id: s
            for s in await uow.submissions.get_by_assignment_list(
                [a.id for a in assignments]
            )
            if s.student_id == db_user.telegram_id
        } if assignments else {}

    if not course or not role or role.role != "student":
        await query.answer("Нет доступа.", show_alert=True)
        return

    if not assignments:
        await query.message.edit_text(f"📚 <b>{course.name}</b>\n\nЗаданий пока нет.")
        return

    _STATUS_ICON = {"pending": "⏳", "reviewed": "✅"}
    buttons = []
    for a in assignments:
        sub = submissions.get(a.id)
        icon = _STATUS_ICON.get(sub.status, "⏳") if sub else "📄"
        deadline = f" · {a.deadline.strftime('%d.%m')}" if a.deadline else ""
        buttons.append([InlineKeyboardButton(
            text=f"{icon} {a.title}{deadline}",
            callback_data=StudentAssignmentCD(action="view", assignment_id=a.id, course_id=course_id).pack(),
        )])

    await query.message.edit_text(
        f"📚 <b>{course.name}</b>\nЗаданий: {len(assignments)}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(StudentCourseCD.filter(F.action == "view"))
async def cb_student_course_view(query: CallbackQuery, callback_data: StudentCourseCD, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return
    await _render_course_assignments(query, callback_data.course_id, db_user, uow_factory)
    await query.answer()
