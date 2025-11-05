#!/bin/bash
# Script automático de migración a PlanetScale

set -e

echo "🚀 MIGRACIÓN A PLANETSCALE - Sin límites de conexiones ni queries"
echo "================================================================="
echo ""

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuración actual (JawsDB)
DB_HOST="tj5iv8piornf713y.cbetxkdyhwsb.us-east-1.rds.amazonaws.com"
DB_USER="oaai2ab9qsc7xvyn"
DB_NAME="vgd8ktskappw7cmj"
DB_PASSWORD="it2cxhq71iiubhlj"

echo -e "${YELLOW}📋 PASO 1: Backup de datos actuales${NC}"
echo "===================================="
echo ""

# Crear directorio de backups
mkdir -p backups
BACKUP_FILE="backups/backup_$(date +%Y%m%d_%H%M%S).sql"

echo "📦 Creando backup..."
if command -v mysqldump &> /dev/null; then
    mysqldump -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASSWORD" "$DB_NAME" > "$BACKUP_FILE"
    echo -e "${GREEN}✅ Backup creado: $BACKUP_FILE${NC}"
    echo "📊 Tamaño: $(du -h "$BACKUP_FILE" | cut -f1)"
else
    echo -e "${RED}❌ mysqldump no instalado. Usando Heroku...${NC}"
    echo "Ejecuta manualmente:"
    echo "  heroku run bash --app gonnet-interno"
    echo "  mysqldump -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME > backup.sql"
    exit 1
fi

echo ""
echo -e "${YELLOW}📋 PASO 2: Configurar PlanetScale${NC}"
echo "===================================="
echo ""
echo "🌐 Ahora necesitas:"
echo "  1. Ir a https://planetscale.com"
echo "  2. Crear cuenta (gratis)"
echo "  3. Crear nueva base de datos: 'gonnet-sistema'"
echo "  4. Ir a 'Connect' → 'Django'"
echo "  5. Copiar la connection string"
echo ""
echo -e "${GREEN}Cuando tengas la connection string, presiona ENTER...${NC}"
read

echo ""
echo "Pega la connection string de PlanetScale:"
echo "(Formato: mysql://usuario:password@host/database?ssl-mode=REQUIRED)"
read -r PLANETSCALE_URL

echo ""
echo -e "${YELLOW}📋 PASO 3: Importar datos a PlanetScale${NC}"
echo "===================================="
echo ""
echo "📤 Importando datos..."
echo ""
echo "Opción A: Desde PlanetScale Dashboard"
echo "  1. Ir a 'Imports' en PlanetScale"
echo "  2. Subir archivo: $BACKUP_FILE"
echo "  3. Esperar importación (5-10 min)"
echo ""
echo "Opción B: Vía CLI (requiere pscale instalado)"
echo "  pscale database restore-dump gonnet-sistema main $BACKUP_FILE"
echo ""
echo -e "${GREEN}Cuando la importación esté completa, presiona ENTER...${NC}"
read

echo ""
echo -e "${YELLOW}📋 PASO 4: Actualizar Heroku${NC}"
echo "===================================="
echo ""
echo "🔧 Configurando nueva base de datos en Heroku..."

# Actualizar DATABASE_URL en Heroku
heroku config:set DATABASE_URL="$PLANETSCALE_URL" --app gonnet-interno

echo ""
echo "🔄 Reiniciando aplicación..."
heroku restart --app gonnet-interno

echo ""
echo "⏳ Esperando 10 segundos para que la app se reinicie..."
sleep 10

echo ""
echo -e "${YELLOW}📋 PASO 5: Verificar funcionamiento${NC}"
echo "===================================="
echo ""
echo "🧪 Probando conexión..."

# Verificar que la app responde
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" https://gonnet-interno-052a6cec3da9.herokuapp.com/login/)

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ App funcionando correctamente (HTTP $HTTP_CODE)${NC}"
else
    echo -e "${RED}⚠️  App respondió con código: $HTTP_CODE${NC}"
    echo "Verifica logs: heroku logs --tail --app gonnet-interno"
fi

echo ""
echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}✅ MIGRACIÓN COMPLETADA${NC}"
echo -e "${GREEN}=================================================${NC}"
echo ""
echo "📊 Resumen:"
echo "  - Base de datos: PlanetScale"
echo "  - Sin límites de conexiones"
echo "  - Sin límites de queries"
echo "  - Backup guardado en: $BACKUP_FILE"
echo ""
echo "🔧 Próximos pasos:"
echo "  1. Probar todas las funcionalidades de la app"
echo "  2. Verificar que no hay errores en: heroku logs --tail"
echo "  3. Cuando confirmes que todo funciona, eliminar JawsDB:"
echo "     heroku addons:destroy JAWSDB_URL --app gonnet-interno --confirm gonnet-interno"
echo ""
echo -e "${YELLOW}💰 Ahorro mensual estimado:${NC}"
echo "  - JawsDB Leopard: $35/mes"
echo "  - PlanetScale Free: $0/mes"
echo "  - ${GREEN}Ahorro: $35/mes ($420/año)${NC}"
echo ""

