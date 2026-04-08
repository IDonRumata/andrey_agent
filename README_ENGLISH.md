# English Module — A1→B1 для Андрея

Изолированный модуль изучения английского языка внутри `andrey_agent`.
Готов к выносу в отдельный продукт (мультитенантность заложена в схему БД).

## Что внутри

- **Учебник:** Outcomes Elementary (Cengage / NGL), 16 юнитов от A1 до B1
- **TTS:** edge-tts (бесплатно), голос по умолчанию `en-GB-SoniaNeural` (BrE)
- **SRS:** SM-2 алгоритм с двумя очередями (passive → active)
- **Speaking eval:** Whisper + Claude Sonnet по CEFR-рубрике
- **Адаптация:** темп подстраивается под retention последних 3 дней
- **Stoимость:** ~$2-3/мес (только speaking eval + парсинг отчётов через LLM)

## Файлы

```
services/english/
  __init__.py
  tts.py              # edge-tts с кешем по хешу содержимого
  srs.py              # SM-2 обёртка
  exercises.py        # генераторы 4 типов упражнений из БД
  speaking_eval.py    # Claude Sonnet по CEFR-рубрике
  lesson_parser.py    # Claude Haiku парсинг отчёта с урока
  curriculum.py       # адаптивный планировщик дня
  assessment.py       # placement test (25 vocab + 15 grammar + 1 speaking)

handlers/english.py   # все команды, FSM, inline-меню

scripts/
  ingest_outcomes.py  # парсер Student's Book + Workbook PDF
  ingest_oxford.py    # Oxford 3000/5000
  ingest_tatoeba.py   # пары EN↔RU из Tatoeba
  render_audio.py     # пакетная генерация TTS

data/english/
  audio/              # pre-rendered .ogg
  tts_cache/          # on-demand кеш TTS
  sources/            # внешние словари (oxford_3000.txt, tatoeba.tsv)
```

## Команды бота

| Команда | Что делает |
|---|---|
| `/en` | Главное меню (inline-кнопки) |
| `/en_start` | Placement test — оценка уровня (10 мин) |
| `/en_unit N` | Установить текущий юнит (синхронизация с учителем) |
| `/en_block` | Блок упражнений ~10 мин (6 заданий) |
| `/en_review` | Повторение SRS-карточек на сегодня |
| `/en_speak` | Speaking practice + оценка по CEFR |
| `/en_lesson` | Отчёт с живого занятия (парсится в БД) |
| `/en_homework` | Активные домашки от учителя |
| `/en_progress` | Прогресс, статистика, контент в БД |
| `/en_voice X` | Сменить голос: uk_f / uk_m / us_f / us_m |
| `/en_grammar тема` | Справка по грамматике |
| `/vocab слово` | Добавить/найти слово (legacy) |

## Деплой на VPS — пошагово

### 1. Установить системные зависимости

```bash
ssh root@185.229.251.166
cd /root/andrey_agent
git pull
pip install -r requirements.txt
# poppler не нужен — pdfplumber работает без него
```

### 2. Залить PDF учебника на VPS

С локальной машины:
```bash
scp "C:/Users/Asus/Downloads/Telegram Desktop/532_1_Outcomes_Elementary_Student's_Book_2015,_2ed,_213p.pdf" \
    root@185.229.251.166:/root/andrey_agent/data/english/sources/sb.pdf

scp "C:/Users/Asus/Downloads/Telegram Desktop/532_7- Outcomes. Elementary_Workbook_2017, 2ed, 137p.pdf" \
    root@185.229.251.166:/root/andrey_agent/data/english/sources/wb.pdf
```

В `.env` на VPS добавить пути:
```
EN_OUTCOMES_SB_PDF=/root/andrey_agent/data/english/sources/sb.pdf
EN_OUTCOMES_WB_PDF=/root/andrey_agent/data/english/sources/wb.pdf
```

### 3. Инициализировать БД (создаст новые таблицы)

```bash
cd /root/andrey_agent
python -c "import asyncio, database; asyncio.run(database.init_db())"
```

### 4. Загрузить учебник в БД

```bash
python -m scripts.ingest_outcomes
```

Проверь финальную статистику в выводе. Должно быть ~16 юнитов и сотни чанков.

### 5. (Опционально) Загрузить Oxford 3000 и Tatoeba

