"""
Модуль 4 — Контент-помощник.
Генерация постов, подписей, заголовков с учётом личного бренда.
Команды: /post, /caption, /hook, /tg, /rewrite.
"""
from aiogram import Router, types
from aiogram.filters import Command

from services.claude_api import ask_claude
import database as db

router = Router()

# Развёрнутый системный промпт — один раз, переиспользуется во всех командах.
# Контекст бренда зашит сюда чтобы не тратить токены на его передачу каждый раз.
CONTENT_SYSTEM = """Ты контент-мейкер для личного бренда Андрея.

БРЕНД "ВОДИТЕЛЬ-ИНВЕСТОР":
- Андрей — дальнобойщик (польская компания), который строит цифровые продукты из кабины фуры
- Жена Марина — партнёр по контенту и публичная роль
- Продукт: Графин — 5-дневный TG-курс по инвестициям для новичков (45 BYN)
- Апсейл: Kronon MultiTrade — Forex-робот ($300)
- Аудитория: русскоязычные новички в инвестициях, 25-45 лет

ТОН И СТИЛЬ:
- Простой язык, как разговор с другом
- Честный, без пафоса и "успешного успеха"
- Истории из жизни в рейсе — главная фишка контента
- Мотивирующий, но реалистичный
- Короткие предложения, абзацы по 2-3 строки
- Эмодзи умеренно (2-4 на пост)

ЮРИДИЧЕСКИЕ ОГРАНИЧЕНИЯ (Беларусь):
- НЕЛЬЗЯ обещать доходность или конкретный заработок
- Вместо "заработаешь X" → "научишься управлять деньгами"
- Вместо "гарантированный доход" → "инструменты для принятия решений"

ФОРМАТЫ:
- Telegram: до 1500 символов, разбивка на абзацы, CTA в конце
- Instagram: до 2200 символов, больше сторителлинга
- Reels/Shorts подпись: до 150 символов + 5-7 хештегов
"""

# --- Шаблоны для быстрых промптов (экономия токенов) ---
TEMPLATES = {
    "post": "Напиши черновик поста для Telegram и Instagram.\nТема: {topic}\nФормат: 800-1200 символов, абзацы, CTA.",
    "caption": "Напиши подпись под Reels/Shorts.\nВидео: {topic}\nФормат: до 150 символов + 5-7 хештегов. Только текст подписи, без пояснений.",
    "hook": "Дай 3 варианта цепляющего первого предложения для поста.\nТема: {topic}\nФормат: только 3 предложения, пронумерованные.",
    "tg": "Напиши пост для Telegram-канала курса Графин.\nТема: {topic}\nФормат: 600-1000 символов, разбивка на абзацы, CTA 'запишись на курс'.",
    "rewrite": "Перепиши этот текст в стиле бренда 'водитель-инвестор'.\nОригинал:\n{topic}\nСохрани смысл, улучши подачу.",
}

# Какие команды дешёвые (Haiku), какие нужен Sonnet
TIER_MAP = {
    "post": "sonnet",     # полноценный пост — нужно качество
    "caption": "haiku",   # короткая подпись — Haiku справится
    "hook": "haiku",      # заголовки — Haiku справится
    "tg": "sonnet",       # пост для канала — нужно качество
    "rewrite": "sonnet",  # рерайт — нужно понимание стиля
}


async def _generate_content(message: types.Message, cmd: str):
    """Общий обработчик для всех контент-команд."""
    topic = message.text.replace(f"/{cmd}", "").strip()
    if not topic:
        hints = {
            "post": "/post инвестиции для новичков",
            "caption": "/caption обзор рабочего места в кабине",
            "hook": "/hook пассивный доход",
            "tg": "/tg почему я начал инвестировать",
            "rewrite": "/rewrite [вставь текст для переработки]",
        }
        await message.answer(f"Укажи тему: {hints.get(cmd, f'/{cmd} [тема]')}")
        return

    template = TEMPLATES[cmd]
    prompt = template.format(topic=topic)
    tier = TIER_MAP[cmd]

    response = await ask_claude(
        prompt,
        system_prompt=CONTENT_SYSTEM,
        tier=tier,
        use_history=False,
        use_cache=True,
        cache_ttl_hours=72,  # контент кешируем 3 дня
    )

    # Сохраняем сгенерированный контент как идею (можно вернуться)
    await db.add_idea(f"[{cmd}] {topic}: {response[:100]}...", project="grafin")

    await message.answer(response)


@router.message(Command("post"))
async def cmd_post(message: types.Message):
    """Черновик поста для Telegram/Instagram."""
    await _generate_content(message, "post")


@router.message(Command("caption"))
async def cmd_caption(message: types.Message):
    """Подпись под Reels/Shorts."""
    await _generate_content(message, "caption")


@router.message(Command("hook"))
async def cmd_hook(message: types.Message):
    """3 варианта цепляющего первого предложения."""
    await _generate_content(message, "hook")


@router.message(Command("tg"))
async def cmd_tg(message: types.Message):
    """Пост для Telegram-канала Графина."""
    await _generate_content(message, "tg")


@router.message(Command("rewrite"))
async def cmd_rewrite(message: types.Message):
    """Переписать текст в стиле бренда."""
    await _generate_content(message, "rewrite")
