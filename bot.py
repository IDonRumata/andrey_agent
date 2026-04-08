import asyncio
import logging
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    BotCommandScopeDefault,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import config
import database as db

# --- Логирование с ротацией (макс 5 МБ x 3 файла) ---
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

file_handler = RotatingFileHandler(
    config.LOG_DIR / "agent.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
file_handler.setFormatter(log_formatter)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])
logger = logging.getLogger(__name__)

# --- Бот и диспетчер (с FSM storage для English-модуля) ---
bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# --- Мидлварь: проверка доступа ---
from aiogram import BaseMiddleware


class AccessMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        if isinstance(event, types.Message):
            if event.from_user and event.from_user.id != config.ALLOWED_USER_ID:
                await event.answer("Доступ запрещён. Этот бот только для Андрея.")
                return
        return await handler(event, data)


class RateLimitMiddleware(BaseMiddleware):
    """Защита от спама: макс 30 сообщений в минуту."""

    def __init__(self):
        self._timestamps: list[float] = []
        self._limit = 30
        self._window = 60.0

    async def __call__(self, handler, event, data):
        import time
        now = time.time()
        self._timestamps = [t for t in self._timestamps if now - t < self._window]
        if len(self._timestamps) >= self._limit:
            if isinstance(event, types.Message):
                await event.answer("⏳ Слишком много сообщений. Подожди минуту.")
            return
        self._timestamps.append(now)
        return await handler(event, data)


dp.message.middleware(AccessMiddleware())
dp.message.middleware(RateLimitMiddleware())


# ─────────────────────── Главное меню (inline) ───────────────────────

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎯 Задачи и идеи", callback_data="m:tasks")],
        [InlineKeyboardButton(text="💼 Проекты", callback_data="m:projects")],
        [InlineKeyboardButton(text="📈 Портфель", callback_data="m:portfolio")],
        [InlineKeyboardButton(text="🇬🇧 Английский", callback_data="m:english")],
        [InlineKeyboardButton(text="📊 Метрики и брифинг", callback_data="m:metrics")],
        [InlineKeyboardButton(text="✍️ Контент", callback_data="m:content")],
        [InlineKeyboardButton(text="🔍 Поиск", callback_data="m:search")],
        [InlineKeyboardButton(text="💰 Расходы AI", callback_data="m:cost")],
    ])


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Меню", callback_data="m:main")]
    ])


@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    await message.answer(
        "☰ *Главное меню*\n\nВыбери раздел или говори голосом — я пойму:",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )


@dp.callback_query(lambda c: c.data == "m:main")
async def cb_main(cb: types.CallbackQuery):
    await cb.message.edit_text(
        "☰ *Главное меню*\n\nВыбери раздел или говори голосом:",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )
    await cb.answer()


@dp.callback_query(lambda c: c.data == "m:tasks")
async def cb_tasks(cb: types.CallbackQuery):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Активные задачи", callback_data="m:tasks_show")],
        [InlineKeyboardButton(text="💡 Идеи", callback_data="m:ideas_show")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="m:main")],
    ])
    await cb.message.edit_text(
        "🎯 *Задачи и идеи*\n\n"
        "Команды:\n"
        "/tasks — список\n"
        "/done ID — закрыть\n"
        "/ideas — идеи\n"
        "/idea2task ID — идея → задача\n"
        "/clear — архив выполненных",
        parse_mode="Markdown", reply_markup=kb,
    )
    await cb.answer()


@dp.callback_query(lambda c: c.data == "m:tasks_show")
async def cb_tasks_show(cb: types.CallbackQuery):
    from handlers.tasks import _format_tasks
    tasks = await db.get_active_tasks()
    msg = await _format_tasks(tasks) if tasks else "✅ Активных задач нет."
    await cb.message.answer(msg, parse_mode="Markdown", reply_markup=back_kb())
    await cb.answer()


@dp.callback_query(lambda c: c.data == "m:ideas_show")
async def cb_ideas_show(cb: types.CallbackQuery):
    ideas = await db.get_ideas()
    if not ideas:
        await cb.message.answer("Идей пока нет.", reply_markup=back_kb())
    else:
        lines = [f"💡 *Идеи ({len(ideas)}):*\n"]
        for i in ideas[:15]:
            lines.append(f"#{i['id']} {i['text'][:70]}")
        await cb.message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=back_kb())
    await cb.answer()


