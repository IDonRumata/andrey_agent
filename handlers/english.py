"""
Модуль изучения английского языка.
Уровень: A1/A2 → B1

Команды:
  /en           — главное меню / текущий прогресс
  /vocab слово  — добавить слово или найти в словаре
  /phrase фраза — сохранить фразу/выражение
  /engram тема  — грамматическое правило
  /enreview     — карточки для повторения (spaced repetition)
  /entest       — мини-тест (перевод слова)
  /enstat       — статистика прогресса
  /enlevel      — текущий уровень и что осталось до B1

Голосовой/текстовый роутинг:
  "запомни слово: achieve — достичь" → vocab
  "запомни фразу: I'm looking forward to..." → phrase
  "как переводится ..."  → поиск в словаре
"""
import json
import logging
import random
from datetime import date, datetime, timedelta

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

import database as db
from services.claude_api import ask_claude

router = Router()
logger = logging.getLogger(__name__)

# ID проекта English (создаётся при первом запуске)
_english_project_id: int | None = None


async def get_english_project_id() -> int:
    """Получить или создать проект English."""
    global _english_project_id
    if _english_project_id:
        return _english_project_id
    project = await db.get_project_by_name("English")
    if project:
        _english_project_id = project["id"]
    else:
        _english_project_id = await db.create_project(
            "English",
            "Изучение английского языка A1/A2 → B1. Дальнобойщик Андрей, Беларусь."
        )
        # Загрузить базовый контент при первом создании
        await _load_base_knowledge(_english_project_id)
    return _english_project_id


# ─────────────────────── База знаний ───────────────────────

ROADMAP_A1_B1 = """
ROADMAP: A1/A2 → B1

📍 A1 (Beginner) — 100-150 слов активно:
• Глагол to be, have got
• Числа, цвета, дни недели, месяцы
• Простое настоящее (Present Simple)
• Личные местоимения, притяжательные
• Базовые вопросы: What? Who? Where? When?
• Темы: семья, еда, работа, транспорт

📍 A2 (Elementary) — 1000-1500 слов:
• Past Simple (правильные + неправильные глаголы)
• Future: will / going to
• Настоящее длительное (Present Continuous)
• Степени сравнения прилагательных
• Модальные: can, must, should
• Предлоги места и времени
• Темы: путешествия, покупки, здоровье, деньги

📍 B1 (Intermediate) — 2500-3000 слов:
• Present Perfect vs Past Simple
• Условные предложения (1-й и 2-й тип)
• Пассивный залог (Passive Voice)
• Герундий и инфинитив
• Reported Speech (косвенная речь)
• Фразовые глаголы (100+ основных)
• Темы: бизнес, инвестиции, технологии, новости

⏱ Темп для занятого человека (из кабины):
• 20-30 мин/день = B1 за 12-18 месяцев
• Утром: 5 новых слов (карточки)
• В рейсе: подкасты/аудио на английском
• Вечером: 1 правило + практика
"""

