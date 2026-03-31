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

    # 1. Привязка к проекту: "по проекту X — ..."
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
