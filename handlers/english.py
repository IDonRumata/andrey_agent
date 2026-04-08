"""
English module — A1→B1 для Андрея.
Учебник: Outcomes Elementary (Cengage / NGL).

Команды:
  /en           — главное меню (inline)
  /en_start     — placement test (входная оценка уровня)
  /en_unit N    — установить текущий юнит (синхронизация с учителем)
  /en_block     — пройти блок упражнений (~10 мин)
  /en_review    — повторение SRS
  /en_speak     — speaking practice (свободная речь, оценка)
  /en_lesson    — отчёт с живого занятия
  /en_homework  — мои ДЗ
  /en_progress  — прогресс и стата
  /en_voice     — переключить голос TTS
  /en_grammar тема — справка по грамматике из БД
  /vocab слово  — добавить/найти слово (legacy совместимость)

Все занятия — в формате "текст + голос" (TTS из БД, без LLM-вызова).
"""
import json
import logging
import random

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import config
import database as db
from services.claude_api import ask_claude
from services.english import assessment, curriculum, exercises, lesson_parser, speaking_eval, srs
from services.english.tts import synthesize
from services.whisper_api import transcribe

router = Router()
logger = logging.getLogger(__name__)


# ─────────────────── FSM states ───────────────────

class PlacementFSM(StatesGroup):
    vocab = State()
    grammar = State()
    speaking = State()


class BlockFSM(StatesGroup):
    in_progress = State()


class LessonFSM(StatesGroup):
    awaiting_report = State()


class SpeakFSM(StatesGroup):
    awaiting_audio = State()


# ─────────────────── Утилиты ───────────────────

def _uid(message_or_cb) -> int:
    if isinstance(message_or_cb, CallbackQuery):
        return message_or_cb.from_user.id
    return message_or_cb.from_user.id


async def _send_with_audio(message: Message, text: str, voice_text: str | None = None,
                            second: bool = False, kb: InlineKeyboardMarkup | None = None):
    """Отправить текст + озвучку (всегда оба, как договорились)."""
    await message.answer(text, parse_mode="Markdown", reply_markup=kb)
    try:
        audio_path = await synthesize(voice_text or _strip_markdown(text), second=second)
        audio = BufferedInputFile(audio_path.read_bytes(), filename="en.ogg")
        await message.answer_voice(audio)
    except Exception as e:
        logger.warning("TTS failed: %s", e)


def _strip_markdown(text: str) -> str:
    return text.replace("*", "").replace("_", "").replace("`", "").replace("«", "").replace("»", "")


# ─────────────────── Главное меню ───────────────────

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Начать блок (10 мин)", callback_data="en:block")],
        [InlineKeyboardButton(text="🔄 Повторение (SRS)", callback_data="en:review")],
        [InlineKeyboardButton(text="🗣 Speaking practice", callback_data="en:speak")],
        [InlineKeyboardButton(text="🎓 Тест уровня", callback_data="en:start_placement")],
        [InlineKeyboardButton(text="📚 Текущий юнит", callback_data="en:unit_info")],
        [InlineKeyboardButton(text="📝 Отчёт с урока", callback_data="en:lesson")],
        [InlineKeyboardButton(text="📊 Мой прогресс", callback_data="en:progress")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="en:settings")],
    ])


@router.message(Command("en"))
async def cmd_english_menu(message: Message):
    profile = await db.en_get_or_create_profile(message.from_user.id)
    stats = await db.en_full_stats(message.from_user.id)
    unit = await curriculum.get_current_unit(message.from_user.id)
    unit_str = f"Unit {unit['number']} · {unit['title']}" if unit else "Юнит не задан (/en_unit 1)"

    text = (
        f"🇬🇧 *English A1→B1*\n\n"
        f"📚 {unit_str}\n"
        f"🎯 Уровень: *{profile['cefr_level']}*\n"
        f"🔄 На повторение: *{stats['srs']['due_today']}*\n"
        f"✅ Освоено чанков: *{stats['srs']['mastered']}*\n"
        f"🔥 Streak: {profile.get('streak_days', 0)} дн\n\n"
        f"_Контент в БД: {stats['content']['chunks']} чанков, "
        f"{stats['content']['sentences']} предложений, "
        f"{stats['content']['exercises']} упражнений_"
    )
    await message.answer(text, parse_mode="Markdown", reply_markup=main_menu_kb())


@router.callback_query(F.data == "en:menu")
async def cb_menu(cb: CallbackQuery):
    await cmd_english_menu(cb.message)
    await cb.answer()


# ─────────────────── /en_unit ───────────────────

