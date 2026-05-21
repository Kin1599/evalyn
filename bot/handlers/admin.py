from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from core.config import settings

router = Router()


def _is_admin(telegram_id: int) -> bool:
    return telegram_id in settings.admin_ids


@router.message(Command("admin"))
async def cmd_admin(message: Message, uow_factory) -> None:
    if not _is_admin(message.from_user.id):
        return

    await message.answer(
        "*Команды администратора:*\n"
        "`/admin add_teacher @username [заметка]`\n"
        "`/admin add_teacher 123456789 [заметка]`\n"
        "`/admin remove_teacher @username`\n"
        "`/admin list_teachers`",
        parse_mode="Markdown",
    )


@router.message(Command("admin_add_teacher"))
async def add_teacher(message: Message, uow_factory) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("Использование: `/admin_add_teacher @username [заметка]`", parse_mode="Markdown")
        return

    target = parts[1].strip()
    notes = parts[2].strip() if len(parts) > 2 else None

    async with uow_factory() as uow:
        if target.startswith("@"):
            username = target.lstrip("@")
            entry = await uow.whitelist.add(
                added_by=message.from_user.id,
                username=username,
                notes=notes,
            )
            label = f"@{username}"
        else:
            try:
                tid = int(target)
            except ValueError:
                await message.answer("Укажите @username или числовой telegram_id.")
                return
            entry = await uow.whitelist.add(
                added_by=message.from_user.id,
                telegram_id=tid,
                notes=notes,
            )
            label = str(tid)
        await uow.commit()

    note_str = f" ({entry.notes})" if entry.notes else ""
    await message.answer(f"✅ Добавлен в whitelist: {label}{note_str}")


@router.message(Command("admin_remove_teacher"))
async def remove_teacher(message: Message, uow_factory) -> None:
    if not _is_admin(message.from_user.id):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: `/admin_remove_teacher @username_or_id`", parse_mode="Markdown")
        return

    target = parts[1].strip()
    async with uow_factory() as uow:
        if target.startswith("@"):
            # remove by username — find entry first
            all_entries = await uow.whitelist.get_all()
            uname = target.lstrip("@")
            entry = next((e for e in all_entries if e.username == uname), None)
            if not entry:
                await message.answer(f"@{uname} не найден в whitelist.")
                return
            removed = await uow.whitelist.delete(entry.id)
        else:
            try:
                tid = int(target)
            except ValueError:
                await message.answer("Укажите @username или числовой telegram_id.")
                return
            removed = await uow.whitelist.remove(tid)
        await uow.commit()

    if removed:
        await message.answer(f"❌ Удалён из whitelist: {target}")
    else:
        await message.answer(f"Не найден в whitelist: {target}")


@router.message(Command("admin_list_teachers"))
async def list_teachers(message: Message, uow_factory) -> None:
    if not _is_admin(message.from_user.id):
        return

    async with uow_factory() as uow:
        entries = await uow.whitelist.get_all()

    if not entries:
        await message.answer("Whitelist пуст.")
        return

    lines = []
    for e in entries:
        who = f"@{e.username}" if e.username else str(e.telegram_id)
        note = f" — {e.notes}" if e.notes else ""
        lines.append(f"• {who}{note}")

    await message.answer("*Whitelist преподавателей:*\n" + "\n".join(lines), parse_mode="Markdown")
