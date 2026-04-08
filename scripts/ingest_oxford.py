"""
Загрузка Oxford 3000 / 5000 в english_chunks с тегами по CEFR.
Источник: открытые списки. Файл oxford_3000.txt должен лежать в data/english/sources/.

Формат файла (один на строку):
    word /ipa/ A1 noun
    word A2 verb
    word B1
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import database as db

logger = logging.getLogger("ingest_oxford")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


SOURCES_DIR = config.EN_DATA_DIR / "sources"
SOURCES_DIR.mkdir(exist_ok=True)

DEFAULT_FILE = SOURCES_DIR / "oxford_3000.txt"

DOWNLOAD_HINT = """
Файл со списком Oxford 3000 не найден. Скачай вручную (открытый список):
  https://www.oxfordlearnersdictionaries.com/wordlists/oxford3000-5000
  или с GitHub-зеркал: https://github.com/sapbmw/The-Oxford-3000

Сохрани как: {path}
Формат — одно слово на строку. Опционально через табуляцию: word\\tA1\\tnoun
""".strip()


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default=str(DEFAULT_FILE))
    parser.add_argument("--cefr", default=None, help="Override CEFR if file has no levels")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(DOWNLOAD_HINT.format(path=path))
        return

    await db.init_db()

    added = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("\t")
            if not parts or not parts[0]:
                continue
            word = parts[0].strip().lower()
            cefr = (parts[1].strip() if len(parts) > 1 else args.cefr) or "A2"
            if not word.replace("'", "").replace("-", "").replace(" ", "").isalpha():
                continue
            cid = await db.en_add_chunk(
                chunk=word, translation_ru="", cefr=cefr,
                type="word", source="oxford_3000",
            )
            if cid:
                added += 1

    print(f"Oxford 3000 загружен: {added} слов")
    print("Переводы пустые — переводить будет handlers/english.py через Haiku по запросу,")
    print("результат кешируется. Это дешевле, чем переводить 3000 слов сразу.")


if __name__ == "__main__":
    asyncio.run(main())
