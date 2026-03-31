"""
APScheduler — еженедельный брифинг и очистка кеша.
"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)


def setup_scheduler(bot, chat_id: int):
    """
    Настроить расписание:
    - Брифинг: воскресенье 20:00
    - Очистка кеша: понедельник 04:00
    """
    from handlers.briefing import send_briefing
    from database import cleanup_expired_cache

    # Еженедельный брифинг
    scheduler.add_job(
        send_briefing,
        CronTrigger(day_of_week="sun", hour=20, minute=0, timezone=config.TIMEZONE),
        args=[bot, chat_id],
        id="weekly_briefing",
        replace_existing=True,
    )

    # Очистка просроченного кеша
    scheduler.add_job(
        cleanup_expired_cache,
        CronTrigger(day_of_week="mon", hour=4, minute=0, timezone=config.TIMEZONE),
        id="cache_cleanup",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Планировщик запущен. Брифинг: вс 20:00, очистка кеша: пн 04:00 (%s)",
        config.TIMEZONE,
    )
