import html
import io
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.enums.parse_mode import ParseMode
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

from agents.output_schema import AgentOutput
from agents.reviewer import CodeReviewAgent
from core.config import settings
from bot.handlers.teacher.courses import CourseCD
from bot.states.assignment import AssignmentCreateStates
from bot.states.review import ReviewEditStates
from bot.states.submission import SubmissionStates
from db.models.submission import Submission
from db.models.user import User

router = Router()

_SKIP_KB = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="Пропустить")]],
    resize_keyboard=True,
    one_time_keyboard=True,
)


async def _resolve_submission_text(query: CallbackQuery, submission: Submission) -> str:
    if submission.content_text:
        return submission.content_text

    if not submission.file_id:
        return ""

    file = await query.bot.get_file(submission.file_id)
    buffer = io.BytesIO()
    await query.bot.download_file(file.file_path, destination=buffer)
    buffer.seek(0)
    try:
        text = buffer.read().decode("utf-8")
        if text.strip():
            return text
    except UnicodeDecodeError:
        pass

    file_name = file.file_path.split("/")[-1] if file.file_path else submission.file_id
    return (
        f"Прикреплён файл {file_name}. "
        "Текстовый контент не удалось прочитать, но ревью запущено для анализа по доступным данным."
    )


class AssignmentCD(CallbackData, prefix="assignment"):
    action: str
    assignment_id: int
    course_id: int


async def _run_review_for_submission(
    query: CallbackQuery,
    uow,
    assignment: object,
    submission: Submission,
    model: str,
) -> tuple[bool, str]:
    submission_text = submission.content_text or ""
    if not submission_text and submission.file_id:
        submission_text = await _resolve_submission_text(query, submission)

    if not submission_text:
        return False, f"submission {submission.id}: нет текста и файла"

    agent = CodeReviewAgent(model=model)
    result, raw_output = await agent.review_submission(
        assignment_title=assignment.title,
        assignment_description=assignment.description,
        assignment_criteria=assignment.criteria,
        submission_text=submission_text,
    )

    review = await uow.reviews.create(
        submission_id=submission.id,
        model=model,
        raw_output=raw_output,
        status="pending_moderation" if isinstance(result, AgentOutput) else "failed",
        overall_score=result.overall_score if isinstance(result, AgentOutput) else None,
        summary=result.summary if isinstance(result, AgentOutput) else str(result),
    )
    if isinstance(result, AgentOutput):
        for item in result.items:
            await uow.reviews.create_item(
                review_id=review.id,
                category=item.category,
                severity=item.severity,
                title=item.title,
                description=item.description,
                location=item.location,
                suggestion=item.suggestion,
            )
        await uow.submissions.update(submission.id, status="reviewed")
    return True, f"submission {submission.id}: {review.status}"


