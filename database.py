import aiosqlite
from datetime import date, datetime, timedelta

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

            -- English vocabulary (spaced repetition)
            CREATE TABLE IF NOT EXISTS english_vocab (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL,
                translation TEXT NOT NULL,
                review_count INTEGER DEFAULT 0,
                next_review TEXT DEFAULT (date('now')),
                created_at DATETIME DEFAULT (datetime('now'))
            );

            -- Лог действий для /undo
            CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                entity_table TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                data TEXT DEFAULT '',
                created_at DATETIME DEFAULT (datetime('now'))
            );

            -- ============================================================
            -- ENGLISH MODULE — A1→B1 (изолированный модуль, готов к выносу)
            -- Контент-таблицы (общие, без user_id) + per-user прогресс.
            -- ============================================================

            -- Юниты учебника (Outcomes Elementary = 16 юнитов)
            CREATE TABLE IF NOT EXISTS english_units (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,         -- 'outcomes_elem'
                number INTEGER NOT NULL,
                title TEXT NOT NULL,
                cefr TEXT,                    -- A1/A2/B1
                topic TEXT,
                grammar_focus TEXT,           -- JSON list
                vocab_focus TEXT,             -- JSON list
                page_start INTEGER,
                page_end INTEGER,
                UNIQUE(source, number)
            );

            -- Лексические единицы (слова, чанки, коллокации)
            CREATE TABLE IF NOT EXISTS english_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_id INTEGER REFERENCES english_units(id),
                chunk TEXT NOT NULL,
                translation_ru TEXT,
                type TEXT DEFAULT 'word',     -- word/collocation/phrase/grammar_pattern
                cefr TEXT,
                ipa TEXT,
                example_en TEXT,
                example_ru TEXT,
                audio_path TEXT,              -- pre-rendered .ogg (edge-tts)
                example_audio_path TEXT,
                source TEXT DEFAULT 'outcomes_elem',
                source_page INTEGER,
                tags TEXT,                    -- JSON list
                created_at DATETIME DEFAULT (datetime('now')),
                UNIQUE(chunk, source)
            );

            -- Готовые предложения для listening / shadowing / drill
            CREATE TABLE IF NOT EXISTS english_sentences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_id INTEGER REFERENCES english_units(id),
                text_en TEXT NOT NULL,
                text_ru TEXT,
                type TEXT DEFAULT 'example',  -- dialog_line/example/drill/story
                speaker TEXT,                 -- A/B
                audio_path TEXT,
                difficulty INTEGER DEFAULT 1, -- 1..5
                source TEXT DEFAULT 'outcomes_elem',
                source_page INTEGER,
                created_at DATETIME DEFAULT (datetime('now'))
            );

            -- Упражнения (gap-fill, matching, multiple choice)
            CREATE TABLE IF NOT EXISTS english_exercises (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_id INTEGER REFERENCES english_units(id),
                type TEXT NOT NULL,           -- gap_fill/multiple_choice/matching/order
                prompt TEXT NOT NULL,
                answer TEXT NOT NULL,
                options TEXT,                 -- JSON list для multiple choice
                explanation_ru TEXT,
                difficulty INTEGER DEFAULT 1,
                source TEXT DEFAULT 'outcomes_wb',
                source_page INTEGER
            );

            -- Грамматические правила
            CREATE TABLE IF NOT EXISTS english_grammar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_id INTEGER REFERENCES english_units(id),
                topic TEXT NOT NULL,
                rule_ru TEXT,
                rule_en TEXT,
                examples TEXT,                -- JSON list
                common_mistakes TEXT,         -- JSON list
                source TEXT DEFAULT 'outcomes_elem'
            );

            -- Диалоги для role-play
            CREATE TABLE IF NOT EXISTS english_dialogs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                unit_id INTEGER REFERENCES english_units(id),
                title TEXT,
                context_ru TEXT,
                turns TEXT NOT NULL,          -- JSON: [{speaker,text_en,text_ru,audio_path}]
                roles TEXT DEFAULT 'A,B',
                source TEXT DEFAULT 'outcomes_elem'
            );

            -- ----- PER-USER (multitenancy ready) -----

            -- Профиль ученика и CEFR sub-scores
            CREATE TABLE IF NOT EXISTS english_profile (
                user_id INTEGER PRIMARY KEY,
                cefr_level TEXT DEFAULT 'A1',
                vocab_score REAL DEFAULT 0,
                grammar_score REAL DEFAULT 0,
                listening_score REAL DEFAULT 0,
                speaking_score REAL DEFAULT 0,
                current_unit INTEGER DEFAULT 1,
                started_at DATETIME DEFAULT (datetime('now')),
                last_assessed_at DATETIME,
                tts_voice TEXT DEFAULT 'en-GB-SoniaNeural',
                tts_voice_second TEXT DEFAULT 'en-GB-RyanNeural',
                tts_rate TEXT DEFAULT '+0%',
                daily_chunks_target INTEGER DEFAULT 8,
                streak_days INTEGER DEFAULT 0,
                last_session_date TEXT
            );

            -- SRS-очередь (расширенная, отдельно от старой english_vocab)
            CREATE TABLE IF NOT EXISTS english_srs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chunk_id INTEGER REFERENCES english_chunks(id),
                queue TEXT DEFAULT 'passive',  -- passive/active/mastered
                ease REAL DEFAULT 2.5,         -- SM-2 ease factor
                interval_days INTEGER DEFAULT 0,
                repetitions INTEGER DEFAULT 0,
                next_review TEXT DEFAULT (date('now')),
                last_grade INTEGER,            -- 0..5
                last_reviewed_at DATETIME,
                added_at DATETIME DEFAULT (datetime('now')),
                UNIQUE(user_id, chunk_id)
            );

            -- Сессии занятий
            CREATE TABLE IF NOT EXISTS english_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                block_type TEXT,              -- chunks/listening/speaking/grammar/review/test
                duration_sec INTEGER DEFAULT 0,
                items_total INTEGER DEFAULT 0,
                items_correct INTEGER DEFAULT 0,
                speaking_score REAL,
                notes TEXT,
                created_at DATETIME DEFAULT (datetime('now'))
            );

            -- Результаты тестов (daily/weekly/monthly)
            CREATE TABLE IF NOT EXISTS english_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                test_type TEXT NOT NULL,      -- placement/daily/weekly/monthly
                score_json TEXT NOT NULL,     -- JSON со всеми sub-scores
                cefr_estimate TEXT,
                created_at DATETIME DEFAULT (datetime('now'))
            );

            -- Домашка от учителя
            CREATE TABLE IF NOT EXISTS english_homework (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                lesson_date TEXT,
                description TEXT NOT NULL,
                deadline TEXT,
                status TEXT DEFAULT 'pending', -- pending/done
                created_at DATETIME DEFAULT (datetime('now'))
            );

            -- Личные примеры (запись Андреем своих чанков, не из учебника)
            CREATE TABLE IF NOT EXISTS english_personal_examples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chunk_id INTEGER REFERENCES english_chunks(id),
                example_en TEXT NOT NULL,
                example_ru TEXT,
                created_at DATETIME DEFAULT (datetime('now'))
            );

            -- Заглушка под биллинг (для будущей монетизации)
            CREATE TABLE IF NOT EXISTS english_subscriptions (
                user_id INTEGER PRIMARY KEY,
                plan TEXT DEFAULT 'free',
                expires_at TEXT,
                created_at DATETIME DEFAULT (datetime('now'))
            );

            -- Индексы для производительности
            CREATE INDEX IF NOT EXISTS idx_chunks_unit ON english_chunks(unit_id);
            CREATE INDEX IF NOT EXISTS idx_sentences_unit ON english_sentences(unit_id);
            CREATE INDEX IF NOT EXISTS idx_exercises_unit ON english_exercises(unit_id);
            CREATE INDEX IF NOT EXISTS idx_srs_review ON english_srs(user_id, next_review);
            CREATE INDEX IF NOT EXISTS idx_sessions_user_date ON english_sessions(user_id, date);

            -- Инвестиционный портфель
            CREATE TABLE IF NOT EXISTS portfolio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset TEXT NOT NULL,
                asset_type TEXT NOT NULL,
                exchange TEXT DEFAULT '',
                quantity REAL NOT NULL,
                buy_price REAL NOT NULL,
                currency TEXT DEFAULT 'USD',
                buy_date TEXT NOT NULL,
                notes TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                sell_price REAL,
                sell_date TEXT,
                created_at DATETIME DEFAULT (datetime('now'))
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
    # Авто-сжатие: если больше 30 сообщений, оставить 10
    count = await get_chat_history_count()
    if count > 30:
        await compress_chat_history(keep_recent=10)


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