GRAMMAR_RULES = {
    "present_simple": """
PRESENT SIMPLE (Настоящее простое)
Факты, привычки, расписания.

✅ Структура:
+ I/You/We/They work    → He/She/It works
- I don't work          → He doesn't work
? Do you work?          → Does he work?

✅ Маркеры: always, usually, often, sometimes, never, every day/week

✅ Примеры:
• I drive trucks for a living.
• He doesn't invest in crypto.
• Do you check the market every morning?

❌ Не путай с Present Continuous!
• I drive (привычка) vs I'm driving now (прямо сейчас)
""",

    "past_simple": """
PAST SIMPLE (Прошедшее простое)
Завершённые действия в прошлом.

✅ Структура:
+ I worked / I went (неправильные!)
- I didn't work / I didn't go
? Did you work? / Did you go?

✅ Маркеры: yesterday, last week/year, ago, in 2020

✅ Топ неправильных глаголов (инвестор/трейдер):
• buy → bought (купил)
• sell → sold (продал)
• grow → grew (вырос)
• fall → fell (упал)
• make → made (заработал)
• lose → lost (потерял)
• hold → held (держал)
• find → found (нашёл)

✅ Примеры:
• I bought BTC last year.
• The stock fell 20% in March.
• Did you sell before the crash?
""",

    "present_perfect": """
PRESENT PERFECT
Связь прошлого с настоящим. Опыт. Результат.

✅ Структура: have/has + V3 (причастие)
+ I have bought / He has sold
- I haven't bought / He hasn't sold
? Have you bought? / Has he sold?

✅ Когда использовать:
1. Опыт (ever/never): Have you ever invested in ETF?
2. Недавно (just): I've just checked the price.
3. Ещё не (yet): I haven't sold yet.
4. Уже (already): He's already made a profit.
5. В жизни (so far): I've earned $5k so far this year.

✅ Отличие от Past Simple:
• I bought BTC in 2021. (конкретная дата — Past Simple)
• I've bought BTC before. (опыт, дата не важна — Present Perfect)
""",

    "conditionals": """
УСЛОВНЫЕ ПРЕДЛОЖЕНИЯ

1️⃣ First Conditional (реальное условие):
If + Present Simple → will + V
• If the price rises, I will sell.
• If you invest $100/month, you will be rich in 10 years.

2️⃣ Second Conditional (нереальное/маловероятное):
If + Past Simple → would + V
• If I had $10,000, I would buy Tesla.
• If BTC reached $200k, I would retire.

✅ Сокращения:
• I will → I'll      • I would → I'd
• It will → It'll    • It would → It'd
""",

    "modal_verbs": """
МОДАЛЬНЫЕ ГЛАГОЛЫ

CAN — умею, могу (физически)
• I can read financial reports in English.
• Can you speak English? — No, not yet.

COULD — мог (в прошлом), вежливо
• I could drive 12 hours straight when I was young.
• Could you explain this term?

SHOULD — следует, рекомендую
• You should diversify your portfolio.
• I shouldn't check the price every hour.

MUST — обязан (внутреннее убеждение)
HAVE TO — обязан (внешнее требование)
• I must learn English to scale my business.
• Truck drivers have to follow regulations.

MIGHT/MAY — возможно (50/50)
• The market might recover next month.
• BTC may reach new highs.

WOULD — бы (вежливо, условно)
• I would like to open a brokerage account.
• Would you recommend ETF for beginners?
""",

    "phrasal_verbs": """
ФРАЗОВЫЕ ГЛАГОЛЫ — Топ для бизнеса и инвестиций

set up — основать, настроить
• I set up a Telegram bot for investors.

take on — взять (задачу, клиента, риск)
• Don't take on too much risk.

look into — изучить, исследовать
• I'm looking into ETF options.

find out — узнать, выяснить
• Let me find out the commission fee.

work out — разобраться, рассчитать
• Work out your monthly expenses first.

carry out — выполнить, провести
• We need to carry out market analysis.

come up with — придумать, предложить
• He came up with a great investment idea.

go through — пройти через, изучить
• Let's go through the report together.

break down — разбить на части, сломаться
• Break down your goal into small steps.

pull off — осуществить (что-то сложное)
• He pulled off a 300% return last year.

give up — сдаться
• Never give up on your financial goals.
""",

    "passive_voice": """
ПАССИВНЫЙ ЗАЛОГ (Passive Voice)
Когда важно ЧТО произошло, а не КТО сделал.

✅ Структура: to be + V3 (причастие)

Present: is/are + V3
• Bitcoin is traded on many exchanges.
• Dividends are paid quarterly.

Past: was/were + V3
• The account was opened in 2023.
• The position was closed at a loss.

Present Perfect: has/have been + V3
• The contract has been signed.
• New rules have been introduced.

✅ Примеры из финансов:
• Shares are listed on the exchange.
• The report was published yesterday.
• Taxes must be paid on capital gains.
""",
}

