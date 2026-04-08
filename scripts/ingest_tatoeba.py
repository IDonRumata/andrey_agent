"""
Загрузка англо-русских пар Tatoeba в english_sentences.

Tatoeba раздаёт TSV дампы:
  https://downloads.tatoeba.org/exports/sentences_in_lists.tar.bz2
  https://downloads.tatoeba.org/exports/per_language/eng_sentences.tsv.bz2
  https://downloads.tatoeba.org/exports/per_language/rus_sentences.tsv.bz2
  https://downloads.tatoeba.org/exports/links.tar.bz2

Для упрощения мы качаем готовый сэмпл (если есть инет) либо используем
файл, положенный вручную в data/english/sources/tatoeba_eng_rus.tsv

Формат TSV:
    en_id<TAB>en_sentence<TAB>ru_sentence

Запуск:
    python -m scripts.ingest_tatoeba --limit 5000
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import database as db

logger = logging.getLogger("ingest_tatoeba")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


SOURCES_DIR = config.EN_DATA_DIR / "sources"
SOURCES_DIR.mkdir(exist_ok=True)
DEFAULT_FILE = SOURCES_DIR / "tatoeba_eng_rus.tsv"

DOWNLOAD_HINT = """
Файл Tatoeba не найден. Готовый сэмпл (5-10k пар) можно собрать так:

1. Скачать дампы:
   curl -O https://downloads.tatoeba.org/exports/per_language/eng_sentences.tsv.bz2
   curl -O https://downloads.tatoeba.org/exports/per_language/rus_sentences.tsv.bz2
   curl -O https://downloads.tatoeba.org/exports/links.tar.bz2
   bunzip2 *.bz2 && tar -xf links.tar

2. Собрать пары EN↔RU (один способ):
   awk -F'\\t' 'NR==FNR{{en[$1]=$3; next}} ($1 in en) && ($2 in ru) {{print en[$1]"\\t"ru[$2]}}' \\
       eng_sentences.tsv links.csv > pairs.tsv

3. Положить в:
   {path}

Или возьми любой готовый CSV из открытых источников. Поддерживаемый формат:
   en_sentence<TAB>ru_sentence
""".strip()


def difficulty_from_length(text: str) -> int:
    """Очень грубая прикидка сложности по длине предложения."""
    n = len(text.split())
    if n <= 4:
        return 1
    if n <= 7:
        return 2
    if n <= 10:
        return 3
    if n <= 14:
        return 4
    return 5


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(DEFAULT_FILE))
    parser.add_argument("--limit", type=int, default=10000)
    parser.add_argument("--max-len", type=int, default=15, help="Skip sentences longer than N words")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(DOWNLOAD_HINT.format(path=path))
        return

    await db.init_db()

    added = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if added >= args.limit:
                break
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            en, ru = parts[-2].strip(), parts[-1].strip()
            if not en or not ru:
                continue
            if len(en.split()) > args.max_len:
                continue
            await db.en_add_sentence(
                text_en=en, text_ru=ru, type="example",
                difficulty=difficulty_from_length(en),
                source="tatoeba",
            )
            added += 1
            if added % 500 == 0:
                logger.info("Tatoeba progress: %d", added)

    print(f"Tatoeba загружен: {added} пар EN↔RU")


if __name__ == "__main__":
    asyncio.run(main())