# ---- Портфель ----

async def add_portfolio_entry(
    asset: str, asset_type: str, exchange: str,
    quantity: float, buy_price: float, currency: str,
    buy_date: str, notes: str = ""
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO portfolio
               (asset, asset_type, exchange, quantity, buy_price, currency, buy_date, notes, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')""",
            (asset.upper(), asset_type, exchange, quantity, buy_price, currency.upper(), buy_date, notes),
        )
        await db.commit()
        return cursor.lastrowid


async def get_portfolio() -> list[dict]:
    """Активные позиции."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM portfolio WHERE status = 'active' ORDER BY created_at DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_portfolio_entry(entry_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM portfolio WHERE id = ?", (entry_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def close_portfolio_entry(entry_id: int, sell_price: float, sell_date: str) -> dict | None:
    """Зафиксировать продажу позиции."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM portfolio WHERE id = ? AND status = 'active'", (entry_id,)
        )
        entry = await cursor.fetchone()
        if not entry:
            return None
        await db.execute(
            "UPDATE portfolio SET status = 'sold', sell_price = ?, sell_date = ? WHERE id = ?",
            (sell_price, sell_date, entry_id),
        )
        await db.commit()
        return dict(entry)


async def get_portfolio_history() -> list[dict]:
    """Все закрытые позиции."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM portfolio WHERE status = 'sold' ORDER BY sell_date DESC"
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ---- Undo (лог действий) ----

async def log_action(action_type: str, entity_table: str, entity_id: int, data: str = ""):
    """Записать действие для /undo."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO action_log (action_type, entity_table, entity_id, data, created_at) VALUES (?, ?, ?, ?, ?)",
            (action_type, entity_table, entity_id, data, datetime.now().isoformat()),
        )
        await db.commit()


