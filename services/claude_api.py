"""
Обёртка Claude API с двухуровневой моделью и экономией токенов.

Принцип: Haiku для рутины, Sonnet для экспертизы.
Кеширование повторных вопросов. Учёт расхода.
"""
import hashlib
import json
import logging

import anthropic

import config
import database as db

logger = logging.getLogger(__name__)

client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

# --- Модели и цены (USD за 1M токенов) ---
MODELS = {
    "haiku": {
        "id": "claude-haiku-4-5-20251001",
        "input_price": 0.80,   # $/1M input
        "output_price": 4.00,  # $/1M output
    },
    "sonnet": {
        "id": "claude-sonnet-4-6",
        "input_price": 3.00,
        "output_price": 15.00,
    },
}


def _calc_cost(model_key: str, input_tokens: int, output_tokens: int) -> float:
    m = MODELS[model_key]
    return (input_tokens * m["input_price"] + output_tokens * m["output_price"]) / 1_000_000


def _query_hash(text: str, system: str) -> str:
    """Хеш запроса для кеша. Нормализуем текст."""
    normalized = text.strip().lower()
    return hashlib.md5(f"{system[:50]}:{normalized}".encode()).hexdigest()


# --- Главная функция: спросить Claude ---

async def ask_claude(
    user_message: str,
    system_prompt: str | None = None,
    tier: str = "sonnet",
    use_history: bool = True,
    use_cache: bool = True,
    cache_ttl_hours: int = 168,
) -> str:
    """
    Отправить сообщение Claude.

    tier: "haiku" (рутина, классификация) или "sonnet" (экспертиза, контент)
    use_history: включать историю диалога (дорого — только для диалога)
    use_cache: проверять/сохранять кеш ответов
    cache_ttl_hours: время жизни кеша (по умолчанию 7 дней)
    """
    system = system_prompt or config.SYSTEM_PROMPT

    # 1. Проверить кеш
    if use_cache:
        qhash = _query_hash(user_message, system)
        cached = await db.get_cached_response(qhash)
        if cached:
            logger.info("Кеш-хит: %s", user_message[:50])
            return cached

    # 2. Собрать сообщения
    messages = []
    if use_history:
        history = await db.get_chat_history(limit=config.CHAT_HISTORY_LIMIT)
        messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_message})

    # 3. Вызвать API
    model_info = MODELS[tier]
    try:
        response = await client.messages.create(
            model=model_info["id"],
            max_tokens=config.CLAUDE_MAX_TOKENS,
            system=system,
            messages=messages,
        )
    except Exception as e:
        logger.error("Claude API error: %s", e)
        return f"Ошибка API: {e}"

    assistant_text = response.content[0].text
    input_tok = response.usage.input_tokens
    output_tok = response.usage.output_tokens
    cost = _calc_cost(tier, input_tok, output_tok)

    # 4. Логировать расход
    await db.log_token_usage(tier, input_tok, output_tok, cost)
    logger.info(
        "Claude [%s]: %d+%d tok = $%.4f | %s",
        tier, input_tok, output_tok, cost, user_message[:40],
    )

    # 5. Сохранить в историю (только для диалогового режима)
    if use_history:
        await db.save_message("user", user_message)
        await db.save_message("assistant", assistant_text)

    # 6. Сохранить в кеш
    if use_cache:
        await db.save_cached_response(qhash, user_message, assistant_text, tier, cache_ttl_hours)

    return assistant_text


# --- Классификация через Haiku (дешёвая) ---

CLASSIFY_SYSTEM = (
    "Классифицируй сообщение. Ответь ТОЛЬКО JSON:\n"
    '{"type":"task|idea|note|question","project":"grafin|kronon|realtor|null","text":"краткая суть"}\n'
    "Проекты: grafin (курс инвестиций), kronon (Forex-робот), realtor (сайт риэлторов).\n"
    "Если проект не очевиден — null."
)


async def classify_message(text: str) -> dict:
    """Классификация через Haiku — ~20x дешевле Sonnet."""
    response = await ask_claude(
        user_message=text,
        system_prompt=CLASSIFY_SYSTEM,
        tier="haiku",
        use_history=False,
        use_cache=True,
        cache_ttl_hours=720,  # 30 дней — классификация стабильна
    )
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return {"type": "note", "project": None, "text": text}


# --- Структурирование записи для проекта (Haiku) ---

STRUCTURE_SYSTEM = (
    "Структурируй запись в 1-2 предложения. Определи тип:\n"
    "idea / update / question / decision / risk\n"
    'Ответь JSON: {"type":"тип","text":"суть"}'
)


async def structure_entry(raw_text: str) -> dict:
    """Структурировать запись по проекту через Haiku."""
    response = await ask_claude(
        user_message=raw_text,
        system_prompt=STRUCTURE_SYSTEM,
        tier="haiku",
        use_history=False,
        use_cache=True,
        cache_ttl_hours=720,
    )
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        return {"type": "idea", "text": raw_text}
