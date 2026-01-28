#!/bin/bash

# Script para configurar entorno de staging en Railway
# Uso: ./setup_staging.sh

echo "🚀 Configuración de Staging en Railway"
echo "======================================"
echo ""

echo "📋 Pasos a seguir:"
echo ""
echo "1. Ve a https://railway.app y crea un nuevo proyecto"
echo "2. Selecciona 'Deploy from GitHub repo'"
echo "3. Elige el mismo repositorio que usas para producción"
echo "4. Railway detectará automáticamente Django"
echo ""
echo "5. Agrega un servicio PostgreSQL (será la BD de staging)"
echo ""
echo "6. Configura estas variables de entorno en Railway:"
echo ""
echo "   DEBUG=True"
echo "   ALLOWED_HOSTS=tu-staging.up.railway.app"
echo "   CSRF_TRUSTED_ORIGINS=https://tu-staging.up.railway.app"
echo "   DATABASE_URL=<la URL de la nueva base de datos PostgreSQL>"
echo ""
echo "7. Copia todas las demás variables de entorno de producción"
echo "   pero asegúrate de usar la nueva DATABASE_URL"
echo ""
echo "8. Railway desplegará automáticamente cuando hagas push"
echo ""
echo "✅ ¡Listo! Ya tienes staging funcionando"
echo ""
echo "💡 Tip: Puedes crear una rama 'staging' y configurar Railway"
echo "   para que despliegue desde esa rama en lugar de 'main'"

