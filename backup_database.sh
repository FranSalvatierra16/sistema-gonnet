#!/bin/bash
# Script de backup de base de datos antes de migrar

set -e

echo "🔄 Iniciando backup de base de datos..."

# Configuración
DB_HOST="tj5iv8piornf713y.cbetxkdyhwsb.us-east-1.rds.amazonaws.com"
DB_USER="oaai2ab9qsc7xvyn"
DB_NAME="vgd8ktskappw7cmj"
DB_PASSWORD="it2cxhq71iiubhlj"
BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/backup_$DATE.sql"

# Crear directorio de backups si no existe
mkdir -p "$BACKUP_DIR"

echo "📦 Creando backup SQL..."
mysqldump -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
    echo "✅ Backup creado: $BACKUP_FILE"
    echo "📊 Tamaño: $(du -h "$BACKUP_FILE" | cut -f1)"
else
    echo "❌ Error al crear backup"
    exit 1
fi

# También crear backup JSON con Django
echo "📦 Creando backup JSON (Django dumpdata)..."
heroku run python manage.py dumpdata --natural-foreign --natural-primary > "$BACKUP_DIR/backup_$DATE.json" --app gonnet-interno 2>/dev/null || echo "⚠️  No se pudo crear backup JSON (requiere Heroku CLI)"

echo ""
echo "✅ Backups completados en: $BACKUP_DIR"
echo ""
echo "📋 Archivos creados:"
ls -lh "$BACKUP_DIR" | grep "$DATE"

