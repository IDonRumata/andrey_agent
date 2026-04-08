"""
Оценка устного ответа через Claude Sonnet по CEFR-рубрике.
Используется только когда локальной проверки недостаточно (свободная речь).
"""
import asyncio
import json
import logging

from services.claude_api import ask_claude

logger = logging.getLogger(__name__)


SPEAKING_RUBRIC_SYSTEM = """You are an expert English language assessor (CEFR scale).
Evaluate a learner's spoken response (transcribed by Whisper).
The learner is a beginner Russian speaker (~A1-A2) aiming for B1.

Score each dimension 0-5 (integer):
- fluency: pace, hesitations, completeness
- grammar: tense agreement, articles, word order
- vocabulary: range, appropriacy, chunk usage
- task_completion: did they answer the question

Return ONLY this JSON, no markdown:
{"fluency":N,"grammar":N,"vocabulary":N,"task_completion":N,
 "cefr":"A1|A1+|A2|A2+|B1|B1+","feedback_ru":"1-2 sentences in Russian","corrected":"corrected version if needed"}
"""


async def evaluate(prompt_en: str, learner_response: str, expected: str | None = None) -> dict:
    """
    Оценить устный ответ. Возвращает dict с оценками 0-5 и feedback.
    """
    user = (
        f"PROMPT (what learner was asked):\n{prompt_en}\n\n"
        f"LEARNER RESPONSE (transcribed):\n{learner_response}\n"
    )
    if expected:
        user += f"\nEXPECTED MODEL ANSWER:\n{expected}\n"

    try:
        response = await asyncio.wait_for(
            ask_claude(
                user_message=user,
                system_prompt=SPEAKING_RUBRIC_SYSTEM,
                tier="sonnet",
                use_history=False,
                use_cache=False,
            ),
            timeout=30.0,
        )
    except asyncio.TimeoutError:
        logger.warning("Speaking eval: timeout after 30s")
        return {
            "fluency": 2, "grammar": 2, "vocabulary": 2, "task_completion": 3,
            "cefr": "A1", "feedback_ru": "Оценка временно недоступна (таймаут). Продолжай!", "corrected": "",
        }
    except Exception as e:
        logger.warning("Speaking eval: API error: %s", e)
        return {
            "fluency": 2, "grammar": 2, "vocabulary": 2, "task_completion": 3,
            "cefr": "A1", "feedback_ru": "Не удалось связаться с оценщиком. Продолжай!", "corrected": "",
        }
    try:
        clean = response.strip().strip("`").replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except json.JSONDecodeError:
        logger.warning("Speaking eval: bad JSON: %s", response[:200])
        return {
            "fluency": 0, "grammar": 0, "vocabulary": 0, "task_completion": 0,
            "cefr": "A1", "feedback_ru": "Не удалось разобрать ответ.", "corrected": "",
        }


def overall_score(eval_dict: dict) -> float:
    keys = ["fluency", "grammar", "vocabulary", "task_completion"]
    vals = [eval_dict.get(k, 0) for k in keys]
    return sum(vals) / (len(vals) * 5) * 100  # 0..100
