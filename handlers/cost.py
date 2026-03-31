"""Трекер расходов на AI-сервисы."""
from aiogram import Router, types
from aiogram.filters import Command

import database as db

router = Router()

EUR_PER_USD = 0.92  # примерный курс, обновлять в config при необходимости


@router.message(Command("cost"))
async def cmd_cost(message: types.Message):
    """Показать расходы на API за текущий месяц."""
    cost_7d = await db.get_total_cost(days=7)
    cost_30d = await db.get_total_cost(days=30)

    usage = await db.get_token_usage(days=7)

    # Сводка по моделям за неделю
    by_model: dict[str, dict] = {}
    for row in usage:
        m = row["model"]
        if m not in by_model:
            by_model[m] = {"calls": 0, "cost": 0.0, "input": 0, "output": 0}
        by_model[m]["calls"] += row["calls"]
        by_model[m]["cost"] += row["cost_usd"]
        by_model[m]["input"] += row["input_tokens"]
        by_model[m]["output"] += row["output_tokens"]

    lines = [
        "💰 **Расходы на AI:**\n",
        f"За 7 дней: **${cost_7d:.2f}** (~{cost_7d * EUR_PER_USD:.2f} EUR)",
        f"За 30 дней: **${cost_30d:.2f}** (~{cost_30d * EUR_PER_USD:.2f} EUR)\n",
    ]

    if by_model:
        lines.append("**По моделям (7 дней):**")
        for model, data in by_model.items():
            lines.append(
                f"  {model}: {data['calls']} вызовов, "
                f"{data['input'] + data['output']} токенов, "
                f"${data['cost']:.3f}"
            )

    # Прогноз на месяц
    if cost_7d > 0:
        projected = cost_7d * 4.3
        lines.append(f"\n📊 Прогноз на месяц: ~${projected:.2f} (~{projected * EUR_PER_USD:.2f} EUR)")

    await message.answer("\n".join(lines), parse_mode="Markdown")
