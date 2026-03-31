import aiosqlite
from datetime import datetime

from config import DB_PATH


async def init_db():
    """Создать все таблицы при первом запуске."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            -- Задачи
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                project TEXT,
                status TEXT DEFAULT 'active',
                created_at DATETIME,
                done_at DATETIME
            );

            -- Идеи
            CREATE TABLE IF NOT EXISTS ideas (
                id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                project TEXT,
                created_at DATETIME
            );

            -- Метрики
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY,
                date DATE,
                grafin_sales INTEGER DEFAULT 0,
                grafin_subscribers INTEGER DEFAULT 0,
                ad_clicks INTEGER DEFAULT 0,
                ad_spend REAL DEFAULT 0,
                tasks_done INTEGER DEFAULT 0,
                pushups INTEGER DEFAULT 0
            );

            -- История диалога
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY,
                role TEXT,
                content TEXT,
                created_at DATETIME
            );

            -- Проекты (модуль 6 - база идей и проектов)
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'active',
                created_at DATETIME,
                updated_at DATETIME
            );

            -- Записи по проектам
            CREATE TABLE IF NOT EXISTS project_entries (
                id INTEGER PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                type TEXT,
                raw_text TEXT,
                structured TEXT,
                created_at DATETIME
            );

            -- Мониторинг (модуль 7 - /watch)
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY,
                query TEXT NOT NULL,
                last_result TEXT,
                active INTEGER DEFAULT 1,
                created_at DATETIME,
                checked_at DATETIME
            );

            -- Кеш ответов Claude (экономия токенов)
            CREATE TABLE IF NOT EXISTS response_cache (
                id INTEGER PRIMARY KEY,
                query_hash TEXT NOT NULL UNIQUE,
                query_text TEXT NOT NULL,
                response TEXT NOT NULL,
                model TEXT,
                hits INTEGER DEFAULT 0,
                created_at DATETIME,
                expires_at DATETIME
            );

            -- Учёт расхода токенов и стоимости
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY,
                date DATE NOT NULL,
                model TEXT NOT NULL,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cost_usd REAL DEFAULT 0,
                calls INTEGER DEFAULT 0
            );
        """)
        await db.commit()


# ---- Задачи ----

async def add_task(text: str, project: str | None = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO tasks (text, project, status, created_at) VALUES (?, ?, 'active', ?)",
            (text, project, datetime.now().isoformat()),
        )
        await db.commit()
        return cursor.lastrowid


async def get_active_tasks(project: str | None = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if project:
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE status = 'active' AND project = ? ORDER BY created_at DESC",
                (project,),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM tasks WHERE status = 'active' ORDER BY created_at DESC"
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_task_by_id(task_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def search_active_tasks(query: str) -> list[dict]:
    """Найти активные задачи по частичному совпадению текста."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE status = 'active' AND text LIKE ? ORDER BY created_at DESC",
            (f"%{query}%",),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def complete_task(task_id: int) -> dict | None:
    """Пометить задачу выполненной по ID. Возвращает задачу или None."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM tasks WHERE id = ? AND status = 'active'", (task_id,))
        task = await cursor.fetchone()
        if not task:
            return None
        await db.execute(
            "UPDATE tasks SET status = 'done', done_at = ? WHERE id = ?",
            (datetime.now().isoformat(), task_id),
        )
        await db.commit()
        return dict(task)


async def complete_task_by_text(text: str) -> dict | None:
    """Пометить задачу выполненной по частичному совпадению текста. Возвращает первую найденную."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE status = 'active' AND LOWER(text) LIKE LOWER(?) LIMIT 1",
            (f"%{text}%",),
        )
        task = await cursor.fetchone()
        if not task:
            return None
        await db.execute(
            "UPDATE tasks SET status = 'done', done_at = ? WHERE id = ?",
            (datetime.now().isoformat(), task["id"]),
        )
        await db.commit()
        return dict(task)


async def get_done_tasks_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM tasks WHERE status = 'done'")
        row = await cursor.fetchone()
        return row[0]


async def archive_done_tasks() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "UPDATE tasks SET status = 'archived' WHERE status = 'done'"
        )
        await db.commit()
        return cursor.rowcount


# ---- Идеи ----

async def add_idea(text: str, project: str | None = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO ideas (text, project, created_at) VALUES (?, ?, ?)",
            (text, project, datetime.now().isoformat()),
        )
        await db.commit()
        return cursor.lastrowid


async def get_ideas(project: str | None = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if project:
            cursor = await db.execute(
                "SELECT * FROM ideas WHERE LOWER(project) = LOWER(?) ORDER BY created_at DESC",
                (project,),
            )
        else:
            cursor = await db.execute("SELECT * FROM ideas ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def delete_idea(idea_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
        await db.commit()
        return cursor.rowcount > 0


async def move_idea_to_task(idea_id: int) -> int | None:
    """Преобразовать идею в задачу. Возвращает ID новой задачи."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,))
        idea = await cursor.fetchone()
        if not idea:
            return None
        task_cursor = await db.execute(
            "INSERT INTO tasks (text, project, status, created_at) VALUES (?, ?, 'active', ?)",
            (idea["text"], idea["project"], datetime.now().isoformat()),
        )
        await db.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
        await db.commit()
        return task_cursor.lastrowid


# ---- История чата ----

async def save_message(role: str, content: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO chat_history (role, content, created_at) VALUES (?, ?, ?)",
            (role, content, datetime.now().isoformat()),
        )
        await db.commit()


async def get_chat_history(limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT role, content FROM chat_history ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in reversed(rows)]


# ---- Метрики ----

async def save_metrics(date: str, **kwargs) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        # Upsert по дате
        existing = await db.execute("SELECT id FROM metrics WHERE date = ?", (date,))
        row = await existing.fetchone()
        if row:
            sets = ", ".join(f"{k} = ?" for k in kwargs)
            await db.execute(
                f"UPDATE metrics SET {sets} WHERE date = ?",
                (*kwargs.values(), date),
            )
            await db.commit()
            return row[0]
        else:
            cols = ", ".join(["date"] + list(kwargs.keys()))
            placeholders = ", ".join(["?"] * (1 + len(kwargs)))
            cursor = await db.execute(
                f"INSERT INTO metrics ({cols}) VALUES ({placeholders})",
                (date, *kwargs.values()),
            )
            await db.commit()
            return cursor.lastrowid


async def get_metrics(days: int = 7) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM metrics ORDER BY date DESC LIMIT ?", (days,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ---- Проекты (модуль 6) ----

async def create_project(name: str, description: str | None = None) -> int:
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO projects (name, description, status, created_at, updated_at) VALUES (?, ?, 'active', ?, ?)",
            (name, description, now, now),
        )
        await db.commit()
        return cursor.lastrowid


