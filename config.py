import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# --- Пути ---
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "agent.db"

DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# --- Токены ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Minsk")

# --- Модель Claude (управляется через claude_api.py) ---
CLAUDE_MAX_TOKENS = 2000

# --- Whisper ---
WHISPER_MODEL = "whisper-1"
WHISPER_MIN_DURATION_SEC = 1  # отсечка тишины — не отправлять аудио короче 1 сек

# --- Лимиты ---
CHAT_HISTORY_LIMIT = 10  # сообщений в контексте (было 20 — экономия ~40% токенов)
CHAT_HISTORY_SUMMARY_AFTER = 20  # после N сообщений — сжимать старые в summary

# --- Obsidian Vault ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_USER = os.getenv("GITHUB_USER", "")
OBSIDIAN_VAULT_DIR = os.getenv("OBSIDIAN_VAULT_DIR", str(BASE_DIR.parent / "andrey_vault"))
OBSIDIAN_GITHUB_REPO = os.getenv("OBSIDIAN_GITHUB_REPO", "andrey_vault")

# --- Системный промпт ---
SYSTEM_PROMPT = """Ты личный бизнес-ассистент Андрея. Отвечай коротко и конкретно.

КОНТЕКСТ:
- Дальнобойщик (польская компания), работает из кабины
- Vibe-coder: Python, aiogram, n8n, Telegram-боты
- Продукты: Графин (TG-курс инвестиций, 45 BYN),
  Kronon MultiTrade (Forex-робот, апсейл $300),
  сайт генерации объявлений для риэлторов (США/Канада/UK)
- Жена Марина - партнёр по контенту и публичной роли
- Цель: 5000+ EUR/мес за 18 месяцев, уйти с рейса
- Бюджет ограничен, время ограничено
- Беларусское законодательство: нельзя обещать доходность

СТИЛЬ ОТВЕТОВ:
- Коротко. Конкретно. Без воды.
- Всегда указывай риски если они есть
- Предлагай следующий конкретный шаг
- Если идея слабая - говори прямо
"""
