"""
Голосовые сообщения: Whisper -> локальный классификатор -> роутинг.
Claude вызывается только если regex не справился.
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

    # Отсечка тишины
    if duration < 1:
        await message.answer("Слишком короткое сообщение, попробуй ещё раз.")
        return

    await message.answer("🎙 Слушаю...")

    # Скачать файл
    file = await message.bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
        await message.bot.download_file(file.file_path, destination=tmp_path)

    try:
        # Транскрибация
        text = await transcribe(tmp_path, duration_sec=duration)
        if not text:
            await message.answer("Не удалось распознать речь. Попробуй ещё раз.")
            return

        logger.info("Голос (%d сек): %s", duration, text[:80])

        # Роутинг через общую функцию
        await route_message(message, text, is_voice=True)
    finally:
        os.unlink(tmp_path)


async def route_message(message: types.Message, text: str, is_voice: bool = False):
    """
    Единый роутер для текста (после транскрибации или напрямую).
    Порядок: локальный классификатор -> Claude (если нужно).
    """
    prefix = f"🎙 _{text}_\n\n" if is_voice else ""

    # 1. Локальная классификация (бесплатно)
    local = classify_local(text)

    if local and local["source"] == "local":
        msg_type = local["type"]

        # Отжимания / метрики
        if msg_type == "pushups":
            from datetime import date
            count = local["value"]
            today = date.today().isoformat()
            await db.save_metrics(today, pushups=count)
            # День челленджа
            from handlers.metrics import _challenge_day
            day_num = _challenge_day()
            day_str = f" (день {day_num})" if day_num else ""
            await message.answer(f"{prefix}💪 {count} отжиманий записано{day_str}!", parse_mode="Markdown")
            return

        # Поиск
        if msg_type == "search":
            from handlers.search import assistant_search
            await message.answer(f"{prefix}🔍 Ищу...", parse_mode="Markdown")
            result = await assistant_search(text)
            await message.answer(result)
            return

        # Привязка к проекту
        if local.get("project_name_raw"):
            await _save_to_project(message, text, local, prefix)
            return

        # Задача
        if msg_type == "task":
            task_id = await db.add_task(local["text"], local.get("project"))
            await message.answer(f"{prefix}✅ Задача #{task_id}: {local['text']}", parse_mode="Markdown")
            return

        # Идея
        if msg_type == "idea":
            idea_id = await db.add_idea(local["text"], local.get("project"))
            await message.answer(f"{prefix}💡 Идея #{idea_id}: {local['text']}", parse_mode="Markdown")
            return

        # Вопрос — сразу Claude Sonnet (пропускаем классификацию Haiku)
        if msg_type == "question":
            response = await ask_claude(text, tier="sonnet", use_history=True)
            await message.answer(f"{prefix}{response}", parse_mode="Markdown")
            return

    # 2. Локальный не справился — Claude Haiku классифицирует
    classified = await classify_message(text)
    msg_type = classified.get("type", "note")
    project = classified.get("project")
    summary = classified.get("text", text)

    if msg_type == "task":
        task_id = await db.add_task(summary, project)
        await message.answer(f"{prefix}✅ Задача #{task_id}: {summary}", parse_mode="Markdown")
    elif msg_type == "idea":
        idea_id = await db.add_idea(summary, project)
        await message.answer(f"{prefix}💡 Идея #{idea_id}: {summary}", parse_mode="Markdown")
    else:
        # Вопрос или заметка — Claude Sonnet отвечает
        response = await ask_claude(text, tier="sonnet", use_history=True)
        await message.answer(f"{prefix}{response}", parse_mode="Markdown")


async def _save_to_project(message: types.Message, raw_text: str, local: dict, prefix: str):
    """Сохранить запись в проект."""
    project_name = local["project_name_raw"]

    project = await db.get_project_by_name(project_name)
    if not project:
        pid = await db.create_project(project_name)
        project = {"id": pid, "name": project_name}

    # Структурируем через Haiku (дёшево)
    structured = await structure_entry(raw_text)
    entry_type = structured.get("type", "idea")
    entry_text = structured.get("text", local["text"])

    await db.add_project_entry(project["id"], entry_type, raw_text, entry_text)
    await message.answer(
        f"{prefix}📁 [{entry_type.upper()}] -> **{project['name']}**: {entry_text}",
        parse_mode="Markdown",
    )
