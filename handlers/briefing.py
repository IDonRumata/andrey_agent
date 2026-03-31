"""
Модуль 3 — Еженедельный брифинг.
Воскресенье 20:00 (Europe/Minsk) — автоматически.
/briefing — ручной вызов в любой момент.

Собирает данные за неделю из SQLite (0 токенов),
Claude Haiku генерирует только "пинок" (1 предложение).
"""
import logging
from datetime import datetime, timedelta

from aiogram import Router, types
from aiogram.filters import Command

import database as db
from handlers.metrics import get_weekly_metrics_summary
from services.claude_api import ask_claude

router = Router()
logger = logging.getLogger(__name__)


async def generate_briefing() -> str:
    """
    Сформировать еженедельный брифинг.
    Данные — из SQLite (бесплатно).
    Claude Haiku — только для мотивационного пинка (~$0.0003).
    """
    now = datetime.now()
    week_ago = (now - timedelta(days=7)).isoformat()
    week_num = now.isocalendar()[1]
    date_from = (now - timedelta(days=7)).strftime("%d.%m")
    date_to = now.strftime("%d.%m")

    # 1. Выполненные задачи
    done_tasks = await db.get_done_tasks_since(week_ago)
    if done_tasks:
        done_lines = "\n".join(f"  ✅ {t['text']}" for t in done_tasks)
    else:
        done_lines = "  — ничего не закрыто"

    # 2. Невыполненные (активные)
    active_tasks = await db.get_overdue_tasks()
    if active_tasks:
        active_lines = "\n".join(f"  ⏳ {t['text']}" for t in active_tasks[:10])
        if len(active_tasks) > 10:
            active_lines += f"\n  ... и ещё {len(active_tasks) - 10}"
    else:
        active_lines = "  — всё чисто!"

    # 3. Метрики (из metrics.py)
    metrics_summary = await get_weekly_metrics_summary()

    # 4. Новые идеи за неделю
    ideas = await db.get_ideas()
    recent_ideas = [i for i in ideas if i["created_at"] and i["created_at"] >= week_ago]
    if recent_ideas:
        ideas_lines = "\n".join(f"  💡 {i['text'][:80]}" for i in recent_ideas[:5])
    else:
        ideas_lines = "  — не было"

    # 5. Расходы на AI
    cost = await db.get_total_cost(days=7)

    # 6. Приоритет — самая старая активная задача
    if active_tasks:
        priority = active_tasks[0]["text"]
    else:
        priority = "Нет активных задач — можно думать стратегически"

    # 7. Мотивационный пинок от Haiku (единственный вызов Claude)
    kick = await _generate_kick(
        done_count=len(done_tasks),
        active_count=len(active_tasks),
        ideas_count=len(recent_ideas),
    )

    # Сборка
    briefing = (
        f"📋 **НЕДЕЛЯ {week_num}** — {date_from} – {date_to}\n\n"
        f"**ВЫПОЛНЕНО ({len(done_tasks)}):**\n{done_lines}\n\n"
        f"**НЕ ВЫПОЛНЕНО ({len(active_tasks)}):**\n{active_lines}\n\n"
        f"**МЕТРИКИ:**\n{metrics_summary}\n\n"
        f"**НОВЫЕ ИДЕИ ({len(recent_ideas)}):**\n{ideas_lines}\n\n"
        f"**РАСХОДЫ НА AI:** ${cost:.2f}\n\n"
        f"**ПРИОРИТЕТ НА СЛЕДУЮЩУЮ НЕДЕЛЮ:**\n  🎯 {priority}\n\n"
        f"{kick}"
    )

    return briefing


async def _generate_kick(done_count: int, active_count: int, ideas_count: int) -> str:
    """Мотивационный пинок через Haiku — 1 предложение, ~$0.0003."""
    context = (
        f"Закрыто задач: {done_count}. Осталось: {active_count}. Новых идей: {ideas_count}."
    )
    try:
        kick = await ask_claude(
            f"Дай короткий мотивационный пинок (1 предложение, макс 100 символов) "
            f"для предпринимателя-дальнобойщика по итогам недели: {context}",
            tier="haiku",
            use_history=False,
            use_cache=False,  # каждую неделю новый
            cache_ttl_hours=0,
        )
        return f"💬 {kick}"
    except Exception as e:
        logger.error("Ошибка генерации пинка: %s", e)
        return "💬 Продолжай давить, Андрей. Фура не остановится сама."


async def send_briefing(bot, chat_id: int):
    """Отправить брифинг — вызывается из scheduler."""
    logger.info("Генерация еженедельного брифинга...")
    try:
        text = await generate_briefing()
        # Telegram лимит — 4096 символов
        if len(text) > 4000:
            parts = [text[:4000], text[4000:]]
            for part in parts:
                await bot.send_message(chat_id, part, parse_mode="Markdown")
        else:
            await bot.send_message(chat_id, text, parse_mode="Markdown")
        logger.info("Брифинг отправлен")
    except Exception as e:
        logger.error("Ошибка отправки брифинга: %s", e)


# --- Ручной вызов ---

@router.message(Command("briefing"))
async def cmd_briefing(message: types.Message):
    """Ручной вызов брифинга в любой момент."""
    await message.answer("📋 Генерирую брифинг...")
    text = await generate_briefing()
    if len(text) > 4000:
        await message.answer(text[:4000], parse_mode="Markdown")
        await message.answer(text[4000:], parse_mode="Markdown")
    else:
        await message.answer(text, parse_mode="Markdown")
