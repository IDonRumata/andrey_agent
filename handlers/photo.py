"""
Обработка фото через Claude Vision.
- Скриншот сделки (Bybit/Binance/FF) → автоматически в портфель
- Скриншот графика → анализ
- Любое другое фото → описание + ответ
"""
import base64
import io
import json
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from services.claude_api import ask_claude_vision
import database as db
from services.prices import detect_asset_type
import config

router = Router()
logger = logging.getLogger(__name__)

VISION_SYSTEM = """Ты личный AI-ассистент Андрея. Он прислал фото в контексте беседы.

ПРАВИЛА:
1. Сначала посмотри КОНТЕКСТ БЕСЕДЫ — если разговор уже идёт на какую-то тему, фото относится к ней.
2. Если фото — скриншот сделки/транзакции (биржа, крипто, брокер) И в контексте речь о покупке/продаже:
   Верни JSON: {"type":"trade","direction":"buy","asset":"BTC","quantity":0.001,"price":69608.0,"exchange":"Bybit","date":"2026-04-01","currency":"USD","confidence":"high"}
3. Если фото прислано КАК ИНФОРМАЦИЯ к текущей беседе (скриншот проекта, интерфейса, чата, квиза и т.д.):
   Ответь текстом на русском — опиши что видишь и продолжи беседу в контексте.
   НЕ пытайся найти сделку если речь не про покупку/продажу.
4. Если несколько фото подряд — это иллюстрации к одной теме, не анализируй каждое как отдельную сущность.

Отвечай кратко, конкретно, по делу. Как опытный бизнес-партнёр."""


def _fmt(n: float) -> str:
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:,.6g}"


@router.message(F.photo)
async def handle_photo(message: Message):
    """Получить фото, распознать через Claude Vision с контекстом беседы."""
    await message.answer("🔍 Читаю фото...")

    # Скачать фото максимального размера
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)

    buf = io.BytesIO()
    await message.bot.download_file(file.file_path, destination=buf)
    buf.seek(0)
    image_b64 = base64.b64encode(buf.read()).decode()

    # Подтянуть последние сообщения беседы для контекста
    history = await db.get_chat_history(limit=6)
    context_lines = []
    for msg in history:
        role = "Андрей" if msg["role"] == "user" else "Ассистент"
        context_lines.append(f"{role}: {msg['content'][:200]}")
    context_str = "\n".join(context_lines)

    # Подпись от пользователя (если есть)
    caption = message.caption or ""
    prompt = (
        f"КОНТЕКСТ БЕСЕДЫ (последние сообщения):\n{context_str}\n\n"
        f"Андрей прислал фото.{' Подпись: ' + caption if caption else ''}\n"
        f"Проанализируй в контексте беседы."
    )

    # Отправить в Claude Vision
    raw = await ask_claude_vision(
        image_base64=image_b64,
        media_type="image/jpeg",
        prompt=prompt,
        system_prompt=VISION_SYSTEM,
    )

    # Сохранить ответ в историю чата (чтобы следующие фото знали контекст)
    photo_desc = f"[Фото] {caption}" if caption else "[Фото]"
    await db.save_message("user", photo_desc)
    await db.save_message("assistant", raw[:500])

    # Попробовать распарсить JSON (только если Claude вернул JSON — значит это сделка)
    parsed = None
    try:
        clean = raw.strip().strip("`").replace("```json", "").replace("```", "").strip()
        parsed = json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        pass  # Обычный текст — не сделка

    if parsed is None:
        # Claude ответил текстом — это описание/аналитика, просто показать
        await message.answer(raw, parse_mode="Markdown")
        return

    result_type = parsed.get("type", "other")

    # ─── Не сделка, но JSON с текстом ───
    if result_type != "trade":
        text = parsed.get("text", raw)
        await message.answer(text)
        return

    # ─── Сделка — показать с кнопками подтверждения ───
    if result_type == "trade":
        direction = parsed.get("direction", "buy")
        asset = (parsed.get("asset") or "").upper()
        quantity = parsed.get("quantity")
        price = parsed.get("price")
        exchange = parsed.get("exchange", "")
        date = parsed.get("date", "")
        currency = parsed.get("currency", "USD")
        confidence = parsed.get("confidence", "medium")

        if not asset or not quantity or not price:
            await message.answer(
                "Вижу что это сделка, но не все данные читаются чётко.\n"
                "Введи вручную:\n"
                f"`/buy АКТИВ КОЛ-ВО ЦЕНА БИРЖА`",
                parse_mode="Markdown"
            )
            return

        asset_type = detect_asset_type(asset)
        conf_note = "" if confidence == "high" else f"\n⚠️ Уверенность: {confidence}"
        total = float(quantity) * float(price)
        dir_text = "Покупка" if direction == "buy" else "Продажа"

        # Данные для callback
        cb_data = f"trade:{direction}:{asset}:{quantity}:{price}:{exchange}:{date}:{currency}:{asset_type}"
        # Telegram callback_data max 64 bytes — обрезаем если надо
        if len(cb_data) > 64:
            cb_data = cb_data[:64]

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Сохранить", callback_data=cb_data),
                InlineKeyboardButton(text="❌ Не надо", callback_data="trade:cancel"),
            ]
        ])

        await message.answer(
            f"📸 Распознана сделка:{conf_note}\n\n"
            f"📌 {dir_text}: {asset} ({asset_type})\n"
            f"Кол-во: {_fmt(float(quantity))}\n"
            f"Цена: {_fmt(float(price))} {currency}\n"
            f"Сумма: {_fmt(total)} {currency}\n"
            f"Биржа: {exchange or '—'}\n"
            f"Дата: {date}\n\n"
            f"Сохранить в портфель?",
            reply_markup=keyboard,
        )


@router.callback_query(F.data.startswith("trade:"))
async def handle_trade_callback(callback: CallbackQuery):
    """Обработка кнопок подтверждения сделки."""
    data = callback.data

    if data == "trade:cancel":
        await callback.message.edit_text(
            callback.message.text + "\n\n❌ Отменено.",
        )
        await callback.answer("Отменено")
        return

    # Парсим: trade:direction:asset:quantity:price:exchange:date:currency:asset_type
    parts = data.split(":")
    if len(parts) < 9:
        await callback.answer("Ошибка данных")
        return

    _, direction, asset, quantity, price, exchange, date, currency, asset_type = parts[:9]
    quantity = float(quantity)
    price = float(price)

    if direction == "buy":
        entry_id = await db.add_portfolio_entry(
            asset=asset, asset_type=asset_type, exchange=exchange,
            quantity=quantity, buy_price=price, currency=currency, buy_date=date,
        )
        await db.log_action("add", "portfolio", entry_id)
        await callback.message.edit_text(
            callback.message.text + f"\n\n✅ Сохранено! Позиция #{entry_id}\n/portfolio",
        )
    elif direction == "sell":
        positions = await db.get_portfolio()
        matching = [p for p in positions if p["asset"] == asset]
        if matching:
            entry = matching[0]
            await db.close_portfolio_entry(entry["id"], price, date)
            buy_total = entry["quantity"] * entry["buy_price"]
            sell_total = quantity * price
            pnl = sell_total - buy_total
            sign = "+" if pnl >= 0 else ""
            await callback.message.edit_text(
                callback.message.text + f"\n\n{'🟢' if pnl >= 0 else '🔴'} Продажа зафиксирована. P&L: {sign}{pnl:.2f} {currency}",
            )
        else:
            await callback.message.edit_text(
                callback.message.text + f"\n\n⚠️ Нет активной позиции по {asset}",
            )

    await callback.answer("Готово!")
