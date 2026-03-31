"""
Модуль 1 — Захват идей. Команды: /ideas, /delidea, /idea2task.
Идеи создаются из свободного текста или голоса через классификатор.
"""
from aiogram import Router, types
from aiogram.filters import Command

import database as db
from services.classifier import PROJECT_ALIASES

router = Router()


@router.message(Command("ideas"))
async def cmd_ideas(message: types.Message):
    """
    /ideas — все идеи.
    /ideas grafin — по проекту.
    """
    args = message.text.replace("/ideas", "").strip().lower()
    project_filter = PROJECT_ALIASES.get(args, args) if args else None

    ideas = await db.get_ideas(project=project_filter)
    if not ideas:
        if project_filter:
            await message.answer(f"Нет идей по проекту '{args}'. Наговори что-нибудь!")
        else:
            await message.answer("Идей пока нет. Наговори что-нибудь!")
        return

    # Группировка по проектам
    by_project: dict[str, list] = {}
    for idea in ideas:
        proj = idea["project"] or "без проекта"
        by_project.setdefault(proj, []).append(idea)

    lines = ["💡 **Идеи:**\n"]
    for project, items in by_project.items():
        lines.append(f"**{project.upper()}** ({len(items)})")
        for idea in items[:10]:  # максимум 10 на проект чтобы не залить чат
            dt = idea["created_at"][:10] if idea["created_at"] else ""
            lines.append(f"  `{idea['id']}` {idea['text']} _{dt}_")
        if len(items) > 10:
            lines.append(f"  ... и ещё {len(items) - 10}")
        lines.append("")

    lines.append("Удалить: /delidea [ID] | В задачу: /idea2task [ID]")
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("delidea"))
async def cmd_delete_idea(message: types.Message):
    """Удалить идею по ID."""
    args = message.text.replace("/delidea", "").strip()
    if not args or not args.isdigit():
        await message.answer("Укажи ID идеи: /delidea 5")
        return

    ok = await db.delete_idea(int(args))
    if ok:
        await message.answer(f"🗑 Идея #{args} удалена.")
    else:
        await message.answer(f"Идея #{args} не найдена.")


@router.message(Command("idea2task"))
async def cmd_idea_to_task(message: types.Message):
    """Преобразовать идею в задачу."""
    args = message.text.replace("/idea2task", "").strip()
    if not args or not args.isdigit():
        await message.answer("Укажи ID идеи: /idea2task 5")
        return

    task_id = await db.move_idea_to_task(int(args))
    if task_id:
        await message.answer(f"✅ Идея #{args} стала задачей #{task_id}!")
    else:
        await message.answer(f"Идея #{args} не найдена.")
