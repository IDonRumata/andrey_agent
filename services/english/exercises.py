"""
Генераторы упражнений из БД (без LLM).
Все типы возвращают dict с единым контрактом для handlers/english.py:
  {type, prompt_text, prompt_audio_path?, expected_answer, options?, hint?, source}
"""
import json
import random

import database as db


def _normalize(s: str) -> str:
    return " ".join((s or "").lower().strip().split())


def check_answer(expected: str, given: str) -> bool:
    """
    Лояльная проверка:
    - регистр/пробелы/точка не важны
    - если ответ содержит ожидаемую фразу — засчитываем (partial match)
    - 1 опечатка для коротких слов
    """
    a = _normalize(expected).rstrip(".!?,")
    b = _normalize(given).rstrip(".!?,")
    if a == b:
        return True
    # Partial match: ответ содержит ключевую фразу
    if a and a in b:
        return True
    # Ключевая фраза содержится в ожидаемом (студент сказал правильный чанк в составе)
    if b and b in a:
        return True
    # 1 опечатка для коротких слов
    if len(a) <= 10 and len(b) <= 10:
        return _levenshtein(a, b) <= 1
    return False


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


# ─────────────────── Генераторы ───────────────────

async def gen_translate_to_en(unit_id: int) -> dict | None:
    """RU → EN: Андрей видит русский, голосом говорит/пишет английский чанк."""
    chunks = await db.en_get_chunks_by_unit(unit_id, limit=200)
    chunks = [c for c in chunks if c.get("translation_ru")]
    if not chunks:
        return None
    c = random.choice(chunks)
    # Проверяем по ЧАНКУ (ключевой фразе), не по полному предложению.
    # Полное предложение — только как образец в фидбеке.
    ru_prompt = c.get("example_ru") or c["translation_ru"]
    example_en = c.get("example_en") or ""
    return {
        "type": "translate_to_en",
        "prompt_text": f"«{ru_prompt}»",  # без "Скажи по-английски" — он в заголовке
        "expected_answer": c["chunk"],    # проверяем только ключевой чанк
        "example_en": example_en,         # полное предложение-образец для фидбека
        "hint": c["chunk"],
        "chunk_id": c["id"],
        "source": "outcomes_elem",
    }


async def gen_chunk_drill(unit_id: int) -> dict | None:
    """Shadowing: бот произносит, Андрей повторяет."""
    chunks = await db.en_get_chunks_by_unit(unit_id, limit=200)
    if not chunks:
        return None
    c = random.choice(chunks)
    text = c.get("example_en") or c["chunk"]
    return {
        "type": "chunk_drill",
        "prompt_text": text,
        "prompt_audio_path": c.get("example_audio_path") or c.get("audio_path"),
        "expected_answer": text,
        "translation": c.get("translation_ru"),
        "chunk_id": c["id"],
        "source": "outcomes_elem",
    }


async def gen_gap_fill(unit_id: int) -> dict | None:
    """Берём готовое gap-fill из workbook."""
    exs = await db.en_get_exercises_by_unit(unit_id, limit=50)
    exs = [e for e in exs if e["type"] == "gap_fill"]
    if not exs:
        return None
    e = random.choice(exs)
    return {
        "type": "gap_fill",
        "prompt_text": e["prompt"],
        "expected_answer": e["answer"],
        "explanation": e.get("explanation_ru"),
        "exercise_id": e["id"],
        "source": e.get("source", "outcomes_wb"),
    }


async def gen_multiple_choice(unit_id: int) -> dict | None:
    exs = await db.en_get_exercises_by_unit(unit_id, limit=50)
    exs = [e for e in exs if e["type"] == "multiple_choice" and e.get("options")]
    if not exs:
        return None
    e = random.choice(exs)
    options = json.loads(e["options"])
    return {
        "type": "multiple_choice",
        "prompt_text": e["prompt"],
        "options": options,
        "expected_answer": e["answer"],
        "explanation": e.get("explanation_ru"),
        "exercise_id": e["id"],
        "source": e.get("source", "outcomes_wb"),
    }


# ─────────────────── Композиция блока ───────────────────

EXERCISE_GENERATORS = {
    "translate": gen_translate_to_en,
    "drill": gen_chunk_drill,
    "gap_fill": gen_gap_fill,
    "mc": gen_multiple_choice,
}


async def build_block(unit_id: int, n: int = 6) -> list[dict]:
    """Собрать упражнения для одного блока (~10 мин). Interleaving по типам."""
    types_order = ["drill", "translate", "gap_fill", "mc", "drill", "translate"]
    block = []
    for t in types_order[:n]:
        gen = EXERCISE_GENERATORS[t]
        ex = await gen(unit_id)
        if ex:
            block.append(ex)
    # Если упражнений из одного типа нет — заполнить из других
    if len(block) < n:
        for t in EXERCISE_GENERATORS:
            while len(block) < n:
                ex = await EXERCISE_GENERATORS[t](unit_id)
                if not ex:
                    break
                block.append(ex)
    return block[:n]
