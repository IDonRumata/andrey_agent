"""
/undo — отменить последнее действие.
/export — выгрузить портфель в CSV.
"""
import csv
import io
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, BufferedInputFile

import database as db

router = Router()
logger = logging.getLogger(__name__)


@router.message(Command("undo"))
async def cmd_undo(message: Message):
    """Отменить последнее действие."""
    action = await db.get_last_action()
    if not action:
        await message.answer("Нечего отменять.")
        return

    table = action["entity_table"]
    entity_id = action["entity_id"]
    action_type = action["action_type"]

    try:
        if action_type == "add" and table == "tasks":
            await db.delete_task(entity_id)
            await message.answer(f"↩️ Задача #{entity_id} удалена.")

        elif action_type == "add" and table == "ideas":
            await db.delete_idea(entity_id)
            await message.answer(f"↩️ Идея #{entity_id} удалена.")

        elif action_type == "add" and table == "portfolio":
            await db.delete_portfolio_entry(entity_id)
            await message.answer(f"↩️ Позиция #{entity_id} удалена из портфеля.")

        elif action_type == "done" and table == "tasks":
            await db.reopen_task(entity_id)
            await message.answer(f"↩️ Задача #{entity_id} возвращена в активные.")

        elif action_type == "add" and table == "metrics":
            await message.answer(f"↩️ Отмена записи метрик не поддерживается. Перезаписать: /m")

        else:
            await message.answer(f"Не знаю как отменить: {action_type} в {table}")
            return

        await db.delete_action_log(action["id"])
    except Exception as e:
        logger.error("Undo error: %s", e)
        await message.answer(f"Ошибка отмены: {e}")


@router.message(Command("export"))
async def cmd_export(message: Message):
    """Экспорт портфеля в CSV."""
    positions = await db.get_all_portfolio()
    if not positions:
        await message.answer("Портфель пустой, нечего экспортировать.")
        return

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "ID", "Asset", "Type", "Exchange", "Qty", "BuyPrice",
        "Currency", "BuyDate", "Status", "SellPrice", "SellDate"
    ])
    for p in positions:
        writer.writerow([
            p["id"], p["asset"], p["asset_type"], p["exchange"],
            p["quantity"], p["buy_price"], p["currency"], p["buy_date"],
            p["status"], p.get("sell_price", ""), p.get("sell_date", ""),
        ])

    csv_bytes = buf.getvalue().encode("utf-8-sig")
    doc = BufferedInputFile(csv_bytes, filename="portfolio.csv")
    await message.answer_document(doc, caption="Портфель в CSV")
