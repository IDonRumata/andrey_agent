"""
Инвестиционный дневник.
/buy  — записать покупку актива
/sell — зафиксировать продажу
/portfolio (/p) — текущие позиции с актуальными ценами
/pnl — реализованная прибыль по закрытым сделкам
"""
import logging
from datetime import datetime

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import database as db
from services.prices import get_price, detect_asset_type, CRYPTO_TICKERS

router = Router()
logger = logging.getLogger(__name__)

HELP_BUY = (
    "Формат:\n"
    "/buy BTC 0.001 69000 Bybit\n"
    "/buy BTC 0.001 Bybit   — цену подтяну сам\n"
    "/buy SBER 10 280 FF    — акция, 10 шт по 280\n\n"
    "Параметры: актив, кол-во, [цена], [биржа]"
)

HELP_SELL = (
    "Формат:\n"
    "/sell 3         — продать позицию #3 по текущей цене\n"
    "/sell 3 71000   — продать позицию #3 по указанной цене\n\n"
    "Номер позиции смотри в /portfolio"
)


def _fmt_num(n: float) -> str:
    """Форматировать число: убрать лишние нули."""
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:,.6g}"


def _pnl_emoji(pct: float) -> str:
    if pct >= 10:
        return "🚀"
    if pct > 0:
        return "🟢"
    if pct == 0:
        return "⚪️"
    if pct > -10:
        return "🔴"
    return "💥"


# ─────────────────────── /buy ───────────────────────

@router.message(Command("buy"))
async def cmd_buy(message: Message):
    args = (message.text or "").split()[1:]  # всё после /buy

    if len(args) < 2:
        await message.answer(HELP_BUY)
        return

    asset = args[0].upper()
    try:
        quantity = float(args[1].replace(",", "."))
    except ValueError:
        await message.answer(f"Не понял количество: `{args[1]}`\n\n{HELP_BUY}", parse_mode="Markdown")
        return

    # Разбираем оставшиеся аргументы
    buy_price = None
    exchange = ""
    if len(args) >= 3:
        try:
            buy_price = float(args[2].replace(",", "."))
            exchange = args[3] if len(args) >= 4 else ""
        except ValueError:
            exchange = args[2]  # это биржа, цену подтянем

    asset_type = detect_asset_type(asset)

    # Подтянуть цену если не указана
    if buy_price is None:
        await message.answer(f"Получаю текущую цену {asset}...")
        price, currency = await get_price(asset, asset_type)
        if price is None:
            await message.answer(
                f"Не смог получить цену {asset}. Укажи цену вручную:\n"
                f"`/buy {asset} {quantity} ЦЕНА {exchange}`",
                parse_mode="Markdown"
            )
            return
        buy_price = price
    else:
        ru_stocks = {"SBER", "GAZP", "LKOH", "GMKN", "YNDX", "VTBR", "ROSN", "NVTK", "MGNT", "TATN"}
        if asset_type == "crypto":
            currency = "USD"
        elif asset in ru_stocks:
            currency = "RUB"
        else:
            currency = "USD"

    buy_date = datetime.now().strftime("%Y-%m-%d")
    entry_id = await db.add_portfolio_entry(
        asset=asset,
        asset_type=asset_type,
        exchange=exchange,
        quantity=quantity,
        buy_price=buy_price,
        currency=currency,
        buy_date=buy_date,
    )

    total = quantity * buy_price
    await message.answer(
        f"✅ Записал покупку #{entry_id}\n\n"
        f"📌 {asset} ({asset_type})\n"
        f"Кол-во: {_fmt_num(quantity)}\n"
        f"Цена: {_fmt_num(buy_price)} {currency}\n"
        f"Сумма: {_fmt_num(total)} {currency}\n"
        f"Биржа: {exchange or '—'}\n"
        f"Дата: {buy_date}"
    )


# ─────────────────────── /sell ───────────────────────

@router.message(Command("sell"))
async def cmd_sell(message: Message):
    args = (message.text or "").split()[1:]

    if not args:
        await message.answer(HELP_SELL)
        return

    try:
        entry_id = int(args[0])
    except ValueError:
        await message.answer(f"Укажи номер позиции из /portfolio\n\n{HELP_SELL}")
        return

    entry = await db.get_portfolio_entry(entry_id)
    if not entry:
        await message.answer(f"Позиция #{entry_id} не найдена или уже закрыта.")
        return

    # Цена продажи
    sell_price = None
    if len(args) >= 2:
        try:
            sell_price = float(args[1].replace(",", "."))
        except ValueError:
            pass

    if sell_price is None:
        await message.answer(f"Получаю текущую цену {entry['asset']}...")
        price, _ = await get_price(entry["asset"], entry["asset_type"])
        if price is None:
            await message.answer(
                f"Не смог получить цену. Укажи вручную:\n`/sell {entry_id} ЦЕНА`",
                parse_mode="Markdown"
            )
            return
        sell_price = price

    sell_date = datetime.now().strftime("%Y-%m-%d")
    await db.close_portfolio_entry(entry_id, sell_price, sell_date)

    buy_total = entry["quantity"] * entry["buy_price"]
    sell_total = entry["quantity"] * sell_price
    pnl = sell_total - buy_total
    pnl_pct = (pnl / buy_total * 100) if buy_total else 0
    cur = entry["currency"]

    sign = "+" if pnl >= 0 else ""
    await message.answer(
        f"{'🟢' if pnl >= 0 else '🔴'} Продажа зафиксирована\n\n"
        f"📌 {entry['asset']} × {_fmt_num(entry['quantity'])}\n"
        f"Куплено: {_fmt_num(entry['buy_price'])} {cur} → {_fmt_num(buy_total)} {cur}\n"
        f"Продано: {_fmt_num(sell_price)} {cur} → {_fmt_num(sell_total)} {cur}\n"
        f"P&L: {sign}{_fmt_num(pnl)} {cur} ({sign}{pnl_pct:.1f}%)"
    )


