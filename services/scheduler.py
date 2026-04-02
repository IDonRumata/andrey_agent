"""
APScheduler — планировщик задач.
- Брифинг: вс 20:00
- Дайджест: ежедневно 21:00
- Бэкап БД: ежедневно 03:00
- Очистка кеша: пн 04:00
"""
import logging
import subprocess
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import config

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=config.TIMEZONE)


async def run_backup(bot, chat_id: int):
    """Запустить backup.sh и уведомить о результате."""
    backup_script = Path(config.BASE_DIR) / "deploy" / "backup.sh"
    if not backup_script.exists():
        logger.warning("backup.sh не найден: %s", backup_script)
        return
    try:
        result = subprocess.run(
            ["bash", str(backup_script)],
            capture_output=True, text=True, timeout=60,
            env={"PATH": "/usr/bin:/bin:/usr/local/bin",
                 "TELEGRAM_BOT_TOKEN": config.TELEGRAM_BOT_TOKEN,
                 "ALLOWED_USER_ID": str(config.ALLOWED_USER_ID)},
        )
        if result.returncode == 0:
            logger.info("Бэкап выполнен успешно")
        else:
            logger.error("Бэкап ошибка: %s", result.stderr)
    except Exception as e:
        logger.error("Бэкап exception: %s", e)


def setup_scheduler(bot, chat_id: int):
    """Настроить все задачи по расписанию."""
    from handlers.briefing import send_briefing
    from handlers.digest import send_digest
    from database import cleanup_expired_cache

    # Еженедельный брифинг — вс 20:00
    scheduler.add_job(
        send_briefing,
        CronTrigger(day_of_week="sun", hour=20, minute=0, timezone=config.TIMEZONE),
        args=[bot, chat_id],
        id="weekly_briefing",
        replace_existing=True,
    )

    # Ежедневный дайджест — 21:00
    scheduler.add_job(
        send_digest,
        CronTrigger(hour=21, minute=0, timezone=config.TIMEZONE),
        args=[bot, chat_id],
        id="daily_digest",
        replace_existing=True,
    )

    # Бэкап БД — 03:00
    scheduler.add_job(
        run_backup,
        CronTrigger(hour=3, minute=0, timezone=config.TIMEZONE),
        args=[bot, chat_id],
        id="daily_backup",
        replace_existing=True,
    )

    # Очистка кеша — пн 04:00
    scheduler.add_job(
        cleanup_expired_cache,
        CronTrigger(day_of_week="mon", hour=4, minute=0, timezone=config.TIMEZONE),
        id="cache_cleanup",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Планировщик запущен: брифинг вс 20:00, дайджест 21:00, бэкап 03:00, кеш пн 04:00 (%s)",
        config.TIMEZONE,
    )
