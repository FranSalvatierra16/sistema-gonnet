# Configuración de Entorno de Staging/Prueba en Railway

## Opción 1: Proyecto Separado (Recomendado) ✅

Esta es la opción más segura y recomendada. Te permite tener producción y staging completamente separados.

### Pasos:

1. **Crear un nuevo proyecto en Railway:**
   - Ve a [Railway Dashboard](https://railway.app)
   - Haz clic en "New Project"
   - Selecciona "Deploy from GitHub repo"
   - Elige el mismo repositorio que usas para producción

2. **Configurar el servicio:**
   - Railway detectará automáticamente que es Django
   - Configura las variables de entorno necesarias (ver abajo)

3. **Crear una base de datos separada:**
   - En el nuevo proyecto, agrega un servicio PostgreSQL
   - Esta será la base de datos de staging (separada de producción)

4. **Configurar variables de entorno:**
   - `DEBUG=True` (para staging)
   - `ALLOWED_HOSTS=tu-staging.up.railway.app`
   - `CSRF_TRUSTED_ORIGINS=https://tu-staging.up.railway.app`
   - `DATABASE_URL` (de la nueva base de datos PostgreSQL)
   - Todas las demás variables que uses en producción

5. **Configurar el branch (opcional):**
   - En Railway, ve a Settings → Source
   - Puedes configurar para que staging use una rama `staging` o `develop`
   - O usar `main` pero con variables de entorno diferentes

### Ventajas:
- ✅ Completamente separado de producción
- ✅ Base de datos independiente
- ✅ Puedes probar sin riesgo
- ✅ Fácil de resetear si algo sale mal

---

## Opción 2: Usar Branches Diferentes

Si prefieres usar el mismo proyecto pero diferentes branches:

1. **Crear una rama de staging:**
   ```bash
   git checkout -b staging
   git push origin staging
   ```

2. **En Railway:**
   - Ve a tu proyecto
   - Settings → Source
   - Cambia el branch a `staging` para un servicio específico
   - O crea un nuevo servicio que apunte a `staging`

3. **Configurar variables de entorno diferentes:**
   - Cada servicio puede tener sus propias variables
   - Staging puede tener `DEBUG=True`
   - Producción tiene `DEBUG=False`

---

## Configuración Recomendada para Staging

### Variables de Entorno para Staging:

```bash
# Debug activado para staging
DEBUG=True

# Hosts permitidos
ALLOWED_HOSTS=tu-staging.up.railway.app,localhost

# CSRF
CSRF_TRUSTED_ORIGINS=https://tu-staging.up.railway.app

# Base de datos (debe ser diferente a producción)
DATABASE_URL=postgresql://usuario:password@host:puerto/db_staging

# Secret key (puede ser diferente)
SECRET_KEY=tu-secret-key-staging

# Email (opcional, usar un servicio de prueba)
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

### Variables de Entorno para Producción:

```bash
# Debug desactivado
DEBUG=False

# Hosts permitidos
ALLOWED_HOSTS=tu-produccion.up.railway.app

# CSRF
CSRF_TRUSTED_ORIGINS=https://tu-produccion.up.railway.app

# Base de datos de producción
DATABASE_URL=postgresql://usuario:password@host:puerto/db_produccion

# Secret key de producción
SECRET_KEY=tu-secret-key-produccion
```

---

## Flujo de Trabajo Recomendado

1. **Desarrollo local:**
   - Trabajas en tu máquina local
   - Haces commits a una rama `develop` o `feature/nombre`

2. **Staging:**
   - Haces merge a `staging`
   - Railway despliega automáticamente a staging
   - Pruebas todo en staging

3. **Producción:**
   - Si todo está bien en staging
   - Haces merge a `main` o `production`
   - Railway despliega a producción

---

## Comandos Útiles

### Ver diferencias entre staging y producción:
```bash
git diff staging main
```

### Crear un script para desplegar a staging:
```bash
# deploy-staging.sh
git checkout staging
git merge develop
git push origin staging
# Railway desplegará automáticamente
```

---

## Notas Importantes

⚠️ **NUNCA uses la base de datos de producción en staging**
⚠️ **NUNCA uses el mismo SECRET_KEY en staging y producción**
⚠️ **Asegúrate de que staging tenga DEBUG=True para ver errores**
⚠️ **Usa datos de prueba en staging, no datos reales de clientes**

---

## Configuración Rápida (5 minutos)

1. Crea nuevo proyecto en Railway → "New Project"
2. Conecta el mismo repositorio
3. Agrega servicio PostgreSQL
4. Configura variables de entorno (copia de producción pero cambia DEBUG=True)
5. Deploy automático ✅

¡Listo! Ya tienes staging funcionando.

