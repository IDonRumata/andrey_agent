"""
TTS-обёртка с кешем. По умолчанию edge-tts (бесплатный).
Можно переключить на OpenAI TTS через .env: EN_TTS_PROVIDER=openai
"""
import hashlib
import logging
from pathlib import Path

import config

logger = logging.getLogger(__name__)


def _cache_path(text: str, voice: str, rate: str) -> Path:
    """Стабильный путь к файлу по содержимому."""
    h = hashlib.md5(f"{voice}|{rate}|{text}".encode("utf-8")).hexdigest()
    return config.EN_TTS_CACHE_DIR / f"{h}.ogg"


async def synthesize(
    text: str,
    voice: str | None = None,
    rate: str | None = None,
    second: bool = False,
) -> Path:
    """
    Сгенерировать или взять из кеша озвучку. Возвращает Path к .ogg.
    second=True — использовать второй голос (для диалогов).
    """
    voice = voice or (config.EN_TTS_VOICE_SECOND if second else config.EN_TTS_VOICE_MAIN)
    rate = rate or config.EN_TTS_RATE

    out = _cache_path(text, voice, rate)
    if out.exists() and out.stat().st_size > 0:
        return out

    provider = config.EN_TTS_PROVIDER.lower()
    if provider == "edge":
        await _synth_edge(text, voice, rate, out)
    elif provider == "openai":
        await _synth_openai(text, voice, out)
    else:
        raise ValueError(f"Unknown TTS provider: {provider}")
    return out


async def _synth_edge(text: str, voice: str, rate: str, out: Path):
    """edge-tts: бесплатно, нейросетевые голоса Microsoft Edge."""
    try:
        import edge_tts
    except ImportError:
        raise RuntimeError("edge-tts не установлен. pip install edge-tts")

    communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await communicate.save(str(out))
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"edge-tts не сгенерировал файл для: {text[:50]}")
    logger.debug("TTS edge: %s -> %s", text[:30], out.name)


async def _synth_openai(text: str, voice: str, out: Path):
    """OpenAI TTS — платный, fallback. voice: alloy/echo/fable/onyx/nova/shimmer."""
    import openai
    client = openai.AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    # Маппинг naming на openai голоса
    if voice.startswith("en-GB"):
        v = "fable"
    elif voice.startswith("en-US"):
        v = "alloy"
    else:
        v = "alloy"
    response = await client.audio.speech.create(
        model="tts-1", voice=v, input=text, response_format="opus"
    )
    out.write_bytes(response.read())
    logger.debug("TTS openai: %s -> %s", text[:30], out.name)


async def synthesize_to_ogg(text: str, **kwargs) -> bytes:
    """Хелпер: вернуть байты файла для прямой отправки в Telegram."""
    path = await synthesize(text, **kwargs)
    return path.read_bytes()
