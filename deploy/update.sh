#!/bin/bash
# Обновление бота на VPS (после git pull или scp новых файлов)
# Запуск: bash deploy/update.sh

set -e

APP_DIR="/home/ubuntu/andrey_agent"
SERVICE_NAME="andrey-agent"

echo "=== Обновление AI-агента ==="

cd "$APP_DIR"

# 1. Обновить зависимости если изменились
echo "[1/3] Обновление зависимостей..."
source .venv/bin/activate
pip install -r requirements.txt --quiet

# 2. Перезапуск
echo "[2/3] Перезапуск бота..."
sudo systemctl restart ${SERVICE_NAME}

# 3. Проверка
echo "[3/3] Проверка..."
sleep 2
sudo systemctl status ${SERVICE_NAME} --no-pager

echo ""
echo "=== Обновление завершено ==="
