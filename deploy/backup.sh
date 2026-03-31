#!/bin/bash
# Бэкап базы данных в приватный Telegram-чат (стратегия 3-2-1 из ТЗ)
# Запуск вручную или через cron: 0 3 * * * /home/ubuntu/andrey_agent/deploy/backup.sh
#
# Настройка cron:
#   crontab -e
#   0 3 * * * /home/ubuntu/andrey_agent/deploy/backup.sh >> /home/ubuntu/andrey_agent/logs/backup.log 2>&1

set -e

APP_DIR="/home/ubuntu/andrey_agent"
DB_PATH="$APP_DIR/data/agent.db"
BACKUP_DIR="$APP_DIR/data/backups"
DATE=$(date +%Y-%m-%d_%H%M)

# Загрузить переменные
source "$APP_DIR/.env"

mkdir -p "$BACKUP_DIR"

# 1. Создать бэкап (sqlite online backup — безопасно при работающем боте)
BACKUP_FILE="$BACKUP_DIR/agent_${DATE}.db"
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

# 2. Сжать
gzip "$BACKUP_FILE"
BACKUP_GZ="${BACKUP_FILE}.gz"

# 3. Отправить в Telegram (приватный чат с самим собой)
if [ -n "$TELEGRAM_BOT_TOKEN" ] && [ -n "$ALLOWED_USER_ID" ]; then
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendDocument" \
        -F "chat_id=${ALLOWED_USER_ID}" \
        -F "document=@${BACKUP_GZ}" \
        -F "caption=Бэкап agent.db — ${DATE}" \
        > /dev/null
    echo "[$(date)] Бэкап отправлен в Telegram: $(du -h "$BACKUP_GZ" | cut -f1)"
else
    echo "[$(date)] TELEGRAM_BOT_TOKEN или ALLOWED_USER_ID не заданы, бэкап сохранён локально"
fi

# 4. Удалить бэкапы старше 30 дней
find "$BACKUP_DIR" -name "*.gz" -mtime +30 -delete

echo "[$(date)] Бэкап завершён: $BACKUP_GZ"
