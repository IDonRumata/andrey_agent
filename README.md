# AI-агент "Андрей"

Персональный AI-ассистент в Telegram для предпринимателя-дальнобойщика.

## Быстрый старт

```bash
# 1. Клонировать на VPS
scp -r andrey_agent/ ubuntu@your-vps:/home/ubuntu/

# 2. На VPS
cd /home/ubuntu/andrey_agent
cp .env.example .env
nano .env  # заполнить токены

# 3. Установка и запуск
bash deploy/setup.sh
```

## Переменные окружения (.env)

| Переменная | Описание |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Токен от @BotFather |
| `ANTHROPIC_API_KEY` | Ключ Anthropic API |
| `OPENAI_API_KEY` | Ключ OpenAI (для Whisper) |
| `ALLOWED_USER_ID` | Твой Telegram ID (только ты) |
| `TIMEZONE` | `Europe/Minsk` |

## Команды бота

### Задачи и идеи
- `/tasks` — активные задачи (`/tasks grafin` — по проекту)
- `/ideas` — список идей
- `/done [ID/текст]` — закрыть задачу
- `/idea2task [ID]` — идея → задача
- `/clear` — архивировать выполненные

### Проекты
- `/projects` — список проектов
- `/project [назв]` — база проекта
- `/new [назв]` — создать проект
- `/brain` — идеи за 7 дней
- `/summary [назв]` — AI-резюме проекта
- `/archive [назв]` — в архив

### Контент
- `/post [тема]` — черновик поста TG/Instagram
- `/tg [тема]` — пост для канала Графин
- `/caption [описание]` — подпись Reels/Shorts
- `/hook [тема]` — 3 цепляющих заголовка
- `/rewrite [текст]` — рерайт под бренд

### Метрики
- `/m` — ввод метрик (пошагово или `/m продажи=2, отжимания=50`)
- `/stats` — сводка за неделю (`/stats месяц`)
- `/pushups [N]` — быстро записать отжимания

### Прочее
- `/briefing` — еженедельный отчёт (авто: вс 20:00)
- `/find [запрос]` — веб-поиск через Claude
- `/cost` — расходы на AI за месяц

### Свободный ввод
Текст или голос без команды — агент сам классифицирует (задача/идея/вопрос).

## Управление на VPS

```bash
sudo systemctl status andrey-agent    # статус
sudo systemctl restart andrey-agent   # перезапуск
sudo systemctl stop andrey-agent      # остановка
journalctl -u andrey-agent -f         # логи realtime
bash deploy/update.sh                 # обновление после правок
bash deploy/backup.sh                 # ручной бэкап БД
```

## Бэкап (автоматический)

```bash
# Добавить в cron:
crontab -e
0 3 * * * /home/ubuntu/andrey_agent/deploy/backup.sh >> /home/ubuntu/andrey_agent/logs/backup.log 2>&1
```

Бэкап отправляется в Telegram как документ + хранится локально 30 дней.

## Архитектура экономии токенов

1. **Локальный классификатор** — regex покрывает ~70% сообщений (0 токенов)
2. **Haiku для рутины** — классификация, подписи (~20x дешевле Sonnet)
3. **Sonnet для экспертизы** — советы, посты, диалог
4. **Кеш ответов** — повторные вопросы = 0 токенов
5. **История 10 сообщений** — только для диалога, не для команд
6. **Трекер расходов** — `/cost` показывает куда уходят деньги

Ожидаемые расходы: **$5-10/мес** при 500-1000 запросов.

## Обновление системного промпта

Файл `config.py`, переменная `SYSTEM_PROMPT`. Обновить → `sudo systemctl restart andrey-agent`.

## Структура

```
andrey_agent/
├── bot.py              # точка входа
├── config.py           # токены, промпт
├── database.py         # SQLite (9 таблиц)
├── handlers/
│   ├── tasks.py        # /tasks, /done, /clear
│   ├── ideas.py        # /ideas, /delidea, /idea2task
│   ├── content.py      # /post, /caption, /hook, /tg, /rewrite
│   ├── metrics.py      # /m, /stats, /pushups
│   ├── projects.py     # /projects, /project, /new, /brain, /summary
│   ├── briefing.py     # /briefing + авто вс 20:00
│   ├── search.py       # /find, /watch, /watchlist
│   ├── cost.py         # /cost
│   ├── voice.py        # голос → Whisper → роутинг
│   └── chat.py         # свободный текст → роутинг
├── services/
│   ├── claude_api.py   # Haiku/Sonnet + кеш + учёт токенов
│   ├── whisper_api.py  # транскрибация
│   ├── classifier.py   # локальный regex-классификатор
│   └── scheduler.py    # APScheduler
├── deploy/
│   ├── andrey-agent.service  # systemd
│   ├── setup.sh        # первоначальная установка
│   ├── update.sh       # обновление
│   └── backup.sh       # бэкап БД → Telegram
├── data/               # agent.db (создаётся автоматически)
└── logs/               # agent.log (ротация 5МБ x 3)
```
