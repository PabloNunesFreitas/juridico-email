#!/bin/bash
# Backup automático do PostgreSQL — roda via cron diariamente
# Instalar: chmod +x /opt/juridico-email/scripts/backup-db.sh
# Cron: 0 2 * * * /opt/juridico-email/scripts/backup-db.sh >> /var/log/juridico-backup.log 2>&1

set -e

BACKUP_DIR="/opt/backups/juridico"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
CONTAINER="juridico-email-db-1"
DB_NAME="juridico"
DB_USER="postgres"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Iniciando backup..."

docker exec "$CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_DIR/backup_${TIMESTAMP}.sql.gz"

echo "[$(date)] Backup salvo: backup_${TIMESTAMP}.sql.gz ($(du -sh "$BACKUP_DIR/backup_${TIMESTAMP}.sql.gz" | cut -f1))"

# Manter apenas os últimos 7 dias
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +7 -delete

echo "[$(date)] Backups antigos removidos. Total atual: $(ls "$BACKUP_DIR"/*.sql.gz 2>/dev/null | wc -l) arquivo(s)"
