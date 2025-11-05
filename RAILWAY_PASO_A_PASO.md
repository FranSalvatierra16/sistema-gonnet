# 🚂 MIGRACIÓN A RAILWAY - Guía Paso a Paso

## ✅ PREPARACIÓN COMPLETADA

Los siguientes archivos ya están configurados:
- ✅ `railway.json` - Configuración de deploy
- ✅ `runtime.txt` - Python 3.9.7
- ✅ `requirements.txt` - PostgreSQL configurado
- ✅ `sistema_gonnet/settings.py` - Soporte para PostgreSQL

---

## 📋 PASOS A SEGUIR

### PASO 1: Crear proyecto en Railway (5 minutos)

1. **Ir a Railway:**
   - Abrir: https://railway.app
   - Click en "Login" → "Login with GitHub"
   - Autorizar Railway

2. **Crear nuevo proyecto:**
   - Click "New Project"
   - Seleccionar "Deploy from GitHub repo"
   - Buscar y seleccionar: `sistema-gonnet`
   - Click en el repositorio

3. **Seleccionar branch:**
   - Cuando pregunte, seleccionar branch: `finalizacion10`
   - Railway comenzará a detectar tu proyecto (Django)

4. **Agregar PostgreSQL:**
   - En el proyecto, click "New"
   - Seleccionar "Database"
   - Click "Add PostgreSQL"
   - Esperar 30 segundos hasta que esté "Active"

---

### PASO 2: Configurar variables de entorno (10 minutos)

En Railway, ve al servicio de tu app (no la base de datos):
- Click en tu servicio web
- Click en "Variables"
- Click "RAW Editor"

Pega estas variables (ajustar valores según tu config actual):

```env
# Django
SECRET_KEY=django-insecure-#ry=f1tqj+=1*32^c54&0qk2)1xt02qpg-%r)ae6%-+3ip*fx^
DEBUG=False
ALLOWED_HOSTS=.up.railway.app,.railway.app
DISABLE_COLLECTSTATIC=1

# AWS S3 (copiar de Heroku)
AWS_ACCESS_KEY_ID=tu_access_key
AWS_SECRET_ACCESS_KEY=tu_secret_key
AWS_STORAGE_BUCKET_NAME=gonnet-interno-media17
AWS_S3_REGION_NAME=us-east-1

# Email
EMAIL_HOST_USER=gonnetinterno@gmail.com
EMAIL_HOST_PASSWORD=mfzt dvrp rqmb cbek

# SendGrid (si lo usas)
SENDGRID_API_KEY=tu_sendgrid_key
```

**IMPORTANTE:** No agregues `DATABASE_URL` - Railway lo genera automáticamente.

**Para copiar todas tus variables de Heroku:**
```bash
heroku config --app gonnet-interno
```

---

### PASO 3: Deploy automático (Railway lo hace solo)

Railway detecta Django automáticamente y hace:
1. Instala dependencias de `requirements.txt`
2. Corre collectstatic (si es necesario)
3. Inicia con el comando de `railway.json`

**Monitorear deploy:**
- En Railway → Tu servicio → "Deployments"
- Ver logs en tiempo real
- Esperar hasta ver "✓ Deployment Successful"

**Obtener URL:**
- En Railway → Settings → Generate Domain
- Te dará algo como: `https://sistema-gonnet-production.up.railway.app`

---

### PASO 4: Ejecutar migraciones (5 minutos)

En Railway, ve al servicio web:
- Settings → "Deploy"
- Scroll hasta "Custom Start Command (override)"
- Ejecutar uno por uno:

```bash
python manage.py migrate
```

Una vez que las migraciones estén aplicadas, dejar el start command vacío (Railway usará el de railway.json).

---

### PASO 5: Migrar datos de Heroku a Railway (15 minutos)

**Opción A: Usando dumpdata/loaddata (recomendado)**

1. Exportar datos de Heroku:
```bash
heroku run python manage.py dumpdata --natural-foreign --natural-primary --app gonnet-interno > backup.json
```

2. Crear usuario admin en Railway:
```bash
# En Railway → Deploy → Run Command
python manage.py createsuperuser
```

3. Importar datos:
```bash
# En Railway → Deploy → Run Command
# Primero subir backup.json al servicio, luego:
python manage.py loaddata backup.json
```

