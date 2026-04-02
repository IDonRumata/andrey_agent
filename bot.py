import asyncio
import logging
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import BotCommand, BotCommandScopeDefault

import config
import database as db

# --- Логирование с ротацией (макс 5 МБ x 3 файла) ---
log_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

file_handler = RotatingFileHandler(
    config.LOG_DIR / "agent.log",
    maxBytes=5 * 1024 * 1024,  # 5 МБ
    backupCount=3,
    encoding="utf-8",
)
file_handler.setFormatter(log_formatter)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(log_formatter)

logging.basicConfig(level=logging.INFO, handlers=[file_handler, stream_handler])
logger = logging.getLogger(__name__)

# --- Бот и диспетчер ---
bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()


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


# --- Базовые команды ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет, Андрей! Я твой AI-агент.\n\n"
        "📋 **Задачи и идеи:**\n"
        "/tasks — активные задачи (+ /tasks grafin)\n"
        "/ideas — список идей\n"
        "/done [ID/текст] — закрыть задачу\n"
        "/idea2task [ID] — идея → задача\n"
        "/clear — архивировать выполненные\n\n"
        "📁 **Проекты:**\n"
        "/projects — список проектов\n"
        "/project [назв] — база проекта\n"
        "/new [назв] — новый проект\n"
        "/brain — идеи за 7 дней\n"
        "/summary [назв] — резюме проекта\n\n"
        "✍️ **Контент:**\n"
        "/post /caption /hook /tg [тема]\n"
        "/rewrite [текст] — рерайт под бренд\n\n"
        "📊 **Метрики:** /m, /stats, /pushups [N]\n"
        "📋 **Брифинг:** /briefing\n"
        "🔍 **Поиск:** /find [запрос]\n"
        "💰 **Расходы:** /cost\n\n"
        "💼 **Портфель:**\n"
        "/buy актив кол-во [цена] [биржа]\n"
        "/sell ID [цена] — зафиксировать продажу\n"
        "/portfolio — портфель с текущими ценами\n"
        "/pnl — реализованная прибыль\n"
        "/export — выгрузить в CSV\n\n"
        "📅 /digest — сводка за сегодня (авто 21:00)\n"
        "↩️ /undo — отменить последнее действие\n\n"
        "Или просто напиши/надиктуй/скинь фото — я пойму.",
        parse_mode="Markdown",
    )


@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await cmd_start(message)


# --- Запуск ---

async def main():
    logger.info("Инициализация базы данных...")
    await db.init_db()

    # Подгрузить проекты из БД в локальный классификатор
    from services.classifier import load_projects_from_db
    await load_projects_from_db()
    logger.info("Проекты загружены в классификатор")

    # Импорт и подключение роутеров handlers
    from handlers import tasks, ideas, content, metrics, projects, search, cost, briefing, digest, chat, voice, portfolio, photo, undo, english
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
    dp.include_router(english.router)
    dp.include_router(voice.router)
    dp.include_router(chat.router)  # chat последним - ловит всё остальное

    # Планировщик: брифинг вс 20:00, очистка кеша пн 04:00
    from services.scheduler import setup_scheduler
    setup_scheduler(bot, config.ALLOWED_USER_ID)

    # Установить меню команд
    await bot.set_my_commands([
        BotCommand(command="tasks",    description="Активные задачи"),
        BotCommand(command="ideas",    description="Список идей"),
        BotCommand(command="projects", description="Список проектов"),
        BotCommand(command="new",      description="Создать проект: /new название"),
        BotCommand(command="brain",    description="Идеи за 7 дней"),
        BotCommand(command="summary",  description="AI-резюме проекта"),
        BotCommand(command="post",     description="Пост TG/Instagram: /post тема"),
        BotCommand(command="tg",       description="Пост для канала Графин"),
        BotCommand(command="hook",     description="3 цепляющих заголовка"),
        BotCommand(command="caption",  description="Подпись Reels/Shorts"),
        BotCommand(command="rewrite",  description="Рерайт под бренд"),
        BotCommand(command="m",        description="Ввод метрик"),
        BotCommand(command="stats",    description="Статистика за неделю/месяц"),
        BotCommand(command="pushups",  description="Записать отжимания: /pushups N"),
        BotCommand(command="briefing", description="Еженедельный отчёт"),
        BotCommand(command="find",     description="Веб-поиск: /find запрос"),
        BotCommand(command="done",      description="Закрыть задачу: /done ID"),
        BotCommand(command="cost",      description="Расходы на AI за месяц"),
        BotCommand(command="buy",       description="Купил актив: /buy BTC 0.001 69000 Bybit"),
        BotCommand(command="sell",      description="Продал актив: /sell ID [цена]"),
        BotCommand(command="portfolio", description="Мой портфель с текущими ценами"),
        BotCommand(command="pnl",       description="Реализованная прибыль по сделкам"),
        BotCommand(command="digest",    description="Сводка за сегодня"),
        BotCommand(command="undo",      description="Отменить последнее действие"),
        BotCommand(command="export",    description="Экспорт портфеля в CSV"),
        BotCommand(command="en",        description="English A1→B1 — меню"),
        BotCommand(command="vocab",     description="Словарь: /vocab word — перевод"),
        BotCommand(command="enreview",  description="Слова на повторение"),
        BotCommand(command="entest",    description="Мини-тест по словам"),
        BotCommand(command="engram",    description="Грамматика: /engram present perfect"),
        BotCommand(command="help",      description="Список всех команд"),
    ], scope=BotCommandScopeDefault())
    logger.info("Меню команд установлено")

    logger.info("Бот запущен. Polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
