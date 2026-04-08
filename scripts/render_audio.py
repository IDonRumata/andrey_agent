"""
Пакетная генерация TTS-аудио для всех чанков, у которых audio_path IS NULL.
По умолчанию использует edge-tts (бесплатно).

Запуск:
    python -m scripts.render_audio
    python -m scripts.render_audio --limit 200
    python -m scripts.render_audio --batch 10  # параллельность
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import database as db
from services.english.tts import synthesize

logger = logging.getLogger("render_audio")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def render_one(chunk: dict, semaphore: asyncio.Semaphore) -> bool:
    async with semaphore:
        try:
            # Озвучка самого чанка
            chunk_audio = await synthesize(chunk["chunk"])
            example_audio = None
            if chunk.get("example_en"):
                example_audio = await synthesize(chunk["example_en"])

            await db.en_set_chunk_audio(
                chunk["id"],
                str(chunk_audio.relative_to(config.BASE_DIR)),
                str(example_audio.relative_to(config.BASE_DIR)) if example_audio else None,
            )
            return True
        except Exception as e:
            logger.warning("Render failed for chunk %d (%s): %s", chunk["id"], chunk["chunk"], e)
            return False


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=2000, help="Max chunks per run")
    parser.add_argument("--batch", type=int, default=5, help="Concurrent TTS requests")
    args = parser.parse_args()

    await db.init_db()

    chunks = await db.en_get_chunks_without_audio(limit=args.limit)
    if not chunks:
        print("Все чанки уже озвучены.")
        return

    print(f"Генерирую TTS для {len(chunks)} чанков (provider={config.EN_TTS_PROVIDER}, voice={config.EN_TTS_VOICE_MAIN})...")
    sem = asyncio.Semaphore(args.batch)
    tasks = [render_one(c, sem) for c in chunks]
    results = await asyncio.gather(*tasks)
    ok = sum(1 for r in results if r)
    print(f"Готово: {ok}/{len(chunks)} успешно. Кеш: {config.EN_TTS_CACHE_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
