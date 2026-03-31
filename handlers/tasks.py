"""
Модуль 1 — Захват задач. Команды: /tasks, /done, /clear.
Задачи создаются из свободного текста (через классификатор) или явно.
"""
from aiogram import Router, types
from aiogram.filters import Command

import database as db
from services.classifier import PROJECT_ALIASES

router = Router()


@router.message(Command("tasks"))
async def cmd_tasks(message: types.Message):
    """
    /tasks — все активные задачи, группировка по проектам.
    /tasks grafin — только по проекту.
    """
    args = message.text.replace("/tasks", "").strip().lower()
    project_filter = PROJECT_ALIASES.get(args, args) if args else None

    tasks = await db.get_active_tasks(project=project_filter)
    if not tasks:
        if project_filter:
            await message.answer(f"Нет активных задач по проекту '{args}'.")
        else:
            await message.answer("Нет активных задач. Свобода!")
        return

    # Группировка по проектам
    by_project: dict[str, list] = {}
    for t in tasks:
        proj = t["project"] or "без проекта"
        by_project.setdefault(proj, []).append(t)

    lines = ["📋 **Активные задачи:**\n"]
    total = 0
    for project, items in by_project.items():
        lines.append(f"**{project.upper()}** ({len(items)})")
        for t in items:
            age = _task_age(t["created_at"])
            age_str = f" ⚠️ {age}д" if age >= 7 else ""
            lines.append(f"  `{t['id']}` {t['text']}{age_str}")
            total += 1
        lines.append("")

    lines.append(f"Всего: {total} | Закрыть: /done [ID или текст]")
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("done"))
async def cmd_done(message: types.Message):
    """
    /done 5 — закрыть по ID.
    /done купить домен — закрыть по тексту.
    """
    args = message.text.replace("/done", "").strip()
    if not args:
        await message.answer("Укажи ID или текст задачи:\n/done 5\n/done купить домен")
        return

    # Попробовать как ID
    if args.isdigit():
        task = await db.complete_task(int(args))
    else:
        task = await db.complete_task_by_text(args)

    if task:
        remaining = len(await db.get_active_tasks())
        await message.answer(f"✅ Закрыта: {task['text']}\nОсталось задач: {remaining}")
    else:
        # Подсказка — показать похожие
        if not args.isdigit():
            similar = await db.search_active_tasks(args)
            if similar:
                hints = "\n".join(f"  `{t['id']}` {t['text']}" for t in similar[:3])
                await message.answer(f"Не нашёл точного совпадения. Может одна из этих?\n{hints}", parse_mode="Markdown")
                return
        await message.answer("Задача не найдена. Проверь /tasks")


@router.message(Command("clear"))
async def cmd_clear(message: types.Message):
    """Архивировать все выполненные задачи."""
    done_count = await db.get_done_tasks_count()
    if done_count == 0:
        await message.answer("Нечего архивировать — выполненных задач нет.")
        return

    archived = await db.archive_done_tasks()
    await message.answer(f"🗃 Архивировано: {archived} задач")


def _task_age(created_at: str | None) -> int:
    """Возраст задачи в днях."""
    if not created_at:
        return 0
    from datetime import datetime
    try:
        created = datetime.fromisoformat(created_at)
        return (datetime.now() - created).days
    except (ValueError, TypeError):
        return 0
