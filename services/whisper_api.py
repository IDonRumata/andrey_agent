"""
Whisper API — транскрибация голосовых сообщений.
С отсечкой тишины и учётом стоимости.
"""
import logging

import openai

import config
import database as db

logger = logging.getLogger(__name__)

client = openai.AsyncOpenAI(api_key=config.OPENAI_API_KEY)

# Whisper: $0.006 / минута
WHISPER_PRICE_PER_SEC = 0.006 / 60


async def transcribe(audio_path: str, duration_sec: int = 0) -> str | None:
    """
    Транскрибировать аудиофайл через Whisper API.
    Возвращает None если аудио слишком короткое.
    """
    if duration_sec and duration_sec < config.WHISPER_MIN_DURATION_SEC:
        logger.info("Аудио слишком короткое (%d сек), пропуск", duration_sec)
        return None

    with open(audio_path, "rb") as audio_file:
        response = await client.audio.transcriptions.create(
            model=config.WHISPER_MODEL,
            file=audio_file,
            language="ru",
        )

    text = response.text.strip()
    if not text:
        return None

    # Учёт стоимости
    cost = duration_sec * WHISPER_PRICE_PER_SEC if duration_sec else 0
    if cost > 0:
        await db.log_token_usage("whisper", 0, 0, cost)
        logger.info("Whisper: %d сек = $%.4f | %s", duration_sec, cost, text[:50])

    return text