@router.message(Command("en_unit"))
async def cmd_en_unit(message: Message):
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        units = await db.en_list_units()
        if not units:
            await message.answer("База юнитов пустая. Запусти `python -m scripts.ingest_outcomes` на VPS.", parse_mode="Markdown")
            return
        lines = ["📚 *Доступные юниты Outcomes Elementary:*\n"]
        for u in units:
            lines.append(f"{u['number']:>2}. {u['title']} _({u['cefr']})_")
        lines.append("\nУстановить: `/en_unit 3`")
        await message.answer("\n".join(lines), parse_mode="Markdown")
        return

    num = int(parts[1])
    unit = await db.en_get_unit_by_number(num)
    if not unit:
        await message.answer(f"Юнит {num} не найден. Доступны 1..16.")
        return

    await db.en_update_profile(message.from_user.id, current_unit=num)
    # Залить чанки юнита в SRS
    added = await srs.bulk_add_unit_chunks(message.from_user.id, unit["id"], limit=20)
    await message.answer(
        f"✅ Текущий юнит: *Unit {num} — {unit['title']}*\n"
        f"Тема: {unit['topic']}\n"
        f"Добавлено в SRS: *{added}* чанков\n\n"
        f"Готов начать? /en_block",
        parse_mode="Markdown",
    )


# ─────────────────── /en_voice ───────────────────

@router.message(Command("en_voice"))
async def cmd_en_voice(message: Message):
    parts = (message.text or "").split()
    voices = {
        "uk_f": "en-GB-SoniaNeural",
        "uk_m": "en-GB-RyanNeural",
        "us_f": "en-US-AriaNeural",
        "us_m": "en-US-GuyNeural",
    }
    if len(parts) < 2 or parts[1] not in voices:
        await message.answer(
            "Доступные голоса:\n"
            "`/en_voice uk_f` — британский ж (Sonia) — *по умолчанию*\n"
            "`/en_voice uk_m` — британский м (Ryan)\n"
            "`/en_voice us_f` — американский ж (Aria)\n"
            "`/en_voice us_m` — американский м (Guy)",
            parse_mode="Markdown",
        )
        return
    voice = voices[parts[1]]
    await db.en_update_profile(message.from_user.id, tts_voice=voice)
    # Замечание: services/english/tts.py читает config.EN_TTS_VOICE_MAIN. Профиль перезаписывается
    # глобально, потому что у нас один пользователь сейчас. При мультитенантности — читать профиль.
    await message.answer(f"✅ Голос обновлён: `{voice}`\nПерезапусти бота, чтобы применить.", parse_mode="Markdown")


# ─────────────────── /en_start (placement test) ───────────────────

@router.message(Command("en_start"))
async def cmd_en_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🎓 *Placement Test — оценка уровня*\n\n"
        "Три части, ~10 минут:\n"
        "1️⃣ Словарь — 10 слов с inline-кнопками\n"
        "2️⃣ Грамматика — 10 вопросов с вариантами\n"
        "3️⃣ Speaking — 1 голосовой ответ\n\n"
        "Поехали 👇",
        parse_mode="Markdown",
    )

    # Берём 10 слов из placement vocab (рандомно из 25)
    vocab_sample = random.sample(assessment.PLACEMENT_VOCAB, 10)
    await state.update_data(vocab_queue=vocab_sample, vocab_idx=0, vocab_correct=0)
    await state.set_state(PlacementFSM.vocab)
    await _ask_placement_vocab(message, state)


async def _ask_placement_vocab(message: Message, state: FSMContext):
    data = await state.get_data()
    idx = data["vocab_idx"]
    queue = data["vocab_queue"]
    if idx >= len(queue):
        await _start_placement_grammar(message, state)
        return
    word, correct_translation, level = queue[idx]
    # 4 варианта: правильный + 3 случайных из других слов того же уровня
    distractors = [t for w, t, l in assessment.PLACEMENT_VOCAB if w != word]
    options = [correct_translation] + random.sample(distractors, 3)
    random.shuffle(options)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=opt, callback_data=f"plv:{i}")] for i, opt in enumerate(options)
    ] + [[InlineKeyboardButton(text="Не знаю", callback_data="plv:idk")]])

    await state.update_data(current_options=options, current_correct=correct_translation)
    await message.answer(
        f"*{idx + 1}/{len(queue)}*\nКак переводится: *{word}*?",
        parse_mode="Markdown", reply_markup=kb,
    )