def _assignments_kb(assignments, course_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for a in assignments:
        label = f"📄 {a.title}"
        if getattr(a, "is_private", False):
            label = f"🔒 {a.title}"
        buttons.append([
            InlineKeyboardButton(
                text=label,
                callback_data=AssignmentCD(action="view", assignment_id=a.id, course_id=course_id).pack(),
            )
        ])
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


class SubmissionCD(CallbackData, prefix="submission"):
    action: str
    assignment_id: int
    course_id: int
    submission_id: int
    review_id: int = 0


def _submission_status_label(submission: Submission) -> str:
    if submission.status == "pending":
        return "на проверке"
    if submission.status == "reviewed":
        return "проверено"
    if submission.status == "feedback_sent":
        return "фидбек отправлен"
    return submission.status


def _submission_list_kb(submissions: list[Submission], assignment_id: int, course_id: int) -> InlineKeyboardMarkup:
    buttons = []
    for submission in submissions:
        label = str(submission.student_id)
        if submission.content_text:
            label += " — text"
        elif submission.file_id:
            label += " — file"
        else:
            label += " — empty"
        label += f" — {_submission_status_label(submission)}"
        buttons.append([
            InlineKeyboardButton(
                text=label,
                callback_data=SubmissionCD(
                    action="view",
                    assignment_id=assignment_id,
                    course_id=course_id,
                    submission_id=submission.id,
                ).pack(),
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            text="← Назад к заданию",
            callback_data=AssignmentCD(action="view", assignment_id=assignment_id, course_id=course_id).pack(),
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


class ReviewItemCD(CallbackData, prefix="review_item"):
    action: str
    review_id: int
    item_id: int
    submission_id: int
    assignment_id: int
    course_id: int


class ReviewModelCD(CallbackData, prefix="review_model"):
    action: str
    model: str
    assignment_id: int
    course_id: int
    submission_id: int


def _review_navigation_kb(review_id: int, submission_id: int, assignment_id: int, course_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🔎 Просмотреть результаты",
            callback_data=SubmissionCD(
                action="review_summary",
                assignment_id=assignment_id,
                course_id=course_id,
                submission_id=submission_id,
                review_id=review_id,
            ).pack(),
        )],
        [InlineKeyboardButton(
            text="📨 Отправить финальный фидбек",
            callback_data=SubmissionCD(
                action="send_feedback",
                assignment_id=assignment_id,
                course_id=course_id,
                submission_id=submission_id,
                review_id=review_id,
            ).pack(),
        )],
        [InlineKeyboardButton(
            text="← Назад к работе",
            callback_data=SubmissionCD(
                action="view",
                assignment_id=assignment_id,
                course_id=course_id,
                submission_id=submission_id,
            ).pack(),
        )],
    ])


def _review_summary_kb(review_id: int, submission_id: int, assignment_id: int, course_id: int, items: list) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        label = item.title if len(item.title) <= 32 else item.title[:29] + "..."
        status = item.teacher_decision or "pending"
        buttons.append([
            InlineKeyboardButton(
                text=f"{label} — {status}",
                callback_data=ReviewItemCD(
                    action="view",
                    review_id=review_id,
                    item_id=item.id,
                    submission_id=submission_id,
                    assignment_id=assignment_id,
                    course_id=course_id,
                ).pack(),
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            text="📨 Отправить финальный фидбек",
            callback_data=SubmissionCD(
                action="send_feedback",
                assignment_id=assignment_id,
                course_id=course_id,
                submission_id=submission_id,
                review_id=review_id,
            ).pack(),
        )
    ])
    buttons.append([
        InlineKeyboardButton(
            text="← Назад к работе",
            callback_data=SubmissionCD(
                action="view",
                assignment_id=assignment_id,
                course_id=course_id,
                submission_id=submission_id,
            ).pack(),
        )
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _review_item_kb(review_id: int, item_id: int, submission_id: int, assignment_id: int, course_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Принять",
            callback_data=ReviewItemCD(
                action="accept",
                review_id=review_id,
                item_id=item_id,
                submission_id=submission_id,
                assignment_id=assignment_id,
                course_id=course_id,
            ).pack(),
        )],
        [InlineKeyboardButton(
            text="❌ Отклонить",
            callback_data=ReviewItemCD(
                action="reject",
                review_id=review_id,
                item_id=item_id,
                submission_id=submission_id,
                assignment_id=assignment_id,
                course_id=course_id,
            ).pack(),
        )],
        [InlineKeyboardButton(
            text="✏️ Редактировать",
            callback_data=ReviewItemCD(
                action="edit",
                review_id=review_id,
                item_id=item_id,
                submission_id=submission_id,
                assignment_id=assignment_id,
                course_id=course_id,
            ).pack(),
        )],
        [InlineKeyboardButton(
            text="← Назад к результатам",
            callback_data=SubmissionCD(
                action="review_summary",
                assignment_id=assignment_id,
                course_id=course_id,
                submission_id=submission_id,
                review_id=review_id,
            ).pack(),
        )],
    ])


