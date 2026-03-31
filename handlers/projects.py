from datetime import datetime, timedelta

from aiogram import Router, types
from aiogram.filters import Command

import database as db
from services.claude_api import ask_claude
from services.classifier import load_projects_from_db

router = Router()


@router.message(Command("projects"))
async def cmd_projects(message: types.Message):
    """Список всех проектов."""
    args = message.text.replace("/projects", "").strip()
    include_archive = "--archive" in args
    projects = await db.get_projects(include_archive=include_archive)

    if not projects:
        await message.answer("Нет проектов. Создай: /new [название]")
        return

    lines = ["📁 **Проекты:**\n"]
    for p in projects:
        status = "🟢" if p["status"] == "active" else "⏸" if p["status"] == "paused" else "📦"
        lines.append(f"{status} **{p['name']}** — {p['description'] or 'без описания'}")
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("project"))
async def cmd_project(message: types.Message):
    """Открыть базу проекта — все записи в хронологии."""
    name = message.text.replace("/project", "").strip()
    if not name:
        await message.answer("Укажи название: /project [название]")
        return

    project = await db.get_project_by_name(name)
    if not project:
        await message.answer(f"Проект '{name}' не найден. Смотри /projects")
        return

    entries = await db.get_project_entries(project["id"])
    lines = [
        f"ПРОЕКТ: {project['name']} — {project['description'] or ''}",
        f"Статус: {project['status']} | Записей: {len(entries)}",
        "—" * 40,
    ]
    for e in entries:
        dt = e["created_at"][:10] if e["created_at"] else ""
        lines.append(f"[{e['type'].upper()}] {dt}")
        lines.append(f"  {e['structured'] or e['raw_text']}")
        lines.append("")

    lines.append("—" * 40)
    lines.append(f"Команды: /summary {name} | /archive {name}")
    await message.answer("\n".join(lines))


@router.message(Command("new"))
async def cmd_new_project(message: types.Message):
    """Создать новый проект."""
    name = message.text.replace("/new", "").strip()
    if not name:
        await message.answer("Укажи название: /new [название]")
        return

    project_id = await db.create_project(name)
    # Обновить динамический кеш проектов в классификаторе
    await load_projects_from_db()
    await message.answer(f"✅ Проект '{name}' создан (ID: {project_id}). Добавляй записи голосом или текстом!")


@router.message(Command("brain"))
async def cmd_brain(message: types.Message):
    """Все идеи за последние 7 дней по всем проектам."""
    projects = await db.get_projects()
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()

    lines = ["🧠 **Идеи за последние 7 дней:**\n"]
    found = False
    for p in projects:
        entries = await db.get_project_entries(p["id"])
        recent = [e for e in entries if e["created_at"] and e["created_at"] >= week_ago]
        if recent:
            found = True
            lines.append(f"**{p['name']}**")
            for e in recent:
                lines.append(f"  [{e['type']}] {e['structured'] or e['raw_text']}")
            lines.append("")

    if not found:
        lines.append("Пусто. Наговори идей!")

    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("summary"))
async def cmd_summary(message: types.Message):
    """Claude делает резюме всех мыслей по проекту."""
    name = message.text.replace("/summary", "").strip()
    if not name:
        await message.answer("Укажи проект: /summary [название]")
        return

    project = await db.get_project_by_name(name)
    if not project:
        await message.answer(f"Проект '{name}' не найден.")
        return

    entries = await db.get_project_entries(project["id"])
    if not entries:
        await message.answer("По этому проекту пока нет записей.")
        return

    entries_text = "\n".join(
        f"[{e['type']}] {e['created_at'][:10]}: {e['structured'] or e['raw_text']}"
        for e in entries
    )
    response = await ask_claude(
        f"Сделай краткое резюме всех мыслей по проекту '{name}':\n\n{entries_text}",
    )
    await message.answer(f"📝 Резюме проекта **{name}**:\n\n{response}", parse_mode="Markdown")


@router.message(Command("archive"))
async def cmd_archive_project(message: types.Message):
    """Архивировать проект."""
    name = message.text.replace("/archive", "").strip()
    if not name:
        await message.answer("Укажи проект: /archive [название]")
        return

    project = await db.get_project_by_name(name)
    if not project:
        await message.answer(f"Проект '{name}' не найден.")
        return

    import aiosqlite
    from config import DB_PATH
    async with aiosqlite.connect(DB_PATH) as conn:
        await conn.execute("UPDATE projects SET status = 'archive' WHERE id = ?", (project["id"],))
        await conn.commit()

    await message.answer(f"📦 Проект '{name}' перемещён в архив.")