@router.callback_query(PlacementFSM.vocab, F.data.startswith("plv:"))
async def cb_placement_vocab(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    payload = cb.data.split(":", 1)[1]
    correct = data["current_correct"]
    if payload == "idk":
        is_correct = False
        chosen = "(не знаю)"
    else:
        idx = int(payload)
        chosen = data["current_options"][idx]
        is_correct = chosen == correct

    feedback = "✅" if is_correct else f"❌ Правильно: *{correct}*"
    await cb.message.edit_text(f"{cb.message.text}\n\nТы выбрал: {chosen}\n{feedback}", parse_mode="Markdown")
    await state.update_data(
        vocab_idx=data["vocab_idx"] + 1,
        vocab_correct=data["vocab_correct"] + (1 if is_correct else 0),
    )
    await cb.answer()
    await _ask_placement_vocab(cb.message, state)


async def _start_placement_grammar(message: Message, state: FSMContext):
    grammar_sample = random.sample(assessment.PLACEMENT_GRAMMAR, 10)
    await state.update_data(gram_queue=grammar_sample, gram_idx=0, gram_correct=0)
    await state.set_state(PlacementFSM.grammar)
    await message.answer("📐 *Часть 2 — Грамматика*", parse_mode="Markdown")
    await _ask_placement_grammar(message, state)


async def _ask_placement_grammar(message: Message, state: FSMContext):
    data = await state.get_data()
    idx = data["gram_idx"]
    queue = data["gram_queue"]
    if idx >= len(queue):
        await _start_placement_speaking(message, state)
        return
    q = queue[idx]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=opt, callback_data=f"plg:{i}")]
        for i, opt in enumerate(q["options"])
    ])
    await state.update_data(current_q=q)
    # HTML mode: grammar questions contain ___ (fill-in blanks) which break Markdown parsing
    await message.answer(
        f"<b>{idx + 1}/{len(queue)}</b>\n{q['q']}", parse_mode="HTML", reply_markup=kb,
    )


