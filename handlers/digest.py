"""
/digest — ежедневная сводка.
Автоматически в 21:00 Europe/Minsk + ручной вызов.
"""
import logging
from datetime import datetime, timedelta, date

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import database as db

router = Router()
logger = logging.getLogger(__name__)


async def generate_digest() -> str:
    """Сводка за сегодня. Данные из SQLite — 0 токенов."""
    today = date.today()
    today_str = today.isoformat()
    today_start = f"{today_str}T00:00:00"

    # 1. Задачи закрытые сегодня
    done_tasks = await db.get_done_tasks_since(today_start)

    # 2. Активные задачи
    active_tasks = await db.get_active_tasks()

    # 3. Метрики за сегодня
    metrics = await db.get_metrics(days=1)
    today_metrics = metrics[0] if metrics and metrics[0].get("date") == today_str else None

    # 4. Расход AI сегодня
    usage = await db.get_token_usage(days=1)
    today_cost = sum(u["cost_usd"] for u in usage if u["date"] == today_str)

    # 5. Новые идеи сегодня
    all_ideas = await db.get_ideas()
    today_ideas = [i for i in all_ideas if i.get("created_at", "").startswith(today_str)]

    # 6. Портфель
    positions = await db.get_portfolio()

    # Сборка
    lines = [f"📅 **СВОДКА ЗА {today.strftime('%d.%m.%Y')}**\n"]

    # Выполнено
    if done_tasks:
        lines.append(f"✅ **Выполнено ({len(done_tasks)}):**")
        for t in done_tasks[:5]:
            lines.append(f"  - {t['text']}")
    else:
        lines.append("⏸ Задачи не закрывались сегодня")

    # Активные
    lines.append(f"\n⏳ **Активных задач:** {len(active_tasks)}")
    overdue = [t for t in active_tasks if t.get("created_at") and t["created_at"] < (datetime.now() - timedelta(days=7)).isoformat()]
    if overdue:
        lines.append(f"  ⚠️ Из них просрочено (>7 дней): {len(overdue)}")

    # Метрики
    if today_metrics:
        m_parts = []
        if today_metrics.get("grafin_sales"):
            m_parts.append(f"продажи: {today_metrics['grafin_sales']}")
        if today_metrics.get("pushups"):
            m_parts.append(f"отжимания: {today_metrics['pushups']}")
        if today_metrics.get("grafin_subscribers"):
            m_parts.append(f"подписчики: {today_metrics['grafin_subscribers']}")
        if m_parts:
            lines.append(f"\n📊 **Метрики:** {', '.join(m_parts)}")

    # Идеи
    if today_ideas:
        lines.append(f"\n💡 **Новых идей:** {len(today_ideas)}")

    # Портфель
    if positions:
        lines.append(f"\n💼 **Портфель:** {len(positions)} позиций")

    # Расходы
    lines.append(f"\n💰 **Расход AI сегодня:** ${today_cost:.3f}")

    return "\n".join(lines)


async def send_digest(bot, chat_id: int):
    """Отправить дайджест — вызывается из scheduler."""
    logger.info("Генерация дайджеста...")
    try:
        text = await generate_digest()
        await bot.send_message(chat_id, text, parse_mode="Markdown")
        logger.info("Дайджест отправлен")
    except Exception as e:
        logger.error("Ошибка дайджеста: %s", e)


@router.message(Command("digest"))
async def cmd_digest(message: Message):
    text = await generate_digest()
    await message.answer(text, parse_mode="Markdown")