@router.callback_query(AssignmentCD.filter(F.action == "view"))
async def cb_assignment_view(query: CallbackQuery, callback_data: AssignmentCD, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        assignment = await uow.assignments.get_by_id(callback_data.assignment_id)
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)
        submissions = await uow.submissions.get_by_assignment(callback_data.assignment_id)

    if not assignment or not role or role.role != "owner":
        await query.answer("Нет доступа.", show_alert=True)
        return

    deadline_str = assignment.deadline.strftime("%d.%m.%Y") if assignment.deadline else "не указан"
    criteria_str = f"\n\n<b>Критерии:</b>\n{assignment.criteria}" if assignment.criteria else ""
    submission_count = len(submissions)
    submission_info = (
        f"\n\n<b>Сдано работ:</b> {submission_count}"
        if submission_count
        else "\n\nНет отправленных работ."
    )

    text = (
        f"📄 <b>{assignment.title}</b>\n"
        f"🗓 Дедлайн: {deadline_str}\n\n"
        f"{assignment.description}"
        f"{criteria_str}"
        f"{submission_info}"
    )

    if getattr(assignment, "is_private", False):
        text += "\n\n🔒 <b>Это приватное задание. Студенты не видят его в общем списке.</b>"

    buttons = []
    if submission_count:
        buttons.append([
            InlineKeyboardButton(
                text="📝 Показать работы",
                callback_data=AssignmentCD(action="submissions", assignment_id=callback_data.assignment_id, course_id=callback_data.course_id).pack(),
            )
        ])
        buttons.append([
            InlineKeyboardButton(
                text="🤖 Проверить всё задание",
                callback_data=AssignmentCD(action="review_all", assignment_id=callback_data.assignment_id, course_id=callback_data.course_id).pack(),
            )
        ])
    if getattr(assignment, "is_private", False):
        buttons.append([
            InlineKeyboardButton(
                text="🌐 Сделать публичным",
                callback_data=AssignmentCD(action="make_public", assignment_id=callback_data.assignment_id, course_id=callback_data.course_id).pack(),
            )
        ])
    # allow owner to perform a test submission without being a student
    buttons.append([
        InlineKeyboardButton(
            text="📤 Протестировать сдачу",
            callback_data=AssignmentCD(action="self_submit", assignment_id=callback_data.assignment_id, course_id=callback_data.course_id).pack(),
        )
    ])
    buttons.append([
        InlineKeyboardButton(
            text="← Назад к заданиям",
            callback_data=CourseCD(action="assignments", course_id=callback_data.course_id).pack(),
        )
    ])

    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await query.answer()


@router.callback_query(AssignmentCD.filter(F.action == "self_submit"))
async def cb_assignment_self_submit(query: CallbackQuery, callback_data: AssignmentCD, state: FSMContext, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        assignment = await uow.assignments.get_by_id(callback_data.assignment_id)
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)

    if not assignment or not role or role.role != "owner":
        await query.answer("Нет доступа.", show_alert=True)
        return

    await state.set_state(SubmissionStates.waiting_for_content)
    await state.update_data(
        assignment_id=callback_data.assignment_id,
        course_id=callback_data.course_id,
    )
    await query.message.answer(
        "Отправьте вашу работу — текст, код или файл (документ/фото).\n\n"
        "Чтобы отменить — /cancel",
        reply_markup=ReplyKeyboardRemove(),
    )
    await query.answer()


@router.callback_query(AssignmentCD.filter(F.action == "make_public"))
async def cb_assignment_make_public(query: CallbackQuery, callback_data: AssignmentCD, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        assignment = await uow.assignments.get_by_id(callback_data.assignment_id)
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)

    if not assignment or not role or role.role != "owner":
        await query.answer("Нет доступа.", show_alert=True)
        return

    if not getattr(assignment, "is_private", False):
        await query.answer("Задание уже публичное.", show_alert=True)
        return

    async with uow_factory() as uow:
        await uow.assignments.update(assignment.id, is_private=False)
        await uow.commit()

    await query.answer("Задание сделано публичным.")
    await cb_assignment_view(query, callback_data, db_user, uow_factory)


@router.callback_query(AssignmentCD.filter(F.action == "review_all"))
async def cb_assignment_review_all(query: CallbackQuery, callback_data: AssignmentCD, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        assignment = await uow.assignments.get_by_id(callback_data.assignment_id)
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)
        submissions = await uow.submissions.get_by_assignment(callback_data.assignment_id)

    if not assignment or not role or role.role != "owner":
        await query.answer("Нет доступа.", show_alert=True)
        return

    pending_submissions = [s for s in submissions if s.status == "pending"]
    if not pending_submissions:
        await query.answer("Нет новых отправок для проверки.", show_alert=True)
        return

    await query.answer("Запускаю проверку новых отправок, подождите...")

    messages = []
    async with uow_factory() as uow:
        for submission in pending_submissions:
            success, status_msg = await _run_review_for_submission(query, uow, assignment, submission, settings.default_agent_model)
            messages.append(status_msg)
        await uow.commit()

    text = "Проверка выполнена для следующих отправок:\n" + "\n".join(messages)
    await query.message.answer(text)