async def get_last_action() -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM action_log ORDER BY id DESC LIMIT 1")
        row = await cursor.fetchone()
        return dict(row) if row else None


async def delete_action_log(action_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM action_log WHERE id = ?", (action_id,))
        await db.commit()


async def delete_task(task_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        await db.commit()


async def delete_portfolio_entry(entry_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM portfolio WHERE id = ?", (entry_id,))
        await db.commit()


async def reopen_task(task_id: int):
    """Вернуть задачу в active из done."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tasks SET status = 'active', done_at = NULL WHERE id = ?",
            (task_id,),
        )
        await db.commit()


# ---- Сжатие истории чата ----

async def get_chat_history_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM chat_history")
        row = await cursor.fetchone()
        return row[0]


async def compress_chat_history(keep_recent: int = 10):
    """Удалить старые сообщения, оставив последние keep_recent."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM chat_history WHERE id NOT IN (SELECT id FROM chat_history ORDER BY id DESC LIMIT ?)",
            (keep_recent,),
        )
        await db.commit()


# ---- Экспорт портфеля ----

async def get_all_portfolio() -> list[dict]:
    """Все позиции для экспорта."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM portfolio ORDER BY buy_date DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ---- English Vocabulary ----

async def add_english_vocab(word: str, translation: str) -> int:
    """Добавить слово. Если уже есть — обновить перевод."""
    async with aiosqlite.connect(DB_PATH) as db:
        existing = await db.execute("SELECT id FROM english_vocab WHERE word = ?", (word.lower(),))
        row = await existing.fetchone()
        if row:
            await db.execute(
                "UPDATE english_vocab SET translation = ?, next_review = date('now') WHERE id = ?",
                (translation, row[0]),
            )
            await db.commit()
            return row[0]
        cursor = await db.execute(
            "INSERT INTO english_vocab (word, translation, next_review) VALUES (?, ?, date('now'))",
            (word.lower(), translation),
        )
        await db.commit()
        return cursor.lastrowid


async def find_english_vocab(word: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM english_vocab WHERE word = ?", (word.lower(),)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_english_vocab_for_review(limit: int = 10) -> list[dict]:
    """Слова у которых next_review <= сегодня."""
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM english_vocab WHERE next_review <= ? ORDER BY next_review LIMIT ?",
            (today, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_all_english_vocab(limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM english_vocab ORDER BY created_at DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def mark_english_vocab_reviewed(vocab_id: int):
    """Обновить дату следующего повторения по spaced repetition."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT review_count FROM english_vocab WHERE id = ?", (vocab_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return
        count = (row[0] or 0) + 1
        # Интервалы: 1, 3, 7, 14, 30, 60 дней
        intervals = [1, 3, 7, 14, 30, 60]
        days = intervals[min(count - 1, len(intervals) - 1)]
        next_rev = (date.today() + timedelta(days=days)).isoformat()
        await db.execute(
            "UPDATE english_vocab SET review_count = ?, next_review = ? WHERE id = ?",
            (count, next_rev, vocab_id),
        )
        await db.commit()


async def get_english_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        today = date.today().isoformat()
        vocab_count = (await (await db.execute("SELECT COUNT(*) FROM english_vocab")).fetchone())[0]
        review_due = (await (await db.execute(
            "SELECT COUNT(*) FROM english_vocab WHERE next_review <= ?", (today,)
        )).fetchone())[0]
        total_reviews = (await (await db.execute(
            "SELECT COALESCE(SUM(review_count), 0) FROM english_vocab"
        )).fetchone())[0]
        # Фразы — из project_entries
        db.row_factory = aiosqlite.Row
        project = await (await db.execute(
            "SELECT id FROM projects WHERE LOWER(name) = 'english'"
        )).fetchone()
        phrases_count = 0
        if project:
            phrases_count = (await (await db.execute(
                "SELECT COUNT(*) FROM project_entries WHERE project_id = ? AND type = 'phrase'",
                (project["id"],),
            )).fetchone())[0]

        return {
            "vocab_count": vocab_count,
            "review_due": review_due,
            "total_reviews": total_reviews,
            "phrases_count": phrases_count,
        }


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


# ============================================================
# ENGLISH MODULE — helper functions (изолированный API)
# ============================================================

# ---- Профиль ученика ----

async def en_get_or_create_profile(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM english_profile WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            return dict(row)
        await db.execute("INSERT INTO english_profile (user_id) VALUES (?)", (user_id,))
        await db.commit()
        cursor = await db.execute("SELECT * FROM english_profile WHERE user_id = ?", (user_id,))
        return dict(await cursor.fetchone())


async def en_update_profile(user_id: int, **fields):
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"UPDATE english_profile SET {sets} WHERE user_id = ?",
            (*fields.values(), user_id),
        )
        await db.commit()


# ---- Юниты ----

async def en_get_unit(unit_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM english_units WHERE id = ?", (unit_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def en_get_unit_by_number(number: int, source: str = "outcomes_elem") -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM english_units WHERE number = ? AND source = ?", (number, source)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def en_list_units(source: str = "outcomes_elem") -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM english_units WHERE source = ? ORDER BY number", (source,)
        )
        return [dict(r) for r in await cursor.fetchall()]


async def en_upsert_unit(source: str, number: int, title: str, **fields) -> int:
    """Создать или обновить юнит."""
    import json as _json
    fields_clean = {k: (_json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v)
                    for k, v in fields.items()}
    async with aiosqlite.connect(DB_PATH) as db:
        existing = await db.execute(
            "SELECT id FROM english_units WHERE source = ? AND number = ?", (source, number)
        )
        row = await existing.fetchone()
        if row:
            if fields_clean:
                sets = ", ".join(f"{k} = ?" for k in fields_clean)
                await db.execute(
                    f"UPDATE english_units SET title = ?, {sets} WHERE id = ?",
                    (title, *fields_clean.values(), row[0]),
                )
                await db.commit()
            return row[0]
        cols = ["source", "number", "title"] + list(fields_clean.keys())
        vals = [source, number, title] + list(fields_clean.values())
        ph = ", ".join(["?"] * len(cols))
        cursor = await db.execute(
            f"INSERT INTO english_units ({', '.join(cols)}) VALUES ({ph})", vals
        )
        await db.commit()
        return cursor.lastrowid


# ---- Чанки ----

async def en_add_chunk(
    chunk: str, translation_ru: str = "", unit_id: int | None = None,
    type: str = "word", cefr: str | None = None, ipa: str | None = None,
    example_en: str | None = None, example_ru: str | None = None,
    source: str = "outcomes_elem", source_page: int | None = None,
    tags: list | None = None,
) -> int:
    import json as _json
    tags_json = _json.dumps(tags or [], ensure_ascii=False)
    async with aiosqlite.connect(DB_PATH) as db:
        # Идемпотентно по (chunk, source)
        existing = await db.execute(
            "SELECT id FROM english_chunks WHERE chunk = ? AND source = ?", (chunk, source)
        )
        row = await existing.fetchone()
        if row:
            return row[0]
        cursor = await db.execute(
            """INSERT INTO english_chunks
               (unit_id, chunk, translation_ru, type, cefr, ipa, example_en, example_ru,
                source, source_page, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (unit_id, chunk, translation_ru, type, cefr, ipa, example_en, example_ru,
             source, source_page, tags_json),
        )
        await db.commit()
        return cursor.lastrowid


async def en_get_chunks_by_unit(unit_id: int, limit: int = 100) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM english_chunks WHERE unit_id = ? LIMIT ?", (unit_id, limit)
        )
        return [dict(r) for r in await cursor.fetchall()]


async def en_count_chunks() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM english_chunks")
        return (await cursor.fetchone())[0]


async def en_get_chunks_without_audio(limit: int = 500) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT id, chunk, example_en FROM english_chunks WHERE audio_path IS NULL LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def en_set_chunk_audio(chunk_id: int, audio_path: str, example_audio_path: str | None = None):
    async with aiosqlite.connect(DB_PATH) as db:
        if example_audio_path:
            await db.execute(
                "UPDATE english_chunks SET audio_path = ?, example_audio_path = ? WHERE id = ?",
                (audio_path, example_audio_path, chunk_id),
            )
        else:
            await db.execute(
                "UPDATE english_chunks SET audio_path = ? WHERE id = ?",
                (audio_path, chunk_id),
            )
        await db.commit()


# ---- Предложения ----

async def en_add_sentence(
    text_en: str, text_ru: str = "", unit_id: int | None = None,
    type: str = "example", speaker: str | None = None,
    difficulty: int = 1, source: str = "outcomes_elem", source_page: int | None = None,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO english_sentences
               (unit_id, text_en, text_ru, type, speaker, difficulty, source, source_page)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (unit_id, text_en, text_ru, type, speaker, difficulty, source, source_page),
        )
        await db.commit()
        return cursor.lastrowid


async def en_count_sentences() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM english_sentences")
        return (await cursor.fetchone())[0]


# ---- Упражнения ----

async def en_add_exercise(
    type: str, prompt: str, answer: str,
    unit_id: int | None = None, options: list | None = None,
    explanation_ru: str | None = None, difficulty: int = 1,
    source: str = "outcomes_wb", source_page: int | None = None,
) -> int:
    import json as _json
    opts_json = _json.dumps(options, ensure_ascii=False) if options else None
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO english_exercises
               (unit_id, type, prompt, answer, options, explanation_ru, difficulty,
                source, source_page)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (unit_id, type, prompt, answer, opts_json, explanation_ru, difficulty,
             source, source_page),
        )
        await db.commit()
        return cursor.lastrowid


async def en_get_exercises_by_unit(unit_id: int, limit: int = 20) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM english_exercises WHERE unit_id = ? LIMIT ?", (unit_id, limit)
        )
        return [dict(r) for r in await cursor.fetchall()]


async def en_count_exercises() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM english_exercises")
        return (await cursor.fetchone())[0]


# ---- Грамматика ----

async def en_add_grammar(topic: str, rule_ru: str = "", rule_en: str = "",
                          examples: list | None = None, common_mistakes: list | None = None,
                          unit_id: int | None = None, source: str = "outcomes_elem") -> int:
    import json as _json
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO english_grammar
               (unit_id, topic, rule_ru, rule_en, examples, common_mistakes, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (unit_id, topic, rule_ru, rule_en,
             _json.dumps(examples or [], ensure_ascii=False),
             _json.dumps(common_mistakes or [], ensure_ascii=False), source),
        )
        await db.commit()
        return cursor.lastrowid


async def en_find_grammar(topic_query: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM english_grammar WHERE LOWER(topic) LIKE LOWER(?) LIMIT 1",
            (f"%{topic_query}%",),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


# ---- Диалоги ----

async def en_add_dialog(title: str, turns: list, unit_id: int | None = None,
                         context_ru: str = "", source: str = "outcomes_elem") -> int:
    import json as _json
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO english_dialogs (unit_id, title, context_ru, turns, source)
               VALUES (?, ?, ?, ?, ?)""",
            (unit_id, title, context_ru, _json.dumps(turns, ensure_ascii=False), source),
        )
        await db.commit()
        return cursor.lastrowid


async def en_get_dialogs_by_unit(unit_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM english_dialogs WHERE unit_id = ?", (unit_id,)
        )
        return [dict(r) for r in await cursor.fetchall()]


# ---- SRS (SM-2) ----

async def en_srs_add(user_id: int, chunk_id: int, queue: str = "passive") -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        existing = await db.execute(
            "SELECT id FROM english_srs WHERE user_id = ? AND chunk_id = ?", (user_id, chunk_id)
        )
        row = await existing.fetchone()
        if row:
            return row[0]
        cursor = await db.execute(
            "INSERT INTO english_srs (user_id, chunk_id, queue) VALUES (?, ?, ?)",
            (user_id, chunk_id, queue),
        )
        await db.commit()
        return cursor.lastrowid


async def en_srs_due(user_id: int, limit: int = 20) -> list[dict]:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT s.*, c.chunk, c.translation_ru, c.example_en, c.example_ru,
                      c.audio_path, c.example_audio_path
               FROM english_srs s
               JOIN english_chunks c ON c.id = s.chunk_id
               WHERE s.user_id = ? AND s.next_review <= ? AND s.queue != 'mastered'
               ORDER BY s.next_review LIMIT ?""",
            (user_id, today, limit),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def en_srs_review(srs_id: int, grade: int):
    """SM-2: grade 0..5. Обновляет ease, interval, next_review."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM english_srs WHERE id = ?", (srs_id,))
        row = await cursor.fetchone()
        if not row:
            return
        ease = row["ease"] or 2.5
        reps = row["repetitions"] or 0
        interval = row["interval_days"] or 0

        if grade < 3:
            reps = 0
            interval = 1
        else:
            if reps == 0:
                interval = 1
            elif reps == 1:
                interval = 3
            else:
                interval = max(1, round(interval * ease))
            reps += 1
            ease = ease + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))
            ease = max(1.3, ease)

        next_review = (date.today() + timedelta(days=interval)).isoformat()
        queue = "mastered" if reps >= 6 and grade >= 4 else (
            "active" if reps >= 2 else "passive"
        )

        await db.execute(
            """UPDATE english_srs
               SET ease = ?, interval_days = ?, repetitions = ?,
                   next_review = ?, last_grade = ?, last_reviewed_at = datetime('now'),
                   queue = ?
               WHERE id = ?""",
            (ease, interval, reps, next_review, grade, queue, srs_id),
        )
        await db.commit()