async def get_projects(include_archive: bool = False) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if include_archive:
            cursor = await db.execute("SELECT * FROM projects ORDER BY updated_at DESC")
        else:
            cursor = await db.execute(
                "SELECT * FROM projects WHERE status != 'archive' ORDER BY updated_at DESC"
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_project_by_name(name: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM projects WHERE LOWER(name) = LOWER(?)", (name,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def add_project_entry(project_id: int, entry_type: str, raw_text: str, structured: str) -> int:
    now = datetime.now().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO project_entries (project_id, type, raw_text, structured, created_at) VALUES (?, ?, ?, ?, ?)",
            (project_id, entry_type, raw_text, structured, now),
        )
        await db.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id)
        )
        await db.commit()
        return cursor.lastrowid


async def get_project_entries(project_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM project_entries WHERE project_id = ? ORDER BY created_at", (project_id,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ---- Брифинг (данные за неделю) ----

async def get_done_tasks_since(since: str) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE status = 'done' AND done_at >= ? ORDER BY done_at",
            (since,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_overdue_tasks() -> list[dict]:
    """Задачи, которые active уже больше 7 дней."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tasks WHERE status = 'active' ORDER BY created_at"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ---- Кеш ответов (экономия токенов) ----

async def get_cached_response(query_hash: str) -> str | None:
    """Получить кешированный ответ если есть и не истёк."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT response FROM response_cache WHERE query_hash = ? AND expires_at > ?",
            (query_hash, datetime.now().isoformat()),
        )
        row = await cursor.fetchone()
        if row:
            await db.execute(
                "UPDATE response_cache SET hits = hits + 1 WHERE query_hash = ?",
                (query_hash,),
            )
            await db.commit()
            return row["response"]
        return None


async def save_cached_response(
    query_hash: str, query_text: str, response: str, model: str, ttl_hours: int = 168
):
    """Сохранить ответ в кеш. TTL по умолчанию = 7 дней."""
    now = datetime.now()
    from datetime import timedelta
    expires = (now + timedelta(hours=ttl_hours)).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO response_cache
               (query_hash, query_text, response, model, hits, created_at, expires_at)
               VALUES (?, ?, ?, ?, 0, ?, ?)""",
            (query_hash, query_text, response, model, now.isoformat(), expires),
        )
        await db.commit()


async def cleanup_expired_cache():
    """Удалить просроченные записи кеша."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM response_cache WHERE expires_at < ?",
            (datetime.now().isoformat(),),
        )
        await db.commit()
        return cursor.rowcount


# ---- Учёт токенов ----

async def log_token_usage(model: str, input_tokens: int, output_tokens: int, cost_usd: float):
    """Записать расход токенов за сегодня."""
    today = datetime.now().strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        existing = await db.execute(
            "SELECT id FROM token_usage WHERE date = ? AND model = ?", (today, model)
        )
        row = await existing.fetchone()
        if row:
            await db.execute(
                """UPDATE token_usage
                   SET input_tokens = input_tokens + ?,
                       output_tokens = output_tokens + ?,
                       cost_usd = cost_usd + ?,
                       calls = calls + 1
                   WHERE date = ? AND model = ?""",
                (input_tokens, output_tokens, cost_usd, today, model),
            )
        else:
            await db.execute(
                """INSERT INTO token_usage (date, model, input_tokens, output_tokens, cost_usd, calls)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (today, model, input_tokens, output_tokens, cost_usd),
            )
        await db.commit()


async def get_token_usage(days: int = 30) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM token_usage ORDER BY date DESC LIMIT ?", (days * 3,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_total_cost(days: int = 30) -> float:
    """Суммарная стоимость за N дней."""
    from datetime import timedelta
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM token_usage WHERE date >= ?",
            (since,),
        )
        row = await cursor.fetchone()
        return row[0]