@router.callback_query(AssignmentCD.filter(F.action == "submissions"))
async def cb_assignment_submissions(query: CallbackQuery, callback_data: AssignmentCD, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        assignment = await uow.assignments.get_by_id(callback_data.assignment_id)
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)
        submissions = await uow.submissions.get_by_assignment(callback_data.assignment_id)

        users = {}
        for submission in submissions:
            if submission.student_id not in users:
                users[submission.student_id] = await uow.users.get_by_telegram_id(submission.student_id)

    if not assignment or not role or role.role != "owner":
        await query.answer("Нет доступа.", show_alert=True)
        return

    if not submissions:
        await query.answer("Нет отправленных работ.", show_alert=True)
        return

    buttons = []
    for submission in submissions:
        student = users.get(submission.student_id)
        student_name = student.name if student else str(submission.student_id)
        kind = "text" if submission.content_text else "file" if submission.file_id else "empty"
        buttons.append([
            InlineKeyboardButton(
                text=f"{student_name} — {kind}",
                callback_data=SubmissionCD(
                    action="view",
                    assignment_id=callback_data.assignment_id,
                    course_id=callback_data.course_id,
                    submission_id=submission.id,
                ).pack(),
            )
        ])
    buttons.append([
        InlineKeyboardButton(
            text="← Назад к заданию",
            callback_data=AssignmentCD(action="view", assignment_id=callback_data.assignment_id, course_id=callback_data.course_id).pack(),
        )
    ])

    await query.message.edit_text(
        f"📝 Отправления для <b>{assignment.title}</b> ({len(submissions)}):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )
    await query.answer()


@router.callback_query(SubmissionCD.filter(F.action == "view"))
async def cb_submission_view(query: CallbackQuery, callback_data: SubmissionCD, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        submission = await uow.submissions.get_by_id(callback_data.submission_id)
        assignment = await uow.assignments.get_by_id(callback_data.assignment_id)
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)
        student = await uow.users.get_by_telegram_id(submission.student_id) if submission else None
        review = await uow.reviews.get_latest_by_submission(submission.id) if submission else None

    if not submission or not assignment or not role or role.role != "owner":
        await query.answer("Нет доступа.", show_alert=True)
        return

    student_name = student.name if student else str(submission.student_id)
    status_label = submission.status
    preview = submission.content_text or "Файл прикреплён или текст отсутствует."
    if submission.content_text and len(submission.content_text) > 600:
        preview = submission.content_text[:600] + "…"

    review_info = ""
    if review:
        review_info = f"\n\n<b>Review:</b> {review.status}, модель {html.escape(review.model)}"

    text = (
        f"👤 <b>{student_name}</b>\n"
        f"📄 <b>{assignment.title}</b>\n"
        f"Статус: <b>{status_label}</b>{review_info}\n\n"
        f"<b>Содержание:</b>\n{preview}"
    )

    buttons = []
    if submission.content_text or submission.file_id:
        buttons.append([
            InlineKeyboardButton(
                text="🤖 Проверить эту работу",
                callback_data=SubmissionCD(
                    action="review",
                    assignment_id=callback_data.assignment_id,
                    course_id=callback_data.course_id,
                    submission_id=submission.id,
                ).pack(),
            )
        ])
    if review:
        buttons.append([
            InlineKeyboardButton(
                text="📄 Посмотреть результаты",
                callback_data=SubmissionCD(
                    action="review_summary",
                    assignment_id=callback_data.assignment_id,
                    course_id=callback_data.course_id,
                    submission_id=submission.id,
                    review_id=review.id,
                ).pack(),
            )
        ])
    buttons.extend([
        [InlineKeyboardButton(
            text="← Назад к списку работ",
            callback_data=AssignmentCD(action="submissions", assignment_id=callback_data.assignment_id, course_id=callback_data.course_id).pack(),
        )],
        [InlineKeyboardButton(
            text="← Назад к заданию",
            callback_data=AssignmentCD(action="view", assignment_id=callback_data.assignment_id, course_id=callback_data.course_id).pack(),
        )],
    ])

    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode=ParseMode.HTML)
    await query.answer()