USEFUL_PHRASES = {
    "investing": [
        "diversify your portfolio — диверсифицировать портфель",
        "compound interest — сложный процент",
        "return on investment (ROI) — доходность инвестиций",
        "bull market — бычий рынок (рост)",
        "bear market — медвежий рынок (падение)",
        "long-term investment — долгосрочные инвестиции",
        "dividend yield — дивидендная доходность",
        "market capitalization — рыночная капитализация",
        "price-to-earnings ratio (P/E) — соотношение цены и прибыли",
        "stop-loss order — стоп-лосс ордер",
        "take profit — тейк профит",
        "exchange-traded fund (ETF) — биржевой фонд",
        "asset allocation — распределение активов",
    ],
    "business": [
        "revenue — выручка",
        "net profit — чистая прибыль",
        "operating expenses — операционные расходы",
        "cash flow — денежный поток",
        "break even — выйти в ноль",
        "scale up — масштабировать",
        "target audience — целевая аудитория",
        "conversion rate — конверсия",
        "sales funnel — воронка продаж",
        "customer acquisition cost (CAC) — стоимость привлечения клиента",
    ],
    "daily": [
        "I'm on my way — Я в пути",
        "I'll be there in an hour — Буду там через час",
        "Could you repeat that? — Не могли бы вы повторить?",
        "I'm not sure I follow — Не совсем понимаю",
        "Let me think about it — Дайте подумать",
        "That makes sense — Это логично",
        "I'll look into it — Разберусь с этим",
        "Keep me posted — Держи в курсе",
        "It's up to you — Решать тебе",
        "No worries — Не беспокойся",
        "Fair enough — Справедливо / Хорошо",
        "It depends — Зависит от ситуации",
    ],
}

LEARNING_TIPS = """
СОВЕТЫ ДЛЯ АНДРЕЯ (из кабины фуры):

🎧 В дороге:
• Подкасты: BBC Learning English, 6 Minute English, EnglishPod
• YouTube: English with Lucy, mmmEnglish
• Фильмы/сериалы с субтитрами на английском

📱 Приложения:
• Anki — карточки со spaced repetition (лучшее для слов)
• Duolingo — 10 мин/день для регулярности
• Elsa Speak — произношение с AI-оценкой

📝 Твой метод (минимум времени → максимум результата):
1. 5 слов утром → повторить вечером
2. 1 грамматическое правило в неделю
3. 1 подкаст в дороге (слушать, не переводить)
4. Писать мысли в этот бот на английском

🎯 Цель B1 — что нужно уметь:
• Понимать основную мысль в новостях и разговорах
• Описывать опыт, события, планы
• Объяснить свою позицию на бытовые темы
• Читать простые статьи об инвестициях
• Вести деловую переписку на базовом уровне

⚡ Лайфхак для запоминания:
Используй новые слова СРАЗУ в контексте своей жизни:
"Today I diversified my portfolio" (не "сегодня я диверсифицировал")
"""


async def _load_base_knowledge(project_id: int):
    """Загрузить базовые знания в базу при создании проекта."""
    entries = [
        ("roadmap", "ROADMAP A1→B1", ROADMAP_A1_B1),
        ("grammar", "Present Simple", GRAMMAR_RULES["present_simple"]),
        ("grammar", "Past Simple", GRAMMAR_RULES["past_simple"]),
        ("grammar", "Present Perfect", GRAMMAR_RULES["present_perfect"]),
        ("grammar", "Conditionals", GRAMMAR_RULES["conditionals"]),
        ("grammar", "Modal Verbs", GRAMMAR_RULES["modal_verbs"]),
        ("grammar", "Phrasal Verbs", GRAMMAR_RULES["phrasal_verbs"]),
        ("grammar", "Passive Voice", GRAMMAR_RULES["passive_voice"]),
        ("phrases", "Investing vocabulary", "\n".join(USEFUL_PHRASES["investing"])),
        ("phrases", "Business vocabulary", "\n".join(USEFUL_PHRASES["business"])),
        ("phrases", "Daily phrases", "\n".join(USEFUL_PHRASES["daily"])),
        ("tips", "Learning tips", LEARNING_TIPS),
    ]
    for entry_type, topic, content in entries:
        structured = json.dumps({"topic": topic, "content": content}, ensure_ascii=False)
        await db.add_project_entry(project_id, entry_type, topic, structured)


# ─────────────────────── Команды ───────────────────────

