from datetime import datetime

from aiogram import F, Router
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from bot.handlers.teacher.courses import CourseCD
from bot.states.assignment import AssignmentCreateStates
from db.models.user import User

router = Router()

_SKIP_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Пропустить")]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


class AssignmentCD(CallbackData, prefix="assignment"):
    action: str
    assignment_id: int
    course_id: int


def _assignments_kb(assignments, course_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=f"📄 {a.title}",
            callback_data=AssignmentCD(action="view", assignment_id=a.id, course_id=course_id).pack(),
        )]
        for a in assignments
    ]
    buttons.append([
        InlineKeyboardButton(
            text="➕ Создать задание",
            callback_data=AssignmentCD(action="create", assignment_id=0, course_id=course_id).pack(),
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(CourseCD.filter(F.action == "assignments"))
async def cb_course_assignments(query: CallbackQuery, callback_data: CourseCD, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    course_id = callback_data.course_id
    async with uow_factory() as uow:
        course = await uow.courses.get_by_id(course_id)
        role = await uow.courses.get_role(db_user.telegram_id, course_id)
        assignments = await uow.assignments.get_by_course(course_id)

    if not course or not role or role.role != "owner":
        await query.answer("Нет доступа.", show_alert=True)
        return

    count = len(assignments)
    text = f"📚 <b>{course.name}</b>\nЗаданий: {count}" if count else f"📚 <b>{course.name}</b>\nЗаданий ещё нет."
    await query.message.edit_text(text, reply_markup=_assignments_kb(assignments, course_id))
    await query.answer()


@router.callback_query(AssignmentCD.filter(F.action == "view"))
async def cb_assignment_view(query: CallbackQuery, callback_data: AssignmentCD, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        assignment = await uow.assignments.get_by_id(callback_data.assignment_id)
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)

    if not assignment or not role or role.role != "owner":
        await query.answer("Нет доступа.", show_alert=True)
        return

    deadline_str = assignment.deadline.strftime("%d.%m.%Y") if assignment.deadline else "не указан"
    criteria_str = f"\n\n<b>Критерии:</b>\n{assignment.criteria}" if assignment.criteria else ""

    text = (
        f"📄 <b>{assignment.title}</b>\n"
        f"🗓 Дедлайн: {deadline_str}\n\n"
        f"{assignment.description}"
        f"{criteria_str}"
    )
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="← Назад к заданиям",
            callback_data=CourseCD(action="assignments", course_id=callback_data.course_id).pack(),
        )
    ]])
    await query.message.edit_text(text, reply_markup=back_kb)
    await query.answer()


@router.callback_query(AssignmentCD.filter(F.action == "create"))
async def cb_assignment_create(query: CallbackQuery, callback_data: AssignmentCD, state: FSMContext, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)

    if not role or role.role != "owner":
        await query.answer("Нет доступа.", show_alert=True)
        return

    await state.set_state(AssignmentCreateStates.waiting_for_title)
    await state.update_data(course_id=callback_data.course_id)
    await query.message.answer("Введите название задания:", reply_markup=ReplyKeyboardRemove())
    await query.answer()


@router.message(AssignmentCreateStates.waiting_for_title)
async def process_assignment_title(message: Message, state: FSMContext) -> None:
    title = message.text.strip() if message.text else ""
    if not title or len(title) > 256:
        await message.answer("Название не может быть пустым или длиннее 256 символов. Попробуйте ещё раз:")
        return
    await state.update_data(title=title)
    await state.set_state(AssignmentCreateStates.waiting_for_description)
    await message.answer("Введите описание / условие задания:")


@router.message(AssignmentCreateStates.waiting_for_description)
async def process_assignment_description(message: Message, state: FSMContext) -> None:
    description = message.text.strip() if message.text else ""
    if not description:
        await message.answer("Описание не может быть пустым. Попробуйте ещё раз:")
        return
    await state.update_data(description=description)
    await state.set_state(AssignmentCreateStates.waiting_for_criteria)
    await message.answer(
        "Введите критерии оценки или нажмите «Пропустить»:",
        reply_markup=_SKIP_KB,
    )


@router.message(AssignmentCreateStates.waiting_for_criteria)
async def process_assignment_criteria(message: Message, state: FSMContext) -> None:
    text = message.text.strip() if message.text else ""
    criteria = None if text == "Пропустить" else (text or None)
    await state.update_data(criteria=criteria)
    await state.set_state(AssignmentCreateStates.waiting_for_deadline)
    await message.answer(
        "Введите дедлайн в формате ДД.ММ.ГГГГ или нажмите «Пропустить»:",
        reply_markup=_SKIP_KB,
    )


@router.message(AssignmentCreateStates.waiting_for_deadline)
async def process_assignment_deadline(message: Message, state: FSMContext, db_user: User, uow_factory) -> None:
    text = message.text.strip() if message.text else ""
    deadline = None
    if text and text != "Пропустить":
        try:
            deadline = datetime.strptime(text, "%d.%m.%Y")
        except ValueError:
            await message.answer("Неверный формат даты. Введите ДД.ММ.ГГГГ или нажмите «Пропустить»:")
            return

    data = await state.get_data()
    await state.clear()

    async with uow_factory() as uow:
        assignment = await uow.assignments.create(
            course_id=data["course_id"],
            title=data["title"],
            description=data["description"],
            criteria=data.get("criteria"),
            deadline=deadline,
        )
        await uow.commit()

    deadline_str = deadline.strftime("%d.%m.%Y") if deadline else "не указан"
    await message.answer(
        f"✅ Задание создано!\n\n"
        f"📄 <b>{assignment.title}</b>\n"
        f"🗓 Дедлайн: {deadline_str}",
        reply_markup=ReplyKeyboardRemove(),
    )