@router.callback_query(SubmissionCD.filter(F.action == "review"))
async def cb_submission_review(query: CallbackQuery, callback_data: SubmissionCD, db_user: User | None, state: FSMContext, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        submission = await uow.submissions.get_by_id(callback_data.submission_id)
        assignment = await uow.assignments.get_by_id(callback_data.assignment_id)
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)

    if not submission or not assignment or not role or role.role != "owner":
        await query.answer("Нет доступа.", show_alert=True)
        return

    submission_text = await _resolve_submission_text(query, submission)
    if not submission_text:
        await query.answer("Эта работа не содержит текста для анализа.", show_alert=True)
        return

    # Сохраняем данные для FSM
    await state.set_state(ReviewEditStates.waiting_for_temperature)
    await state.update_data(
        assignment_id=assignment.id,
        course_id=callback_data.course_id,
        submission_id=submission.id,
        submission_text=submission_text,
    )
    await query.message.answer(
        "Выберите модель для проверки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"Default ({settings.default_agent_model})", callback_data="model|{0}".format(settings.default_agent_model))],
            [InlineKeyboardButton(text="Qwen Code (qwen/qwen3-coder:free)", callback_data="model|qwen/qwen3-coder:free")],
            [InlineKeyboardButton(text="gpt-4o-mini", callback_data="model|openai/gpt-4o-mini")],
        ])
    )

# FSM: выбор модели и температуры
@router.callback_query(lambda c: c.data and c.data.startswith("model|"), ReviewEditStates.waiting_for_temperature)
async def cb_choose_model(query: CallbackQuery, state: FSMContext) -> None:
    model = query.data.split("|", 1)[1]
    await state.update_data(model=model)
    await state.set_state(ReviewEditStates.waiting_for_system_prompt)
    await query.message.answer(
        "Выберите температуру генерации (чем выше — тем креативнее, но менее предсказуемо):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="0.2 (по умолчанию)", callback_data="temp|0.2")],
            [InlineKeyboardButton(text="0.5", callback_data="temp|0.5")],
            [InlineKeyboardButton(text="0.8", callback_data="temp|0.8")],
        ])
    )
    await query.answer()

@router.callback_query(lambda c: c.data and c.data.startswith("temp|"), ReviewEditStates.waiting_for_system_prompt)
async def cb_choose_temperature(query: CallbackQuery, state: FSMContext) -> None:
    temperature = float(query.data.split("|", 1)[1])
    await state.update_data(temperature=temperature)
    await state.set_state(ReviewEditStates.waiting_for_system_prompt)
    await query.message.answer(
        "Введите system prompt для агента (или отправьте - для значения по умолчанию):"
    )
    await query.answer()

@router.message(ReviewEditStates.waiting_for_system_prompt)
async def cb_enter_system_prompt(message: Message, state: FSMContext, db_user: User | None, uow_factory) -> None:
    data = await state.get_data()
    model = data.get("model", settings.default_agent_model)
    temperature = data.get("temperature", 0.2)
    system_prompt = message.text.strip() if message.text and message.text.strip() != "-" else None
    assignment_id = data["assignment_id"]
    course_id = data["course_id"]
    submission_id = data["submission_id"]
    submission_text = data["submission_text"]

    async with uow_factory() as uow:
        assignment = await uow.assignments.get_by_id(assignment_id)
        submission = await uow.submissions.get_by_id(submission_id)
    # Передаём параметры в агент
    agent = CodeReviewAgent(model=model, temperature=temperature, system_prompt=system_prompt)
    result, raw_output = await agent.review_submission(
        assignment_title=assignment.title,
        assignment_description=assignment.description,
        assignment_criteria=assignment.criteria,
        submission_text=submission_text,
        system_prompt=system_prompt,
    )

    async with uow_factory() as uow:
        review = await uow.reviews.create(
            submission_id=submission.id,
            model=model,
            raw_output=raw_output,
            status="pending_moderation" if isinstance(result, AgentOutput) else "failed",
            overall_score=result.overall_score if isinstance(result, AgentOutput) else None,
            summary=result.summary if isinstance(result, AgentOutput) else str(result),
            temperature=temperature,
            system_prompt=system_prompt,
        )
        if isinstance(result, AgentOutput):
            for item in result.items:
                await uow.reviews.create_item(
                    review_id=review.id,
                    category=item.category,
                    severity=item.severity,
                    title=item.title,
                    description=item.description,
                    location=item.location,
                    suggestion=item.suggestion,
                )
            await uow.submissions.update(submission.id, status="reviewed")
        await uow.commit()

    await state.clear()
    if isinstance(result, AgentOutput):
        await message.answer(
            f"Ревью выполнено (модель: {model}, температура: {temperature}).\nМожете просмотреть результаты.",
        )
    else:
        await message.answer(
            "⚠️ Agent returned an unexpected response:\n" + str(result),
        )


