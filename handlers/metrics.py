"""
Модуль 5 — Трекер метрик.
Ежедневная фиксация показателей. Данные включаются в еженедельный брифинг.
Команды: /m, /stats, /pushups.

Два режима ввода:
  /m продажи=2, подписчики=15, отжимания=50   — быстрый, одной строкой
  /m                                           — пошаговая FSM-форма
"""
from datetime import date, datetime, timedelta

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db

router = Router()

# Дата старта челленджа отжиманий (из ТЗ: 25.10.2025)
PUSHUP_CHALLENGE_START = date(2025, 10, 25)

# Маппинг русских названий → поля в БД
FIELD_MAP = {
    "продажи": "grafin_sales",
    "подписчики": "grafin_subscribers",
    "клики": "ad_clicks",
    "расходы": "ad_spend",
    "отжимания": "pushups",
    "задачи": "tasks_done",
}


# --- Быстрый ввод одной строкой ---

def _parse_inline_metrics(text: str) -> dict:
    """Разобрать строку вида 'продажи=2, подписчики=15'."""
    result = {}
    for part in text.split(","):
        part = part.strip()
        if "=" not in part:
            continue
        key, val = part.split("=", 1)
        key = key.strip().lower()
        val = val.strip()
        db_field = FIELD_MAP.get(key)
        if db_field:
            try:
                result[db_field] = float(val) if "." in val else int(val)
            except ValueError:
                pass
    return result


# --- FSM для пошагового ввода ---

class MetricsForm(StatesGroup):
    grafin_sales = State()
    grafin_subscribers = State()
    ad_clicks = State()
    ad_spend = State()
    pushups = State()


def _safe_int(text: str | None) -> int:
    try:
        return int(text.strip()) if text else 0
    except (ValueError, AttributeError):
        return 0


def _safe_float(text: str | None) -> float:
    try:
        return float(text.strip()) if text else 0.0
    except (ValueError, AttributeError):
        return 0.0


@router.message(Command("m"))
async def cmd_metrics(message: types.Message, state: FSMContext):
    """Ввод метрик: быстрый или пошаговый."""
    args = message.text.replace("/m", "").strip()

    # Быстрый режим: /m продажи=2, отжимания=50
    if "=" in args:
        parsed = _parse_inline_metrics(args)
        if not parsed:
            await message.answer(
                "Не распознал. Пример:\n"
                "/m продажи=2, подписчики=15, отжимания=50"
            )
            return
        today = date.today().isoformat()
        await db.save_metrics(today, **parsed)
        summary = ", ".join(f"{k}: {v}" for k, v in parsed.items())
        await message.answer(f"✅ Метрики за {today}:\n{summary}")
        return

    # Пошаговый режим
    await state.set_state(MetricsForm.grafin_sales)
    day_num = _challenge_day()
    day_str = f" (день {day_num} челленджа)" if day_num else ""
    await message.answer(
        f"📊 Метрики за сегодня{day_str}.\n\n"
        "Графин — продажи за день (число, 0 если нет):"
    )


@router.message(MetricsForm.grafin_sales)
async def step_sales(message: types.Message, state: FSMContext):
    await state.update_data(grafin_sales=_safe_int(message.text))
    await state.set_state(MetricsForm.grafin_subscribers)
    await message.answer("Графин — новые подписчики бота:")


@router.message(MetricsForm.grafin_subscribers)
async def step_subs(message: types.Message, state: FSMContext):
    await state.update_data(grafin_subscribers=_safe_int(message.text))
    await state.set_state(MetricsForm.ad_clicks)
    await message.answer("Реклама — клики:")


@router.message(MetricsForm.ad_clicks)
async def step_clicks(message: types.Message, state: FSMContext):
    await state.update_data(ad_clicks=_safe_int(message.text))
    await state.set_state(MetricsForm.ad_spend)
    await message.answer("Реклама — расходы (EUR):")


@router.message(MetricsForm.ad_spend)
async def step_spend(message: types.Message, state: FSMContext):
    await state.update_data(ad_spend=_safe_float(message.text))
    await state.set_state(MetricsForm.pushups)
    day_num = _challenge_day()
    day_str = f" (день {day_num})" if day_num else ""
    await message.answer(f"Отжимания сегодня{day_str}:")