@router.message(Command("en"))
async def cmd_english_menu(message: Message):
    """Главное меню модуля English."""
    stats = await db.get_english_stats()
    vocab_count = stats.get("vocab_count", 0)
    phrases_count = stats.get("phrases_count", 0)
    review_due = stats.get("review_due", 0)

    text = (
        "🇬🇧 *English A1/A2 → B1*\n\n"
        f"📚 Слов в словаре: *{vocab_count}*\n"
        f"💬 Фраз сохранено: *{phrases_count}*\n"
        f"🔄 На повторение сегодня: *{review_due}*\n\n"
        "Команды:\n"
        "/vocab *слово* — добавить/найти слово\n"
        "/phrase *фраза* — сохранить выражение\n"
        "/engram *тема* — грамматическое правило\n"
        "/enreview — слова на повторение\n"
        "/entest — мини-тест\n"
        "/enstat — прогресс\n"
        "/enlevel — до B1 осталось\n\n"
        "Или просто напиши/надиктуй:\n"
        "_\"запомни слово: achieve — достичь\"_\n"
        "_\"как переводится diversify\"_\n"
        "_\"объясни present perfect\"_"
    )
    await message.answer(text, parse_mode="Markdown")


@router.message(Command("vocab"))
async def cmd_vocab(message: Message):
    """Добавить слово или найти в словаре."""
    args = (message.text or "").replace("/vocab", "").strip()

    if not args:
        await message.answer(
            "Добавить слово:\n`/vocab achieve — достичь`\n\n"
            "Найти слово:\n`/vocab achieve`",
            parse_mode="Markdown"
        )
        return

    # Проверяем — добавление или поиск
    if "—" in args or "-" in args or "=" in args:
        # Добавление: word — перевод
        sep = "—" if "—" in args else ("-" if "-" in args else "=")
        parts = args.split(sep, 1)
        word = parts[0].strip().lower()
        translation = parts[1].strip() if len(parts) > 1 else ""

        entry_id = await db.add_english_vocab(word, translation)
        await db.log_action("add", "english_vocab", entry_id)
        await message.answer(
            f"✅ Слово сохранено:\n"
            f"*{word}* — {translation}\n\n"
            f"Повторение: через 1 день",
            parse_mode="Markdown"
        )
    else:
        # Поиск в словаре
        word = args.strip().lower()
        entry = await db.find_english_vocab(word)
        if entry:
            due = entry.get("next_review", "")
            reviews = entry.get("review_count", 0)
            await message.answer(
                f"📖 *{entry['word']}* — {entry['translation']}\n\n"
                f"Повторений: {reviews}\n"
                f"Следующее: {due[:10] if due else '—'}",
                parse_mode="Markdown"
            )
        else:
            # Не найдено — спросить у Claude
            await message.answer(f"Не нашёл в словаре. Переводю через AI...")
            response = await ask_claude(
                f"Переведи слово/фразу на русский и дай краткий пример предложения: '{word}'.\n"
                f"Формат: перевод | пример на английском | перевод примера",
                tier="haiku",
                use_history=False,
                use_cache=True,
            )
            await message.answer(
                f"📖 *{word}*\n\n{response}\n\n"
                f"Добавить в словарь: `/vocab {word} — перевод`",
                parse_mode="Markdown"
            )


@router.message(Command("phrase"))
async def cmd_phrase(message: Message):
    """Сохранить фразу/выражение."""
    args = (message.text or "").replace("/phrase", "").strip()
    if not args:
        await message.answer(
            "Формат:\n`/phrase I'm looking forward to — с нетерпением жду`\n\n"
            "Или просто:\n`/phrase fair enough`",
            parse_mode="Markdown"
        )
        return

    pid = await get_english_project_id()
    structured = json.dumps({"type": "phrase", "content": args}, ensure_ascii=False)
    await db.add_project_entry(pid, "phrase", args, structured)

    # Если перевод не указан — переведём через Haiku
    if "—" not in args and "-" not in args:
        translation = await ask_claude(
            f"Переведи фразу на русский (1-2 слова/короткое объяснение): '{args}'",
            tier="haiku", use_history=False, use_cache=True,
        )
        await message.answer(f"✅ Фраза сохранена:\n*{args}* — {translation}", parse_mode="Markdown")
    else:
        await message.answer(f"✅ Фраза сохранена:\n*{args}*", parse_mode="Markdown")