@router.callback_query(PlacementFSM.grammar, F.data.startswith("plg:"))
async def cb_placement_grammar(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    q = data["current_q"]
    chosen = q["options"][int(cb.data.split(":")[1])]
    is_correct = chosen == q["answer"]
    feedback = "✅" if is_correct else f"❌ Правильно: <b>{q['answer']}</b>"
    await cb.message.edit_text(f"{cb.message.text}\n\nТы выбрал: {chosen}\n{feedback}", parse_mode="HTML")
    await state.update_data(
        gram_idx=data["gram_idx"] + 1,
        gram_correct=data["gram_correct"] + (1 if is_correct else 0),
    )
    await cb.answer()
    await _ask_placement_grammar(cb.message, state)


async def _start_placement_speaking(message: Message, state: FSMContext):
    q = assessment.PLACEMENT_SPEAKING[1]  # средний (A2) — для начала
    await state.update_data(speaking_q=q["q"])
    await state.set_state(PlacementFSM.speaking)
    await _send_with_audio(
        message,
        f"🗣 *Часть 3 — Speaking*\n\nПрослушай вопрос и запиши голосовой ответ (30-90 сек):\n\n_{q['q']}_",
        voice_text=q["q"],
    )


def _heuristic_speaking_score(text: str) -> tuple[dict, float]:
    """
    Быстрая оценка speaking без LLM.
    Считаем английские слова — достаточно для placement test.
    Полная LLM-оценка доступна через /en_speak.
    """
    if not text:
        return {"fluency": 0, "grammar": 0, "vocabulary": 0, "task_completion": 0,
                "cefr": "A0", "feedback_ru": "Ответ не записан.", "corrected": ""}, 0.0
    words = text.split()
    # Считаем слова с латинскими буквами как английские
    en_words = [w for w in words if any(c.isalpha() and ord(c) < 128 for c in w)]
    en_ratio = len(en_words) / max(len(words), 1)
    wc = len(en_words)
    if en_ratio < 0.3:
        # Ответил не по-английски
        score_dict = {"fluency": 1, "grammar": 1, "vocabulary": 1, "task_completion": 1,
                      "cefr": "A1", "feedback_ru": "Постарайся отвечать по-английски — даже простыми словами!", "corrected": ""}
        return score_dict, 20.0
    if wc >= 25:
        fd = {"fluency": 4, "grammar": 3, "vocabulary": 3, "task_completion": 4,
              "cefr": "A2", "feedback_ru": "Хороший развёрнутый ответ!", "corrected": ""}
        return fd, 70.0
    if wc >= 12:
        fd = {"fluency": 3, "grammar": 2, "vocabulary": 2, "task_completion": 3,
              "cefr": "A2", "feedback_ru": "Неплохо! Попробуй добавить больше деталей.", "corrected": ""}
        return fd, 50.0
    fd = {"fluency": 2, "grammar": 2, "vocabulary": 2, "task_completion": 2,
          "cefr": "A1", "feedback_ru": "Начало есть! Старайся говорить полными предложениями.", "corrected": ""}
    return fd, 35.0


@router.message(PlacementFSM.speaking, F.voice)
async def placement_speaking_voice(message: Message, state: FSMContext):
    import os
    import tempfile
    file = await message.bot.get_file(message.voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
        await message.bot.download_file(file.file_path, destination=tmp_path)
    try:
        text = await transcribe(tmp_path, duration_sec=message.voice.duration or 0)
    finally:
        os.unlink(tmp_path)

    if not text:
        await message.answer("Не разобрал речь, попробуй ещё раз.")
        return

    from html import escape as _esc_txt
    await message.answer(f"📝 Распознано: <i>{_esc_txt(text)}</i>", parse_mode="HTML")

    data = await state.get_data()
    # Placement test: быстрая эвристика без LLM (мгновенно).
    # Полная AI-оценка доступна через /en_speak
    eval_result, speaking_score = _heuristic_speaking_score(text)

    cefr = assessment.estimate_cefr(
        data["vocab_correct"], len(data["vocab_queue"]),
        data["gram_correct"], len(data["gram_queue"]),
        speaking_score,
    )
    starting_unit = assessment.recommend_starting_unit(cefr)

    score = {
        "vocab": f"{data['vocab_correct']}/{len(data['vocab_queue'])}",
        "grammar": f"{data['gram_correct']}/{len(data['gram_queue'])}",
        "speaking": eval_result,
        "speaking_overall": round(speaking_score, 1),
        "cefr": cefr,
    }
    await db.en_save_test(message.from_user.id, "placement", score, cefr_estimate=cefr)
    await db.en_update_profile(
        message.from_user.id,
        cefr_level=cefr,
        vocab_score=data["vocab_correct"] / len(data["vocab_queue"]) * 100,
        grammar_score=data["gram_correct"] / len(data["gram_queue"]) * 100,
        speaking_score=speaking_score,
        current_unit=starting_unit,
        last_assessed_at="datetime('now')",
    )

    from html import escape as _esc
    feedback = _esc(eval_result.get('feedback_ru', ''))
    await message.answer(
        f"🎓 <b>Результаты теста</b>\n\n"
        f"📚 Словарь: {data['vocab_correct']}/{len(data['vocab_queue'])}\n"
        f"📐 Грамматика: {data['gram_correct']}/{len(data['gram_queue'])}\n"
        f"🗣 Speaking: {speaking_score:.0f}/100\n"
        f"   • fluency: {eval_result.get('fluency', 0)}/5\n"
        f"   • grammar: {eval_result.get('grammar', 0)}/5\n"
        f"   • vocab: {eval_result.get('vocabulary', 0)}/5\n\n"
        f"🎯 <b>Твой уровень: {_esc(cefr)}</b>\n"
        f"📖 Рекомендую начать с <b>Unit {starting_unit}</b>\n\n"
        f"💬 <i>{feedback}</i>\n\n"
        f"Установить юнит: <code>/en_unit {starting_unit}</code>\n"
        f"Затем: /en_block",
        parse_mode="HTML",
    )
    await state.clear()


# ─────────────────── /en_block — блок упражнений ───────────────────

@router.message(Command("en_block"))
async def cmd_en_block(message: Message, state: FSMContext):
    await state.clear()
    profile = await db.en_get_or_create_profile(message.from_user.id)
    unit = await db.en_get_unit_by_number(profile.get("current_unit") or 1)
    if not unit:
        await message.answer("Сначала задай юнит: `/en_unit 1`", parse_mode="Markdown")
        return

    block = await exercises.build_block(unit["id"], n=6)
    if not block:
        await message.answer(
            f"В юните {unit['number']} '{unit['title']}' нет материала.\n"
            "Запусти `python -m scripts.ingest_outcomes` на VPS, чтобы загрузить контент.",
            parse_mode="Markdown",
        )
        return

    await state.set_state(BlockFSM.in_progress)
    await state.update_data(block=block, idx=0, correct=0, unit_id=unit["id"])
    await message.answer(
        f"▶️ *Блок упражнений* — Unit {unit['number']} {unit['title']}\n"
        f"6 упражнений · ~10 минут\n\n"
        f"Отвечай голосом или текстом. Команда `/skip` — пропустить.",
        parse_mode="Markdown",
    )
    await _show_exercise(message, state)


async def _show_exercise(message: Message, state: FSMContext):
    data = await state.get_data()
    idx = data["idx"]
    block = data["block"]
    if idx >= len(block):
        await _finish_block(message, state)
        return

    ex = block[idx]
    header = f"*{idx + 1}/{len(block)}* · _{ex['type']}_"

    if ex["type"] == "chunk_drill":
        await _send_with_audio(
            message,
            f"{header}\n\n🔁 *Shadowing*\nПовтори вслух за голосом:\n\n*{ex['prompt_text']}*\n\n_{ex.get('translation') or ''}_",
            voice_text=ex["prompt_text"],
        )
        await message.answer("Когда повторил — отправь любое сообщение или `/next`.", parse_mode="Markdown")

    elif ex["type"] == "translate_to_en":
        await message.answer(
            f"{header}\n\n🔄 *Скажи по-английски:*\n\n«{ex['prompt_text'].split('«')[-1].rstrip('»')}»\n\n"
            f"_Подсказка: ключевое слово — {ex.get('hint','')}_",
            parse_mode="Markdown",
        )

    elif ex["type"] == "gap_fill":
        await message.answer(
            f"{header}\n\n📝 *Заполни пропуск:*\n\n`{ex['prompt_text']}`",
            parse_mode="Markdown",
        )

    elif ex["type"] == "multiple_choice":
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=opt, callback_data=f"enmc:{i}")]
            for i, opt in enumerate(ex["options"])
        ])
        await message.answer(
            f"{header}\n\n☑️ *Выбери:*\n\n{ex['prompt_text']}",
            parse_mode="Markdown", reply_markup=kb,
        )