@dp.callback_query(lambda c: c.data == "m:projects")
async def cb_projects(cb: types.CallbackQuery):
    projects = await db.get_projects()
    if not projects:
        text = "📁 Проектов нет.\n\nДобавить: `/new название`"
    else:
        lines = ["📁 *Проекты:*\n"]
        for p in projects:
            lines.append(f"• *{p['name']}* — {p['status']}")
        lines.append("\n/new название · /summary название · /brain")
        text = "\n".join(lines)
    await cb.message.edit_text(text, parse_mode="Markdown", reply_markup=back_kb())
    await cb.answer()


@dp.callback_query(lambda c: c.data == "m:portfolio")
async def cb_portfolio(cb: types.CallbackQuery):
    await cb.message.edit_text(
        "📈 *Портфель*\n\n"
        "/portfolio — текущие позиции\n"
        "/buy BTC 0.001 69000 Bybit — купить\n"
        "/sell ID — закрыть позицию\n"
        "/pnl — реализованная прибыль\n"
        "/export — выгрузить в CSV",
        parse_mode="Markdown", reply_markup=back_kb(),
    )
    await cb.answer()


@dp.callback_query(lambda c: c.data == "m:english")
async def cb_english(cb: types.CallbackQuery):
    from handlers.english import cmd_english_menu
    await cmd_english_menu(cb.message)
    await cb.answer()


@dp.callback_query(lambda c: c.data == "m:metrics")
async def cb_metrics(cb: types.CallbackQuery):
    await cb.message.edit_text(
        "📊 *Метрики*\n\n"
        "/m — добавить метрику\n"
        "/stats — статистика недели\n"
        "/pushups N — отжимания\n"
        "/digest — сводка дня (авто 21:00)\n"
        "/briefing — еженедельный отчёт",
        parse_mode="Markdown", reply_markup=back_kb(),
    )
    await cb.answer()


@dp.callback_query(lambda c: c.data == "m:content")
async def cb_content(cb: types.CallbackQuery):
    await cb.message.edit_text(
        "✍️ *Контент*\n\n"
        "/post тема — пост TG/Instagram\n"
        "/tg тема — пост для канала «Графин»\n"
        "/hook — 3 цепляющих заголовка\n"
        "/caption — подпись Reels/Shorts\n"
        "/rewrite текст — рерайт под бренд",
        parse_mode="Markdown", reply_markup=back_kb(),
    )
    await cb.answer()


@dp.callback_query(lambda c: c.data == "m:search")
async def cb_search(cb: types.CallbackQuery):
    await cb.message.edit_text(
        "🔍 *Поиск*\n\n/find запрос — поиск в интернете",
        parse_mode="Markdown", reply_markup=back_kb(),
    )
    await cb.answer()


@dp.callback_query(lambda c: c.data == "m:cost")
async def cb_cost(cb: types.CallbackQuery):
    cost_7d = await db.get_total_cost(days=7)
    cost_30d = await db.get_total_cost(days=30)
    await cb.message.edit_text(
        f"💰 *Расходы на AI*\n\n"
        f"За 7 дней: ${cost_7d:.3f}\n"
        f"За 30 дней: ${cost_30d:.3f}",
        parse_mode="Markdown", reply_markup=back_kb(),
    )
    await cb.answer()