async def en_srs_count_due(user_id: int) -> int:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM english_srs WHERE user_id = ? AND next_review <= ? AND queue != 'mastered'",
            (user_id, today),
        )
        return (await cursor.fetchone())[0]


# ---- Сессии ----

async def en_log_session(user_id: int, block_type: str, duration_sec: int = 0,
                          items_total: int = 0, items_correct: int = 0,
                          speaking_score: float | None = None, notes: str = "") -> int:
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO english_sessions
               (user_id, date, block_type, duration_sec, items_total, items_correct,
                speaking_score, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user_id, today, block_type, duration_sec, items_total, items_correct,
             speaking_score, notes),
        )
        await db.commit()
        return cursor.lastrowid


# ---- Тесты ----

async def en_save_test(user_id: int, test_type: str, score: dict, cefr_estimate: str = "") -> int:
    import json as _json
    today = date.today().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO english_tests (user_id, date, test_type, score_json, cefr_estimate)
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, today, test_type, _json.dumps(score, ensure_ascii=False), cefr_estimate),
        )
        await db.commit()
        return cursor.lastrowid


async def en_last_test(user_id: int, test_type: str | None = None) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if test_type:
            cursor = await db.execute(
                "SELECT * FROM english_tests WHERE user_id = ? AND test_type = ? ORDER BY id DESC LIMIT 1",
                (user_id, test_type),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM english_tests WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,),
            )
        row = await cursor.fetchone()
        return dict(row) if row else None


