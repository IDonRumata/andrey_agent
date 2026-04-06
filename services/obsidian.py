"""
Obsidian vault integration.
Создаёт .md заметки в локальном клоне vault-репо и пушит на GitHub.

Структура vault:
  /Задачи/   — задачи
  /Идеи/     — идеи
  /Заметки/  — произвольные заметки
  /Проекты/  — проектные записи
"""
import asyncio
import logging
import subprocess
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

# Подтягивается из config при первом вызове
_vault: Path | None = None

FOLDERS = {
    "task":    "Задачи",
    "idea":    "Идеи",
    "note":    "Заметки",
    "project": "Проекты",
    "question": "Заметки",
}

ICONS = {
    "task":    "✅",
    "idea":    "💡",
    "note":    "📝",
    "project": "📁",
    "question": "❓",
}


def _get_vault() -> Path | None:
    global _vault
    if _vault is not None:
        return _vault if _vault.exists() else None
    try:
        from config import OBSIDIAN_VAULT_DIR
        if OBSIDIAN_VAULT_DIR:
            p = Path(OBSIDIAN_VAULT_DIR)
            if p.exists():
                _vault = p
                return _vault
    except Exception:
        pass
    return None


def _safe_filename(text: str, max_len: int = 50) -> str:
    for c in r'\/:*?"<>|':
        text = text.replace(c, "")
    return text[:max_len].strip()


def _build_content(entry_type: str, text: str, project: str | None) -> str:
    today = date.today().isoformat()
    tags = [entry_type]
    if project:
        tags.append(project.lower().replace(" ", "_").replace("-", "_"))

    tag_str = ", ".join(tags)
    project_line = f"project: {project}\n" if project else ""

    frontmatter = (
        f"---\n"
        f"date: {today}\n"
        f"tags: [{tag_str}]\n"
        f"{project_line}"
        f"source: telegram-bot\n"
        f"---\n\n"
    )

    icon = ICONS.get(entry_type, "📝")
    return frontmatter + f"# {icon} {text}\n"


async def create_note(
    entry_type: str,
    text: str,
    project: str | None = None,
    push: bool = True,
) -> bool:
    """
    Создать .md заметку в vault.
    entry_type: task / idea / note / project / question
    Возвращает True если файл создан.
    """
    vault = _get_vault()
    if not vault:
        return False

    folder_name = FOLDERS.get(entry_type, "Заметки")
    folder = vault / folder_name
    folder.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    fname = f"{today}_{_safe_filename(text)}.md"
    fpath = folder / fname

    # Не перезаписывать если уже существует
    if fpath.exists():
        return True

    content = _build_content(entry_type, text, project)
    fpath.write_text(content, encoding="utf-8")
    logger.info("Obsidian note created: %s", fpath.name)

    if push:
        await _git_push(f"add: {entry_type} — {text[:40]}")

    return True


async def sync_all(tasks: list, ideas: list) -> int:
    """
    Полная синхронизация задач и идей из БД в vault.
    Один коммит на всё — экономит историю git.
    Возвращает количество созданных файлов.
    """
    vault = _get_vault()
    if not vault:
        return 0

    count = 0
    for t in tasks:
        ok = await create_note("task", t["text"], t.get("project"), push=False)
        if ok:
            count += 1
    for i in ideas:
        ok = await create_note("idea", i["text"], i.get("project"), push=False)
        if ok:
            count += 1

    if count > 0:
        await _git_push(f"sync: {count} записей из базы")

    return count


async def _git_push(commit_msg: str):
    """git add → commit → push (в отдельном потоке, не блокирует бота)."""
    vault = _get_vault()
    if not vault:
        return

    def _run():
        try:
            subprocess.run(
                ["git", "-C", str(vault), "add", "."],
                check=True, capture_output=True
            )
            result = subprocess.run(
                ["git", "-C", str(vault), "commit", "-m", commit_msg],
                capture_output=True, text=True
            )
            stdout = result.stdout + result.stderr
            if result.returncode != 0:
                if "nothing to commit" in stdout:
                    return  # нечего пушить — норма
                logger.warning("git commit failed: %s", stdout)
                return
            subprocess.run(
                ["git", "-C", str(vault), "push"],
                check=True, capture_output=True
            )
            logger.info("Vault pushed: %s", commit_msg)
        except subprocess.CalledProcessError as e:
            logger.warning("Vault git error: %s", e)
        except FileNotFoundError:
            logger.warning("git не установлен или vault не найден")

    await asyncio.to_thread(_run)
