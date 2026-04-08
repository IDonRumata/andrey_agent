"""
Адаптивный планировщик дня и недели.
Без LLM — чистая логика на основе профиля и недавней статистики.
"""
from datetime import date, timedelta

import database as db


# Расписание блоков в течение дня (Mn)
DAILY_BLOCKS = {
    0: [("08:00", "drill"), ("13:00", "translate"), ("18:00", "review")],   # Mon
    1: [("08:00", "listening"), ("13:00", "translate"), ("18:00", "review")],
    2: [("08:00", "review"), ("13:00", "drill"), ("18:00", "speaking")],
    3: [("08:00", "grammar"), ("13:00", "drill"), ("18:00", "review")],
    4: [("08:00", "weekly_test"), ("18:00", "speaking")],   # Fri
    5: [],  # Sat — учитель
    6: [],  # Sun — учитель
}


async def adapt_daily_target(user_id: int) -> int:
    """
    Адаптация количества новых чанков на день по retention последних 3 дней.
    >90% точность 2 дня — повышаем. <70% — понижаем.
    """
    profile = await db.en_get_or_create_profile(user_id)
    current = profile.get("daily_chunks_target", 8)

    import aiosqlite
    from config import DB_PATH
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute(
            """SELECT date, SUM(items_correct) as c, SUM(items_total) as t
               FROM english_sessions
               WHERE user_id = ? AND date >= date('now', '-3 days')
               GROUP BY date""",
            (user_id,),
        )
        rows = [dict(r) for r in await cursor.fetchall()]

    if len(rows) < 2:
        return current

    accuracies = [(r["c"] / r["t"] * 100) if r["t"] else 0 for r in rows]
    high_days = sum(1 for a in accuracies if a >= 90)
    low_days = sum(1 for a in accuracies if a < 70)

    if high_days >= 2:
        new_target = min(current + 2, 16)
    elif low_days >= 2:
        new_target = max(current - 2, 3)
    else:
        new_target = current

    if new_target != current:
        await db.en_update_profile(user_id, daily_chunks_target=new_target)
    return new_target


async def get_today_blocks(user_id: int) -> list[dict]:
    """Список блоков на сегодня с учётом дня недели."""
    weekday = date.today().weekday()
    schedule = DAILY_BLOCKS.get(weekday, [])
    return [{"time": t, "type": btype} for t, btype in schedule]


async def get_current_unit(user_id: int) -> dict | None:
    profile = await db.en_get_or_create_profile(user_id)
    unit_num = profile.get("current_unit", 1)
    return await db.en_get_unit_by_number(unit_num)