@router.message(Command("engram"))
async def cmd_grammar(message: Message):
    """Объяснение грамматики."""
    args = (message.text or "").replace("/engram", "").strip().lower()

    # Поиск по ключевым словам
    mapping = {
        "present simple": "present_simple",
        "present": "present_simple",
        "past simple": "past_simple",
        "past": "past_simple",
        "perfect": "present_perfect",
        "present perfect": "present_perfect",
        "conditional": "conditionals",
        "условн": "conditionals",
        "modal": "modal_verbs",
        "модальн": "modal_verbs",
        "phrasal": "phrasal_verbs",
        "фразов": "phrasal_verbs",
        "passive": "passive_voice",
        "пассив": "passive_voice",
    }

    rule_key = None
    for keyword, key in mapping.items():
        if keyword in args:
            rule_key = key
            break

    if rule_key and rule_key in GRAMMAR_RULES:
        await message.answer(f"```\n{GRAMMAR_RULES[rule_key]}\n```", parse_mode="Markdown")
        return

    if not args:
        topics = "\n".join(f"• /engram {k.replace('_', ' ')}" for k in GRAMMAR_RULES.keys())
        await message.answer(f"Доступные темы:\n{topics}", parse_mode="Markdown")
        return

    # Нет в базе — спросим Claude
    await message.answer(f"Объясняю: *{args}*...", parse_mode="Markdown")
    response = await ask_claude(
        f"Объясни грамматическое правило English '{args}' простым языком для русскоязычного. "
        f"Примеры из темы инвестиций/бизнеса. Макс 300 слов.",
        tier="sonnet", use_history=False, use_cache=True,
    )
    pid = await get_english_project_id()
    structured = json.dumps({"type": "grammar", "topic": args, "content": response}, ensure_ascii=False)
    await db.add_project_entry(pid, "grammar", args, structured)
    await message.answer(response, parse_mode="Markdown")


@router.message(Command("enreview"))
async def cmd_review(message: Message):
    """Слова на повторение (spaced repetition)."""
    words = await db.get_english_vocab_for_review(limit=10)

    if not words:
        await message.answer(
            "🎉 Нет слов на повторение сегодня!\n\n"
            "Добавь новые: `/vocab achieve — достичь`",
            parse_mode="Markdown"
        )
        return

    lines = [f"🔄 *Повторение* — {len(words)} слов:\n"]
    for w in words:
        lines.append(f"• *{w['word']}* — {w['translation']}")

    lines.append(f"\nПроверь себя: `/entest`")
    await message.answer("\n".join(lines), parse_mode="Markdown")


@router.message(Command("entest"))
async def cmd_test(message: Message):
    """Мини-тест: перевод случайного слова."""
    words = await db.get_english_vocab_for_review(limit=20)
    if not words:
        all_words = await db.get_all_english_vocab(limit=20)
        words = all_words

    if not words:
        await message.answer(
            "Словарь пустой. Сначала добавь слова:\n`/vocab invest — инвестировать`",
            parse_mode="Markdown"
        )
        return

    word = random.choice(words)
    # Показать английское, спрятать перевод
    await message.answer(
        f"❓ Как переводится:\n\n*{word['word']}*\n\n"
        f"Ответ: ||{word['translation']}||",
        parse_mode="Markdown"
    )
    # Обновить дату повторения
    await db.mark_english_vocab_reviewed(word["id"])


@router.message(Command("enstat"))
async def cmd_english_stats(message: Message):
    """Статистика прогресса."""
    stats = await db.get_english_stats()

    # Примерный уровень по количеству слов
    vocab_count = stats.get("vocab_count", 0)
    if vocab_count < 150:
        level = "A1"
        next_milestone = 150
    elif vocab_count < 1000:
        level = "A2 (начало)"
        next_milestone = 1000
    elif vocab_count < 2000:
        level = "A2+"
        next_milestone = 2000
    elif vocab_count < 3000:
        level = "B1"
        next_milestone = 3000
    else:
        level = "B1+"
        next_milestone = None

    progress = ""
    if next_milestone:
        pct = min(100, int(vocab_count / next_milestone * 100))
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        progress = f"\n[{bar}] {pct}% до следующего уровня"

    await message.answer(
        f"📊 *Прогресс English*\n\n"
        f"📚 Слов в словаре: *{vocab_count}*\n"
        f"🎯 Примерный уровень: *{level}*\n"
        f"💬 Фраз: {stats.get('phrases_count', 0)}\n"
        f"🔄 На повторение: {stats.get('review_due', 0)}\n"
        f"✅ Повторений всего: {stats.get('total_reviews', 0)}"
        f"{progress}",
        parse_mode="Markdown"
    )


