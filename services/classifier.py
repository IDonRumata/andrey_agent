"""
Локальный классификатор сообщений — без вызова Claude.
Покрывает 60-70% входящих сообщений regex-паттернами.
Claude вызывается только для неоднозначных случаев.
"""
import re

# Статические алиасы проектов — расширяется при добавлении нового
PROJECT_ALIASES = {
    "графин": "grafin",
    "grafin": "grafin",
    "кронон": "kronon",
    "kronon": "kronon",
    "multitrade": "kronon",
    "риэлтор": "realtor",
    "realtor": "realtor",
    "фокус": "fokus",
    "fokus": "fokus",
    "sp500": "sp500-bounce-bot",
    "s&p500": "sp500-bounce-bot",
    "bounce": "sp500-bounce-bot",
    "скринер": "sp500-bounce-bot",
    "sp500-bounce-bot": "sp500-bounce-bot",
    "sp500bounchbot": "sp500-bounce-bot",
}

# Динамические алиасы — подгружаются из БД при старте
_dynamic_projects: dict[str, int] = {}  # name_lower -> project_id


async def load_projects_from_db():
    """Подгрузить проекты из SQLite для автоопределения."""
    import database as db
    projects = await db.get_projects(include_archive=False)
    _dynamic_projects.clear()
    for p in projects:
        _dynamic_projects[p["name"].lower()] = p["id"]


# --- Regex-паттерны для типов сообщений ---

TASK_PATTERNS = [
    re.compile(r"^задача[\s:]+(.+)", re.IGNORECASE | re.DOTALL),
    re.compile(r"^надо[\s:]+(.+)", re.IGNORECASE | re.DOTALL),
    re.compile(r"^нужно[\s:]+(.+)", re.IGNORECASE | re.DOTALL),
    re.compile(r"^сделать[\s:]+(.+)", re.IGNORECASE | re.DOTALL),
    re.compile(r"^todo[\s:]+(.+)", re.IGNORECASE | re.DOTALL),
    re.compile(r"^напомни[\s:]+(.+)", re.IGNORECASE | re.DOTALL),
    re.compile(r"^запланировать[\s:]+(.+)", re.IGNORECASE | re.DOTALL),
    re.compile(r"^добавь задачу[\s:]+(.+)", re.IGNORECASE | re.DOTALL),
]

IDEA_PATTERNS = [
    re.compile(r"^идея[\s:]+(.+)", re.IGNORECASE | re.DOTALL),
    re.compile(r"^а что если[\s:]+(.+)", re.IGNORECASE | re.DOTALL),
    re.compile(r"^можно было бы[\s:]+(.+)", re.IGNORECASE | re.DOTALL),
    re.compile(r"^мысль[\s:]+(.+)", re.IGNORECASE | re.DOTALL),
    re.compile(r"^придумал[\s:]+(.+)", re.IGNORECASE | re.DOTALL),
]

PROJECT_PATTERN = re.compile(
    r"^по проекту\s+(\S+)[\s\-—:,]*(.+)", re.IGNORECASE | re.DOTALL
)

# "добавление в проект X:", "обновление в проект X:", "в проект X:"
PROJECT_NOTE_PATTERN = re.compile(
    r"^(?:добавление|обновление|заметка|запись)\s+(?:в|по)\s+проект[уа]?\s+(\S+)[:\s\-—]*(.*)",
    re.IGNORECASE | re.DOTALL,
)

SEARCH_PATTERNS = [
    re.compile(r"^найди\s+", re.IGNORECASE),
    re.compile(r"^поищи\s+", re.IGNORECASE),
    re.compile(r"^где купить\s+", re.IGNORECASE),
    re.compile(r"^сколько стоит\s+", re.IGNORECASE),
    re.compile(r"^как добраться\s+", re.IGNORECASE),
    re.compile(r"^сравни\s+", re.IGNORECASE),
    re.compile(r"^где найти\s+", re.IGNORECASE),
    re.compile(r"^подбери\s+", re.IGNORECASE),
]

# Паттерны для метрик и физических упражнений
METRIC_PATTERNS = [
    # Отжимания + Whisper-варианты
    re.compile(r"(\d+)\s*от[жш][иеы]мани[йяе]", re.IGNORECASE),
    re.compile(r"от[жш][иеы]мани[йяе]\s*(\d+)", re.IGNORECASE),
    re.compile(r"сделал.*?(\d+)\s*от[жш][иеы]мани[йяе]", re.IGNORECASE),
    re.compile(r"(\d+)\s*раз.*от[жш]", re.IGNORECASE),
    re.compile(r"pushups?\s*(\d+)", re.IGNORECASE),
    re.compile(r"(\d+)\s*pushups?", re.IGNORECASE),
    # Продажи
    re.compile(r"(\d+)\s*продаж[аиейу]", re.IGNORECASE),
    re.compile(r"продаж[аиейу]\s*(\d+)", re.IGNORECASE),
    re.compile(r"продал\s+(\d+)", re.IGNORECASE),
    # Подписчики
    re.compile(r"(\d+)\s*подписчик", re.IGNORECASE),
    re.compile(r"подписчик\w*\s*(\d+)", re.IGNORECASE),
]

