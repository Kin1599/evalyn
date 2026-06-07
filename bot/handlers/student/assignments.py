import io

from aiogram import F, Router
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
)

from bot.states.submission import SubmissionStates
from core.config import settings
from services.review_service import run_assignment_review, store_review
from db.models.user import User

router = Router()

_STATUS_LABEL = {
    "pending": "⏳ На проверке",
    "reviewed": "✅ Проверено",
}


class StudentAssignmentCD(CallbackData, prefix="stud_asgn"):
    action: str
    assignment_id: int
    course_id: int


def _assignment_detail_kb(assignment_id: int, course_id: int, has_submission: bool) -> InlineKeyboardMarkup:
    submit_label = "🔄 Обновить работу" if has_submission else "📤 Сдать работу"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=submit_label,
            callback_data=StudentAssignmentCD(action="submit", assignment_id=assignment_id, course_id=course_id).pack(),
        )],
        [InlineKeyboardButton(
            text="← Назад к заданиям",
            callback_data=StudentAssignmentCD(action="back", assignment_id=0, course_id=course_id).pack(),
        )],
    ])


async def _resolve_submission_text_from_file(message: Message, file_id: str) -> str:
    file = await message.bot.get_file(file_id)
    buffer = io.BytesIO()
    await message.bot.download_file(file.file_path, destination=buffer)
    buffer.seek(0)
    try:
        text = buffer.read().decode("utf-8")
        if text.strip():
            return text
    except UnicodeDecodeError:
        pass

    file_name = file.file_path.split("/")[-1] if file.file_path else file_id
    return (
        f"Прикреплён файл {file_name}. "
        "Текстовый контент не удалось прочитать, но ревью будет выполнено по доступным данным."
    )


@router.callback_query(StudentAssignmentCD.filter(F.action == "view"))
async def cb_assignment_view(query: CallbackQuery, callback_data: StudentAssignmentCD, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        assignment = await uow.assignments.get_by_id(callback_data.assignment_id)
        course = await uow.courses.get_by_id(callback_data.course_id)
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)
        submission = await uow.submissions.get_by_student_and_assignment(
            db_user.telegram_id, callback_data.assignment_id
        )

    if not assignment or not role or role.role != "student" or getattr(assignment, "is_private", False):
        await query.answer("Нет доступа.", show_alert=True)
        return

    deadline_str = assignment.deadline.strftime("%d.%m.%Y") if assignment.deadline else "не указан"

    parts = [f"📄 <b>{assignment.title}</b>", f"🗓 Дедлайн: {deadline_str}", "", assignment.description]

    if assignment.criteria:
        parts += ["", f"<b>Критерии оценки:</b>\n{assignment.criteria}"]
    if getattr(assignment, "materials_text", None):
        parts += ["", f"<b>Материалы:</b>\n{assignment.materials_text}"]
    if getattr(assignment, "materials_file_name", None):
        parts += ["", f"<b>Файл-материал:</b> {assignment.materials_file_name}"]

    if submission:
        status_label = _STATUS_LABEL.get(submission.status, submission.status)
        parts += ["", f"<b>Ваша работа:</b> {status_label}"]
        if submission.content_text:
            preview = submission.content_text[:200]
            if len(submission.content_text) > 200:
                preview += "…"
            parts.append(f"<blockquote>{preview}</blockquote>")
        elif submission.file_id:
            parts.append("📎 Файл прикреплён")

    await query.message.edit_text(
        "\n".join(parts),
        reply_markup=_assignment_detail_kb(
            assignment_id=callback_data.assignment_id,
            course_id=callback_data.course_id,
            has_submission=submission is not None,
        ),
    )
    await query.answer()


@router.callback_query(StudentAssignmentCD.filter(F.action == "submit"))
async def cb_assignment_submit(query: CallbackQuery, callback_data: StudentAssignmentCD, state: FSMContext, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    async with uow_factory() as uow:
        assignment = await uow.assignments.get_by_id(callback_data.assignment_id)
        role = await uow.courses.get_role(db_user.telegram_id, callback_data.course_id)

    if not assignment or getattr(assignment, "is_private", False) or not role or role.role != "student":
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


@router.callback_query(StudentAssignmentCD.filter(F.action == "back"))
async def cb_assignment_back(query: CallbackQuery, callback_data: StudentAssignmentCD, db_user: User | None, uow_factory) -> None:
    if not db_user:
        await query.answer()
        return

    from bot.handlers.student.courses import _render_course_assignments
    await _render_course_assignments(query, callback_data.course_id, db_user, uow_factory)
    await query.answer()


@router.message(SubmissionStates.waiting_for_content)
async def process_submission(message: Message, state: FSMContext, db_user: User, uow_factory) -> None:
    data = await state.get_data()
    assignment_id = data["assignment_id"]
    course_id = data["course_id"]

    content_text: str | None = None
    file_id: str | None = None

    if message.text:
        content_text = message.text
    elif message.document:
        file_id = message.document.file_id
    elif message.photo:
        file_id = message.photo[-1].file_id
    else:
        await message.answer("Отправьте текст, документ или фото. Попробуйте ещё раз:")
        return

    async with uow_factory() as uow:
        submission = await uow.submissions.upsert(
            student_id=db_user.telegram_id,
            assignment_id=assignment_id,
            content_text=content_text,
            file_id=file_id,
        )
        await uow.commit()

    await state.clear()
    await message.answer(
        "✅ Работа принята и поставлена в очередь на проверку. "
        "Дождитесь фидбека преподавателя.",
        reply_markup=ReplyKeyboardRemove(),
    )
