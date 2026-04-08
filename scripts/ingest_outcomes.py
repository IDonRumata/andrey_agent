"""
Парсер Outcomes Elementary (Student's Book + Workbook) → english_units / chunks / sentences / exercises / grammar.

Запуск:
    python3 -m scripts.ingest_outcomes
    python3 -m scripts.ingest_outcomes --sb path/to/SB.pdf --wb path/to/WB.pdf
    python3 -m scripts.ingest_outcomes --ocr          # OCR-режим для сканов

Автоматически определяет: если pdfplumber не получает текст (скан) и установлен
pytesseract — переключается на OCR. Требует: tesseract-ocr + pytesseract + Pillow.

Установка OCR на Ubuntu:
    apt-get install -y tesseract-ocr tesseract-ocr-eng
    pip install pytesseract
"""
import argparse
import asyncio
import logging
import re
import sys
from pathlib import Path

# Чтобы импорты database/config работали при запуске как модуль
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import database as db

logger = logging.getLogger("ingest_outcomes")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


# Известное оглавление Outcomes Elementary (из распарсенных страниц 2-5)
OUTCOMES_ELEM_UNITS = [
    # (number, title, page_start, page_end, topic, grammar_focus, vocab_focus, cefr)
    (1,  "People and Places", 6,   13, "introductions",
     ["be", "Present simple", "there is/are"],
     ["Countries", "Jobs and workplaces", "Describing places"], "A1"),
    (2,  "Free Time",         14,  21, "hobbies",
     ["Verb patterns", "Adverbs of frequency", "Countable/uncountable nouns"],
     ["Free-time activities", "Daily life", "In an English class"], "A1"),
    (3,  "Home",               24,  31, "home and area",
     ["Prepositions of place", "Pronouns / possessives", "can / can't"],
     ["Local facilities", "In the house", "Collocations"], "A1"),
    (4,  "Holidays",           32,  39, "past and holidays",
     ["Past simple", "Past simple negatives", "Past simple questions"],
     ["Holiday and weekend activities", "Months, seasons and dates"], "A2"),
    (5,  "Shops",              42,  49, "shopping",
     ["this/these/that/those", "Present continuous"],
     ["Describing what you want", "Department stores"], "A2"),
    (6,  "Education",          50,  57, "school and study",
     ["Modifiers", "Comparatives"],
     ["School and university", "Courses", "Languages"], "A2"),
    (7,  "People I Know",      60,  67, "family and people",
     ["Auxiliary verbs", "have to / don't have to"],
     ["Relationships", "Jobs and activities at home", "Describing people"], "A2"),
    (8,  "Plans",              68,  75, "future plans",
     ["going to", "would like to + verb"],
     ["Common activities", "Life events and plans", "For and against"], "A2"),
    (9,  "Experiences",        78,  85, "life experiences",
     ["Present perfect", "Past participles"],
     ["Problems", "Describing experiences"], "A2"),
    (10, "Travel",             86,  93, "transport and travel",
     ["too much/many", "not enough", "Superlatives"],
     ["Trains and stations", "Transport"], "A2"),
    (11, "Food",               96, 103, "food and restaurants",
     ["me too / me neither", "Explaining quantity"],
     ["Restaurants", "Food", "Forming negatives with un-"], "B1"),
    (12, "Feelings",          104, 111, "health and feelings",
     ["should / shouldn't", "because, so, after"],
     ["Health problems", "Feelings", "In the news"], "B1"),
    (13, "Nature",            114, 121, "weather and nature",
     ["might", "be going to", "Present perfect to say how long"],
     ["Weather", "Countryside / city", "Animals"], "B1"),
    (14, "Opinions",          122, 129, "media and opinions",
     ["will / won't for predictions", "Adjective + verb"],
     ["Films, plays, musicals", "Life and society"], "B1"),
    (15, "Technology",        132, 139, "tech and internet",
     ["be thinking of + -ing", "Adverbs"],
     ["Machines and technology", "Computers and internet"], "B1"),
    (16, "Love",              140, 147, "relationships",
     ["Past continuous", "will / won't for promises"],
     ["Love and marriage"], "B1"),
]


# ─────────────────────── PDF utils ───────────────────────

def _is_scanned(pdf_path: Path, sample_pages: int = 3) -> bool:
    """Проверить первые N страниц — если текста нет, значит скан."""
    try:
        import pdfplumber
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages[:sample_pages]:
                txt = page.extract_text() or ""
                if len(txt.strip()) > 50:
                    return False
        return True
    except Exception:
        return True


