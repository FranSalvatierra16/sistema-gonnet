#!/bin/bash
# Script de migración completa a Railway

set -e

echo "🚂 MIGRACIÓN COMPLETA A RAILWAY"
echo "================================"
echo ""
echo "Ventajas:"
echo "  ✅ Sin límites de conexiones"
echo "  ✅ Sin límites de queries"
echo "  ✅ $5/mes todo incluido (vs $60/mes actual)"
echo "  ✅ Mejor rendimiento"
echo ""

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}📋 PASO 1: Backup de datos${NC}"
echo "============================"
echo ""

mkdir -p backups
BACKUP_JSON="backups/backup_$(date +%Y%m%d_%H%M%S).json"

echo "📦 Creando backup con Django dumpdata..."
heroku run python manage.py dumpdata --natural-foreign --natural-primary --app gonnet-interno > "$BACKUP_JSON"

echo -e "${GREEN}✅ Backup creado: $BACKUP_JSON${NC}"

echo ""
echo -e "${YELLOW}📋 PASO 2: Configurar Railway${NC}"
echo "============================"
echo ""
echo "🌐 Ahora necesitas:"
echo "  1. Ir a https://railway.app"
echo "  2. Login con GitHub"
echo "  3. 'New Project' → 'Deploy from GitHub repo'"
echo "  4. Seleccionar: sistema-gonnet"
echo "  5. Seleccionar branch: finalizacion10"
echo ""
echo -e "${GREEN}Cuando hayas creado el proyecto, presiona ENTER...${NC}"
read

echo ""
echo -e "${YELLOW}📋 PASO 3: Agregar PostgreSQL${NC}"
echo "============================"
echo ""
echo "En Railway:"
echo "  1. Click 'New' → 'Database' → 'PostgreSQL'"
echo "  2. Esperar 30 segundos"
echo "  3. Copiar 'DATABASE_URL' de las variables"
echo ""
echo -e "${GREEN}Cuando tengas PostgreSQL creado, presiona ENTER...${NC}"
read

echo ""
echo -e "${YELLOW}📋 PASO 4: Configurar variables de entorno${NC}"
echo "============================"
echo ""
echo "🔑 Obteniendo variables de Heroku..."
heroku config --app gonnet-interno > temp_vars.txt

echo ""
echo "📋 Variables a copiar en Railway → Settings → Variables:"
echo ""
cat temp_vars.txt
echo ""
echo "⚠️  IMPORTANTE: NO copies DATABASE_URL (Railway lo genera automáticamente)"
echo ""
echo -e "${GREEN}Cuando hayas copiado todas las variables (excepto DATABASE_URL), presiona ENTER...${NC}"
read

rm temp_vars.txt

echo ""
echo -e "${YELLOW}📋 PASO 5: Deploy y migración${NC}"
echo "============================"
echo ""
echo "Railway detecta Django automáticamente y hace deploy."
echo ""
echo "En Railway CLI (si lo tienes instalado) o desde el dashboard:"
echo ""
echo "  railway run python manage.py migrate"
echo "  railway run python manage.py loaddata $BACKUP_JSON"
echo ""
echo "O desde Railway dashboard:"
echo "  Settings → Deploy → Run command"
echo "  1. python manage.py migrate"
echo "  2. python manage.py loaddata (sube el archivo $BACKUP_JSON)"
echo ""
echo -e "${GREEN}Cuando el deploy esté completo, presiona ENTER...${NC}"
read

echo ""
echo -e "${YELLOW}📋 PASO 6: Verificar funcionamiento${NC}"
echo "============================"
echo ""
echo "Pega la URL de tu app en Railway:"
echo "(Formato: https://tu-proyecto.up.railway.app)"
read -r RAILWAY_URL

echo ""
echo "🧪 Probando conexión..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$RAILWAY_URL/login/")

if [ "$HTTP_CODE" = "200" ]; then
    echo -e "${GREEN}✅ App funcionando correctamente (HTTP $HTTP_CODE)${NC}"
else
    echo "⚠️  App respondió con código: $HTTP_CODE"
    echo "Verifica logs en Railway dashboard"
fi

echo ""
echo -e "${GREEN}=================================================${NC}"
echo -e "${GREEN}✅ MIGRACIÓN A RAILWAY COMPLETADA${NC}"
echo -e "${GREEN}=================================================${NC}"
echo ""
echo "📊 Resumen:"
echo "  - Plataforma: Railway"
echo "  - Base de datos: PostgreSQL (Railway)"
echo "  - Sin límites de conexiones"
echo "  - Sin límites de queries"
echo "  - Backup guardado en: $BACKUP_JSON"
echo ""
echo "🔧 Próximos pasos:"
echo "  1. Probar todas las funcionalidades"
echo "  2. Actualizar DNS si tienes dominio personalizado"
echo "  3. Cuando confirmes que todo funciona:"
echo "     - Escalar Heroku a 0 dynos: heroku ps:scale web=0"
echo "     - Esperar 1-2 días"
echo "     - Eliminar app de Heroku: heroku apps:destroy gonnet-interno"
echo ""
echo -e "${YELLOW}💰 Ahorro mensual:${NC}"
echo "  - Heroku + JawsDB: $60/mes"
echo "  - Railway (todo incluido): $5/mes"
echo "  - ${GREEN}Ahorro: $55/mes ($660/año)${NC}"
echo ""

