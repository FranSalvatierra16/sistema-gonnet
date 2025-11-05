# 🚀 Guía de Migración de Heroku a Railway/Render

## ✅ BUENAS NOTICIAS: Tu setup es PERFECTO para migrar

- ✅ Base de datos: **JawsDB (externa)** → Solo cambiar URL
- ✅ Archivos: **AWS S3** → No toca nada
- ✅ Código: **Django estándar** → Funciona en cualquier lado

---

## 📋 PASO 1: BACKUP DE DATOS (OBLIGATORIO)

### Opción A: mysqldump (recomendado)
```bash
# En tu máquina local
mysqldump -h tj5iv8piornf713y.cbetxkdyhwsb.us-east-1.rds.amazonaws.com \
  -u oaai2ab9qsc7xvyn -p vgd8ktskappw7cmj > backup_$(date +%Y%m%d).sql

# O desde Heroku (si tienes mysqldump instalado)
heroku run bash --app gonnet-interno
# Luego dentro del dyno:
mysqldump -h $DB_HOST -u $DB_USER -p$DB_PASSWORD $DB_NAME > backup.sql
exit
heroku run cat backup.sql --app gonnet-interno > backup_local.sql
```

### Opción B: Django dumpdata (más seguro, más lento)
```bash
heroku run python manage.py dumpdata --natural-foreign --natural-primary > backup_$(date +%Y%m%d).json --app gonnet-interno
```

---

## 🚂 MIGRACIÓN A RAILWAY (RECOMENDADO)

### Paso 1: Crear cuenta en Railway
1. Ir a https://railway.app
2. Login con GitHub
3. Crear nuevo proyecto

### Paso 2: Conectar repositorio
1. "New Project" → "Deploy from GitHub repo"
2. Seleccionar tu repo `sistema-gonnet`
3. Seleccionar branch `finalizacion10` (o el que uses)

### Paso 3: Configurar variables de entorno
En Railway → Settings → Variables, agregar:

```env
# Base de datos (usar la misma JawsDB, solo cambiar URL si es necesario)
DATABASE_URL=mysql://oaai2ab9qsc7xvyn:it2cxhq71iiubhlj@tj5iv8piornf713y.cbetxkdyhwsb.us-east-1.rds.amazonaws.com:3306/vgd8ktskappw7cmj

# Django
SECRET_KEY=tu-secret-key-actual
DEBUG=False
ALLOWED_HOSTS=tu-app.up.railway.app,tu-dominio.com

# AWS S3 (copiar de Heroku)
AWS_ACCESS_KEY_ID=tu-key
AWS_SECRET_ACCESS_KEY=tu-secret
AWS_STORAGE_BUCKET_NAME=gonnet-interno-media17
AWS_S3_REGION_NAME=us-east-1

# Email (si usas SendGrid)
SENDGRID_API_KEY=tu-key

# Otros
DISABLE_COLLECTSTATIC=1
PYTHON_VERSION=3.9.7
```

**Copiar todas las variables de Heroku:**
```bash
heroku config --app gonnet-interno
```

### Paso 4: Configurar build
Railway detecta Django automáticamente, pero crear `railway.json`:

```json
{
  "$schema": "https://railway.app/railway.schema.json",
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "startCommand": "gunicorn sistema_gonnet.wsgi --workers=1 --threads=1 --timeout=120",
    "restartPolicyType": "ON_FAILURE",
    "restartPolicyMaxRetries": 10
  }
}
```

### Paso 5: Desplegar
1. Railway detecta automáticamente y despliega
2. Esperar 2-3 minutos
3. Verificar en: `https://tu-app.up.railway.app`

### Paso 6: Migrar base de datos (si es necesario)
```bash
# En Railway → Deploy → Run Command
python manage.py migrate
```

---

## 🎨 MIGRACIÓN A RENDER (ALTERNATIVA)

### Paso 1: Crear cuenta
1. Ir a https://render.com
2. Login con GitHub

### Paso 2: Crear Web Service
1. "New" → "Web Service"
2. Conectar repositorio
3. Configuración:
   - **Name**: `gonnet-interno`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn sistema_gonnet.wsgi --workers=1 --threads=1 --timeout=120`

### Paso 3: Variables de entorno
En Render → Environment, agregar todas las variables (igual que Railway)

### Paso 4: Desplegar
1. Click "Create Web Service"
2. Esperar deploy
3. URL: `https://gonnet-interno.onrender.com`

---

## 🔄 MIGRACIÓN SIN DOWNTIME (OPCIONAL)

### Estrategia Blue-Green Deployment
1. **Deploy en nueva plataforma** (Railway/Render)
2. **Probar todo** en la nueva URL
3. **Cambiar DNS** cuando esté listo
4. **Mantener Heroku activo** 1-2 días por si acaso
5. **Desactivar Heroku** cuando confirmes que todo funciona

---

## 📊 COMPARACIÓN DE COSTOS

| Plataforma | Precio Inicial | Precio Producción | Dificultad |
|------------|---------------|-------------------|------------|
| **Heroku** | $0 | $7-60/mes | ⭐ Fácil |
| **Railway** | $5/mes | $5-20/mes | ⭐ Fácil |
| **Render** | $0 | $7/mes | ⭐⭐ Medio |
| **Fly.io** | $0 | $3-5/mes | ⭐⭐⭐ Avanzado |

---

## ⚠️ CHECKLIST ANTES DE MIGRAR

- [ ] Backup completo de base de datos
- [ ] Backup de archivos S3 (opcional, pero recomendado)
- [ ] Lista de todas las variables de entorno
- [ ] Probar localmente con nuevas configuraciones
- [ ] Planificar ventana de mantenimiento (si es necesario)
- [ ] Notificar usuarios (si aplica)

---

## 🆘 ROLLBACK PLAN

Si algo sale mal:

1. **Railway/Render**: Desactivar deploy
2. **Heroku**: Mantener activo como backup
3. **DNS**: Revertir cambios si cambiaste dominio
4. **BD**: Ya está en JawsDB, no se toca

---

## 📝 NOTAS IMPORTANTES

1. **Base de datos NO cambia**: Seguís usando JawsDB, solo cambia dónde corre el código
2. **S3 NO cambia**: Los archivos siguen ahí
3. **Dominio**: Si tenés dominio personalizado, solo cambiar DNS
4. **Email**: Si usás SendGrid, sigue funcionando igual

---

## 🎯 RECOMENDACIÓN FINAL

**Para tu caso: Railway.app**

- ✅ Más fácil que Heroku
- ✅ Más barato ($5/mes vs $60/mes)
- ✅ Sin límites de queries
- ✅ Mejor performance
- ✅ 15 minutos de migración

**¿Querés que te ayude con la migración paso a paso?**