# ─────────────────────── /portfolio ───────────────────────

@router.message(Command("portfolio", "p"))
async def cmd_portfolio(message: Message):
    positions = await db.get_portfolio()
    if not positions:
        await message.answer(
            "Портфель пустой.\n\nДобавь позицию:\n`/buy BTC 0.001 69000 Bybit`",
            parse_mode="Markdown"
        )
        return

    await message.answer("Загружаю цены, секунду...")

    lines = [f"💼 <b>Портфель</b> — {datetime.now().strftime('%d.%m.%Y')}\n"]
    total_invested = {}   # currency → sum
    total_current = {}    # currency → sum

    for pos in positions:
        asset = pos["asset"]
        qty = pos["quantity"]
        buy_p = pos["buy_price"]
        cur = pos["currency"]
        atype = pos["asset_type"]
        exchange = pos["exchange"] or "—"

        # Текущая цена
        cur_price, _ = await get_price(asset, atype)

        invested = qty * buy_p
        total_invested[cur] = total_invested.get(cur, 0) + invested

        if cur_price:
            current = qty * cur_price
            pnl = current - invested
            pnl_pct = (pnl / invested * 100) if invested else 0
            sign = "+" if pnl >= 0 else ""
            total_current[cur] = total_current.get(cur, 0) + current

            emoji = _pnl_emoji(pnl_pct)
            lines.append(
                f"{emoji} <b>#{pos['id']} {asset}</b> × {_fmt_num(qty)}\n"
                f"   Куплено: {_fmt_num(buy_p)} → Сейчас: {_fmt_num(cur_price)} {cur}\n"
                f"   P&amp;L: {sign}{_fmt_num(pnl)} {cur} ({sign}{pnl_pct:.1f}%)\n"
                f"   📍 {exchange} · {pos['buy_date']}"
            )
        else:
            lines.append(
                f"⚪️ <b>#{pos['id']} {asset}</b> × {_fmt_num(qty)}\n"
                f"   Куплено: {_fmt_num(buy_p)} {cur} · цена недоступна\n"
                f"   📍 {exchange} · {pos['buy_date']}"
            )
        lines.append("")

    # Итог
    for cur in total_invested:
        inv = total_invested[cur]
        cur_val = total_current.get(cur)
        if cur_val:
            pnl = cur_val - inv
            pnl_pct = (pnl / inv * 100) if inv else 0
            sign = "+" if pnl >= 0 else ""
            emoji = _pnl_emoji(pnl_pct)
            lines.append(
                f"{'─' * 20}\n"
                f"💰 Вложено: {_fmt_num(inv)} {cur}\n"
                f"📈 Сейчас:  {_fmt_num(cur_val)} {cur}\n"
                f"{emoji} Итого P&amp;L: {sign}{_fmt_num(pnl)} {cur} ({sign}{pnl_pct:.1f}%)"
            )

    await message.answer("\n".join(lines), parse_mode="HTML")


# ─────────────────────── /pnl ───────────────────────

@router.message(Command("pnl"))
async def cmd_pnl(message: Message):
    history = await db.get_portfolio_history()
    if not history:
        await message.answer("Закрытых сделок пока нет.")
        return

    lines = ["📊 <b>Реализованный P&amp;L</b>\n"]
    totals: dict[str, float] = {}

    for pos in history:
        if not pos.get("sell_price"):
            continue
        qty = pos["quantity"]
        buy_total = qty * pos["buy_price"]
        sell_total = qty * pos["sell_price"]
        pnl = sell_total - buy_total
        pnl_pct = (pnl / buy_total * 100) if buy_total else 0
        cur = pos["currency"]
        totals[cur] = totals.get(cur, 0) + pnl
        sign = "+" if pnl >= 0 else ""
        emoji = _pnl_emoji(pnl_pct)
        lines.append(
            f"{emoji} <b>#{pos['id']} {pos['asset']}</b> × {_fmt_num(qty)}\n"
            f"   {_fmt_num(pos['buy_price'])} → {_fmt_num(pos['sell_price'])} {cur}\n"
            f"   {sign}{_fmt_num(pnl)} {cur} ({sign}{pnl_pct:.1f}%)"
            f"   · закрыто {pos['sell_date']}"
        )

    lines.append("")
    for cur, total in totals.items():
        sign = "+" if total >= 0 else ""
        emoji = "🟢" if total >= 0 else "🔴"
        lines.append(f"{emoji} Итого {cur}: {sign}{_fmt_num(total)}")

    await message.answer("\n".join(lines), parse_mode="HTML")
