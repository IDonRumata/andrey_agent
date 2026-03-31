import anthropic
from aiogram import Router, types
from aiogram.filters import Command

import config

router = Router()

client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

SEARCH_SYSTEM = f"""Ты личный помощник директора Андрея.
Регион пользователя: Беларусь (Витебск), работает в ЕС.
Предпочтительные валюты: BYN, EUR, USD.
При поиске билетов учитывай маршруты из Беларуси.
При поиске товаров - доступность в Беларуси или доставку.
Давай конкретные ссылки, цены, краткие выводы.
Формат: структурированно, без воды."""


async def assistant_search(user_request: str) -> str:
    """Поиск через Claude API с web_search."""
    response = await client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=config.CLAUDE_MAX_TOKENS,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        system=SEARCH_SYSTEM,
        messages=[{"role": "user", "content": user_request}],
    )
    # Собираем текстовые блоки из ответа
    parts = []
    for block in response.content:
        if block.type == "text":
            parts.append(block.text)
    return "\n".join(parts) or "Не удалось найти информацию."


SEARCH_TRIGGERS = ("найди", "поищи", "где купить", "сколько стоит", "как добраться", "сравни")


@router.message(Command("find"))
async def cmd_find(message: types.Message):
    """Явный поиск по запросу."""
    query = message.text.replace("/find", "").strip()
    if not query:
        await message.answer("Укажи запрос: /find [что ищем]")
        return
    await message.answer("🔍 Ищу...")
    result = await assistant_search(query)
    await message.answer(result)


@router.message(Command("watch"))
async def cmd_watch(message: types.Message):
    """Добавить в мониторинг (заглушка для будущего)."""
    query = message.text.replace("/watch", "").strip()
    if not query:
        await message.answer("Укажи что отслеживать: /watch [запрос]")
        return

    import aiosqlite
    from datetime import datetime
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO watchlist (query, active, created_at) VALUES (?, 1, ?)",
            (query, datetime.now().isoformat()),
        )
        await conn.commit()
    await message.answer(f"👁 Добавлено в мониторинг: {query}")


@router.message(Command("watchlist"))
async def cmd_watchlist(message: types.Message):
    """Список активных мониторингов."""
    import aiosqlite
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM watchlist WHERE active = 1 ORDER BY created_at DESC")
        rows = await cursor.fetchall()

    if not rows:
        await message.answer("Список мониторинга пуст.")
        return

    lines = ["👁 **Мониторинг:**\n"]
    for r in rows:
        lines.append(f"• {r['query']} (с {r['created_at'][:10]})")
    await message.answer("\n".join(lines), parse_mode="Markdown")