```bash
# Oxford 3000 — открытый список, скачать вручную:
# https://github.com/sapbmw/The-Oxford-3000/blob/master/Oxford%203000.txt
wget -O data/english/sources/oxford_3000.txt \
    https://raw.githubusercontent.com/sapbmw/The-Oxford-3000/master/Oxford%203000.txt
python -m scripts.ingest_oxford

# Tatoeba (нужен .tsv с парами en↔ru — см. инструкцию в скрипте)
python -m scripts.ingest_tatoeba --limit 5000
```

### 6. Сгенерить TTS-аудио (один раз, ~30 мин)

```bash
python -m scripts.render_audio --batch 5
```

Файлы лягут в `data/english/tts_cache/`. После этого 95% упражнений работают без LLM.

### 7. Перезапустить бота

```bash
systemctl restart andrey-agent
journalctl -u andrey-agent -f
```

В Telegram открыть бота, отправить `/en_start` — пройти placement test.

## Локальная разработка (Windows)

```powershell
cd "D:\Claude Code doc\andrey_agent"
pip install -r requirements.txt

# Парсинг учебника локально
python -m scripts.ingest_outcomes `
  --sb "C:\Users\Asus\Downloads\Telegram Desktop\532_1_Outcomes_Elementary_Student's_Book_2015,_2ed,_213p.pdf" `
  --wb "C:\Users\Asus\Downloads\Telegram Desktop\532_7- Outcomes. Elementary_Workbook_2017, 2ed, 137p.pdf"

python -m scripts.render_audio
```

## Архитектурные решения

### Почему всё в одном боте

См. предыдущее обсуждение: единая точка входа голосом, общая инфраструктура,
кросс-модульный контекст. Изоляция кода поддерживается на уровне директорий
(`services/english/`) и префиксов таблиц (`english_*`), не на уровне процесса.

### Multitenancy ready

Все per-user таблицы (`english_profile`, `english_srs`, `english_sessions`,
`english_tests`, `english_homework`, `english_personal_examples`) содержат
колонку `user_id`. Контент-таблицы (`english_units`, `english_chunks`, ...)
общие для всех пользователей. При выносе в SaaS — нужно только заменить
hard-coded `ALLOWED_USER_ID` на контекст из middleware.

Заглушка под биллинг — `english_subscriptions(user_id, plan, expires_at)`.
Проверка лицензии — пустая функция, всегда возвращает True.

### Минимизация LLM

| Операция | LLM? |
|---|---|
| Показ чанка/примера/перевода | ❌ (SQL) |
| Gap-fill, multiple choice | ❌ (БД) |
| Озвучка | ❌ (pre-rendered .ogg) |
| Объяснение грамматики | ❌ (БД) → Sonnet с кешем (fallback) |
| Оценка speaking | ✅ Sonnet (ядро ценности) |
| Парсинг отчёта с урока | ✅ Haiku |
| Перевод незнакомого слова | ✅ Haiku с кешем (1 раз на слово) |

### Голос TTS

По умолчанию `en-GB-SoniaNeural` — британский, чистый RP, под учебник Outcomes (UK).
Сменить: `/en_voice uk_m | us_f | us_m`. Или в `.env`:
```
EN_TTS_VOICE_MAIN=en-US-AriaNeural
```

Если захочется OpenAI TTS (платно, но качественнее):
```
EN_TTS_PROVIDER=openai
```

## Что ещё планируется

- Weekly test (пятница) с графиком прогресса
- Monthly CEFR re-assessment (тот же placement test)
- Role-play диалоги из `english_dialogs`
- Listening comprehension (длинные предложения из Tatoeba + 3 вопроса)
- Минимальные пары для произношения
- Дайджест для учителя (что прошли за неделю)

## Вынос в отдельный продукт

Когда придёт время монетизации, потребуется:

1. Скопировать `services/english/`, `handlers/english.py`, `scripts/ingest_*`,
   `scripts/render_audio.py` в новый репозиторий.
2. Скопировать миграции таблиц с префиксом `english_*` из `database.py`.
3. Заменить `ALLOWED_USER_ID` на полноценный auth (Telegram login).
4. Заполнить функцию `check_access(user_id)` логикой на основе
   `english_subscriptions`.
5. Вынести `data/english/` в S3 или volume.

Оценка работ — пара дней. Архитектура к этому готова.