@router.callback_query(SubmissionCD.filter(F.action == "review_summary"))
async def cb_submission_review_summary(query: CallbackQuery, callback_data: SubmissionCD, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        submission = await uow.submissions.get_by_id(callback_data.submission_id)
        assignment = await uow.assignments.get_by_id(callback_data.assignment_id)
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)
        review = await uow.reviews.get_latest_by_submission(callback_data.submission_id)

    if not submission or not assignment or not role or role.role != "owner" or not review:
        await query.answer("Нет доступа или обзор не найден.", show_alert=True)
        return

    items = await uow.reviews.get_items_by_review(review.id)
    item_lines = []
    for item in items:
        decision = item.teacher_decision or "pending"
        note = f"\n<i>Teacher note:</i> {html.escape(item.teacher_comments)}" if item.teacher_comments else ""
        item_lines.append(
            f"• <b>{html.escape(item.title)}</b> [{html.escape(item.severity)}] — {html.escape(decision)}"
            f"\n{html.escape(item.description)}"
            f"{f'\nLocation: {html.escape(item.location)}' if item.location else ''}"
            f"{f'\nSuggestion: {html.escape(item.suggestion)}' if item.suggestion else ''}"
            f"{note}"
        )

    status_label = review.status.replace("_", " ").capitalize()
    if review.feedback_sent_at:
        status_label += " / feedback sent"

    score_text = f"{review.overall_score:.1f}/10" if review.overall_score is not None else "n/a"
    feedback_note = f"\n\n<b>Teacher feedback:</b> {review.teacher_feedback}" if review.teacher_feedback else ""
    text = (
        f"🧾 <b>Review summary</b>\n"
        f"Status: <b>{status_label}</b>\n"
        f"Score: <b>{score_text}</b>\n\n"
        f"{review.summary or ''}{feedback_note}\n\n"
        f"<b>Items:</b>\n{chr(10).join(item_lines)}"
    )

    await query.message.edit_text(
        text,
        reply_markup=_review_summary_kb(
            review_id=review.id,
            submission_id=submission.id,
            assignment_id=assignment.id,
            course_id=callback_data.course_id,
            items=items,
        ),
        parse_mode=ParseMode.HTML,
    )
    await query.answer()