**Opción B: Si dumpdata falla por límite de queries**

Migrar tabla por tabla:
```bash
# En Heroku:
heroku run "python manage.py dumpdata inmobiliaria.Vendedor --natural-foreign" --app gonnet-interno > vendedores.json
heroku run "python manage.py dumpdata inmobiliaria.Propiedad --natural-foreign" --app gonnet-interno > propiedades.json
# ... etc

# En Railway, cargar cada archivo:
python manage.py loaddata vendedores.json
python manage.py loaddata propiedades.json
# ... etc
```

---

### PASO 6: Verificar funcionamiento (10 minutos)

1. **Probar login:**
   - Ir a tu URL de Railway: `https://tu-app.up.railway.app/login/`
   - Intentar login con tus credenciales

2. **Verificar funcionalidades:**
   - [ ] Login funciona
   - [ ] Propiedades se cargan
   - [ ] Imágenes se ven (S3)
   - [ ] Crear reserva
   - [ ] Generar recibo
   - [ ] Movimientos de caja

3. **Verificar rendimiento:**
   - Railway → Metrics
   - Ver uso de CPU, RAM, y tiempo de respuesta
   - Debería ser más rápido que Heroku

---

### PASO 7: Cambiar DNS (si tienes dominio) - OPCIONAL

Si tienes dominio personalizado:
1. Railway → Settings → Domains
2. Click "Add Custom Domain"
3. Agregar tu dominio (ej: `sistema.gonnet.com`)
4. Railway te dará un CNAME
5. En tu proveedor de DNS, crear registro CNAME:
   - Nombre: `sistema` (o `www`)
   - Valor: el CNAME que te dio Railway

---

### PASO 8: Desactivar Heroku (después de confirmar que todo funciona)

**IMPORTANTE: Esperar 24-48 horas antes de eliminar Heroku**

1. Escalar dynos a 0 (mantener como backup):
```bash
heroku ps:scale web=0 --app gonnet-interno
```

2. Después de 2-3 días sin problemas, eliminar addons:
```bash
heroku addons:destroy JAWSDB_URL --app gonnet-interno --confirm gonnet-interno
```

3. Finalmente, eliminar app (cuando estés 100% seguro):
```bash
heroku apps:destroy gonnet-interno --confirm gonnet-interno
```

---

## 💰 RESUMEN DE COSTOS

| Concepto | Antes (Heroku) | Después (Railway) | Ahorro |
|----------|----------------|-------------------|---------|
| Hosting | $7/mes | $5/mes | $2/mes |
| Base de datos | $35/mes | $0/mes* | $35/mes |
| SendGrid | $0 | $0 | $0 |
| S3 | $1-2/mes | $1-2/mes | $0 |
| **TOTAL** | **$43-44/mes** | **$5-7/mes** | **$37-38/mes** |

**Ahorro anual: ~$450/año**

*Railway incluye PostgreSQL gratis con el plan de $5/mes

---

## 🆘 PROBLEMAS COMUNES

### Error: "Module not found: mysqlclient"
- Ya está solucionado, eliminamos mysqlclient de requirements.txt

### Error: "No module named psycopg2"
- Ya tienes psycopg2-binary en requirements.txt

### Error al cargar datos: "IntegrityError"
- Cargar tablas en orden (primero Vendedor, luego Propiedad, etc.)

### Imágenes no se ven
- Verificar variables AWS_* en Railway
- S3 sigue funcionando igual

---

## ✅ CHECKLIST FINAL

Antes de eliminar Heroku:
- [ ] Login funciona en Railway
- [ ] Todas las propiedades se ven
- [ ] Imágenes de S3 funcionan
- [ ] Crear/editar reservas funciona
- [ ] Generar recibos funciona
- [ ] Caja funciona
- [ ] Comisiones funcionan
- [ ] Vales funcionan
- [ ] Sin errores de conexión a BD
- [ ] Rendimiento es bueno
- [ ] 24-48 horas de uso sin problemas

---

## 📞 AYUDA

Si tienes problemas:
1. Ver logs en Railway → Deployments → View Logs
2. Revisar variables de entorno
3. Verificar que DATABASE_URL esté configurada (Railway la genera automáticamente)
4. Consultarme por cualquier error

---

¡Éxito con la migración! 🚀