@router.message(MetricsForm.pushups)
async def step_pushups(message: types.Message, state: FSMContext):
    data = await state.get_data()
    data["pushups"] = _safe_int(message.text)
    today = date.today().isoformat()
    await db.save_metrics(today, **data)
    await state.clear()

    # Формируем итог
    lines = [
        f"✅ Метрики за {today} сохранены!\n",
        f"Графин: {data['grafin_sales']} продаж, {data['grafin_subscribers']} подп.",
        f"Реклама: {data['ad_clicks']} кликов, {data['ad_spend']} EUR",
        f"Отжимания: {data['pushups']}",
    ]

    day_num = _challenge_day()
    if day_num and data["pushups"] > 0:
        lines.append(f"\n💪 День {day_num} челленджа — {data['pushups']} отжиманий!")

    await message.answer("\n".join(lines))


# --- /stats ---

@router.message(Command("stats"))
async def cmd_stats(message: types.Message):
    """
    /stats — за неделю.
    /stats месяц — за 30 дней.
    """
    args = message.text.replace("/stats", "").strip().lower()
    days = 30 if "месяц" in args else 7
    rows = await db.get_metrics(days=days)

    if not rows:
        await message.answer("Нет данных. Начни вносить через /m")
        return

    # Суммы
    total_sales = sum(r["grafin_sales"] or 0 for r in rows)
    total_subs = sum(r["grafin_subscribers"] or 0 for r in rows)
    total_spend = sum(r["ad_spend"] or 0 for r in rows)
    total_pushups = sum(r["pushups"] or 0 for r in rows)
    total_clicks = sum(r["ad_clicks"] or 0 for r in rows)
    days_with_data = len(rows)

    lines = [f"📊 **Метрики за {days} дней** ({days_with_data} дней с данными)\n"]

    # Таблица по дням
    for r in rows:
        d = r["date"]
        lines.append(
            f"`{d}` | 💰{r['grafin_sales'] or 0} "
            f"👥{r['grafin_subscribers'] or 0} "
            f"🖱{r['ad_clicks'] or 0} "
            f"💸{r['ad_spend'] or 0}€ "
            f"💪{r['pushups'] or 0}"
        )

    # Итоги
    lines.append(f"\n**Итого:**")
    lines.append(f"Продажи: {total_sales} | Подписчики: +{total_subs}")
    lines.append(f"Реклама: {total_clicks} кликов, {total_spend:.1f} EUR")
    if total_sales > 0 and total_spend > 0:
        cpa = total_spend / total_sales
        lines.append(f"CPA: {cpa:.1f} EUR/продажа")
    lines.append(f"Отжимания: {total_pushups}")

    # Челлендж
    day_num = _challenge_day()
    if day_num:
        lines.append(f"\n💪 Челлендж: день {day_num}")

    await message.answer("\n".join(lines), parse_mode="Markdown")


# --- /pushups (быстрый ввод только отжиманий) ---

@router.message(Command("pushups"))
async def cmd_pushups(message: types.Message):
    """Быстро записать отжимания: /pushups 50."""
    args = message.text.replace("/pushups", "").strip()
    if not args or not args.isdigit():
        await message.answer("Укажи количество: /pushups 50")
        return

    count = int(args)
    today = date.today().isoformat()
    await db.save_metrics(today, pushups=count)

    day_num = _challenge_day()
    day_str = f" (день {day_num})" if day_num else ""
    await message.answer(f"💪 {count} отжиманий записано{day_str}!")


# --- Утилиты ---

def _challenge_day() -> int | None:
    """Номер дня челленджа отжиманий (с 25.10.2025). None если ещё не начался."""
    today = date.today()
    if today >= PUSHUP_CHALLENGE_START:
        return (today - PUSHUP_CHALLENGE_START).days + 1
    return None


async def get_weekly_metrics_summary() -> str:
    """Сводка метрик за неделю для брифинга. Вызывается из scheduler."""
    rows = await db.get_metrics(days=7)
    if not rows:
        return "Метрики за неделю не вносились."

    total_sales = sum(r["grafin_sales"] or 0 for r in rows)
    total_subs = sum(r["grafin_subscribers"] or 0 for r in rows)
    total_spend = sum(r["ad_spend"] or 0 for r in rows)
    total_pushups = sum(r["pushups"] or 0 for r in rows)

    lines = [
        f"Продажи Графин: {total_sales}",
        f"Новые подписчики: +{total_subs}",
        f"Расходы на рекламу: {total_spend:.1f} EUR",
        f"Отжимания: {total_pushups}",
    ]
    if total_sales > 0 and total_spend > 0:
        lines.append(f"CPA: {total_spend / total_sales:.1f} EUR")

    return "\n".join(lines)
