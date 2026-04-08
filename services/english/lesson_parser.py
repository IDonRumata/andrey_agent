"""
Парсер отчёта Андрея с живого занятия.
Вход: свободный текст голосом ("Сегодня прошли past simple, новые слова: borrow,
invite, домашка — упражнение 5 на странице 12").
Выход: структурированный JSON через Claude Haiku.
"""
import json
import logging

from services.claude_api import ask_claude

logger = logging.getLogger(__name__)


LESSON_PARSE_SYSTEM = """You parse a Russian-speaking English learner's notes from their live lesson.
Extract structured info as JSON ONLY (no markdown):

{
  "topic": "what was studied (e.g. 'Past Simple', 'food vocabulary')",
  "grammar": ["grammar topics covered"],
  "chunks": [{"chunk": "english word/phrase", "translation_ru": "русский перевод"}],
  "homework": [{"description": "what to do", "deadline": null}],
  "notes": "free-form notes for the learner"
}

If info is missing — return empty arrays / null. Do not invent.
The input may be in Russian or mixed Russian/English.
"""


async def parse_lesson_report(text: str) -> dict:
    response = await ask_claude(
        user_message=text,
        system_prompt=LESSON_PARSE_SYSTEM,
        tier="haiku",
        use_history=False,
        use_cache=False,
    )
    try:
        clean = response.strip().strip("`").replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except json.JSONDecodeError:
        logger.warning("Lesson parse: bad JSON: %s", response[:200])
        return {"topic": "", "grammar": [], "chunks": [], "homework": [], "notes": text}
