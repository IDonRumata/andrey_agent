#!/bin/bash
# Скрипт первоначальной установки на VPS (Zomro / Beget)
# Запуск: bash deploy/setup.sh

set -e

APP_DIR="/home/ubuntu/andrey_agent"
SERVICE_NAME="andrey-agent"

echo "=== Установка AI-агента Андрей ==="

# 1. Системные зависимости
echo "[1/6] Обновление системы..."
sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip

# 2. Копирование проекта (если ещё не скопирован)
if [ ! -d "$APP_DIR" ]; then
    echo "[2/6] Создание директории..."
    mkdir -p "$APP_DIR"
    echo "Скопируй файлы проекта в $APP_DIR и перезапусти скрипт."
    exit 1
fi

# 3. Виртуальное окружение
echo "[3/6] Создание виртуального окружения..."
cd "$APP_DIR"
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 4. Проверка .env
if [ ! -f "$APP_DIR/.env" ]; then
    echo "[!] Файл .env не найден!"
    echo "    Скопируй .env.example в .env и заполни токены:"
    echo "    cp .env.example .env && nano .env"
    exit 1
fi

# 5. Systemd сервис
echo "[5/6] Установка systemd сервиса..."
sudo cp deploy/andrey-agent.service /etc/systemd/system/${SERVICE_NAME}.service
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl start ${SERVICE_NAME}

# 6. Проверка
echo "[6/6] Проверка статуса..."
sleep 2
sudo systemctl status ${SERVICE_NAME} --no-pager

echo ""
echo "=== Готово! ==="
echo "Команды управления:"
echo "  sudo systemctl status ${SERVICE_NAME}   — статус"
echo "  sudo systemctl restart ${SERVICE_NAME}   — перезапуск"
echo "  sudo systemctl stop ${SERVICE_NAME}      — остановка"
echo "  journalctl -u ${SERVICE_NAME} -f         — логи в реальном времени"
echo "  cat ${APP_DIR}/logs/agent.log            — файловые логи"