@router.callback_query(ReviewItemCD.filter())
async def cb_review_item_action(query: CallbackQuery, callback_data: ReviewItemCD, db_user: User | None, state: FSMContext, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        item = await uow.reviews.get_item_by_id(callback_data.item_id)
        review = await uow.reviews.get_by_id(callback_data.review_id)
        submission = await uow.submissions.get_by_id(callback_data.submission_id)
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)

    if not item or not review or not submission or not role or role.role != "owner":
        await query.answer("Нет доступа.", show_alert=True)
        return

    if callback_data.action == "view":
        item_text = (
            f"<b>{html.escape(item.title)}</b> [{html.escape(item.severity)}]\n"
            f"{html.escape(item.description)}"
            f"{f'\nLocation: {html.escape(item.location)}' if item.location else ''}"
            f"{f'\nSuggestion: {html.escape(item.suggestion)}' if item.suggestion else ''}"
            f"{f'\n\nTeacher note: {html.escape(item.teacher_comments)}' if item.teacher_comments else ''}"
            f"\n\nCurrent status: {html.escape(item.teacher_decision or 'pending')}"
        )
        await query.message.edit_text(
            item_text,
            reply_markup=_review_item_kb(
                review_id=review.id,
                item_id=item.id,
                submission_id=submission.id,
                assignment_id=callback_data.assignment_id,
                course_id=callback_data.course_id,
            ),
            parse_mode=ParseMode.HTML,
        )
        await query.answer()
        return
    if callback_data.action == "accept":
        await uow.reviews.update_item(item.id, teacher_decision="accepted")
        await uow.commit()
        await query.answer("Замечание принято.")
    elif callback_data.action == "reject":
        await uow.reviews.update_item(item.id, teacher_decision="rejected")
        await uow.commit()
        await query.answer("Замечание отклонено.")
    elif callback_data.action == "edit":
        await state.set_state(ReviewEditStates.waiting_for_edited_text)
        await state.update_data(
            review_id=callback_data.review_id,
            item_id=callback_data.item_id,
            submission_id=callback_data.submission_id,
            assignment_id=callback_data.assignment_id,
            course_id=callback_data.course_id,
        )
        await query.message.answer(
            "Введите правки/дополнения к этому замечанию:",
            reply_markup=ReplyKeyboardRemove(),
        )
        await query.answer()
        return
    else:
        await query.answer("Неизвестное действие.", show_alert=True)
        return

    await query.message.answer(
        "Действие сохранено. Вы можете продолжить проверку или отправить финальный фидбек.",
        reply_markup=_review_item_kb(
            review_id=review.id,
            item_id=item.id,
            submission_id=submission.id,
            assignment_id=callback_data.assignment_id,
            course_id=callback_data.course_id,
        ),
    )
    await query.answer()


@router.callback_query(ReviewModelCD.filter(F.action == "select"))
async def cb_review_with_model(query: CallbackQuery, callback_data: ReviewModelCD, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        submission = await uow.submissions.get_by_id(callback_data.submission_id)
        assignment = await uow.assignments.get_by_id(callback_data.assignment_id)
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)

    if not submission or not assignment or not role or role.role != "owner":
        await query.answer("Нет доступа.", show_alert=True)
        return

    submission_text = await _resolve_submission_text(query, submission)
    if not submission_text:
        await query.answer("Эта работа не содержит текста для анализа.", show_alert=True)
        return

    await query.answer("Запрос отправлен агенту, подождите...")

    agent = CodeReviewAgent(model=callback_data.model)
    result, raw_output = await agent.review_submission(
        assignment_title=assignment.title,
        assignment_description=assignment.description,
        assignment_criteria=assignment.criteria,
        submission_text=submission_text,
    )

    async with uow_factory() as uow:
        review = await uow.reviews.create(
            submission_id=submission.id,
            model=callback_data.model,
            raw_output=raw_output,
            status="pending_moderation" if isinstance(result, AgentOutput) else "failed",
            overall_score=result.overall_score if isinstance(result, AgentOutput) else None,
            summary=result.summary if isinstance(result, AgentOutput) else str(result),
        )
        if isinstance(result, AgentOutput):
            for item in result.items:
                await uow.reviews.create_item(
                    review_id=review.id,
                    category=item.category,
                    severity=item.severity,
                    title=item.title,
                    description=item.description,
                    location=item.location,
                    suggestion=item.suggestion,
                )
            await uow.submissions.update(submission.id, status="reviewed")
        await uow.commit()

    if isinstance(result, AgentOutput):
        item_lines = []
        for item in result.items:
            item_lines.append(
                f"• <b>{html.escape(item.title)}</b> [{html.escape(item.severity)}]"
                f"\n{html.escape(item.description)}"
                f"{f'\nLocation: {html.escape(item.location)}' if item.location else ''}"
                f"{f'\nSuggestion: {html.escape(item.suggestion)}' if item.suggestion else ''}"
            )

        summary_text = (
            f"🤖 Automatic review completed (model: {html.escape(callback_data.model)}):\n"
            f"Score: <b>{result.overall_score:.1f}/10</b>\n"
            f"{html.escape(result.summary)}\n\n"
            f"<b>Strengths:</b> {html.escape(', '.join(result.strengths)) if result.strengths else 'none'}\n\n"
            f"<b>Items:</b>\n{chr(10).join(item_lines)}"
        )
        await query.message.answer(summary_text, parse_mode=ParseMode.HTML)
        await query.message.answer(
            "Вы можете скорректировать итоговую проверку и отправить студенту финальный фидбек.",
            reply_markup=_review_navigation_kb(
                review_id=review.id,
                submission_id=submission.id,
                assignment_id=assignment.id,
                course_id=callback_data.course_id,
            ),
        )
    else:
        await query.message.answer(
            "⚠️ Agent returned an unexpected response:\n" + str(result),
        )


