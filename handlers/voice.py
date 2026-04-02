"""
Голосовые сообщения и единый роутер сообщений.

Архитектура:
  Whisper → локальный классификатор (0 токенов, ~70% случаев)
          → Claude Haiku intent-router (~$0.001, ~25% случаев)
          → Claude Sonnet ответ (~$0.01, ~5% случаев — только если нужен ответ)
"""
import os
import tempfile
import logging

from aiogram import Router, types, F

from services.whisper_api import transcribe
from services.classifier import classify_local
from services.claude_api import classify_message, ask_claude, structure_entry
import database as db

router = Router()
logger = logging.getLogger(__name__)


@router.message(F.voice)
async def handle_voice(message: types.Message):
    """Голос -> Whisper -> классификация -> действие."""
    voice = message.voice
    duration = voice.duration or 0

    if duration < 1:
        await message.answer("Слишком короткое сообщение, попробуй ещё раз.")
        return

    await message.answer("🎙 Слушаю...")

    file = await message.bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
        await message.bot.download_file(file.file_path, destination=tmp_path)

    try:
        text = await transcribe(tmp_path, duration_sec=duration)
        if not text:
            await message.answer("Не удалось распознать речь. Попробуй ещё раз.")
            return
        logger.info("Голос (%d сек): %s", duration, text[:80])
        await route_message(message, text, is_voice=True)
    finally:
        os.unlink(tmp_path)


async def route_message(message: types.Message, text: str, is_voice: bool = False):
    """
    Единый роутер. Голос или текст — не важно.
    Определяет intent и вызывает нужный обработчик.
    """
    prefix = f"🎙 _{text}_\n\n" if is_voice else ""

    # ── 1. Локальный классификатор (0 токенов) ──
    local = classify_local(text)

    if local and local["source"] == "local":
        handled = await _dispatch_intent(message, local["type"], local, text, prefix)
        if handled:
            return

    # ── 2. Claude Haiku — определить intent ──
    classified = await classify_message(text)
    intent = classified.get("intent") or classified.get("type", "chat")
    handled = await _dispatch_intent(message, intent, classified, text, prefix)
    if not handled:
        # Fallback: Sonnet отвечает как ассистент
        response = await ask_claude(text, tier="sonnet", use_history=True)
        await message.answer(f"{prefix}{response}", parse_mode="Markdown")


def _hashtag(project: str | None) -> str:
    """Хэштег проекта для поиска в Telegram."""
    if not project:
        return ""
    tag = project.replace(" ", "_").replace("-", "_")
    return f"\n\n#{tag}"