PUSHUP_PATTERNS = [
    # Стандартные + Whisper-ошибки (отшимания, отжемания, отжимания)
    re.compile(r"(\d+)\s*от[жш][иеы]мани[йяе]", re.IGNORECASE),
    re.compile(r"от[жш][иеы]мани[йяе]\s*(\d+)", re.IGNORECASE),
    re.compile(r"сделал.*?(\d+)\s*от[жш][иеы]мани[йяе]", re.IGNORECASE),
    re.compile(r"(\d+)\s*раз.*от[жш]", re.IGNORECASE),
    re.compile(r"pushups?\s*(\d+)", re.IGNORECASE),
    re.compile(r"(\d+)\s*pushups?", re.IGNORECASE),
    # "отжался 50 раз"
    re.compile(r"от[жш]ался\s*(\d+)", re.IGNORECASE),
    re.compile(r"(\d+)\s*раз\s*от[жш]ался", re.IGNORECASE),
]


# ── Голосовые команды → интенты (без вызова Claude) ──

VOICE_COMMAND_PATTERNS: list[tuple[re.Pattern, str, dict]] = [
    # Показать задачи
    (re.compile(r"покажи\s+(мои\s+)?задачи|список\s+дел|что\s+(у\s+меня\s+)?(по\s+задачам|нужно\s+сделать)|мои\s+задачи", re.IGNORECASE), "show_tasks", {}),
    # Показать идеи
    (re.compile(r"покажи\s+(мои\s+)?идеи|список\s+идей|мои\s+идеи", re.IGNORECASE), "show_ideas", {}),
    # Показать проекты
    (re.compile(r"покажи\s+(мои\s+)?проекты|список\s+проектов|мои\s+проекты|статус\s+проектов", re.IGNORECASE), "show_projects", {}),
    # Портфель
    (re.compile(r"покажи\s+(мой\s+)?портфель|что\s+(у\s+меня\s+)?в\s+портфеле|мои\s+(акции|крипта|инвестиции)|состояние\s+портфеля", re.IGNORECASE), "portfolio", {}),
    # Прибыль
    (re.compile(r"(моя\s+)?(прибыль|убыток|доходность|p.?n.?l|результат\s+по\s+сделкам)", re.IGNORECASE), "pnl", {}),
    # Брифинг
    (re.compile(r"(сделай|дай|покажи)?\s*брифинг|отчёт\s+за\s+неделю|недельный\s+отчёт", re.IGNORECASE), "briefing", {}),
    # Дайджест / сводка дня
    (re.compile(r"(сводка|дайджест|итоги)\s+(за\s+)?(сегодня|день)|что\s+сегодня\s+сделал", re.IGNORECASE), "digest", {}),
    # Расходы на AI
    (re.compile(r"сколько\s+(потратил|стоит)\s+(на\s+)?(ии|ai|клода|claude|искусственный\s+интеллект)|расходы\s+на\s+(ии|ai)", re.IGNORECASE), "cost", {}),
    # Статистика / метрики
    (re.compile(r"(покажи\s+)?(статистику|метрики|показатели)(\s+за\s+(неделю|месяц))?", re.IGNORECASE), "metrics", {}),
    # Выполнил задачу (по тексту) — исключить отжимания, продажи, метрики
    (re.compile(r"(выполнил|завершил|закрыл|готово)\s+(.+)", re.IGNORECASE), "done_task", {}),
    (re.compile(r"сделал\s+(?!.*(?:от[жш][иеы]мани|pushup|продаж|подход))(.+)", re.IGNORECASE), "done_task", {}),
]


def detect_voice_command(text: str) -> dict | None:
    """Распознать голосовую команду без Claude."""
    for pattern, intent, extra in VOICE_COMMAND_PATTERNS:
        m = pattern.search(text)
        if m:
            result = {"type": intent, "text": text, "source": "local"}
            result.update(extra)
            # Для done_task — извлечь текст задачи
            if intent == "done_task" and m.lastindex and m.lastindex >= 2:
                result["task_text"] = m.group(2).strip()
            # Определить проект если упомянут
            result["project"] = detect_project(text)
            return result
    return None


