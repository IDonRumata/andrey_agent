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
from aiogram.types import Message

from services.claude_api import ask_claude_vision
import database as db
from services.prices import detect_asset_type

router = Router()
logger = logging.getLogger(__name__)

VISION_TRADE_SYSTEM = """Ты анализируешь скриншоты финансовых приложений для инвестора Андрея.

Если на изображении видна сделка или транзакция (биржа, брокер, крипто-кошелёк):
Верни ТОЛЬКО JSON без markdown:
{"type":"trade","direction":"buy","asset":"BTC","quantity":0.001,"price":69608.0,"exchange":"Bybit","date":"2026-04-01","currency":"USD","confidence":"high"}

direction: buy или sell
confidence: high (данные чёткие) / medium (частично видно) / low (предположение)

Если это НЕ сделка (график, новость, фото, другое) — верни ТОЛЬКО JSON:
{"type":"other","text":"описание что на фото и твой комментарий для Андрея"}

Отвечай ТОЛЬКО JSON, без пояснений."""


def _fmt(n: float) -> str:
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:,.6g}"


@router.message(F.photo)
async def handle_photo(message: Message):
    """Получить фото, распознать через Claude Vision, сохранить если сделка."""
    await message.answer("🔍 Читаю фото...")

    # Скачать фото максимального размера
    photo = message.photo[-1]
    file = await message.bot.get_file(photo.file_id)

    buf = io.BytesIO()
    await message.bot.download_file(file.file_path, destination=buf)
    buf.seek(0)
    image_b64 = base64.b64encode(buf.read()).decode()

    # Подпись от пользователя (если есть)
    caption = message.caption or ""
    prompt = f"Проанализируй это изображение.{' Контекст от пользователя: ' + caption if caption else ''}"

    # Отправить в Claude Vision
    raw = await ask_claude_vision(
        image_base64=image_b64,
        media_type="image/jpeg",
        prompt=prompt,
        system_prompt=VISION_TRADE_SYSTEM,
    )

    # Попробовать распарсить JSON
    parsed = None
    try:
        # Убрать возможные markdown-блоки
        clean = raw.strip().strip("`").replace("```json", "").replace("```", "").strip()
        parsed = json.loads(clean)
    except (json.JSONDecodeError, ValueError):
        logger.warning("Vision вернул не JSON: %s", raw[:200])

    if parsed is None:
        # Claude ответил текстом — просто показать
        await message.answer(raw)
        return

    result_type = parsed.get("type", "other")

    # ─── Сделка ───
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
        conf_note = "" if confidence == "high" else f"\n⚠️ Уверенность: {confidence} — проверь данные"

        if direction == "buy":
            entry_id = await db.add_portfolio_entry(
                asset=asset,
                asset_type=asset_type,
                exchange=exchange,
                quantity=float(quantity),
                buy_price=float(price),
                currency=currency,
                buy_date=date,
            )
            total = float(quantity) * float(price)
            await message.answer(
                f"✅ Покупка #{entry_id} сохранена в портфель{conf_note}\n\n"
                f"📌 {asset} ({asset_type})\n"
                f"Кол-во: {_fmt(float(quantity))}\n"
                f"Цена: {_fmt(float(price))} {currency}\n"
                f"Сумма: {_fmt(total)} {currency}\n"
                f"Биржа: {exchange or '—'}\n"
                f"Дата: {date}\n\n"
                f"Проверь: /portfolio"
            )
        else:
            # Продажа — ищем активную позицию
            positions = await db.get_portfolio()
            matching = [p for p in positions if p["asset"] == asset]

            if matching:
                # Закрываем последнюю позицию по этому активу
                entry = matching[0]
                await db.close_portfolio_entry(entry["id"], float(price), date)
                buy_total = entry["quantity"] * entry["buy_price"]
                sell_total = float(quantity) * float(price)
                pnl = sell_total - buy_total
                sign = "+" if pnl >= 0 else ""
                await message.answer(
                    f"{'🟢' if pnl >= 0 else '🔴'} Продажа #{entry['id']} зафиксирована{conf_note}\n\n"
                    f"📌 {asset} × {_fmt(float(quantity))}\n"
                    f"Куплено: {_fmt(entry['buy_price'])} → Продано: {_fmt(float(price))} {currency}\n"
                    f"P&L: {sign}{_fmt(pnl)} {currency}"
                )
            else:
                await message.answer(
                    f"Вижу продажу {asset}, но в портфеле нет активной позиции по этому активу.\n"
                    f"Если нужно — добавь покупку: `/buy {asset} {quantity} ЦЕНА БИРЖА`",
                    parse_mode="Markdown"
                )

    # ─── Не сделка ───
    else:
        text = parsed.get("text", raw)
        await message.answer(text)
