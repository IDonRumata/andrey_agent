import asyncio
import logging
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

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


dp.message.middleware(AccessMiddleware())


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
        "Или просто напиши/надиктуй — я пойму.",
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
    from handlers import tasks, ideas, content, metrics, projects, search, cost, briefing, chat, voice
    dp.include_router(tasks.router)
    dp.include_router(ideas.router)
    dp.include_router(content.router)
    dp.include_router(metrics.router)
    dp.include_router(projects.router)
    dp.include_router(search.router)
    dp.include_router(cost.router)
    dp.include_router(briefing.router)
    dp.include_router(voice.router)
    dp.include_router(chat.router)  # chat последним - ловит всё остальное

    # Планировщик: брифинг вс 20:00, очистка кеша пн 04:00
    from services.scheduler import setup_scheduler
    setup_scheduler(bot, config.ALLOWED_USER_ID)

    logger.info("Бот запущен. Polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