def detect_pushups(text: str) -> int | None:
    """Извлечь число отжиманий из текста."""
    for pat in PUSHUP_PATTERNS:
        m = pat.search(text)
        if m:
            return int(m.group(1))
    return None


# Паттерны, которые точно НЕ задачи/идеи — вопросы для Claude
QUESTION_PATTERNS = [
    re.compile(r"^(как|что|почему|зачем|когда|где|кто|сколько)\b", re.IGNORECASE),
    re.compile(r"\?$"),
]


def detect_project(text: str) -> str | None:
    """Определить проект по ключевым словам (статические + динамические)."""
    text_lower = text.lower()
    # Сначала статические алиасы
    for alias, project in PROJECT_ALIASES.items():
        if alias in text_lower:
            return project
    # Потом динамические из БД
    for name_lower in _dynamic_projects:
        if name_lower in text_lower:
            return name_lower
    return None


def detect_project_id(text: str) -> int | None:
    """Определить ID проекта из динамической базы."""
    text_lower = text.lower()
    for name_lower, pid in _dynamic_projects.items():
        if name_lower in text_lower:
            return pid
    return None


def classify_local(text: str) -> dict | None:
    """
    Локальная классификация без Claude.
    Возвращает dict {type, project, text, source} или None если не уверен.
    None = пусть решает Claude Haiku.
    """
    text = text.strip()
    if not text:
        return None

    # 0a. Метрики — отжимания (ПЕРЕД голосовыми командами, чтобы "сделал отжимания" не путалось с done_task)
    pushups = detect_pushups(text)
    if pushups is not None:
        return {
            "type": "pushups",
            "value": pushups,
            "text": text,
            "source": "local",
        }

    # 0b. Голосовые команды (show_tasks, portfolio, briefing и т.д.)
    voice_cmd = detect_voice_command(text)
    if voice_cmd:
        return voice_cmd

    # 1а. "Добавление/обновление в проект X: ..."
    m = PROJECT_NOTE_PATTERN.match(text)
    if m:
        project_name = m.group(1).strip().rstrip(":")
        content = m.group(2).strip() or text
        project = PROJECT_ALIASES.get(project_name.lower()) or project_name.lower()
        return {
            "type": "note",
            "project": project,
            "project_name_raw": project_name,
            "text": content,
            "source": "local",
        }

    # 1б. Привязка к проекту: "по проекту X — ..."
    m = PROJECT_PATTERN.match(text)
    if m:
        project_name = m.group(1).strip()
        content = m.group(2).strip()
        project = PROJECT_ALIASES.get(project_name.lower())
        sub = _classify_content(content)
        return {
            "type": sub or "idea",
            "project": project,
            "project_name_raw": project_name,
            "text": content,
            "source": "local",
        }

    # 2. Явная задача
    for pat in TASK_PATTERNS:
        m = pat.match(text)
        if m:
            content = m.group(1).strip()
            return {
                "type": "task",
                "project": detect_project(content),
                "text": content,
                "source": "local",
            }

    # 3. Явная идея
    for pat in IDEA_PATTERNS:
        m = pat.match(text)
        if m:
            content = m.group(1).strip()
            return {
                "type": "idea",
                "project": detect_project(content),
                "text": content,
                "source": "local",
            }

    # 4. Поисковый запрос
    for pat in SEARCH_PATTERNS:
        if pat.match(text):
            return {
                "type": "search",
                "project": None,
                "text": text,
                "source": "local",
            }

    # 5. Явный вопрос — отправить Claude для ответа (не для классификации)
    for pat in QUESTION_PATTERNS:
        if pat.search(text):
            return {
                "type": "question",
                "project": detect_project(text),
                "text": text,
                "source": "local",
            }

    # 6. Не уверен — вернуть None, пусть решает Claude Haiku
    return None


def _classify_content(text: str) -> str | None:
    """Подклассификация содержимого записи по проекту."""
    t = text.lower()
    if any(w in t for w in ("идея", "можно", "а что если", "придумал")):
        return "idea"
    if any(w in t for w in ("решил", "решение", "утвердил", "запускаем", "делаем")):
        return "decision"
    if any(w in t for w in ("риск", "опасно", "может заблокировать", "проблема")):
        return "risk"
    if any(w in t for w in ("уточнение", "правка", "дополнение", "изменить", "обновление")):
        return "update"
    if any(w in t for w in ("задача", "надо", "нужно", "сделать", "напомни")):
        return "task"
    if t.endswith("?") or any(w in t for w in ("стоит ли", "не уверен", "как думаешь")):
        return "question"
    return None