async def _dispatch_intent(
    message: types.Message,
    intent: str,
    data: dict,
    raw_text: str,
    prefix: str,
) -> bool:
    """
    Диспетчер интентов. Возвращает True если обработан.
    """
    project = data.get("project")
    text = data.get("text", raw_text)
    tag = _hashtag(project)

    # ── Показать задачи ──
    if intent == "show_tasks":
        from handlers.tasks import _format_tasks
        tasks = await db.get_active_tasks(project=project)
        if not tasks:
            p_note = f" по проекту {project}" if project else ""
            await message.answer(f"{prefix}✅ Активных задач{p_note} нет.")
        else:
            msg = await _format_tasks(tasks)
            await message.answer(f"{prefix}{msg}", parse_mode="Markdown")
        return True

    # ── Показать идеи ──
    if intent == "show_ideas":
        ideas = await db.get_ideas(project=project)
        if not ideas:
            await message.answer(f"{prefix}Идей пока нет.")
        else:
            lines = [f"💡 *Идеи ({len(ideas)}):*\n"]
            for i in ideas[:10]:
                lines.append(f"#{i['id']} {i['text'][:70]}")
            await message.answer(f"{prefix}" + "\n".join(lines), parse_mode="Markdown")
        return True

    # ── Показать проекты ──
    if intent == "show_projects":
        projects = await db.get_projects()
        if project:
            # Конкретный проект — показать summary
            from handlers.projects import _project_summary
            await _project_summary(message, project, prefix)
        elif not projects:
            await message.answer(f"{prefix}Проектов нет. Добавить: /new название")
        else:
            lines = [f"📁 *Проекты ({len(projects)}):*\n"]
            for p in projects:
                lines.append(f"• *{p['name']}* — {p['status']}")
            await message.answer(f"{prefix}" + "\n".join(lines), parse_mode="Markdown")
        return True

    # ── Портфель ──
    if intent == "portfolio":
        from handlers.portfolio import cmd_portfolio
        await cmd_portfolio(message)
        return True

    # ── P&L ──
    if intent == "pnl":
        from handlers.portfolio import cmd_pnl
        await cmd_pnl(message)
        return True

    # ── Купить актив ──
    if intent == "buy_asset":
        # Парсим "BTC 0.001 69000 Bybit" из text
        parts = text.strip().split()
        if len(parts) >= 2:
            fake_msg = message.model_copy(update={"text": f"/buy {text}"})
            from handlers.portfolio import cmd_buy
            await cmd_buy(fake_msg)
        else:
            await message.answer(
                f"{prefix}Уточни детали покупки:\n"
                f"Актив, количество, цена, биржа.\n"
                f"Например: _«купил BTC 0.001 по 69000 на Bybit»_",
                parse_mode="Markdown"
            )
        return True

    # ── Брифинг ──
    if intent == "briefing":
        await message.answer(f"{prefix}📋 Генерирую брифинг...")
        from handlers.briefing import generate_briefing
        briefing = await generate_briefing()
        if len(briefing) > 4000:
            await message.answer(briefing[:4000], parse_mode="Markdown")
            await message.answer(briefing[4000:], parse_mode="Markdown")
        else:
            await message.answer(briefing, parse_mode="Markdown")
        return True

    # ── Дайджест ──
    if intent == "digest":
        from handlers.digest import generate_digest
        digest = await generate_digest()
        await message.answer(f"{prefix}{digest}", parse_mode="Markdown")
        return True

    # ── Расходы ──
    if intent == "cost":
        cost_7d = await db.get_total_cost(days=7)
        cost_30d = await db.get_total_cost(days=30)
        await message.answer(
            f"{prefix}💰 *Расходы на AI:*\n"
            f"За 7 дней: ${cost_7d:.3f}\n"
            f"За 30 дней: ${cost_30d:.3f}",
            parse_mode="Markdown"
        )
        return True

    # ── Метрики / статистика ──
    if intent == "metrics":
        from handlers.metrics import cmd_stats
        await cmd_stats(message)
        return True

    # ── English — повторение ──
    if intent == "english_review":
        from handlers.english import cmd_review
        await cmd_review(message)
        return True

    # ── English — тест ──
    if intent == "english_test":
        from handlers.english import cmd_test
        await cmd_test(message)
        return True

    # ── English — общее ──
    if intent == "english":
        from handlers.english import handle_english_voice
        await handle_english_voice(message, raw_text, prefix)
        return True

    # ── Отжимания / метрики ──
    if intent == "pushups":
        from datetime import date
        count = data.get("value", 0)
        today = date.today().isoformat()
        await db.save_metrics(today, pushups=count)
        await db.log_action("add", "metrics", 0, f"pushups={count}")
        # Сохранить в историю чата (чтобы агент помнил контекст)
        await db.save_message("user", raw_text)
        await db.save_message("assistant", f"Записал {count} отжиманий")
        from handlers.metrics import _challenge_day
        day_num = _challenge_day()
        day_str = f" (день {day_num})" if day_num else ""
        await message.answer(f"{prefix}💪 {count} отжиманий записано{day_str}!", parse_mode="Markdown")
        return True

    # ── Выполнить задачу ──
    if intent == "done_task":
        task_text = data.get("task_text", text)
        # Попробовать найти по тексту
        task = await db.complete_task_by_text(task_text)
        if task:
            await message.answer(f"{prefix}✅ Задача закрыта: {task['text']}")
        else:
            # Не нашли — показать список
            tasks = await db.get_active_tasks()
            if tasks:
                lines = ["Не нашёл такую задачу. Активные:\n"]
                for t in tasks[:8]:
                    lines.append(f"#{t['id']} {t['text'][:60]}")
                lines.append("\nСкажи: _«закрыть задачу 3»_")
                await message.answer(f"{prefix}" + "\n".join(lines), parse_mode="Markdown")
            else:
                await message.answer(f"{prefix}Активных задач нет.")
        return True

    # ── Поиск ──
    if intent == "search":
        from handlers.search import assistant_search
        await message.answer(f"{prefix}🔍 Ищу...", parse_mode="Markdown")
        result = await assistant_search(raw_text)
        await message.answer(result)
        return True

    # ── Привязка к проекту ──
    if intent == "note" and project:
        await _save_to_project(message, raw_text, data, prefix)
        return True
    if data.get("project_name_raw"):
        await _save_to_project(message, raw_text, data, prefix)
        return True

    # ── Задача ──
    if intent == "task":
        task_text = text or raw_text
        task_id = await db.add_task(task_text, project)
        await db.log_action("add", "tasks", task_id)
        await db.save_message("user", raw_text)
        await db.save_message("assistant", f"Задача #{task_id}: {task_text}")
        await message.answer(f"{prefix}✅ Задача #{task_id}: {task_text}{tag}", parse_mode="Markdown")
        return True

    # ── Идея ──
    if intent == "idea":
        idea_text = text or raw_text
        idea_id = await db.add_idea(idea_text, project)
        await db.log_action("add", "ideas", idea_id)
        await db.save_message("user", raw_text)
        await db.save_message("assistant", f"Идея #{idea_id}: {idea_text}")
        await message.answer(f"{prefix}💡 Идея #{idea_id}: {idea_text}{tag}", parse_mode="Markdown")
        return True

    # ── Вопрос — сразу Sonnet ──
    if intent == "question":
        await db.save_message("user", raw_text)
        response = await ask_claude(raw_text, tier="sonnet", use_history=True)
        await db.save_message("assistant", response)
        await message.answer(f"{prefix}{response}{tag}", parse_mode="Markdown")
        return True

    return False  # не обработано


async def _save_to_project(message: types.Message, raw_text: str, local: dict, prefix: str):
    """Сохранить запись в проект."""
    project_name = local.get("project_name_raw") or local.get("project") or ""
    if not project_name:
        return

    project = await db.get_project_by_name(project_name)
    if not project:
        pid = await db.create_project(project_name)
        project = {"id": pid, "name": project_name}

    structured = await structure_entry(raw_text)
    entry_type = structured.get("type", "idea")
    entry_text = structured.get("text", local.get("text", raw_text))

    await db.add_project_entry(project["id"], entry_type, raw_text, entry_text)
    tag = _hashtag(project["name"])
    await message.answer(
        f"{prefix}📁 [{entry_type.upper()}] → *{project['name']}*: {entry_text}{tag}",
        parse_mode="Markdown",
    )