@router.callback_query(SubmissionCD.filter(F.action == "send_feedback"))
async def cb_submission_send_feedback(query: CallbackQuery, callback_data: SubmissionCD, db_user: User | None, state: FSMContext, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        submission = await uow.submissions.get_by_id(callback_data.submission_id)
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)
        review = await uow.reviews.get_latest_by_submission(callback_data.submission_id)

    if not submission or not role or role.role != "owner" or not review:
        await query.answer("Нет доступа или обзор не найден.", show_alert=True)
        return

    await state.set_state(ReviewEditStates.waiting_for_feedback_text)
    await state.update_data(
        review_id=review.id,
        submission_id=submission.id,
        assignment_id=callback_data.assignment_id,
        course_id=callback_data.course_id,
    )
    await query.message.answer(
        "Введите финальный фидбек студенту:",
        reply_markup=ReplyKeyboardRemove(),
    )
    await query.answer()


@router.message(ReviewEditStates.waiting_for_edited_text)
async def process_review_item_edit(message: Message, state: FSMContext, db_user: User | None, uow_factory) -> None:
    if not db_user or not message.text:
        await message.answer("Неверный ввод. Попробуйте ещё раз.")
        return

    data = await state.get_data()
    item_id = data.get("item_id")
    review_id = data.get("review_id")
    assignment_id = data.get("assignment_id")
    course_id = data.get("course_id")

    async with uow_factory() as uow:
        item = await uow.reviews.update_item(item_id, teacher_comments=message.text, teacher_decision="edited")
        await uow.commit()

    await state.clear()
    await message.answer(
        "Комментарий сохранён. Откройте обзор заново, чтобы продолжить.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(ReviewEditStates.waiting_for_feedback_text)
async def process_review_feedback(message: Message, state: FSMContext, db_user: User | None, uow_factory) -> None:
    if not db_user or not message.text:
        await message.answer("Неверный ввод. Попробуйте ещё раз.")
        return

    data = await state.get_data()
    review_id = data.get("review_id")
    submission_id = data.get("submission_id")

    async with uow_factory() as uow:
        review = await uow.reviews.get_by_id(review_id)
        submission = await uow.submissions.get_by_id(submission_id)
        student = await uow.users.get_by_telegram_id(submission.student_id) if submission else None

        if review:
            await uow.reviews.update(
                review.id,
                teacher_feedback=message.text,
                feedback_sent_at=datetime.now(timezone.utc),
                status="finalized",
            )
        if submission:
            await uow.submissions.update(submission.id, status="feedback_sent")
        await uow.commit()

    await state.clear()

    if student:
        try:
            await message.bot.send_message(
                student.telegram_id,
                f"📩 Ваше задание было проверено. Вот комментарий от преподавателя:\n\n{message.text}",
            )
            await message.answer("Фидбек отправлен студенту.")
        except Exception:
            await message.answer(
                "Фидбек сохранён, но не удалось отправить сообщение студенту."
            )
    else:
        await message.answer("Фидбек сохранён, но студент не найден в базе.")


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
    await state.set_state(AssignmentCreateStates.waiting_for_privacy)
    await message.answer(
        "Это приватное тестовое задание для преподавателя? Ответьте Да или Нет:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Да"), KeyboardButton(text="Нет")],
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )


@router.message(AssignmentCreateStates.waiting_for_privacy)
async def process_assignment_privacy(message: Message, state: FSMContext) -> None:
    text = message.text.strip().lower() if message.text else ""
    is_private = text == "да"
    await state.update_data(is_private=is_private)
    await state.set_state(AssignmentCreateStates.waiting_for_deadline)
    await message.answer(
        "Введите дедлайн в формате ДД.MM.ГГГГ или нажмите «Пропустить»:",
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
            is_private=data.get("is_private", False),
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