@router.callback_query(BlockFSM.in_progress, F.data.startswith("enmc:"))
async def cb_block_mc(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    ex = data["block"][data["idx"]]
    chosen = ex["options"][int(cb.data.split(":")[1])]
    is_correct = exercises.check_answer(ex["expected_answer"], chosen)
    fb = "✅" if is_correct else f"❌ Правильно: *{ex['expected_answer']}*"
    await cb.message.edit_text(f"{cb.message.text}\n\n{chosen}\n{fb}", parse_mode="Markdown")
    await state.update_data(idx=data["idx"] + 1, correct=data["correct"] + (1 if is_correct else 0))
    await cb.answer()
    await _show_exercise(cb.message, state)


@router.message(BlockFSM.in_progress, F.voice)
async def block_voice_answer(message: Message, state: FSMContext):
    import os
    import tempfile
    file = await message.bot.get_file(message.voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
        await message.bot.download_file(file.file_path, destination=tmp_path)
    try:
        text = await transcribe(tmp_path, duration_sec=message.voice.duration or 0)
    finally:
        os.unlink(tmp_path)

    if not text:
        await message.answer("Не разобрал, попробуй ещё.")
        return
    await _check_text_answer(message, state, text)


@router.message(BlockFSM.in_progress, Command("skip"))
async def block_skip(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(idx=data["idx"] + 1)
    await message.answer("⏭ Пропустил.")
    await _show_exercise(message, state)


@router.message(BlockFSM.in_progress, Command("next"))
async def block_next(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(idx=data["idx"] + 1)
    await _show_exercise(message, state)


@router.message(BlockFSM.in_progress)
async def block_text_answer(message: Message, state: FSMContext):
    if (message.text or "").startswith("/"):
        return  # пусть другие команды работают
    await _check_text_answer(message, state, message.text or "")


async def _check_text_answer(message: Message, state: FSMContext, given: str):
    data = await state.get_data()
    ex = data["block"][data["idx"]]
    if ex["type"] == "chunk_drill":
        # Для drill — не проверяем строго, считаем выполненным
        is_correct = True
        feedback = "👍"
    else:
        is_correct = exercises.check_answer(ex["expected_answer"], given)
        feedback = "✅" if is_correct else f"❌ Правильно: *{ex['expected_answer']}*"

    await message.answer(f"_{given}_\n{feedback}", parse_mode="Markdown")
    await state.update_data(idx=data["idx"] + 1, correct=data["correct"] + (1 if is_correct else 0))
    await _show_exercise(message, state)


async def _finish_block(message: Message, state: FSMContext):
    data = await state.get_data()
    correct = data["correct"]
    total = len(data["block"])
    pct = int(correct / total * 100) if total else 0
    bar = "▓" * (pct // 10) + "░" * (10 - pct // 10)
    await db.en_log_session(
        user_id=message.from_user.id,
        block_type="mixed",
        items_total=total, items_correct=correct,
    )
    # Адаптация целевого темпа
    new_target = await curriculum.adapt_daily_target(message.from_user.id)
    await message.answer(
        f"🏁 *Блок завершён*\n\n"
        f"Правильно: {correct}/{total}\n"
        f"`{bar}` {pct}%\n\n"
        f"Цель на день: {new_target} новых чанков\n\n"
        f"Ещё блок? /en_block · Меню: /en",
        parse_mode="Markdown",
    )
    await state.clear()


# ─────────────────── /en_review — SRS ───────────────────

@router.message(Command("en_review"))
async def cmd_en_review(message: Message):
    items = await srs.get_due(message.from_user.id, limit=10)
    if not items:
        await message.answer("🎉 На сегодня повторений нет. /en_block — новый материал.", parse_mode="Markdown")
        return

    lines = [f"🔄 *На повторение:* {len(items)}\n"]
    for it in items:
        lines.append(f"• *{it['chunk']}* — {it.get('translation_ru') or '?'}")
    lines.append("\nДля интерактивного теста — /en_block")
    await message.answer("\n".join(lines), parse_mode="Markdown")


# ─────────────────── /en_speak — speaking practice ───────────────────

@router.message(Command("en_speak"))
async def cmd_en_speak(message: Message, state: FSMContext):
    await state.clear()
    profile = await db.en_get_or_create_profile(message.from_user.id)
    unit = await db.en_get_unit_by_number(profile.get("current_unit") or 1)

    # Берём случайный вопрос для текущего уровня
    questions = {
        "A0": "Tell me your name and your job. Use simple sentences.",
        "A1": "Describe your day. What do you do in the morning?",
        "A1+": "Tell me about your family. How many people, what they do.",
        "A2": "What did you do last weekend? Use 4-5 sentences.",
        "A2+": "Describe your favourite food and why you like it.",
        "B1": "Imagine you have a free week. What would you do and why?",
        "B1+": "What do you think about learning English as an adult?",
    }
    q = questions.get(profile["cefr_level"], questions["A1"])

    await state.set_state(SpeakFSM.awaiting_audio)
    await state.update_data(question=q)
    await _send_with_audio(
        message,
        f"🗣 *Speaking practice*\n\nПрослушай вопрос и ответь голосом (30-90 сек):\n\n_{q}_",
        voice_text=q,
    )


@router.message(SpeakFSM.awaiting_audio, F.voice)
async def speak_answer(message: Message, state: FSMContext):
    import os
    import tempfile
    file = await message.bot.get_file(message.voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
        await message.bot.download_file(file.file_path, destination=tmp_path)
    try:
        text = await transcribe(tmp_path, duration_sec=message.voice.duration or 0)
    finally:
        os.unlink(tmp_path)

    if not text:
        await message.answer("Не разобрал. Попробуй ещё раз.")
        return

    await message.answer(f"📝 Распознано: _{text}_\n\n🤖 Оцениваю...", parse_mode="Markdown")
    data = await state.get_data()
    eval_result = await speaking_eval.evaluate(data["question"], text)
    score = speaking_eval.overall_score(eval_result)

    await db.en_log_session(
        user_id=message.from_user.id, block_type="speaking",
        items_total=1, items_correct=1 if score >= 60 else 0,
        speaking_score=score,
    )
    await message.answer(
        f"🎯 *Оценка:*\n\n"
        f"Fluency: {eval_result.get('fluency',0)}/5\n"
        f"Grammar: {eval_result.get('grammar',0)}/5\n"
        f"Vocabulary: {eval_result.get('vocabulary',0)}/5\n"
        f"Task: {eval_result.get('task_completion',0)}/5\n"
        f"📊 Overall: *{score:.0f}/100* ({eval_result.get('cefr','?')})\n\n"
        f"💬 {eval_result.get('feedback_ru','')}\n\n"
        f"Исправлено:\n_{eval_result.get('corrected','')}_",
        parse_mode="Markdown",
    )
    await state.clear()


# ─────────────────── /en_lesson — отчёт с урока ───────────────────

@router.message(Command("en_lesson"))
async def cmd_en_lesson(message: Message, state: FSMContext):
    await state.set_state(LessonFSM.awaiting_report)
    await message.answer(
        "📝 *Отчёт с урока*\n\n"
        "Расскажи (текстом или голосом):\n"
        "• Что прошли — тема, грамматика\n"
        "• Какие новые слова/фразы\n"
        "• Что задал учитель на ДЗ\n\n"
        "Я разберу и сохраню. /cancel — отмена",
        parse_mode="Markdown",
    )


@router.message(LessonFSM.awaiting_report, Command("cancel"))
async def lesson_cancel(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отменил.")


@router.message(LessonFSM.awaiting_report, F.voice)
async def lesson_voice(message: Message, state: FSMContext):
    import os
    import tempfile
    file = await message.bot.get_file(message.voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
        await message.bot.download_file(file.file_path, destination=tmp_path)
    try:
        text = await transcribe(tmp_path, duration_sec=message.voice.duration or 0)
    finally:
        os.unlink(tmp_path)
    if text:
        await _process_lesson_report(message, state, text)


@router.message(LessonFSM.awaiting_report, F.text)
async def lesson_text(message: Message, state: FSMContext):
    if (message.text or "").startswith("/"):
        return
    await _process_lesson_report(message, state, message.text)


async def _process_lesson_report(message: Message, state: FSMContext, text: str):
    await message.answer("🤖 Разбираю отчёт...")
    parsed = await lesson_parser.parse_lesson_report(text)

    # Сохраняем чанки в SRS
    profile = await db.en_get_or_create_profile(message.from_user.id)
    unit_num = profile.get("current_unit") or 1
    unit = await db.en_get_unit_by_number(unit_num)
    unit_id = unit["id"] if unit else None

    chunks_added = 0
    for c in parsed.get("chunks", []):
        if not c.get("chunk"):
            continue
        cid = await db.en_add_chunk(
            chunk=c["chunk"].lower(), translation_ru=c.get("translation_ru", ""),
            unit_id=unit_id, type="phrase",
            source="teacher",
        )
        if cid:
            await srs.add_to_srs(message.from_user.id, cid, queue="passive")
            chunks_added += 1

    # Домашка
    hw_added = 0
    for hw in parsed.get("homework", []):
        if hw.get("description"):
            await db.en_add_homework(
                message.from_user.id,
                description=hw["description"],
                deadline=hw.get("deadline"),
            )
            hw_added += 1

    await message.answer(
        f"✅ *Отчёт сохранён*\n\n"
        f"Тема: *{parsed.get('topic','—')}*\n"
        f"Грамматика: {', '.join(parsed.get('grammar', [])) or '—'}\n"
        f"Новых чанков в SRS: *{chunks_added}*\n"
        f"Домашка: *{hw_added}*\n\n"
        f"Посмотреть ДЗ: /en_homework",
        parse_mode="Markdown",
    )
    await state.clear()


# ─────────────────── /en_homework ───────────────────

@router.message(Command("en_homework"))
async def cmd_en_homework(message: Message):
    items = await db.en_get_pending_homework(message.from_user.id)
    if not items:
        await message.answer("📚 Активных ДЗ нет.")
        return
    lines = ["📚 *Домашка:*\n"]
    for hw in items:
        deadline = f" _до {hw['deadline']}_" if hw.get("deadline") else ""
        lines.append(f"#{hw['id']} {hw['description']}{deadline}")
    lines.append("\nОтметить выполненной: `/en_hw_done ID`")
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("en_hw_done"))
async def cmd_en_hw_done(message: Message):
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Формат: `/en_hw_done ID`", parse_mode="Markdown")
        return
    await db.en_complete_homework(int(parts[1]))
    await message.answer("✅ ДЗ закрыто.")


# ─────────────────── /en_progress ───────────────────

@router.message(Command("en_progress"))
async def cmd_en_progress(message: Message):
    stats = await db.en_full_stats(message.from_user.id)
    p = stats["profile"]

    pct = stats["week"]["accuracy"]
    bar = "▓" * (int(pct) // 10) + "░" * (10 - int(pct) // 10)

    await message.answer(
        f"📊 *Прогресс English*\n\n"
        f"🎯 Уровень: *{p['cefr_level']}*\n"
        f"📚 Текущий юнит: {p.get('current_unit', '—')}\n"
        f"🔥 Streak: {p.get('streak_days', 0)} дн\n\n"
        f"🧠 *SRS:*\n"
        f"  Всего в очереди: {stats['srs']['total']}\n"
        f"  На повторение: {stats['srs']['due_today']}\n"
        f"  Освоено: {stats['srs']['mastered']}\n\n"
        f"📅 *За неделю:*\n"
        f"  Сессий: {stats['week']['sessions']}\n"
        f"  Точность: {pct:.0f}%\n"
        f"  `{bar}`\n\n"
        f"📖 Контент в БД:\n"
        f"  Чанков: {stats['content']['chunks']}\n"
        f"  Предложений: {stats['content']['sentences']}\n"
        f"  Упражнений: {stats['content']['exercises']}",
        parse_mode="Markdown",
    )


# ─────────────────── /en_grammar ───────────────────

@router.message(Command("en_grammar"))
async def cmd_en_grammar(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Формат: `/en_grammar past simple`", parse_mode="Markdown")
        return
    topic = parts[1]
    g = await db.en_find_grammar(topic)
    if not g:
        # Fallback: спросим Sonnet (с кешем)
        await message.answer(f"Объясняю: *{topic}*...", parse_mode="Markdown")
        response = await ask_claude(
            f"Объясни грамматическое правило English '{topic}' простым языком для русскоязычного "
            f"уровня A1-A2. Краткие примеры. Макс 250 слов.",
            tier="sonnet", use_history=False, use_cache=True,
        )
        await message.answer(response, parse_mode="Markdown")
        return

    text = f"📐 *{g['topic']}*\n\n{g.get('rule_ru','')}\n"
    if g.get("examples"):
        try:
            ex_list = json.loads(g["examples"])
            if ex_list:
                text += "\nПримеры:\n" + "\n".join(f"• {e}" for e in ex_list)
        except (json.JSONDecodeError, TypeError):
            pass
    await message.answer(text, parse_mode="Markdown")


# ─────────────────── Callback handlers для меню ───────────────────

@router.callback_query(F.data == "en:block")
async def cb_block(cb: CallbackQuery, state: FSMContext):
    await cmd_en_block(cb.message, state)
    await cb.answer()


@router.callback_query(F.data == "en:review")
async def cb_review(cb: CallbackQuery):
    await cmd_en_review(cb.message)
    await cb.answer()


@router.callback_query(F.data == "en:speak")
async def cb_speak(cb: CallbackQuery, state: FSMContext):
    await cmd_en_speak(cb.message, state)
    await cb.answer()


@router.callback_query(F.data == "en:start_placement")
async def cb_placement(cb: CallbackQuery, state: FSMContext):
    await cmd_en_start(cb.message, state)
    await cb.answer()


@router.callback_query(F.data == "en:unit_info")
async def cb_unit_info(cb: CallbackQuery):
    await cmd_en_unit(cb.message)
    await cb.answer()


@router.callback_query(F.data == "en:lesson")
async def cb_lesson(cb: CallbackQuery, state: FSMContext):
    await cmd_en_lesson(cb.message, state)
    await cb.answer()


@router.callback_query(F.data == "en:progress")
async def cb_progress(cb: CallbackQuery):
    await cmd_en_progress(cb.message)
    await cb.answer()


@router.callback_query(F.data == "en:settings")
async def cb_settings(cb: CallbackQuery):
    await cb.message.answer(
        "⚙️ *Настройки English*\n\n"
        "`/en_voice uk_f` — голос TTS\n"
        "`/en_unit N` — текущий юнит\n"
        "`/en_start` — пересдать тест уровня",
        parse_mode="Markdown",
    )
    await cb.answer()


# ─────────────────── Legacy: /vocab (для совместимости) ───────────────────

@router.message(Command("vocab"))
async def cmd_vocab(message: Message):
    """Старая команда — добавить слово или найти. Сохранена для совместимости."""
    args = (message.text or "").replace("/vocab", "").strip()
    if not args:
        await message.answer(
            "Добавить:\n`/vocab achieve — достичь`\n\nНайти:\n`/vocab achieve`",
            parse_mode="Markdown",
        )
        return
    sep = next((s for s in ["—", " - ", "="] if s in args), None)
    if sep:
        word, translation = (p.strip() for p in args.split(sep, 1))
        cid = await db.en_add_chunk(
            chunk=word.lower(), translation_ru=translation,
            type="word", source="user",
        )
        await srs.add_to_srs(message.from_user.id, cid, "passive")
        await message.answer(f"✅ *{word}* — {translation}\nДобавлено в SRS.", parse_mode="Markdown")
    else:
        # Поиск
        async with __import__("aiosqlite").connect(config.DB_PATH) as conn:
            import aiosqlite
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM english_chunks WHERE chunk = ? LIMIT 1", (args.lower(),)
            )
            row = await cursor.fetchone()
        if row:
            await message.answer(f"📖 *{row['chunk']}* — {row['translation_ru'] or '?'}", parse_mode="Markdown")
        else:
            response = await ask_claude(
                f"Переведи слово/фразу на русский (1-2 слова): '{args}'",
                tier="haiku", use_history=False, use_cache=True,
            )
            await message.answer(f"📖 *{args}* — {response}\n\nСохранить: `/vocab {args} — {response}`", parse_mode="Markdown")


# ─────────────────── Legacy: интеграция с роутером голоса ───────────────────

async def handle_english_voice(message: Message, text: str, prefix: str = ""):
    """Вызывается из voice.py когда определён English-контекст."""
    text_lower = text.lower()
    if any(t in text_lower for t in ["запомни слово", "новое слово", "добавь слово"]):
        for sep in ["—", " - ", "="]:
            if sep in text:
                raw, translation = text.split(sep, 1)
                for kw in ["запомни слово", "новое слово", "добавь слово", ":"]:
                    raw = raw.replace(kw, "")
                word = raw.strip().lower()
                if word:
                    cid = await db.en_add_chunk(
                        chunk=word, translation_ru=translation.strip(),
                        type="word", source="user",
                    )
                    await srs.add_to_srs(message.from_user.id, cid, "passive")
                    await message.answer(f"{prefix}✅ *{word}* — {translation.strip()}", parse_mode="Markdown")
                    return
    if "переводится" in text_lower or "что значит" in text_lower:
        for kw in ["как переводится", "что значит", "переведи", "перевод"]:
            text = text.replace(kw, "")
        await message.answer(f"{prefix}Использую /vocab")
        return

    response = await ask_claude(
        f"Вопрос об английском от Андрея (уровень A1-A2): {text}\nОтвечай по-русски, кратко.",
        tier="sonnet", use_history=False, use_cache=True,
    )
    await message.answer(f"{prefix}{response}", parse_mode="Markdown")


def is_english_message(text: str) -> bool:
    keywords = [
        "английск", "english", "по-английски",
        "запомни слово", "новое слово", "добавь слово",
        "как переводится", "что значит",
        "grammar", "грамматика", "phrasal verb",
    ]
    return any(kw in text.lower() for kw in keywords)


# Legacy aliases для voice.py диспетчера
cmd_review = cmd_en_review
cmd_test = cmd_en_block