# ---- Домашка ----

async def en_add_homework(user_id: int, description: str, deadline: str | None = None,
                           lesson_date: str | None = None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO english_homework (user_id, lesson_date, description, deadline)
               VALUES (?, ?, ?, ?)""",
            (user_id, lesson_date, description, deadline),
        )
        await db.commit()
        return cursor.lastrowid


async def en_get_pending_homework(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM english_homework WHERE user_id = ? AND status = 'pending' ORDER BY deadline",
            (user_id,),
        )
        return [dict(r) for r in await cursor.fetchall()]


async def en_complete_homework(hw_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE english_homework SET status = 'done' WHERE id = ?", (hw_id,)
        )
        await db.commit()


# ---- Расширенная статистика ----

async def en_full_stats(user_id: int) -> dict:
    """Полная статистика модуля для команды /en_progress."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        prof = await en_get_or_create_profile(user_id)
        chunks_total = await en_count_chunks()
        sentences_total = await en_count_sentences()
        exercises_total = await en_count_exercises()
        srs_due = await en_srs_count_due(user_id)

        cursor = await db.execute(
            "SELECT COUNT(*) FROM english_srs WHERE user_id = ?", (user_id,)
        )
        srs_total = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT COUNT(*) FROM english_srs WHERE user_id = ? AND queue = 'mastered'", (user_id,)
        )
        mastered = (await cursor.fetchone())[0]

        cursor = await db.execute(
            """SELECT COUNT(*), COALESCE(SUM(items_correct), 0), COALESCE(SUM(items_total), 0)
               FROM english_sessions WHERE user_id = ? AND date >= date('now', '-7 days')""",
            (user_id,),
        )
        sess_row = await cursor.fetchone()
        sessions_week, correct_week, total_week = sess_row[0], sess_row[1], sess_row[2]

        return {
            "profile": prof,
            "content": {
                "chunks": chunks_total,
                "sentences": sentences_total,
                "exercises": exercises_total,
            },
            "srs": {
                "total": srs_total,
                "due_today": srs_due,
                "mastered": mastered,
            },
            "week": {
                "sessions": sessions_week,
                "accuracy": (correct_week / total_week * 100) if total_week else 0,
            },
        }