@router.message(Command("enlevel"))
async def cmd_level(message: Message):
    """Что осталось до B1."""
    await message.answer(
        f"```\n{ROADMAP_A1_B1}\n```",
        parse_mode="Markdown"
    )


# ─────────────────────── Публичные функции для роутера ───────────────────────

async def handle_english_voice(message: Message, text: str, prefix: str = ""):
    """
    Обработать English-сообщение из голоса/текста.
    Вызывается из voice.py / chat.py когда определён English-контекст.
    """
    text_lower = text.lower()

    # "запомни слово: achieve — достичь"
    if any(t in text_lower for t in ["запомни слово", "новое слово", "добавь слово"]):
        # Ищем паттерн word — translation
        for sep in ["—", "-", "="]:
            if sep in text:
                parts = text.split(sep, 1)
                # Берём слово из правой части от ключевого слова
                raw_word = parts[0]
                for kw in ["запомни слово", "новое слово", "добавь слово", ":"]:
                    raw_word = raw_word.replace(kw, "").strip()
                word = raw_word.strip().lower()
                translation = parts[1].strip()
                if word:
                    entry_id = await db.add_english_vocab(word, translation)
                    await db.log_action("add", "english_vocab", entry_id)
                    await message.answer(
                        f"{prefix}✅ Слово сохранено:\n*{word}* — {translation}",
                        parse_mode="Markdown"
                    )
                    return

    # "запомни фразу: ..."
    if any(t in text_lower for t in ["запомни фразу", "добавь фразу", "сохрани фразу"]):
        for kw in ["запомни фразу", "добавь фразу", "сохрани фразу", ":"]:
            text = text.replace(kw, "").strip()
        pid = await get_english_project_id()
        structured = json.dumps({"type": "phrase", "content": text}, ensure_ascii=False)
        await db.add_project_entry(pid, "phrase", text, structured)
        await message.answer(f"{prefix}✅ Фраза сохранена:\n*{text}*", parse_mode="Markdown")
        return

    # "как переводится / что значит"
    if any(t in text_lower for t in ["как переводится", "что значит", "переведи", "перевод слова"]):
        for kw in ["как переводится", "что значит", "переведи слово", "перевод слова", "переведи"]:
            text = text.replace(kw, "").strip()
        word = text.strip().strip("?").strip()
        entry = await db.find_english_vocab(word.lower())
        if entry:
            await message.answer(
                f"{prefix}📖 *{entry['word']}* — {entry['translation']}",
                parse_mode="Markdown"
            )
        else:
            response = await ask_claude(
                f"Переведи на русский и дай пример: '{word}'",
                tier="haiku", use_history=False, use_cache=True,
            )
            await message.answer(f"{prefix}📖 *{word}*\n{response}", parse_mode="Markdown")
        return

    # Общий вопрос про английский — отвечает Sonnet
    response = await ask_claude(
        f"Вопрос об английском языке от Андрея (уровень A2, учит до B1): {text}\n"
        f"Отвечай по-русски, кратко, с примерами из темы инвестиций/бизнеса.",
        tier="sonnet",
        use_history=False,
        use_cache=True,
    )
    await message.answer(f"{prefix}{response}", parse_mode="Markdown")


def is_english_message(text: str) -> bool:
    """Определить — сообщение касается английского."""
    keywords = [
        "английск", "english", "по-английски",
        "запомни слово", "новое слово", "добавь слово",
        "запомни фразу", "как переводится", "что значит",
        "grammar", "грамматика", "phrasal verb", "фразовый глагол",
        "pronunciation", "произношение",
    ]
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)