def _extract_page_ocr(pdf_path: Path, page_index: int) -> str:
    """OCR одной страницы через pytesseract."""
    try:
        import pdfplumber
        import pytesseract
        from PIL import Image
        import io

        with pdfplumber.open(str(pdf_path)) as pdf:
            if page_index >= len(pdf.pages):
                return ""
            page = pdf.pages[page_index]
            # Рендерим страницу в изображение с разрешением 200 dpi
            img = page.to_image(resolution=200).original
            # pytesseract принимает PIL Image
            text = pytesseract.image_to_string(img, lang="eng", config="--psm 3")
            return text
    except Exception as e:
        logger.warning("OCR page %d failed: %s", page_index + 1, e)
        return ""


def extract_pages(pdf_path: Path, page_range: tuple[int, int],
                  force_ocr: bool = False) -> list[str]:
    """Извлечь текст со страниц [start, end] (1-indexed inclusive).
    Автоматически переключается на OCR если PDF — скан."""
    try:
        import pdfplumber
    except ImportError:
        logger.error("pdfplumber не установлен. pip install pdfplumber")
        raise

    use_ocr = force_ocr or _is_scanned(pdf_path)
    if use_ocr:
        logger.info("PDF определён как скан — использую OCR (медленнее, но точнее)")

    out = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i in range(page_range[0] - 1, min(page_range[1], len(pdf.pages))):
            if use_ocr:
                txt = _extract_page_ocr(pdf_path, i)
            else:
                try:
                    txt = pdf.pages[i].extract_text() or ""
                except Exception as e:
                    logger.warning("Page %d extract failed: %s", i + 1, e)
                    txt = ""
            out.append(txt)
    return out


# ─────────────────────── Парсеры контента ───────────────────────

# Слово/чанк EN с переводом RU после тире/двоеточия/таба
RE_VOCAB_LINE = re.compile(
    r"^\s*([a-z][a-zA-Z'\- ]{1,40})\s*[—\-–:]\s*([а-яёА-ЯЁ][а-яёА-ЯЁ ,/()\-]{1,60})\s*$"
)

# Просто английская фраза, латиница + пробелы (для examples в диалогах)
RE_EN_SENTENCE = re.compile(r"^[A-Z][A-Za-z0-9 ',.!?\-]{8,120}[.!?]$")

# Speaker pattern для диалогов: "A: Hello." / "B: Hi there."
RE_DIALOG_TURN = re.compile(r"^([AB]):\s*(.+)$")

# Gap-fill: предложение с пропуском "___" или "_____"
RE_GAP_FILL = re.compile(r"(.+?)_{2,}(.+)")


def parse_vocab_lines(text: str) -> list[tuple[str, str]]:
    """Найти строки 'word — перевод'."""
    out = []
    for line in text.splitlines():
        m = RE_VOCAB_LINE.match(line.strip())
        if m:
            chunk = m.group(1).strip().lower()
            translation = m.group(2).strip()
            if 2 <= len(chunk) <= 40 and 2 <= len(translation) <= 60:
                out.append((chunk, translation))
    return out


def parse_dialog(text: str) -> list[dict]:
    """Найти блоки диалогов A:/B:."""
    turns = []
    for line in text.splitlines():
        m = RE_DIALOG_TURN.match(line.strip())
        if m:
            turns.append({"speaker": m.group(1), "text_en": m.group(2).strip(), "text_ru": ""})
    return turns


def parse_example_sentences(text: str, max_n: int = 30) -> list[str]:
    out = []
    for line in text.splitlines():
        s = line.strip()
        if RE_EN_SENTENCE.match(s):
            out.append(s)
            if len(out) >= max_n:
                break
    return out


def parse_gap_fills(text: str, max_n: int = 20) -> list[dict]:
    out = []
    for line in text.splitlines():
        s = line.strip()
        m = RE_GAP_FILL.match(s)
        if m and 5 < len(s) < 200:
            out.append({"prompt": s, "answer": ""})  # answer заполняется через answer key
            if len(out) >= max_n:
                break
    return out


# ─────────────────────── Главный цикл ───────────────────────

