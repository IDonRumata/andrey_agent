#!/bin/bash
# =============================================================
# setup_vault.sh — создаёт GitHub-репо andrey_vault и клонирует
# на VPS как Obsidian vault для синхронизации через Git plugin.
#
# Требует в .env:
#   GITHUB_TOKEN=ghp_xxxxxxxxxxxx   (PAT с правом repo)
#   OBSIDIAN_VAULT_DIR=/root/andrey_vault   (необязательно, по умолчанию)
#   OBSIDIAN_GITHUB_REPO=andrey_vault       (необязательно)
# =============================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Загрузить .env
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
else
    echo "❌ Файл .env не найден в $SCRIPT_DIR"
    exit 1
fi

VAULT_DIR="${OBSIDIAN_VAULT_DIR:-/root/andrey_vault}"
REPO_NAME="${OBSIDIAN_GITHUB_REPO:-andrey_vault}"

if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ GITHUB_TOKEN не задан в .env"
    echo "   Получи токен: GitHub → Settings → Developer settings → Personal access tokens"
    echo "   Нужны права: repo (full control)"
    exit 1
fi

echo "=============================="
echo " Obsidian Vault Setup"
echo "=============================="
echo "Vault dir : $VAULT_DIR"
echo "GitHub repo: $REPO_NAME"
echo ""

# ── 1. Получить имя пользователя GitHub ──
echo "Определяю GitHub username..."
GITHUB_USER=$(curl -sf \
    -H "Authorization: token $GITHUB_TOKEN" \
    https://api.github.com/user | python3 -c "import sys,json; print(json.load(sys.stdin)['login'])")

if [ -z "$GITHUB_USER" ]; then
    echo "❌ Не удалось получить GitHub user. Проверь GITHUB_TOKEN."
    exit 1
fi
echo "✅ GitHub user: $GITHUB_USER"

# Записать GITHUB_USER в .env если ещё нет
if ! grep -q "^GITHUB_USER=" "$SCRIPT_DIR/.env"; then
    echo "GITHUB_USER=$GITHUB_USER" >> "$SCRIPT_DIR/.env"
    echo "   → GITHUB_USER добавлен в .env"
fi

# ── 2. Создать репозиторий ──
echo ""
echo "Создаю репозиторий $GITHUB_USER/$REPO_NAME..."

HTTP_STATUS=$(curl -s -o /tmp/gh_vault_resp.json -w "%{http_code}" \
    -X POST \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Content-Type: application/json" \
    -d "{
        \"name\": \"$REPO_NAME\",
        \"public\": true,
        \"description\": \"Obsidian vault — личная база знаний Андрея\",
        \"auto_init\": true
    }" \
    https://api.github.com/user/repos)

if [ "$HTTP_STATUS" = "201" ]; then
    echo "✅ Репозиторий создан: https://github.com/$GITHUB_USER/$REPO_NAME"
elif [ "$HTTP_STATUS" = "422" ]; then
    echo "⚠️  Репозиторий уже существует — продолжаем"
else
    echo "❌ Ошибка создания репозитория (HTTP $HTTP_STATUS)"
    cat /tmp/gh_vault_resp.json
    exit 1
fi

# ── 3. Клонировать или обновить vault ──
REMOTE_URL="https://$GITHUB_TOKEN@github.com/$GITHUB_USER/$REPO_NAME.git"

echo ""
if [ -d "$VAULT_DIR/.git" ]; then
    echo "Vault уже клонирован, обновляю..."
    git -C "$VAULT_DIR" remote set-url origin "$REMOTE_URL"
    git -C "$VAULT_DIR" pull --rebase origin HEAD 2>/dev/null || true
else
    echo "Клонирую vault в $VAULT_DIR..."
    git clone "$REMOTE_URL" "$VAULT_DIR"
fi

# ── 4. Структура папок ──
echo "Создаю структуру папок..."
for dir in "Задачи" "Идеи" "Заметки" "Проекты"; do
    mkdir -p "$VAULT_DIR/$dir"
    # .gitkeep чтобы пустые папки попали в git
    if [ ! -f "$VAULT_DIR/$dir/.gitkeep" ]; then
        touch "$VAULT_DIR/$dir/.gitkeep"
    fi
done

# ── 5. Настроить git identity ──
git -C "$VAULT_DIR" config user.email "andrey-bot@localhost"
git -C "$VAULT_DIR" config user.name "Andrey Bot"
git -C "$VAULT_DIR" config push.default current

# ── 6. Обновить remote с токеном (для push без пароля) ──
git -C "$VAULT_DIR" remote set-url origin "$REMOTE_URL"

# ── 7. Начальный коммит ──
cd "$VAULT_DIR"
git add . 2>/dev/null || true
if ! git diff --cached --quiet 2>/dev/null; then
    git commit -m "init: структура Obsidian vault"
    BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
    git push -u origin "$BRANCH" 2>/dev/null || \
        (git checkout -b main && git push -u origin main)
    echo "✅ Initial commit запушен"
else
    echo "ℹ️  Нечего коммитить — vault уже актуален"
fi

# ── 8. Добавить OBSIDIAN_VAULT_DIR в .env ──
if ! grep -q "^OBSIDIAN_VAULT_DIR=" "$SCRIPT_DIR/.env"; then
    echo "OBSIDIAN_VAULT_DIR=$VAULT_DIR" >> "$SCRIPT_DIR/.env"
    echo "   → OBSIDIAN_VAULT_DIR добавлен в .env"
fi
if ! grep -q "^OBSIDIAN_GITHUB_REPO=" "$SCRIPT_DIR/.env"; then
    echo "OBSIDIAN_GITHUB_REPO=$REPO_NAME" >> "$SCRIPT_DIR/.env"
    echo "   → OBSIDIAN_GITHUB_REPO добавлен в .env"
fi

echo ""
echo "=============================="
echo " ✅ Vault готов!"
echo "=============================="
echo ""
echo "📂 Локально : $VAULT_DIR"
echo "📦 GitHub   : https://github.com/$GITHUB_USER/$REPO_NAME"
echo ""
echo "Следующий шаг — Obsidian Git на телефоне/ПК:"
echo "  1. Community Plugins → 'Obsidian Git' → Install → Enable"
echo "  2. Settings → Obsidian Git:"
echo "       Remote URL: https://github.com/$GITHUB_USER/$REPO_NAME"
echo "       Authentication: Personal Access Token"
echo "       Token: (тот же GITHUB_TOKEN)"
echo "  3. Pull interval: 5 мин"
echo ""
echo "Перезапусти бота:"
echo "  systemctl restart andrey-agent"