# ─────────────────────── /start, /help ───────────────────────

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет, Андрей! Я твой AI-агент.\n\n"
        "Открой меню — `/menu`\n"
        "Полный список команд — `/help`\n\n"
        "Или просто говори голосом / пиши текстом — я пойму.",
        parse_mode="Markdown",
        reply_markup=main_menu_kb(),
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    text = (
        "📖 *Все команды*\n\n"
        "*☰ Навигация*\n"
        "/menu — главное меню\n"
        "/start — стартовый экран\n\n"
        "*🎯 Задачи и идеи*\n"
        "/tasks · /ideas · /done ID · /idea2task ID · /clear\n\n"
        "*💼 Проекты*\n"
        "/projects · /new · /project · /summary · /brain\n\n"
        "*📈 Портфель*\n"
        "/portfolio · /buy · /sell · /pnl · /export\n\n"
        "*🇬🇧 Английский*\n"
        "/en — меню модуля\n"
        "/en\\_start — placement test (входная оценка)\n"
        "/en\\_unit N — установить юнит учебника\n"
        "/en\\_block — блок упражнений (~10 мин)\n"
        "/en\\_review — повторение SRS\n"
        "/en\\_speak — speaking practice\n"
        "/en\\_lesson — отчёт с урока с учителем\n"
        "/en\\_homework — мои ДЗ\n"
        "/en\\_progress — прогресс\n"
        "/en\\_voice — голос TTS (uk\\_f / uk\\_m / us\\_f / us\\_m)\n"
        "/en\\_grammar тема — справка\n"
        "/vocab — словарь\n\n"
        "*📊 Метрики*\n"
        "/m · /stats · /pushups N · /digest · /briefing\n\n"
        "*✍️ Контент*\n"
        "/post · /tg · /hook · /caption · /rewrite\n\n"
        "*🔍 / 💰 / ↩️*\n"
        "/find · /cost · /undo"
    )
    await message.answer(text, parse_mode="Markdown")


# ─────────────────────── Запуск ───────────────────────

async def main():
    logger.info("Инициализация базы данных...")
    await db.init_db()

    from services.classifier import load_projects_from_db
    await load_projects_from_db()
    logger.info("Проекты загружены в классификатор")

    from handlers import (
        briefing,
        chat,
        content,
        cost,
        digest,
        english,
        ideas,
        metrics,
        photo,
        portfolio,
        projects,
        search,
        tasks,
        undo,
        voice,
    )
    dp.include_router(english.router)  # english до voice — у english свои FSM-фильтры
    dp.include_router(tasks.router)
    dp.include_router(ideas.router)
    dp.include_router(content.router)
    dp.include_router(metrics.router)
    dp.include_router(projects.router)
    dp.include_router(search.router)
    dp.include_router(cost.router)
    dp.include_router(briefing.router)
    dp.include_router(digest.router)
    dp.include_router(portfolio.router)
    dp.include_router(photo.router)
    dp.include_router(undo.router)
    dp.include_router(voice.router)
    dp.include_router(chat.router)  # chat последним

    from services.scheduler import setup_scheduler
    setup_scheduler(bot, config.ALLOWED_USER_ID)

    # Меню команд Telegram (синяя кнопка слева от поля ввода)
    await bot.set_my_commands([
        BotCommand(command="menu", description="☰ Главное меню"),
        BotCommand(command="en", description="🇬🇧 English — меню модуля"),
        BotCommand(command="en_block", description="▶️ Блок English (~10 мин)"),
        BotCommand(command="en_review", description="🔄 Повторение SRS"),
        BotCommand(command="en_speak", description="🗣 Speaking practice"),
        BotCommand(command="en_lesson", description="📝 Отчёт с урока"),
        BotCommand(command="en_progress", description="📊 Прогресс English"),
        BotCommand(command="tasks", description="🎯 Активные задачи"),
        BotCommand(command="ideas", description="💡 Идеи"),
        BotCommand(command="projects", description="📁 Проекты"),
        BotCommand(command="portfolio", description="📈 Портфель"),
        BotCommand(command="buy", description="Купить актив"),
        BotCommand(command="pnl", description="P&L"),
        BotCommand(command="digest", description="📅 Сводка дня"),
        BotCommand(command="briefing", description="📋 Брифинг недели"),
        BotCommand(command="m", description="📊 Метрики"),
        BotCommand(command="find", description="🔍 Поиск"),
        BotCommand(command="cost", description="💰 Расходы AI"),
        BotCommand(command="undo", description="↩️ Отменить"),
        BotCommand(command="help", description="❓ Все команды"),
    ], scope=BotCommandScopeDefault())
    logger.info("Меню команд установлено")

    logger.info("Бот запущен. Polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