async def ingest_student_book(pdf_path: Path):
    if not pdf_path.exists():
        logger.error("Student's Book не найден: %s", pdf_path)
        return
    logger.info("Парсю Student's Book: %s", pdf_path)

    total_units = total_chunks = total_sentences = total_dialogs = 0

    for (num, title, p_start, p_end, topic, grammar_list, vocab_list, cefr) in OUTCOMES_ELEM_UNITS:
        unit_id = await db.en_upsert_unit(
            source="outcomes_elem", number=num, title=title,
            cefr=cefr, topic=topic,
            grammar_focus=grammar_list, vocab_focus=vocab_list,
            page_start=p_start, page_end=p_end,
        )
        total_units += 1

        # Грамматическое правило (заглушка с метаданными — детальный текст добавит ingest_grammar_ref)
        for g in grammar_list:
            await db.en_add_grammar(
                topic=g, rule_ru=f"См. учебник Outcomes Elementary, Unit {num}. Тема: {g}.",
                rule_en=g, examples=[], common_mistakes=[], unit_id=unit_id,
                source="outcomes_elem",
            )

        # Парсим страницы юнита
        pages_text = extract_pages(pdf_path, (p_start, p_end))
        unit_chunks = unit_sentences = unit_dialogs = 0

        for page_idx, text in enumerate(pages_text):
            page_num = p_start + page_idx

            # Чанки
            for chunk, translation in parse_vocab_lines(text):
                cid = await db.en_add_chunk(
                    chunk=chunk, translation_ru=translation,
                    unit_id=unit_id, type="word", cefr=cefr,
                    source="outcomes_elem", source_page=page_num,
                )
                if cid:
                    unit_chunks += 1

            # Примеры
            for sent in parse_example_sentences(text, max_n=10):
                await db.en_add_sentence(
                    text_en=sent, unit_id=unit_id, type="example",
                    source="outcomes_elem", source_page=page_num,
                )
                unit_sentences += 1

            # Диалоги
            turns = parse_dialog(text)
            if len(turns) >= 2:
                await db.en_add_dialog(
                    title=f"Unit {num} dialog (p.{page_num})",
                    turns=turns, unit_id=unit_id,
                    source="outcomes_elem",
                )
                unit_dialogs += 1

        total_chunks += unit_chunks
        total_sentences += unit_sentences
        total_dialogs += unit_dialogs
        logger.info(
            "Unit %d %s: chunks=%d sentences=%d dialogs=%d (pp.%d-%d)",
            num, title, unit_chunks, unit_sentences, unit_dialogs, p_start, p_end,
        )

    logger.info(
        "SB готов: units=%d chunks=%d sentences=%d dialogs=%d",
        total_units, total_chunks, total_sentences, total_dialogs,
    )


async def ingest_workbook(pdf_path: Path):
    if not pdf_path.exists():
        logger.error("Workbook не найден: %s", pdf_path)
        return
    logger.info("Парсю Workbook: %s", pdf_path)

    # Workbook ~8 страниц на юнит, начинается с p.4
    pages_per_unit = 8
    base_page = 4
    total_ex = 0

    for num in range(1, 17):
        unit = await db.en_get_unit_by_number(num)
        if not unit:
            continue
        wb_start = base_page + (num - 1) * pages_per_unit
        wb_end = wb_start + pages_per_unit - 1

        pages_text = extract_pages(pdf_path, (wb_start, wb_end))
        unit_ex = 0

        for page_idx, text in enumerate(pages_text):
            page_num = wb_start + page_idx
            for ex in parse_gap_fills(text, max_n=15):
                # answer пустой — нужен answer key (обычно в конце WB)
                # Сохраняем как pseudo-exercise, чтобы хотя бы prompt был доступен.
                if not ex["prompt"].strip():
                    continue
                eid = await db.en_add_exercise(
                    type="gap_fill", prompt=ex["prompt"], answer=ex["answer"],
                    unit_id=unit["id"], source="outcomes_wb", source_page=page_num,
                )
                unit_ex += 1
        total_ex += unit_ex
        logger.info("Unit %d WB: exercises=%d", num, unit_ex)

    logger.info("WB готов: exercises=%d", total_ex)


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sb", default=config.EN_OUTCOMES_SB_PDF, help="Path to Student's Book PDF")
    parser.add_argument("--wb", default=config.EN_OUTCOMES_WB_PDF, help="Path to Workbook PDF")
    parser.add_argument("--skip-sb", action="store_true")
    parser.add_argument("--skip-wb", action="store_true")
    parser.add_argument("--ocr", action="store_true", help="Force OCR mode (for scanned PDFs)")
    args = parser.parse_args()

    # Передаём force_ocr в extract_pages через monkey-patch аргумента
    if args.ocr:
        import functools
        original_extract = extract_pages
        def extract_pages(path, rng, force_ocr=False):  # noqa: F811
            return original_extract(path, rng, force_ocr=True)

    await db.init_db()

    if not args.skip_sb:
        await ingest_student_book(Path(args.sb))
    if not args.skip_wb:
        await ingest_workbook(Path(args.wb))

    # Финальная статистика
    units = await db.en_list_units()
    chunks = await db.en_count_chunks()
    sentences = await db.en_count_sentences()
    exercises = await db.en_count_exercises()
    print()
    print("=" * 60)
    print(f"  Outcomes Elementary загружен в БД")
    print("=" * 60)
    print(f"  Юнитов:        {len(units)}")
    print(f"  Чанков:        {chunks}")
    print(f"  Предложений:   {sentences}")
    print(f"  Упражнений:    {exercises}")
    print("=" * 60)
    print()
    print("Дальше:")
    print("  python -m scripts.render_audio        # сгенерить TTS для всех чанков")
    print("  python -m scripts.ingest_oxford       # добавить Oxford 3000")
    print("  python -m scripts.ingest_tatoeba      # добавить примеры из Tatoeba")


if __name__ == "__main__":
    asyncio.run(main())
